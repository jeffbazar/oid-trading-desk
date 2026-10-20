#!/usr/bin/env python3
"""Intraday 5m / 15m bars + relative volume (RVOL) for the OID desk (Jeffrey 2026-10-10).

Research / paper only - zero execution. Purpose: confirm wall breaks (break + volume + hold).

Sources (tagged on every bar row as ``src``):
  * ``alpaca-sip``  PRIMARY - Alpaca SIP (consolidated, all venues) 5-min bars via the Mac mini
                    collector ``GET /v1/bars`` (collector >= bars v1; keys stay on the mini).
  * ``rh``          FALLBACK - Robinhood ``get_equity_historicals`` 5minute/regular. Box Python cannot
                    call the RH MCP, so an agent pulls it and drops the raw tool output in
                    cache/bars/rh-raw/ then runs ``mini_bars.py ingest-rh <file>`` (see docs/BARS-RVOL.md).
  When both exist for the same 5-min slot, alpaca-sip wins.

Store:   cache/bars/store/<SYM>-5m.json   (RTH 5-min history, ~30 sessions, per-bar src)
Outputs: cache/bars/<SYM>-5m.json / <SYM>-15m.json   latest session bars with per-slot RVOL
         cache/bars/summary.json                     per-symbol session RVOL snapshot (focus_watch, blotter)

RVOL definitions (prior N=20 full RTH sessions, interpolated RH bars excluded):
  session_rvol = today's cumulative volume through the last real bar
                 / mean cumulative volume through the same slot over the prior sessions
  bar_rvol     = this bar's volume / mean volume of the same time-of-day slot over the prior sessions

CLI:
  mini_bars.py refresh [--symbols A,B] [--days 32]   mini pull (incremental) -> store -> outputs
  mini_bars.py ingest-rh FILE [FILE...]               RH get_equity_historicals output -> store -> outputs
  mini_bars.py build                                  rebuild outputs from store
  mini_bars.py break SYM LEVEL [--date YYYY-MM-DD] [--dir up|down|auto] [--rvol 1.5]
  mini_bars.py status
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mini_client as mc  # noqa: E402

OID = mc.OID
ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")
BARS_DIR = Path(os.environ.get("OID_BARS_DIR", str(OID / "cache" / "bars")))
FOCUS_CFG = OID / "config" / "focus-watch.json"
LOOKBACK = 20
KEEP_SESSIONS = 32
RVOL_BREAK_MIN = 1.5
SLOTS_5M = 78           # 09:30-16:00 ET
FULL_SESSION_MIN = 70   # sessions with fewer real 5m bars (half days / gaps) are not used as baseline
MINI_SRC, RH_SRC = "alpaca-sip", "rh"
SRC_RANK = {MINI_SRC: 2, RH_SRC: 1}
STALE_RTH_S = 15 * 60   # newest bar older than this during RTH -> stale


# ------------------------------------------------------------------ helpers
def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _utc(ts: str) -> Optional[datetime]:
    e = mc._parse_ts(ts)
    return datetime.fromtimestamp(e, timezone.utc) if e is not None else None


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slot_of(d_utc: datetime, minutes: int = 5) -> tuple[str, int]:
    """(ET session date, slot index from 09:30 ET) for a bar start."""
    e = d_utc.astimezone(ET)
    return e.strftime("%Y-%m-%d"), (e.hour * 60 + e.minute - 570) // minutes


def slot_label(slot: int, minutes: int = 5) -> str:
    m = 570 + slot * minutes
    return f"{m // 60:02d}:{m % 60:02d}"


def pt_label(d_utc: datetime) -> str:
    return d_utc.astimezone(PT).strftime("%-I:%M %p PT")


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)
        fh.write("\n")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def universe() -> list[str]:
    """core-20 allowlist + enabled focus-watch names (GOOGL aliases to GOOG for tape)."""
    syms = list(mc.core_symbols())
    cfg = read_json(FOCUS_CFG) or {}
    alias = {k.upper(): v.upper() for k, v in (cfg.get("quote_alias") or {}).items()}
    for s in cfg.get("symbols") or []:
        if s.get("enabled", True) and s.get("symbol"):
            sym = alias.get(s["symbol"].upper(), s["symbol"].upper())
            if sym not in syms:
                syms.append(sym)
    return syms


# ------------------------------------------------------------------ store
def store_path(sym: str) -> Path:
    return BARS_DIR / "store" / f"{sym}-5m.json"


def load_store(sym: str) -> dict[str, dict]:
    rec = read_json(store_path(sym)) or {}
    return {b["t"]: b for b in rec.get("bars") or [] if b.get("t")}


def save_store(sym: str, bars: dict[str, dict]) -> None:
    rows = sorted(bars.values(), key=lambda b: b["t"])
    dates = sorted({b["d"] for b in rows})
    keep = set(dates[-KEEP_SESSIONS:])
    rows = [b for b in rows if b["d"] in keep]
    atomic_write_json(store_path(sym), {"symbol": sym, "interval": "5m", "bounds": "rth",
                                        "updated_pt": mc._pt_stamp(), "bars": rows})


def norm_bar(t_utc: datetime, o, h, l, c, v, src: str, **extra) -> Optional[dict]:
    d, slot = slot_of(t_utc)
    if not (0 <= slot < SLOTS_5M):
        return None  # RTH only
    o, h, l, c, v = _f(o), _f(h), _f(l), _f(c), _f(v)
    if None in (o, h, l, c) or v is None:
        return None
    row = {"t": _iso(t_utc), "d": d, "slot": slot, "o": o, "h": h, "l": l, "c": c, "v": int(v), "src": src}
    row.update({k: v2 for k, v2 in extra.items() if v2 is not None})
    return row


def merge(sym: str, new_rows: Iterable[dict]) -> tuple[int, int]:
    cur = load_store(sym)
    added = replaced = 0
    for r in new_rows:
        old = cur.get(r["t"])
        if old is None:
            cur[r["t"]] = r
            added += 1
        elif SRC_RANK.get(r["src"], 0) >= SRC_RANK.get(old.get("src"), 0):
            if old != r:
                replaced += 1
            cur[r["t"]] = r
    save_store(sym, cur)
    return added, replaced


# ------------------------------------------------------------------ sources
def fetch_mini_bars(symbols: list[str], start: datetime, end: datetime, *, timeframe: str = "5Min",
                    timeout: float = 20.0, opener=None) -> dict[str, list[dict]]:
    """Alpaca SIP bars from the mini (GET /v1/bars). Raises mc.MiniError (scrubbed) on failure."""
    out: dict[str, list[dict]] = {}
    for i in range(0, len(symbols), 25):
        chunk = symbols[i:i + 25]
        params = {"symbols": ",".join(chunk), "timeframe": timeframe, "start": _iso(start), "end": _iso(end),
                  "feed": "sip", "adjustment": "raw"}
        status, data, _lat = mc._http_get_json("/v1/bars", timeout=timeout, auth=True, params=params, opener=opener)
        if status != 200 or not isinstance(data, dict) or "bars" not in data:
            raise mc.MiniError(f"bad /v1/bars response (HTTP {status})")
        if data.get("feed") != "sip":
            raise mc.MiniError(f"mini bars feed={data.get('feed')} (want sip)")
        for sym, rows in (data.get("bars") or {}).items():
            for r in rows or []:
                t = _utc(r.get("t"))
                if not t:
                    continue
                b = norm_bar(t, r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("v"), MINI_SRC,
                             n=r.get("n"), vw=r.get("vw"))
                if b:
                    out.setdefault(sym.upper(), []).append(b)
    return out


def parse_rh_payload(text: str) -> dict[str, list[dict]]:
    """Robinhood get_equity_historicals tool output (raw text, may carry a preamble) -> rows by symbol."""
    i = text.find('{"data"')
    if i < 0:
        i = text.find("{")
    doc, _ = json.JSONDecoder().raw_decode(text[i:])
    results = ((doc.get("data") or doc) or {}).get("results") or []
    out: dict[str, list[dict]] = {}
    for res in results:
        if (res.get("interval") or "5minute") != "5minute":
            raise ValueError(f"RH interval {res.get('interval')} (need 5minute)")
        sym = str(res.get("symbol") or "").upper()
        for b in res.get("bars") or []:
            if b.get("interpolated") or (b.get("session") not in (None, "reg")):
                continue  # gap-fill carries no volume information; RTH only
            t = _utc(b.get("begins_at"))
            if not t:
                continue
            row = norm_bar(t, b.get("open_price"), b.get("high_price"), b.get("low_price"), b.get("close_price"),
                           b.get("volume"), RH_SRC)
            if row:
                out.setdefault(sym, []).append(row)
    return out


# ------------------------------------------------------------------ RVOL core
def sessions(bars: dict[str, dict]) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for b in sorted(bars.values(), key=lambda b: b["t"]):
        by.setdefault(b["d"], []).append(b)
    return by


def agg15(day: list[dict]) -> list[dict]:
    """5-min bars of one session -> 15-min bars (slot//3). ``complete`` = all three 5m bars present."""
    groups: dict[int, list[dict]] = {}
    for b in day:
        groups.setdefault(b["slot"] // 3, []).append(b)
    out = []
    for s15, g in sorted(groups.items()):
        g.sort(key=lambda b: b["slot"])
        srcs = sorted({b["src"] for b in g})
        out.append({"t": g[0]["t"], "d": g[0]["d"], "slot": s15, "o": g[0]["o"], "h": max(b["h"] for b in g),
                    "l": min(b["l"] for b in g), "c": g[-1]["c"], "v": sum(b["v"] for b in g),
                    "n5": len(g), "complete": len(g) == 3 and not any(b.get("partial") for b in g),
                    "src": srcs[0] if len(srcs) == 1 else "+".join(srcs)})
    return out


def baselines(by_day: dict[str, list[dict]], date: str, *, minutes: int = 5, lookback: int = LOOKBACK):
    """Per-slot mean bar volume and mean cumulative volume over the prior full sessions."""
    prior = [d for d in sorted(by_day) if d < date and len(by_day[d]) >= FULL_SESSION_MIN][-lookback:]
    nslots = SLOTS_5M if minutes == 5 else SLOTS_5M // 3
    slot_v = [[] for _ in range(nslots)]
    cum_v = [[] for _ in range(nslots)]
    for d in prior:
        bars = by_day[d] if minutes == 5 else agg15(by_day[d])
        vol = {b["slot"]: b["v"] for b in bars}
        run = 0
        for s in range(nslots):
            if s in vol:
                slot_v[s].append(vol[s])
            run += vol.get(s, 0)
            if s <= max(vol or [-1]):
                cum_v[s].append(run)
    mean = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
    return prior, [mean(x) for x in slot_v], [mean(x) for x in cum_v]


def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    return round(x, n) if x is not None else None


def session_view(sym: str, by_day: dict[str, list[dict]], date: str, now: Optional[float] = None) -> dict:
    day = by_day.get(date) or []
    prior, slot5, cum5 = baselines(by_day, date, minutes=5)
    _, slot15, cum15 = baselines(by_day, date, minutes=15)
    now = time.time() if now is None else now
    rows5, run = [], 0
    for b in day:
        end = _utc(b["t"]) + timedelta(minutes=5)
        run += b["v"]
        base = slot5[b["slot"]] if b["slot"] < len(slot5) else None
        cbase = cum5[b["slot"]] if b["slot"] < len(cum5) else None
        rows5.append({**{k: b[k] for k in ("t", "o", "h", "l", "c", "v", "src")},
                      "et": slot_label(b["slot"]), "pt": pt_label(_utc(b["t"])), "slot": b["slot"],
                      "avg_v": _r(base, 0), "bar_rvol": _r(b["v"] / base if base else None),
                      "cum_v": run, "cum_rvol": _r(run / cbase if cbase else None),
                      "partial": end.timestamp() > now})
    rows15, run = [], 0
    for b in agg15(day):
        run += b["v"]
        base = slot15[b["slot"]] if b["slot"] < len(slot15) else None
        cbase = cum15[b["slot"]] if b["slot"] < len(cum15) else None
        end = _utc(b["t"]) + timedelta(minutes=15)
        rows15.append({**{k: b[k] for k in ("t", "o", "h", "l", "c", "v", "src", "complete")},
                       "et": slot_label(b["slot"], 15), "pt": pt_label(_utc(b["t"])), "slot": b["slot"],
                       "avg_v": _r(base, 0), "bar_rvol": _r(b["v"] / base if base else None),
                       "cum_v": run, "cum_rvol": _r(run / cbase if cbase else None),
                       "partial": end.timestamp() > now or not b["complete"]})
    last = rows5[-1] if rows5 else None
    srcs = sorted({r["src"] for r in rows5})
    newest = _utc(last["t"]) + timedelta(minutes=5) if last else None
    recent = rows5[-6:]
    recent_base = [slot5[r["slot"]] for r in recent if r["slot"] < len(slot5) and slot5[r["slot"]]]
    return {
        "symbol": sym, "session_date": date, "prior_sessions": len(prior),
        "prior_range": [prior[0], prior[-1]] if prior else None,
        "source": srcs[0] if len(srcs) == 1 else ("+".join(srcs) if srcs else None),
        "bars_5m": len(rows5), "last_bar_et": last and last["et"], "last_bar_pt": last and last["pt"],
        "last_close": last and last["c"], "session_volume": rows5[-1]["cum_v"] if rows5 else 0,
        "session_rvol": last and last["cum_rvol"], "last_bar_rvol": last and last["bar_rvol"],
        "recent30_rvol": _r(sum(r["v"] for r in recent) / sum(recent_base)) if recent and len(recent_base) == len(recent) else None,
        "newest_bar_end_pt": newest and newest.astimezone(PT).strftime("%Y-%m-%d %-I:%M %p PT"),
        "newest_bar_end_epoch": newest and newest.timestamp(),
        "bars5": rows5, "bars15": rows15,
    }


def label_rvol(x: Optional[float]) -> Optional[str]:
    if x is None:
        return None
    return "LIGHT" if x < 0.7 else ("INLINE" if x <= 1.3 else "HEAVY")


# ------------------------------------------------------------------ outputs
def build(symbols: Optional[list[str]] = None, *, now: Optional[float] = None, date: Optional[str] = None,
          mini_status: Optional[dict] = None) -> dict:
    now = time.time() if now is None else now
    syms = symbols or sorted(p.name[:-8] for p in (BARS_DIR / "store").glob("*-5m.json"))
    sess = mc.current_session(datetime.fromtimestamp(now, ET))
    summary: dict[str, Any] = {}
    for sym in syms:
        by_day = sessions(load_store(sym))
        if not by_day:
            continue
        d = date or max(by_day)
        v = session_view(sym, by_day, d, now)
        stale = None
        if sess == "rth" and v["newest_bar_end_epoch"]:
            stale = (now - v["newest_bar_end_epoch"]) > STALE_RTH_S or d != datetime.fromtimestamp(now, ET).strftime("%Y-%m-%d")
        head = {k: v[k] for k in v if k not in ("bars5", "bars15")}
        head.update({"rvol_label": label_rvol(v["session_rvol"]), "stale": stale})
        common = {"generated_pt": mc._pt_stamp(now), "writer": "quotes/mini_bars.py",
                  "mandate": "research/paper only - not an order", "lookback_sessions": LOOKBACK,
                  "rvol_def": "bar_rvol = bar volume / mean same-slot volume (prior full RTH sessions); "
                              "cum_rvol = session cumulative volume / mean same-time cumulative"}
        atomic_write_json(BARS_DIR / f"{sym}-5m.json", {**common, **head, "interval": "5m", "bars": v["bars5"]})
        atomic_write_json(BARS_DIR / f"{sym}-15m.json", {**common, **head, "interval": "15m", "bars": v["bars15"]})
        last15 = next((b for b in reversed(v["bars15"]) if not b["partial"]), None)
        summary[sym] = {**head, "last5": v["bars5"][-1] if v["bars5"] else None, "last15_complete": last15}
    rec = {"generated_pt": mc._pt_stamp(now), "generated_epoch": round(now, 1), "session": sess,
           "writer": "quotes/mini_bars.py", "primary": "Alpaca SIP 5-min bars via Mac mini /v1/bars",
           "fallback": "Robinhood get_equity_historicals 5minute (agent-ingested)",
           "mini": mini_status, "symbols": summary,
           "mandate": "research/paper only - not an order"}
    atomic_write_json(BARS_DIR / "summary.json", rec)
    return rec


def refresh(symbols: Optional[list[str]] = None, *, days: int = 32, now: Optional[float] = None, opener=None) -> dict:
    """Incremental mini pull (from each name's newest stored SIP bar, else ``days`` back) -> outputs."""
    now = time.time() if now is None else now
    syms = [s.upper() for s in (symbols or universe())]
    end = datetime.fromtimestamp(now, timezone.utc)
    starts = []
    for s in syms:
        st = load_store(s)
        sip = [b["t"] for b in st.values() if b.get("src") == MINI_SRC]
        starts.append(_utc(max(sip)) - timedelta(minutes=10) if sip else end - timedelta(days=days))
    start = min(starts) if starts else end - timedelta(days=days)
    status: dict[str, Any] = {"ok": False, "start": _iso(start), "end": _iso(end), "at_pt": mc._pt_stamp(now)}
    try:
        got = fetch_mini_bars(syms, start, end, opener=opener)
        n = 0
        for s, rows in got.items():
            a, _r2 = merge(s, rows)
            n += len(rows)
        status.update(ok=True, bars=n, symbols=len(got))
    except mc.MiniError as e:
        status["error"] = str(e)
        status["fallback"] = "using stored bars (RH-ingested where present); agent should pull RH 5minute if stale"
    return build(None, now=now, mini_status=status)


def ingest_rh(paths: list[str]) -> dict:
    tot: dict[str, int] = {}
    for p in paths:
        for sym, rows in parse_rh_payload(Path(p).read_text(encoding="utf-8")).items():
            a, r = merge(sym, rows)
            tot[sym] = tot.get(sym, 0) + len(rows)
    return tot


# ------------------------------------------------------------------ wall-break helper
def confirm_break(sym: str, level: float, *, date: Optional[str] = None, direction: str = "auto",
                  rvol_min: float = RVOL_BREAK_MIN, now: Optional[float] = None) -> dict:
    """Wall-break confirmation on 5m/15m bars: (1) 5m close through ``level``, (2) the next completed
    15m bar (starting at/after the break bar's end) closes beyond the level = hold, (3) break-bar RVOL
    >= rvol_min. Checks every crossing of the session; reports the first confirmed one (else the latest)."""
    sym = sym.upper()
    by_day = sessions(load_store(sym))
    if not by_day:
        return {"symbol": sym, "level": level, "verdict": "NO_BARS"}
    d = date or max(by_day)
    v = session_view(sym, by_day, d, now)
    b5, b15 = v["bars5"], v["bars15"]
    prev_c = None
    if b5:  # prior session's close as the reference for a break on the first bar
        prior = [x for x in sorted(by_day) if x < d]
        prev_c = by_day[prior[-1]][-1]["c"] if prior else None
    tries = []
    for i, b in enumerate(b5):
        pc = b5[i - 1]["c"] if i else prev_c
        if pc is None:
            continue
        up, dn = pc <= level < b["c"], pc >= level > b["c"]
        if not (up or dn) or (direction == "up" and not up) or (direction == "down" and not dn):
            continue
        side = "up" if up else "down"
        beyond = (lambda x: x > level) if up else (lambda x: x < level)
        end = _utc(b["t"]) + timedelta(minutes=5)
        f15 = next((x for x in b15 if _utc(x["t"]) >= end), None)
        hold = None if (f15 is None or f15["partial"]) else beyond(f15["c"])
        nxt = b5[i + 1:i + 3]
        vol_ok = b["bar_rvol"] is not None and b["bar_rvol"] >= rvol_min
        verdict = ("CONFIRMED" if (hold and vol_ok) else
                   "PENDING_HOLD" if hold is None and vol_ok else
                   "FAILED_HOLD" if hold is False else "LIGHT_VOLUME")
        if hold is None and not vol_ok:
            verdict = "PENDING_HOLD_LIGHT_VOLUME"
        tries.append({
            "direction": side, "break_bar_et": b["et"], "break_bar_pt": b["pt"], "prev_close": pc,
            "break_close": b["c"], "break_volume": b["v"], "break_bar_rvol": b["bar_rvol"],
            "volume_ok": vol_ok, "cum_rvol_at_break": b["cum_rvol"],
            "follow_15m": f15 and {k: f15[k] for k in ("et", "pt", "o", "h", "l", "c", "v", "bar_rvol", "partial")},
            "hold_15m": hold, "next_5m_closes": [x["c"] for x in nxt],
            "next_5m_held": all(beyond(x["c"]) for x in nxt) if nxt else None,
            "src": b["src"], "verdict": verdict,
        })
    best = next((t for t in tries if t["verdict"] == "CONFIRMED"), tries[-1] if tries else None)
    return {"symbol": sym, "level": level, "session_date": d, "rule": f"5m close through + next 15m close holds + break-bar RVOL >= {rvol_min}",
            "verdict": best["verdict"] if best else "NO_BREAK", "result": best, "crossings": tries,
            "session_rvol": v["session_rvol"], "source": v["source"], "prior_sessions": v["prior_sessions"],
            "mandate": "research/paper only - not an order"}


def summary_for(sym: str, max_age_s: float = 900) -> Optional[dict]:
    """Slim per-symbol RVOL read for focus_watch (file-only; None when missing/old)."""
    rec = read_json(BARS_DIR / "summary.json") or {}
    if time.time() - float(rec.get("generated_epoch") or 0) > max_age_s:
        return None
    s = (rec.get("symbols") or {}).get(sym)
    if not s:
        return None
    l5 = s.get("last5") or {}
    return {"session_date": s.get("session_date"), "source": s.get("source"), "session_rvol": s.get("session_rvol"),
            "rvol_label": s.get("rvol_label"), "recent30_rvol": s.get("recent30_rvol"),
            "last5_et": l5.get("et"), "last5_close": l5.get("c"), "last5_rvol": l5.get("bar_rvol"), "stale": s.get("stale")}


# ------------------------------------------------------------------ loop (scripts/bars-poller.sh)
def loop(interval_s: float = 60.0) -> int:
    """RTH/PRE/AH: refresh every ``interval_s`` (5m bars close every 300 s; 60 s keeps lag < 1 min).
    CLOSED: idle check every 5 min. Writes cache/bars/bars-poller.pid; logs to cache/bars/bars-poller.log."""
    import signal
    stop = {"v": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(v=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(v=True))
    pid = BARS_DIR / "bars-poller.pid"
    logp = BARS_DIR / "bars-poller.log"
    BARS_DIR.mkdir(parents=True, exist_ok=True)
    pid.write_text(str(os.getpid()))

    def log(msg: str) -> None:
        try:
            if logp.exists() and logp.stat().st_size > 2_000_000:
                logp.replace(logp.with_suffix(".log.1"))
            with logp.open("a", encoding="utf-8") as fh:
                fh.write(f"{mc._pt_stamp()} {msg}\n")
        except OSError:
            pass

    log(f"bars-poller start pid={os.getpid()} interval={interval_s}s")
    last_err = None
    try:
        while not stop["v"]:
            sess = mc.current_session()
            wait = interval_s if sess in ("rth", "pre", "ah") else 300.0
            if sess == "rth" or (sess in ("pre", "ah") and int(time.time()) % 900 < interval_s):
                try:
                    rec = refresh()
                    m = rec.get("mini") or {}
                    if m.get("ok"):
                        if last_err:
                            log("mini bars recovered")
                        last_err = None
                    elif m.get("error") != last_err:
                        last_err = m.get("error")
                        log(f"mini bars FAIL: {last_err} -> stored/RH bars, tagged per row")
                except Exception as e:  # never die
                    log(f"refresh error {type(e).__name__}: {str(e)[:160]}")
            end = time.time() + wait
            while not stop["v"] and time.time() < end:
                time.sleep(1)
    finally:
        log("bars-poller stop")
        try:
            pid.unlink()
        except OSError:
            pass
    return 0


# ------------------------------------------------------------------ CLI
def _main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID 5m/15m bars + RVOL (research only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh"); r.add_argument("--symbols", default=""); r.add_argument("--days", type=int, default=32)
    i = sub.add_parser("ingest-rh"); i.add_argument("files", nargs="+")
    b = sub.add_parser("build"); b.add_argument("--date")
    k = sub.add_parser("break"); k.add_argument("symbol"); k.add_argument("level", type=float)
    k.add_argument("--date"); k.add_argument("--dir", default="auto", choices=["auto", "up", "down"])
    k.add_argument("--rvol", type=float, default=RVOL_BREAK_MIN); k.add_argument("--json", action="store_true")
    sub.add_parser("status")
    lp = sub.add_parser("loop"); lp.add_argument("--interval", type=float, default=60.0)
    a = ap.parse_args(argv)
    if a.cmd == "refresh":
        syms = [s for s in a.symbols.split(",") if s.strip()] or None
        rec = refresh(syms, days=a.days)
        print(json.dumps({"mini": rec["mini"], "symbols": len(rec["symbols"])}, indent=1))
        return 0 if rec["mini"].get("ok") else 2
    if a.cmd == "ingest-rh":
        print(json.dumps(ingest_rh(a.files)))
        build()
        return 0
    if a.cmd == "build":
        rec = build(date=a.date)
        print(f"built {len(rec['symbols'])} symbols -> {BARS_DIR}")
        return 0
    if a.cmd == "break":
        res = confirm_break(a.symbol, a.level, date=a.date, direction=a.dir, rvol_min=a.rvol)
        if a.json:
            print(json.dumps(res, indent=1))
        else:
            print(f"{res['symbol']} {res['level']} {res.get('session_date')}: {res['verdict']} ({res.get('rule')})")
            for t in res.get("crossings") or []:
                f = t["follow_15m"] or {}
                print(f"  {t['direction']:>4} {t['break_bar_et']} ET close {t['break_close']} (prev {t['prev_close']}) "
                      f"vol {t['break_volume']:,} rvol {t['break_bar_rvol']} | 15m {f.get('et')} close {f.get('c')} "
                      f"hold={t['hold_15m']} | next5 {t['next_5m_closes']} -> {t['verdict']} [{t['src']}]")
        return 0
    if a.cmd == "loop":
        return loop(a.interval)
    rec = read_json(BARS_DIR / "summary.json") or {}
    print(json.dumps({"generated_pt": rec.get("generated_pt"), "mini": rec.get("mini"),
                      "symbols": {s: {k: v.get(k) for k in ("session_date", "source", "session_rvol", "rvol_label",
                                                             "last_bar_et", "stale")}
                                  for s, v in (rec.get("symbols") or {}).items()}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
