#!/usr/bin/env python3
"""OID market-overview strip refresh (research / paper only).

Writes:
  market-data/latest/market-tape.json   — SPY · QQQ · DIA (+ helpers RSP/VTV/VUG)
  market-data/latest/fidelity-three.json
  market-data/latest/macro-spot.json   — 10Y · VIX · WTI · Brent — median-growth proxy, credit OAS, valuation proxy

Also writes sibling fred-hy-oas / fred-ig-oas cache stamps for Data sources catalog.

Inputs:
  --equity-quotes-file PATH   RH get_equity_quotes JSON (SPY,QQQ,DIA,RSP,VTV,VUG)
  --from-rh-quotes-cache      piggyback fresh shared rh-quotes (TTL 120s) for covered symbols
  (default)                   try rh-quotes cache first; use --equity-quotes-file only for misses
  --skip-fred                 skip FRED CSV pull (reuse last fidelity-three credit block)
  --skip-yahoo                skip Yahoo 5y history for valuation percentile

Duplicates #2: prefer market-data/latest/rh-quotes.json via cache_io.piggyback_rh_quotes
when fresh — do not re-call get_equity_quotes for overlapping symbols. Rose remains
sole rh-quotes writer (refresh_marks.py / live_refresh.py). This script never writes rh-quotes.

FRED (no API key): public CSV
  https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2
  https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLC0A0CM

Never places orders. Soft/paper only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OID = ROOT.parent
MD = OID / "market-data"
LATEST = MD / "latest"
PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OID / "paper-trades"))
sys.path.insert(0, str(MD))

from cache_io import write_feed, piggyback_rh_quotes  # noqa: E402
from market_session import market_session, session_label  # noqa: E402
from refresh_marks import normalize_equity_quotes, _f  # noqa: E402

TAPE_SYMBOLS = ["SPY", "QQQ", "DIA", "RSP", "VTV", "VUG"]
INDEX_SYMBOLS = ["SPY", "QQQ", "DIA"]
FRED_HY = "BAMLH0A0HYM2"
FRED_IG = "BAMLC0A0CM"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
YAHOO_CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    "?interval=1d&range=10y"
)
UA = "OID-MarketTape/1.0 (+research; paper-only)"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_of_pt(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = _now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(PT)
    return local.strftime("%Y-%m-%d %-I:%M %p PT")


def _fetch_text(url: str, timeout: float = 60.0) -> str:
    """Fetch URL text; prefer curl (more reliable egress) then urllib."""
    import subprocess
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(int(timeout)), "-A", UA, url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if r.returncode == 0 and r.stdout and not r.stdout.lstrip().startswith("<!DOCTYPE"):
            return r.stdout
    except Exception:
        pass
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _fetch_json(url: str, timeout: float = 60.0) -> Any:
    return json.loads(_fetch_text(url, timeout=timeout))


def _read_fred_csv_local(series_id: str) -> Optional[str]:
    """Optional local cache under tmp/fred/{id}.csv (curl pre-warm)."""
    local = OID / "tmp" / "fred" / f"{series_id}.csv"
    if local.is_file() and local.stat().st_size > 50:
        # Prefer fresh local if < 7 days old
        age = _now_utc().timestamp() - local.stat().st_mtime
        if age < 7 * 86400:
            return local.read_text(encoding="utf-8", errors="replace")
    return None


def _day_pct(last: Optional[float], prev: Optional[float]) -> Optional[float]:
    if last is None or prev is None or prev == 0:
        return None
    return round((float(last) - float(prev)) / float(prev) * 100.0, 4)


def _display_spot(q: dict, session: str) -> tuple[Optional[float], bool]:
    """Return (spot, extended_live). PRE/AH prefer last_non_reg."""
    last = _f(q.get("last"))
    ext = _f(q.get("last_non_reg"))
    if session in ("pre", "ah") and ext is not None:
        return ext, True
    if session == "closed":
        return last, False
    return (ext or last), bool(ext is not None and session in ("pre", "ah"))


def build_index_row(sym: str, q: dict, session: str) -> dict[str, Any]:
    spot, ext_live = _display_spot(q, session)
    prev = _f(q.get("prev_close"))
    if session == "closed":
        spot = _f(q.get("last"))
        day = _day_pct(spot, prev)
        ext_live = False
    else:
        day = _day_pct(spot, prev)
    label = "DIA (Dow)" if sym == "DIA" else sym
    return {
        "symbol": sym,
        "label": label,
        "spot": spot,
        "prev_close": prev,
        "day_pct": day,
        "session": session,
        "session_label": session_label(session),
        "last_non_reg": _f(q.get("last_non_reg")),
        "extended_live": ext_live,
        "bid": _f(q.get("bid")),
        "ask": _f(q.get("ask")),
    }


def fetch_fred_series(series_id: str, years: int = 10) -> list[tuple[str, float]]:
    """Return list of (date, value) ascending, filtered to last `years`."""
    raw = _read_fred_csv_local(series_id)
    if not raw:
        raw = _fetch_text(FRED_CSV.format(id=series_id))
        # Warm local cache
        try:
            cache = OID / "tmp" / "fred"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / f"{series_id}.csv").write_text(raw, encoding="utf-8")
        except Exception:
            pass
    rows: list[tuple[str, float]] = []
    reader = csv.DictReader(io.StringIO(raw))
    # columns: DATE, series_id
    date_key = reader.fieldnames[0] if reader.fieldnames else "DATE"
    val_key = reader.fieldnames[1] if reader.fieldnames and len(reader.fieldnames) > 1 else series_id
    cutoff = (_now_utc() - timedelta(days=365 * years + 30)).date()
    for row in reader:
        d = (row.get(date_key) or "").strip()
        v = (row.get(val_key) or "").strip()
        if not d or not v or v in (".", "NA", "nan"):
            continue
        try:
            dt = datetime.strptime(d[:10], "%Y-%m-%d").date()
            val = float(v)
        except ValueError:
            continue
        if dt < cutoff:
            continue
        rows.append((d[:10], val))
    return rows


def _percentile_rank(values: list[float], x: float) -> Optional[float]:
    if not values:
        return None
    n = len(values)
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    # Mid-rank percentile 0–100
    return round(100.0 * (below + 0.5 * equal) / n, 1)


def _delta_vs_ago(series: list[tuple[str, float]], days: int = 365) -> Optional[float]:
    if len(series) < 2:
        return None
    latest_d, latest_v = series[-1]
    target = datetime.strptime(latest_d, "%Y-%m-%d").date() - timedelta(days=days)
    best = None
    best_dist = None
    for d, v in series:
        dd = datetime.strptime(d, "%Y-%m-%d").date()
        dist = abs((dd - target).days)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = v
    if best is None or best_dist is not None and best_dist > 45:
        return None
    return round(latest_v - best, 3)


def summarize_oas(series_id: str, name: str, years: int = 10) -> dict[str, Any]:
    series = fetch_fred_series(series_id, years=years)
    if not series:
        return {
            "series_id": series_id,
            "name": name,
            "error": "empty_series",
        }
    latest_d, latest_v = series[-1]
    vals = [v for _, v in series]
    pct = _percentile_rank(vals, latest_v)
    # Quartile label (1=tightest, 4=widest)
    q = None
    if pct is not None:
        if pct <= 25:
            q = 1
        elif pct <= 50:
            q = 2
        elif pct <= 75:
            q = 3
        else:
            q = 4
    tight_note = None
    if q == 1:
        tight_note = "tight (Q1) — historically more often associated with S&P up next year"
    elif q == 4:
        tight_note = "very wide (Q4) — often near credit/equity stress bottoms"
    return {
        "series_id": series_id,
        "name": name,
        "level": latest_v,
        "as_of_date": latest_d,
        "delta_1y": _delta_vs_ago(series, 365),
        "percentile_10y": pct,
        "quartile": q,
        "history_n": len(series),
        "min": round(min(vals), 3),
        "max": round(max(vals), 3),
        "median": round(sorted(vals)[len(vals) // 2], 3),
        "note": tight_note,
        "source": f"FRED CSV {series_id}",
    }


def fetch_yahoo_closes(sym: str) -> list[tuple[str, float]]:
    data = None
    local = OID / "tmp" / "fred" / f"{sym}-chart.json"
    if local.is_file() and local.stat().st_size > 100:
        age = _now_utc().timestamp() - local.stat().st_mtime
        if age < 7 * 86400:
            try:
                data = json.loads(local.read_text())
            except Exception:
                data = None
    if data is None:
        url = YAHOO_CHART.format(sym=sym)
        data = _fetch_json(url)
        try:
            cache = OID / "tmp" / "fred"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / f"{sym}-chart.json").write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return []
    r0 = result[0]
    ts = r0.get("timestamp") or []
    closes = ((r0.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out: list[tuple[str, float]] = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d")
        out.append((d, float(c)))
    return out


def valuation_spread_proxy(quotes: dict[str, dict], *, use_yahoo: bool = True) -> dict[str, Any]:
    """VTV vs VUG as cheap/expensive gap proxy (not true vendor valuation spreads)."""
    vtv = quotes.get("VTV") or {}
    vug = quotes.get("VUG") or {}
    session = market_session()
    vtv_spot, _ = _display_spot(vtv, session)
    vug_spot, _ = _display_spot(vug, session)
    if session == "closed":
        vtv_spot = _f(vtv.get("last"))
        vug_spot = _f(vug.get("last"))
    vtv_prev = _f(vtv.get("prev_close"))
    vug_prev = _f(vug.get("prev_close"))
    vtv_day = _day_pct(vtv_spot, vtv_prev)
    vug_day = _day_pct(vug_spot, vug_prev)
    day_spread = None
    if vtv_day is not None and vug_day is not None:
        day_spread = round(vtv_day - vug_day, 4)
    ratio = None
    if vtv_spot and vug_spot and vug_spot != 0:
        ratio = round(float(vtv_spot) / float(vug_spot), 6)

    hist: dict[str, Any] = {"available": False}
    if use_yahoo:
        try:
            vtv_h = fetch_yahoo_closes("VTV")
            vug_h = fetch_yahoo_closes("VUG")
            by_d = {d: c for d, c in vtv_h}
            ratios: list[float] = []
            ratio_series: list[tuple[str, float]] = []
            for d, c in vug_h:
                if d in by_d and c and by_d[d]:
                    r = by_d[d] / c
                    ratios.append(r)
                    ratio_series.append((d, r))
            if ratios and ratio is not None:
                # Prefer ratio from aligned last common date if live ratio missing history tip
                pct = _percentile_rank(ratios, ratio)
                # Also compute ~1y ago ratio
                delta_1y = _delta_vs_ago(ratio_series, 365)
                q = None
                if pct is not None:
                    q = 1 if pct <= 25 else 2 if pct <= 50 else 3 if pct <= 75 else 4
                fear_note = None
                if q == 4:
                    fear_note = (
                        "top-quartile VTV/VUG ratio vs ~10y — value/growth gap elevated "
                        "(proxy for cheap-vs-expensive blowout / fear priced; contrarian-friendly)"
                    )
                elif q == 1:
                    fear_note = "bottom-quartile VTV/VUG — gap compressed vs history (proxy)"
                hist = {
                    "available": True,
                    "source": "Yahoo chart 10y daily (VTV/VUG close ratio)",
                    "ratio_percentile_10y": pct,
                    "quartile": q,
                    "history_n": len(ratios),
                    "ratio_min": round(min(ratios), 4),
                    "ratio_max": round(max(ratios), 4),
                    "ratio_median": round(sorted(ratios)[len(ratios) // 2], 4),
                    "ratio_delta_1y": round(delta_1y, 4) if delta_1y is not None else None,
                    "note": fear_note,
                }
        except Exception as e:
            hist = {"available": False, "error": str(e)[:200]}

    return {
        "proxy": "VTV vs VUG (value vs growth ETF)",
        "disclaimer": (
            "Proxy for cheap-vs-expensive valuation gap — NOT a true quant valuation-spread "
            "series (FactSet/Bloomberg/vendor). Soft color only."
        ),
        "vtv": {"spot": vtv_spot, "prev_close": vtv_prev, "day_pct": vtv_day},
        "vug": {"spot": vug_spot, "prev_close": vug_prev, "day_pct": vug_day},
        "day_spread_pct": day_spread,  # VTV day% − VUG day%
        "price_ratio": ratio,  # VTV/VUG
        "history": hist,
    }


def median_growth_proxy(quotes: dict[str, dict]) -> dict[str, Any]:
    """RSP (equal-weight S&P) vs SPY as median-earnings / breadth proxy."""
    session = market_session()
    rsp = quotes.get("RSP") or {}
    spy = quotes.get("SPY") or {}
    rsp_spot, _ = _display_spot(rsp, session)
    spy_spot, _ = _display_spot(spy, session)
    if session == "closed":
        rsp_spot = _f(rsp.get("last"))
        spy_spot = _f(spy.get("last"))
    rsp_prev = _f(rsp.get("prev_close"))
    spy_prev = _f(spy.get("prev_close"))
    rsp_day = _day_pct(rsp_spot, rsp_prev)
    spy_day = _day_pct(spy_spot, spy_prev)
    spread = None
    if rsp_day is not None and spy_day is not None:
        spread = round(rsp_day - spy_day, 4)
    return {
        "proxy": "RSP vs SPY (equal-weight S&P vs cap-weight)",
        "disclaimer": (
            "Median-earnings proxy via equal-weight; true median EPS growth needs "
            "FactSet/Bloomberg (or similar) later. Soft color only."
        ),
        "rsp": {"spot": rsp_spot, "prev_close": rsp_prev, "day_pct": rsp_day},
        "spy": {"spot": spy_spot, "prev_close": spy_prev, "day_pct": spy_day},
        "rsp_minus_spy_day_pct": spread,
        "note": (
            "Equal-weight clearer on economy/jobs breadth than cap-weight; "
            "video: median earnings growth of S&P cos > cap-weighted mean often."
        ),
    }



def resolve_tape_quotes(
    *,
    equity_quotes_file: Path | None = None,
    equity_quotes_stdin: bool = False,
    from_rh_quotes_cache: bool = True,
    require_all: bool = True,
) -> tuple[dict[str, dict], dict[str, Any]]:
    """Resolve tape equity marks: piggyback fresh rh-quotes, then optional RH file for misses.

    Never writes rh-quotes (Rose sole writer). Returns (quotes, meta).
    """
    meta: dict[str, Any] = {
        "piggyback": False,
        "covered": [],
        "missing": list(TAPE_SYMBOLS),
        "source": None,
        "rh_as_of_pt": None,
        "rh_writer": None,
        "rh_age_seconds": None,
    }
    quotes: dict[str, dict] = {}

    if from_rh_quotes_cache:
        pb = piggyback_rh_quotes(TAPE_SYMBOLS, ttl_seconds=120)
        meta["piggyback"] = bool(pb.get("fresh"))
        meta["rh_as_of_pt"] = pb.get("as_of_pt")
        meta["rh_writer"] = pb.get("writer")
        meta["rh_age_seconds"] = pb.get("age_seconds")
        if pb.get("fresh") and pb.get("quotes"):
            quotes.update(pb["quotes"])
            meta["covered"] = list(pb.get("covered") or [])
            meta["missing"] = list(pb.get("missing") or [])
            meta["source"] = "rh-quotes-cache"
            if not meta["missing"]:
                meta["source"] = "rh-quotes-cache (full)"
                return quotes, meta

    file_quotes: dict[str, dict] = {}
    if equity_quotes_stdin or equity_quotes_file:
        raw = sys.stdin.read() if equity_quotes_stdin else Path(equity_quotes_file).read_text()
        file_quotes = normalize_equity_quotes(json.loads(raw))
        for sym, q in file_quotes.items():
            # Prefer live file overlay for any symbol present in the file
            quotes[sym] = q
        # Recompute missing vs TAPE_SYMBOLS after merge
        meta["missing"] = [s for s in TAPE_SYMBOLS if s not in quotes]
        meta["covered"] = [s for s in TAPE_SYMBOLS if s in quotes]
        if meta.get("source") == "rh-quotes-cache":
            meta["source"] = "rh-quotes-cache + equity-quotes-file"
        else:
            meta["source"] = "equity-quotes-file"

    if require_all and meta["missing"]:
        raise ValueError(
            "tape quotes incomplete; missing "
            + ",".join(meta["missing"])
            + (
                " — pass --equity-quotes-file for misses, or wait for Rose rh-quotes"
                if from_rh_quotes_cache
                else " — provide --equity-quotes-file"
            )
        )
    if not quotes:
        raise ValueError("no equity quotes resolved (cache miss and no --equity-quotes-file)")
    return quotes, meta


def build_tape(quotes: dict[str, dict]) -> dict[str, Any]:
    session = market_session()
    indices = []
    for sym in INDEX_SYMBOLS:
        q = quotes.get(sym) or {}
        indices.append(build_index_row(sym, q, session))
    helpers = {}
    for sym in ("RSP", "VTV", "VUG"):
        q = quotes.get(sym) or {}
        if q:
            helpers[sym] = build_index_row(sym, q, session)
    return {
        "session": session,
        "session_label": session_label(session),
        "as_of_pt": _as_of_pt(),
        "indices": indices,
        "helpers": helpers,
        "symbols": [s for s in TAPE_SYMBOLS if s in quotes],
        "source": "user-robinhood-trading get_equity_quotes",
        "mandate": "Research / paper only · Zero execution",
    }


def build_fidelity_three(
    quotes: dict[str, dict],
    *,
    skip_fred: bool = False,
    skip_yahoo: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "as_of_pt": _as_of_pt(),
        "video_ref": "YouTube short jgf3ij05Cgw — Fidelity guest desert-island 3",
        "mandate": "Research / paper only · Soft color · Zero execution",
        "median_growth": median_growth_proxy(quotes),
        "valuation_spreads": valuation_spread_proxy(quotes, use_yahoo=not skip_yahoo),
    }
    if skip_fred:
        # Reuse prior credit block if present
        prev = LATEST / "fidelity-three.json"
        credit = {"error": "skipped"}
        if prev.is_file():
            try:
                old = json.loads(prev.read_text())
                credit = (old.get("payload") or old).get("credit_spreads") or credit
            except Exception:
                pass
        out["credit_spreads"] = credit
    else:
        try:
            hy = summarize_oas(FRED_HY, "ICE BofA US High Yield OAS")
            ig = summarize_oas(FRED_IG, "ICE BofA US Corporate OAS (IG)")
            out["credit_spreads"] = {
                "hy_oas": hy,
                "ig_oas": ig,
                "logic": (
                    "Tight spreads (low percentile / Q1) → historically more likely S&P up next year; "
                    "very wide (Q4) often near bottoms. Soft quartile color only — not a trade signal."
                ),
                "source": "FRED public CSV (no API key)",
            }
            write_feed(
                "fred-hy-oas",
                source=f"FRED CSV {FRED_HY}",
                writer="refresh_market_tape.py",
                symbols=[],
                payload=hy,
                ttl_seconds=86400,
                error=hy.get("error"),
            )
            write_feed(
                "fred-ig-oas",
                source=f"FRED CSV {FRED_IG}",
                writer="refresh_market_tape.py",
                symbols=[],
                payload=ig,
                ttl_seconds=86400,
                error=ig.get("error"),
            )
        except Exception as e:
            out["credit_spreads"] = {
                "error": f"fred_fetch_failed: {e}"[:240],
                "logic": (
                    "Tight spreads (low percentile / Q1) → historically more likely S&P up next year; "
                    "very wide (Q4) often near bottoms. Soft quartile color only — not a trade signal."
                ),
                "source": "FRED public CSV (no API key)",
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh OID market-tape + Fidelity-3 strip caches")
    ap.add_argument("--equity-quotes-file", type=Path, help="RH get_equity_quotes JSON (fills cache misses)")
    ap.add_argument("--equity-quotes-stdin", action="store_true")
    ap.add_argument(
        "--from-rh-quotes-cache",
        action="store_true",
        default=True,
        help="Piggyback fresh shared rh-quotes (default on)",
    )
    ap.add_argument(
        "--no-rh-quotes-cache",
        action="store_true",
        help="Disable rh-quotes piggyback (require equity quotes file)",
    )
    ap.add_argument("--emit-symbols", action="store_true", help="Print tape symbols JSON and exit")
    ap.add_argument(
        "--check-piggyback",
        action="store_true",
        help="Smoke: print piggyback coverage for tape symbols and exit (no RH call, no write)",
    )
    ap.add_argument("--skip-fred", action="store_true")
    ap.add_argument("--skip-yahoo", action="store_true")
    ap.add_argument("--index-quotes-file", type=Path, help="RH get_index_quotes JSON (VIX)")
    ap.add_argument("--index-historicals-file", type=Path, help="RH get_index_historicals JSON (VIX day bars)")
    ap.add_argument("--uw-yield-curve-file", type=Path, help="Optional UW get_yield_curve JSON")
    ap.add_argument("--skip-macro", action="store_true", help="Skip Rates·Vol·Oil macro block")
    ap.add_argument("--emit-index-ids", action="store_true", help="Print VIX instrument_id JSON and exit")
    ap.add_argument("--writer", default="refresh_market_tape.py")
    args = ap.parse_args()

    if args.emit_symbols:
        print(json.dumps({"symbols": TAPE_SYMBOLS, "session": market_session()}))
        return 0
    if getattr(args, "emit_index_ids", False):
        print(json.dumps({
            "index_instrument_ids": ["3b912aa2-88f9-4682-8ae3-e39520bdf4db"],
            "symbols": ["VIX"],
            "note": "Pass ids to user-robinhood-trading get_index_quotes / get_index_historicals",
        }))
        return 0

    if args.check_piggyback:
        pb = piggyback_rh_quotes(TAPE_SYMBOLS, ttl_seconds=120)
        print(
            json.dumps(
                {
                    "ok": True,
                    "check": "piggyback",
                    "fresh": pb.get("fresh"),
                    "reused": pb.get("reused"),
                    "covered": pb.get("covered"),
                    "missing": pb.get("missing"),
                    "as_of_pt": pb.get("as_of_pt"),
                    "writer": pb.get("writer"),
                    "age_seconds": pb.get("age_seconds"),
                    "ttl_seconds": pb.get("ttl_seconds"),
                    "note": "No RH call; support-map/market-tape should reuse covered marks",
                },
                indent=2,
            )
        )
        return 0 if pb.get("fresh") else 1

    use_cache = bool(args.from_rh_quotes_cache) and not bool(args.no_rh_quotes_cache)
    if not args.equity_quotes_file and not args.equity_quotes_stdin and not use_cache:
        ap.error("Provide --equity-quotes-file/--equity-quotes-stdin or allow rh-quotes cache")

    try:
        quotes, qmeta = resolve_tape_quotes(
            equity_quotes_file=args.equity_quotes_file,
            equity_quotes_stdin=bool(args.equity_quotes_stdin),
            from_rh_quotes_cache=use_cache,
            require_all=True,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        # Helpful miss report without burning RH
        pb = piggyback_rh_quotes(TAPE_SYMBOLS, ttl_seconds=120) if use_cache else {}
        print(
            json.dumps(
                {
                    "piggyback_fresh": pb.get("fresh"),
                    "covered": pb.get("covered"),
                    "missing": pb.get("missing"),
                    "hint": "Rose: get_equity_quotes for missing only, then refresh_marks.py writes rh-quotes",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    tape = build_tape(quotes)
    tape["quote_source"] = qmeta.get("source")
    tape["rh_quotes_piggyback"] = {
        "used": bool(qmeta.get("piggyback")),
        "covered": qmeta.get("covered"),
        "missing_filled_from_file": [
            s for s in TAPE_SYMBOLS if s not in (qmeta.get("covered") or []) and s in quotes
        ],
        "rh_as_of_pt": qmeta.get("rh_as_of_pt"),
        "rh_writer": qmeta.get("rh_writer"),
        "rh_age_seconds": qmeta.get("rh_age_seconds"),
    }
    if qmeta.get("source") and "cache" in str(qmeta.get("source")):
        tape["source"] = f"piggyback {qmeta.get('source')}"
    fid = build_fidelity_three(quotes, skip_fred=args.skip_fred, skip_yahoo=args.skip_yahoo)

    macro = None
    if not getattr(args, "skip_macro", False):
        try:
            from macro_spot import build_macro_spot, default_input_paths
            paths = default_input_paths()
            macro = build_macro_spot(
                index_quotes_file=getattr(args, "index_quotes_file", None) or paths["index_quotes_file"],
                index_historicals_file=getattr(args, "index_historicals_file", None) or paths["index_historicals_file"],
                uw_yield_curve_file=getattr(args, "uw_yield_curve_file", None) or paths["uw_yield_curve_file"],
                skip_fred=bool(args.skip_fred),
            )
            tape["macro"] = macro
            write_feed(
                "macro-spot",
                source=macro.get("source_policy") or "FRED + RH VIX",
                writer=args.writer,
                symbols=["US10Y", "VIX", "WTI", "BRENT"],
                payload=macro,
                ttl_seconds=300,
            )
        except Exception as _macro_e:
            tape["macro"] = {"error": f"macro_build_failed: {_macro_e}"[:240]}
            print(f"WARN macro_spot: {_macro_e}", flush=True)

    rec_tape = write_feed(
        "market-tape",
        source="user-robinhood-trading get_equity_quotes",
        writer=args.writer,
        symbols=tape.get("symbols") or list(quotes.keys()),
        payload=tape,
        ttl_seconds=300,
    )
    rec_fid = write_feed(
        "fidelity-three",
        source="RH quotes + FRED CSV + Yahoo chart (valuation hist)",
        writer=args.writer,
        symbols=["RSP", "SPY", "VTV", "VUG"],
        payload=fid,
        ttl_seconds=1800,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "market_tape": rec_tape["as_of_pt"],
                "fidelity_three": rec_fid["as_of_pt"],
                "session": tape["session"],
                "indices": [
                    {
                        "symbol": i["symbol"],
                        "spot": i["spot"],
                        "day_pct": i["day_pct"],
                    }
                    for i in tape["indices"]
                ],
                "hy_oas": (fid.get("credit_spreads") or {}).get("hy_oas", {}).get("level"),
                "ig_oas": (fid.get("credit_spreads") or {}).get("ig_oas", {}).get("level"),
                "rsp_spy_spread": (fid.get("median_growth") or {}).get("rsp_minus_spy_day_pct"),
                "macro": {
                    c["id"]: {"spot": c.get("spot"), "day_pct": c.get("day_pct"), "day_chg_bp": c.get("day_chg_bp")}
                    for c in ((tape.get("macro") or {}).get("items") or [])
                },
                "vtv_vug_ratio": (fid.get("valuation_spreads") or {}).get("price_ratio"),
                "quote_source": tape.get("quote_source"),
                "rh_quotes_piggyback": tape.get("rh_quotes_piggyback"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
