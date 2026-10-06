#!/usr/bin/env python3
"""OID support-map refresh — piggyback shared rh-quotes (Duplicates #2).

Writes:
  market-data/latest/support-map.json
  paper-trades/universe-support-watch.json (+ dashboard copy)
  paper-trades/nvda-support-watch.json (+ dashboard copy)

Quote policy:
  1. Read fresh rh-quotes via cache_io.piggyback_rh_quotes (TTL 120s).
  2. If covered for needed symbols → reuse marks; no RH get_equity_quotes.
  3. On miss/partial: optional --equity-quotes-file fills missing only.
  4. This script NEVER writes rh-quotes — Rose sole writer remains
     refresh_marks.py / live_refresh.py. Hal is reader-only.

Soft / paper only. Zero RH orders. Never elevates.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OID = ROOT.parent
MD = OID / "market-data"
PT = ZoneInfo("America/Los_Angeles")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OID / "paper-trades"))
sys.path.insert(0, str(MD))

from cache_io import (  # noqa: E402
    age_seconds,
    piggyback_rh_quotes,
    read_fresh,
    write_feed,
)
from market_session import market_session, session_label  # noqa: E402
from refresh_marks import normalize_equity_quotes  # noqa: E402

PRIMARY = [
    "SPY", "QQQ", "NVDA", "TSLA", "PLTR", "GOOGL", "NFLX",
    "META", "AMZN", "AMD", "CBRS", "INTC", "TSM",
]
EXTENDED = ["MU", "BE", "MRVL", "NBIS", "IREN", "CRWV", "SNDK", "AVGO", "ASML", "GOOG"]
ALL = PRIMARY + EXTENDED


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_of_pt(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = _now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(PT)
    return local.strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " ")


def _f(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _load_fa_walls() -> tuple[dict[str, dict], dict[str, Any]]:
    """Return (walls_by_symbol, meta). Prefer fresh fa-levels; else STALE_CARRY if walls present."""
    meta: dict[str, Any] = {"freshness": "FRESH", "record": None}
    rec = read_fresh("fa-levels")
    if rec is None:
        path = MD / "latest" / "fa-levels.json"
        if not path.is_file():
            raise FileNotFoundError("fa-levels missing entirely")
        rec = json.loads(path.read_text(encoding="utf-8"))
        meta["freshness"] = "STALE_CARRY"
    meta["record"] = rec
    payload = rec.get("payload") or {}
    walls: dict[str, dict] = {}

    def ingest_map(m: Any) -> None:
        if not isinstance(m, dict):
            return
        for sym, v in m.items():
            if not isinstance(v, dict):
                continue
            s = str(sym).strip().upper()
            lv = v.get("raw_levels") if isinstance(v.get("raw_levels"), dict) else {}
            put = v.get("put_wall") if v.get("put_wall") is not None else v.get("pw")
            if put is None:
                put = lv.get("put_wall")
            call = v.get("call_wall") if v.get("call_wall") is not None else v.get("cw")
            if call is None:
                call = lv.get("call_wall")
            flip = v.get("gamma_flip") if "gamma_flip" in v else v.get("flip")
            if flip is None:
                flip = lv.get("gamma_flip")
            if put is None and call is None:
                continue
            walls[s] = {
                "put_wall": _f(put),
                "call_wall": _f(call),
                "gamma_flip": _f(flip),
                "freshness": v.get("freshness") or v.get("status"),
            }

    if isinstance(payload, dict):
        if any(k in payload for k in ("symbols", "levels", "walls")):
            ingest_map(payload.get("walls"))
            ingest_map(payload.get("symbols"))
            ingest_map(payload.get("levels"))
        else:
            ingest_map(payload)
    meta["as_of_pt"] = rec.get("as_of_pt")
    meta["writer"] = rec.get("writer")
    meta["age_seconds"] = age_seconds("fa-levels")
    return walls, meta


def _display_spot(q: dict, session: str) -> Optional[float]:
    last = _f(q.get("last"))
    ext = _f(q.get("last_non_reg"))
    if session in ("pre", "ah") and ext is not None:
        return ext
    if session == "closed":
        return last
    return ext if ext is not None else last


def classify(spot: float, put: Optional[float], flip: Optional[float]) -> tuple[Optional[float], bool, str, str]:
    if put is None or put == 0:
        return None, False, "WALLS_DATA_INSUFFICIENT", "walls data insufficient"
    pct = (spot - put) / put * 100.0
    band = abs(pct) <= 0.5 or spot <= put * 1.005
    if spot < put:
        return round(pct, 2), True, "THRU_PUT", "through put wall"
    if band:
        note = "within 0.5% of put wall"
        if flip is not None and spot <= max(flip, put) * 1.002:
            note = f"testing flip {flip:.2f} with put held ({put:g})"
        return round(pct, 2), True, "GOOD_LOW", note
    if flip is not None and put <= spot:
        if spot <= flip * 1.005 or (put < spot < flip):
            return round(pct, 2), False, "ABOVE_PUT", f"testing flip {flip:.2f} with put held ({put:g})"
    return round(pct, 2), False, "ABOVE_PUT", "above put wall"


def resolve_support_quotes(
    *,
    equity_quotes_file: Path | None = None,
    from_rh_quotes_cache: bool = True,
    require_primary: bool = True,
) -> tuple[dict[str, dict], dict[str, Any]]:
    """Piggyback rh-quotes; optional file fills misses. Never writes rh-quotes."""
    meta: dict[str, Any] = {
        "piggyback": False,
        "covered": [],
        "missing": list(ALL),
        "source": None,
        "rh_as_of_pt": None,
        "rh_writer": None,
        "rh_age_seconds": None,
        "rh_label": "cache",
    }
    quotes: dict[str, dict] = {}
    if from_rh_quotes_cache:
        pb = piggyback_rh_quotes(ALL, ttl_seconds=120)
        meta["piggyback"] = bool(pb.get("fresh"))
        meta["rh_as_of_pt"] = pb.get("as_of_pt")
        meta["rh_writer"] = pb.get("writer")
        meta["rh_age_seconds"] = pb.get("age_seconds")
        if pb.get("fresh") and pb.get("quotes"):
            quotes.update(pb["quotes"])
            meta["covered"] = list(pb.get("covered") or [])
            meta["missing"] = list(pb.get("missing") or [])
            meta["source"] = "rh-quotes-cache"
            meta["rh_label"] = "cache"
            if not meta["missing"]:
                meta["source"] = "rh-quotes-cache (full)"
                return quotes, meta

    if equity_quotes_file:
        file_quotes = normalize_equity_quotes(json.loads(Path(equity_quotes_file).read_text()))
        for sym, q in file_quotes.items():
            quotes[sym] = q
        meta["missing"] = [s for s in ALL if s not in quotes]
        meta["covered"] = [s for s in ALL if s in quotes]
        if meta.get("source") and "cache" in str(meta.get("source")):
            meta["source"] = "rh-quotes-cache + equity-quotes-file"
            meta["rh_label"] = "cache+file"
        else:
            meta["source"] = "equity-quotes-file"
            meta["rh_label"] = "file"

    primary_missing = [s for s in PRIMARY if s not in quotes]
    if require_primary and primary_missing:
        raise ValueError(
            "support-map primary quotes incomplete; missing "
            + ",".join(primary_missing)
            + " — Rose: get_equity_quotes for missing only, then refresh_marks.py (sole rh-quotes writer)"
        )
    if not quotes:
        raise ValueError("no equity quotes resolved for support-map")
    return quotes, meta


def build_rows(
    walls: dict[str, dict],
    quotes: dict[str, dict],
    *,
    session: str,
    as_of_pt: str,
    quote_label: str,
) -> tuple[list[dict], list[str], dict, dict]:
    rows: list[dict] = []
    near: list[str] = []
    key_map: dict[str, Any] = {}
    ext_map: dict[str, Any] = {}
    human = session_label(session)

    for sym in ALL:
        fa = walls.get(sym) or {}
        q = quotes.get(sym)
        book = "primary" if sym in PRIMARY else "extended"
        put = fa.get("put_wall")
        call = fa.get("call_wall")
        flip = fa.get("gamma_flip")
        spot = _display_spot(q, session) if q else None
        prev = _f(q.get("prev_close")) if q else None

        if put is None:
            row = {
                "symbol": sym,
                "faCallWall": call,
                "faPutWall": None,
                "faFlip": flip,
                "supportPrimary": None,
                "supportSecondary": flip,
                "resistance": call,
                "last": spot,
                "prevClose": prev,
                "dayPct": (
                    round((spot - prev) / prev * 100.0, 4)
                    if spot is not None and prev
                    else None
                ),
                "distanceToPutWallPct": None,
                "inGoodLowBand": False,
                "statusHint": "WALLS_DATA_INSUFFICIENT",
                "softNote": "walls data insufficient",
                "softOnly": True,
                "session": session,
                "sessionLabel": human,
                "updatedAtPT": as_of_pt,
                "quoteAgeSec": None,
                "quoteLabel": quote_label if q else None,
                "book": book,
                "putHardRoll": None,
            }
            rows.append(row)
            continue

        if spot is None:
            row = {
                "symbol": sym,
                "faCallWall": call,
                "faPutWall": put,
                "faFlip": flip,
                "supportPrimary": put,
                "supportSecondary": flip,
                "resistance": call,
                "last": None,
                "prevClose": prev,
                "dayPct": None,
                "distanceToPutWallPct": None,
                "inGoodLowBand": False,
                "statusHint": "WALLS_DATA_INSUFFICIENT",
                "softNote": "no RH quote",
                "softOnly": True,
                "session": session,
                "sessionLabel": human,
                "updatedAtPT": as_of_pt,
                "quoteAgeSec": None,
                "quoteLabel": None,
                "book": book,
                "putHardRoll": None,
            }
            rows.append(row)
            continue

        day_pct = round((spot - prev) / prev * 100.0, 4) if prev else None
        dist, in_band, hint, note = classify(float(spot), put, flip)
        row = {
            "symbol": sym,
            "faCallWall": call,
            "faPutWall": put,
            "faFlip": flip,
            "supportPrimary": put,
            "supportSecondary": flip,
            "resistance": call,
            "last": float(spot),
            "prevClose": prev,
            "dayPct": day_pct,
            "distanceToPutWallPct": dist,
            "inGoodLowBand": in_band,
            "statusHint": hint,
            "softNote": note,
            "softOnly": True,
            "session": session,
            "sessionLabel": human,
            "updatedAtPT": as_of_pt,
            "quoteAgeSec": None,
            "quoteLabel": quote_label,
            "book": book,
            "putHardRoll": None,
        }
        rows.append(row)
        summary = {
            "put": put,
            "call": call,
            "flip": flip,
            "last": float(spot),
            "distPct": dist,
            "hint": hint,
            "inBand": in_band,
            "dayPct": day_pct,
            "note": note,
        }
        if book == "primary":
            key_map[sym] = summary
        else:
            ext_map[sym] = summary
        if in_band or note.startswith("testing flip") or hint in ("GOOD_LOW", "THRU_PUT"):
            near.append(sym)
    return rows, near, key_map, ext_map


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh OID support-map (piggyback rh-quotes)")
    ap.add_argument("--equity-quotes-file", type=Path, help="RH JSON for cache misses only")
    ap.add_argument("--no-rh-quotes-cache", action="store_true", help="Require equity file; skip piggyback")
    ap.add_argument("--dry-run", action="store_true", help="Resolve + build; do not write files")
    ap.add_argument(
        "--check-piggyback",
        action="store_true",
        help="Smoke: print rh-quotes coverage for support symbols; no write / no RH call",
    )
    ap.add_argument("--writer", default="refresh_support_map.py")
    args = ap.parse_args()

    if args.check_piggyback:
        pb = piggyback_rh_quotes(ALL, ttl_seconds=120)
        print(
            json.dumps(
                {
                    "ok": True,
                    "check": "piggyback",
                    "fresh": pb.get("fresh"),
                    "reused": pb.get("reused"),
                    "covered": pb.get("covered"),
                    "missing": pb.get("missing"),
                    "primary_missing": [s for s in PRIMARY if s in (pb.get("missing") or [])],
                    "as_of_pt": pb.get("as_of_pt"),
                    "writer": pb.get("writer"),
                    "age_seconds": pb.get("age_seconds"),
                    "note": "Hal/readers never write rh-quotes; Rose refresh_marks is sole writer",
                },
                indent=2,
            )
        )
        return 0 if pb.get("fresh") else 1

    use_cache = not bool(args.no_rh_quotes_cache)
    try:
        quotes, qmeta = resolve_support_quotes(
            equity_quotes_file=args.equity_quotes_file,
            from_rh_quotes_cache=use_cache,
            require_primary=True,
        )
        walls, fa_meta = _load_fa_walls()
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        pb = piggyback_rh_quotes(ALL, ttl_seconds=120) if use_cache else {}
        print(
            json.dumps(
                {
                    "piggyback_fresh": pb.get("fresh"),
                    "covered": pb.get("covered"),
                    "missing": pb.get("missing"),
                    "hint": "Rose sole writer: refresh_marks.py / live_refresh.py → rh-quotes; then re-run",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    session = market_session()
    as_of_pt = _as_of_pt()
    qlabel = "cache" if qmeta.get("rh_label") == "cache" else str(qmeta.get("rh_label") or "mix")
    rows, near, key_map, ext_map = build_rows(
        walls, quotes, session=session, as_of_pt=as_of_pt, quote_label=qlabel
    )

    support_payload = {
        "as_of_pt": as_of_pt,
        "session": session,
        "sessionLabel": session_label(session),
        "faAsOfPT": fa_meta.get("as_of_pt"),
        "faFreshness": fa_meta.get("freshness"),
        "faWriter": fa_meta.get("writer"),
        "faAgeSec": round(fa_meta["age_seconds"], 1) if fa_meta.get("age_seconds") is not None else None,
        "rhAsOfPT": qmeta.get("rh_as_of_pt"),
        "rhAgeSec": round(qmeta["rh_age_seconds"], 1) if qmeta.get("rh_age_seconds") is not None else None,
        "rhWriter": qmeta.get("rh_writer"),
        "rhLabel": qlabel,
        "rhPiggyback": True,
        "quoteSource": qmeta.get("source"),
        "nearSupportNow": near,
        "key": key_map,
        "extended": ext_map,
    }

    watch = {
        "id": "UNIVERSE-SUPPORT-20261005",
        "type": "soft_watch",
        "softOnly": True,
        "neverElevateAlone": True,
        "status": "pinned",
        "title": "OID universe dealer support map (put wall / flip)",
        "thesis": (
            "Jeffrey: track key-name demand dips near FA put walls (flip secondary). "
            "Soft color only — never elevate on support alone."
        ),
        "goodLowBandRule": "within ~0.5% of FA put wall OR testing put/flip with put held",
        "faAsOfPT": fa_meta.get("as_of_pt"),
        "faWriter": fa_meta.get("writer"),
        "faFreshness": fa_meta.get("freshness"),
        "faAgeSec": support_payload["faAgeSec"],
        "rhAsOfPT": qmeta.get("rh_as_of_pt"),
        "rhAgeSec": support_payload["rhAgeSec"],
        "addedAtPT": "2026-09-23 10:07 AM PT",
        "updatedAtPT": as_of_pt,
        "session": session,
        "sessionLabel": session_label(session),
        "source": f"FlashAlpha fa-levels ({fa_meta.get('freshness')}) + RH quotes ({qmeta.get('source')})",
        "notes": (
            "Duplicates #2: piggybacks fresh shared rh-quotes (TTL 120s). "
            "Never writes rh-quotes. Soft only — never elevate."
        ),
        "nearSupportNow": near,
        "symbols": rows,
    }

    nvda_row = next((r for r in rows if r["symbol"] == "NVDA"), None)
    nvda_watch = None
    if nvda_row:
        nvda_watch = {
            "id": "NVDA-SUPPORT-20261005",
            "type": "soft_watch",
            "softOnly": True,
            "neverElevateAlone": True,
            "status": "pinned",
            "symbol": "NVDA",
            "title": "NVDA dealer support (put wall / flip) — soft",
            "thesis": "Good-low soft watch near FA put wall; never elevate on support alone.",
            "faCallWall": nvda_row["faCallWall"],
            "faPutWall": nvda_row["faPutWall"],
            "faFlip": nvda_row["faFlip"],
            "last": nvda_row["last"],
            "prevClose": nvda_row["prevClose"],
            "dayPct": nvda_row["dayPct"],
            "distanceToPutWallPct": nvda_row["distanceToPutWallPct"],
            "inGoodLowBand": nvda_row["inGoodLowBand"],
            "statusHint": nvda_row["statusHint"],
            "softNote": nvda_row["softNote"],
            "updatedAtPT": as_of_pt,
            "session": session,
            "sessionLabel": session_label(session),
            "quoteAgeSec": nvda_row.get("quoteAgeSec"),
            "quoteLabel": qlabel,
            "universeWatch": "paper-trades/universe-support-watch.json",
        }

    summary = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "as_of_pt": as_of_pt,
        "session": session,
        "fa": {
            "freshness": fa_meta.get("freshness"),
            "as_of_pt": fa_meta.get("as_of_pt"),
            "writer": fa_meta.get("writer"),
        },
        "rh_quotes_piggyback": {
            "used": bool(qmeta.get("piggyback")),
            "source": qmeta.get("source"),
            "covered": qmeta.get("covered"),
            "missing": qmeta.get("missing"),
            "rh_as_of_pt": qmeta.get("rh_as_of_pt"),
            "rh_writer": qmeta.get("rh_writer"),
            "wrote_rh_quotes": False,
        },
        "nearSupportNow": near,
        "n_rows": len(rows),
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return 0

    write_feed(
        "support-map",
        source=f"FlashAlpha fa-levels ({fa_meta.get('freshness')}) + RH quotes ({qmeta.get('source')})",
        writer=args.writer,
        symbols=ALL,
        payload=support_payload,
        ttl_seconds=300,
    )
    for path in (
        OID / "paper-trades" / "universe-support-watch.json",
        ROOT / "universe-support-watch.json",
    ):
        path.write_text(json.dumps(watch, indent=2) + "\n", encoding="utf-8")
    if nvda_watch:
        for path in (
            OID / "paper-trades" / "nvda-support-watch.json",
            ROOT / "nvda-support-watch.json",
        ):
            path.write_text(json.dumps(nvda_watch, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
