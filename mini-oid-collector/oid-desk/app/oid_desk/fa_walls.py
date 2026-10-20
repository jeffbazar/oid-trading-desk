"""OID mini walls writer (com.oid.desk.fa-walls, 2026-10-20). Research / paper only - ZERO execution.

Every 10 min, 6:30 AM-1:00 PM PT weekdays (launchd StartInterval 600 + time gate here), pulls
GET https://lab.flashalpha.com/v1/flow/levels/{SYM} (live_call_wall / live_put_wall / live_gamma_flip / live_max_pain)
for the private live page's tickers (minus WDC, STX, SNDK) and atomically writes
~/oid-live-page/data/fa-walls-pulse.json in the shape livepage.py already reads ({SYM: {symbol, underlying_price,
as_of, levels{...}, freshness, oi_feed}}). Replaces the old manual copy of the box's tmp/fa-walls-last.json.

Budget (shared Growth account, 2,500/day, resets 00:00 UTC = 5 PM PT):
  * CORE names refresh every run (10 min); the rest ROTATE in groups so each refreshes every ROT_GROUPS x 10 min.
    ~19 core x 39 runs + ~39 others / 4 groups x 39 runs = ~1,130 calls/day.
  * /v1/account checked first each run: remaining < CORE_ONLY_BELOW -> core only; < PAUSE_BELOW -> skip run
    (keeps futures-live's 300 guard and vix-live fed). Per-record stale_after_s tells the page when to tag STALE.
WIDE / Sector watch (2026-10-20, Jeffrey approved): after core + rotation, walls for SURGING wide names only
(page state.json "wide.surging": 1-min rvol >= 3x or a +/-3% move), written to ~/oid-live-page/data/fa-walls-wide.json.
  * only when this run is core+rotation AND FlashAlpha remaining >= WIDE_MIN_REMAINING (800; well above the 500/380/300 guards)
  * at most WIDE_MAX_PER_RUN (3) per 10-min run, WIDE_MAX_PER_DAY (30) per quota day, one refresh per name per hour
  => worst case 30 calls/day (1.2% of the 2,500/day account). Wide names never enter the core/rotation list.
FLASHALPHA_API_KEY comes from run-job.sh env (or the secrets file) and is only sent as X-Api-Key; never logged.
Per-strike weights stay in livepage.py (Alpaca OI/volume -> data/wall-weights.json); untouched here.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from oid_desk import util

JOB = "fa-walls"
PT = ZoneInfo("America/Los_Angeles")
HOME = Path.home()
OUT = Path(os.environ.get("OID_FA_WALLS_OUT", str(HOME / "oid-live-page/data/fa-walls-pulse.json")))
STATE = Path(os.environ.get("OID_FA_WALLS_STATE", str(HOME / "oid-desk/state/fa-walls/state.json")))
PAGE = os.environ.get("OID_FA_WALLS_PAGE", "http://127.0.0.1:8791/state.json")
BASE = "https://lab.flashalpha.com"
AVOID = {"WDC", "STX", "SNDK"}
CORE = ["SPY", "QQQ", "NVDA", "TSLA", "PLTR", "GOOGL", "NFLX", "META", "AMZN", "AMD", "CBRS", "BE", "NBIS",
        "IREN", "CRWV", "MU", "SPCX", "INTC", "MRVL"]
ROT_GROUPS = int(os.environ.get("OID_FA_WALLS_ROT_GROUPS", "4"))
INTERVAL_S = 600
CORE_STALE_S = 20 * 60
ROT_STALE_S = ROT_GROUPS * INTERVAL_S + 10 * 60
CORE_ONLY_BELOW = int(os.environ.get("OID_FA_WALLS_CORE_ONLY_BELOW", "500"))
PAUSE_BELOW = int(os.environ.get("OID_FA_WALLS_PAUSE_BELOW", "380"))
GAP_S = 0.3
WIDE_OUT = Path(os.environ.get("OID_FA_WALLS_WIDE_OUT", str(HOME / "oid-live-page/data/fa-walls-wide.json")))
WIDE_MIN_REMAINING = int(os.environ.get("OID_FA_WALLS_WIDE_MIN_REMAINING", "800"))
WIDE_MAX_PER_RUN = int(os.environ.get("OID_FA_WALLS_WIDE_MAX_PER_RUN", "3"))
WIDE_MAX_PER_DAY = int(os.environ.get("OID_FA_WALLS_WIDE_MAX_PER_DAY", "30"))
WIDE_REFETCH_S = 3600
WIDE_STALE_S = 3600


def _key() -> str:
    k = util.read_secret("FLASHALPHA_API_KEY")
    if not k:
        raise RuntimeError("FLASHALPHA_API_KEY missing")
    return k.strip()


def _get(path: str, key: str, timeout: float = 12):
    req = urllib.request.Request(BASE + path, headers={"X-Api-Key": key, "Accept": "application/json",
                                                       "User-Agent": "oid-mini-walls/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rem = r.headers.get("X-RateLimit-Remaining")
        return json.load(r), (int(rem) if rem and rem.isdigit() else None)


def _read(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n")
    tmp.replace(p)


def in_window(now: float) -> bool:
    d = datetime.fromtimestamp(now, PT)
    m = d.hour * 60 + d.minute
    return d.weekday() < 5 and 6 * 60 + 30 <= m <= 13 * 60


def page_symbols(prev: list[str]) -> list[str]:
    try:
        with urllib.request.urlopen(PAGE, timeout=5) as r:
            rows = json.load(r).get("rows") or []
        syms = [x.get("symbol") or x.get("sym") for x in rows if (x.get("symbol") or x.get("sym")) and x.get("kind") != "ext"]
        if syms:
            return sorted(set(syms))
    except Exception:
        pass
    return prev or CORE  # page down: last good list from state (never overwritten by this fallback)


def wide_candidates() -> list[str]:
    """Surging wide names from the live page, strongest first (surge by rvol, then movers by |% change|)."""
    try:
        with urllib.request.urlopen(PAGE, timeout=5) as r:
            w = json.load(r).get("wide") or {}
    except Exception:
        return []
    rows = [x for g in (w.get("groups") or []) for x in (g.get("rows") or [])]
    if (w.get("session") or "") != "RTH":
        return []
    sg = sorted((x for x in rows if x.get("sg")), key=lambda x: -(x.get("r") or 0))
    mv = sorted((x for x in rows if x.get("mv") and not x.get("sg")), key=lambda x: -abs(x.get("c") or 0))
    out = []
    for x in sg + mv:
        s = x.get("s")
        if s and s not in AVOID and s not in out:
            out.append(s)
    return out


def run_wide(key: str, st: dict, remaining, mode: str, core_syms: set) -> dict:
    """WIDE walls on surge (capped). Returns a small status dict; never raises."""
    info = {"fetched": 0, "skipped": None}
    if mode != "core+rotation":
        info["skipped"] = f"mode {mode}"
        return info
    if remaining is None or remaining < WIDE_MIN_REMAINING:
        info["skipped"] = f"remaining {remaining} < {WIDE_MIN_REMAINING}"
        return info
    used = int(st.get("wide_calls_today", 0))
    if used >= WIDE_MAX_PER_DAY:
        info["skipped"] = f"daily cap {WIDE_MAX_PER_DAY} reached"
        return info
    now = time.time()
    last = {k: v for k, v in (st.get("wide_last") or {}).items() if now - float(v) < 86400}
    cands = [s for s in wide_candidates() if s not in core_syms and now - float(last.get(s, 0)) >= WIDE_REFETCH_S]
    todo = cands[: max(0, min(WIDE_MAX_PER_RUN, WIDE_MAX_PER_DAY - used))]
    if not todo:
        info["skipped"] = "no surging wide names due"
        st["wide_last"] = last
        return info
    data = _read(WIDE_OUT, {})
    if not isinstance(data, dict):
        data = {}
    for s in [k for k, v in data.items() if isinstance(v, dict) and k[:1].isupper() and now - float(v.get("_fetched_epoch") or 0) > 86400]:
        data.pop(s, None)
    errs = {}
    for sym in todo:
        try:
            d, rem = _get(f"/v1/flow/levels/{sym}", key)
            if rem is not None:
                remaining = rem
            if d.get("live_call_wall") is None and d.get("live_put_wall") is None and d.get("live_gamma_flip") is None:
                errs[sym] = "no levels"
            else:
                r = rec(sym, d, WIDE_STALE_S)
                r.update(cadence="on surge (wide, <=1/h)", _fetched_epoch=round(time.time()), writer="mini:oid_desk.fa_walls wide")
                data[sym] = r
                info["fetched"] += 1
        except Exception as e:
            errs[sym] = getattr(e, "code", None) or type(e).__name__
        st["wide_calls_today"] = int(st.get("wide_calls_today", 0)) + 1
        st["calls_today"] = st.get("calls_today", 0) + 1
        last[sym] = round(time.time())
        time.sleep(GAP_S)
    data["_meta"] = {"as_of_pt": util.now_pt_str(), "writer": "mini:oid_desk.fa_walls wide (com.oid.desk.fa-walls)",
                     "source": "FlashAlpha REST /v1/flow/levels (Growth key)", "trigger": "wide surge rvol_1m>=3 or +/-3% move",
                     "caps": {"per_run": WIDE_MAX_PER_RUN, "per_day": WIDE_MAX_PER_DAY, "min_remaining": WIDE_MIN_REMAINING, "per_name_s": WIDE_REFETCH_S},
                     "wide_calls_today": st["wide_calls_today"], "errors": errs, "fa_remaining": remaining}
    _write(WIDE_OUT, data)
    st["wide_last"] = last
    info.update(errors=errs, remaining=remaining, syms=todo)
    return info


def _iso(v) -> str | None:
    if not v:
        return None
    s = str(v)
    try:
        return datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return s


def rec(sym: str, d: dict, stale_s: int) -> dict:
    return {"symbol": sym, "underlying_price": d.get("underlying_price"), "as_of": _iso(d.get("as_of")),
            "levels": {"gamma_flip": d.get("live_gamma_flip"), "gamma_flip_status": d.get("gamma_flip_status"),
                       "call_wall": d.get("live_call_wall"), "put_wall": d.get("live_put_wall"),
                       "max_pain": d.get("live_max_pain")},
            "freshness": "FRESH", "oi_feed": "get_flow_levels",
            "oi_as_of": (d.get("data_as_of") or {}).get("oi_feed"), "stale_after_s": stale_s,
            "cadence": "10 min" if stale_s == CORE_STALE_S else f"{ROT_GROUPS * 10} min (rotated)",
            "writer": "mini:oid_desk.fa_walls"}


def run(force: bool = False) -> int:
    now = time.time()
    st = _read(STATE, {})
    qday = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    if st.get("day") != qday:
        st.update(day=qday, calls_today=0, errors_today=0, wide_calls_today=0)
    if not force and not in_window(now):
        print(json.dumps({"skipped": "outside 6:30 AM-1:00 PM PT weekdays"}))
        return 0
    key = _key()
    syms = [s for s in page_symbols(st.get("symbols") or []) if s not in AVOID]
    if len(syms) > len(CORE):
        st["symbols"] = syms
    core = list(CORE)
    others = sorted(s for s in syms if s not in core)
    rot = int(st.get("rot", 0)) % ROT_GROUPS
    group = others[rot::ROT_GROUPS]
    try:
        acct, _ = _get("/v1/account", key)
        remaining = int(acct.get("remaining") or 0)
    except Exception as e:
        remaining = st.get("remaining")
        util.log(JOB, f"account check failed ({type(e).__name__}); using last remaining {remaining}")
    mode = "core+rotation"
    if remaining is not None and remaining < PAUSE_BELOW:
        util.log(JOB, f"GUARD: FlashAlpha remaining {remaining} < {PAUSE_BELOW}; skipping run")
        st.update(remaining=remaining, mode="paused_quota", last_run_pt=util.now_pt_str(now))
        _write(STATE, st)
        return 0
    if remaining is not None and remaining < CORE_ONLY_BELOW:
        mode, group = "core_only_quota", []
    data = _read(OUT, {})
    if not isinstance(data, dict) or "SPY" not in data:
        data = {}
    for s in list(data):
        if s in AVOID or (s[:1].isupper() and s not in syms and s not in core):
            data.pop(s, None)
    ok, errs = 0, {}
    for sym in core + group:
        try:
            d, rem = _get(f"/v1/flow/levels/{sym}", key)
            st["calls_today"] = st.get("calls_today", 0) + 1
            if rem is not None:
                remaining = rem
            if d.get("live_call_wall") is None and d.get("live_put_wall") is None and d.get("live_gamma_flip") is None:
                errs[sym] = "no levels"
            else:
                data[sym] = rec(sym, d, CORE_STALE_S if sym in core else ROT_STALE_S)
                ok += 1
        except Exception as e:
            st["calls_today"] = st.get("calls_today", 0) + 1
            st["errors_today"] = st.get("errors_today", 0) + 1
            errs[sym] = getattr(e, "code", None) or type(e).__name__
        time.sleep(GAP_S)
    data["_meta"] = {"as_of_pt": util.now_pt_str(), "writer": "mini:oid_desk.fa_walls (com.oid.desk.fa-walls)",
                     "source": "FlashAlpha REST /v1/flow/levels (Growth key)", "mode": mode,
                     "core_every": "10 min", "rotated_every": f"{ROT_GROUPS * 10} min", "rot_group": rot,
                     "fetched": ok, "errors": errs, "fa_remaining": remaining}
    _write(OUT, data)
    try:  # WIDE: walls for surging sector-watch names (capped; never touches OUT)
        winfo = run_wide(key, st, remaining, mode, set(core) | set(syms))
        if winfo.get("remaining") is not None:
            remaining = winfo["remaining"]
    except Exception as e:  # noqa: BLE001
        winfo = {"fetched": 0, "skipped": f"error {type(e).__name__}"}
    st["wide_last_run"] = {k: v for k, v in winfo.items() if k != "remaining"}
    st.update(rot=(rot + 1) % ROT_GROUPS, remaining=remaining, mode=mode, last_run_pt=util.now_pt_str(now),
              last_errors=errs)
    _write(STATE, st)
    msg = (f"{mode}: {ok} ok / {len(core) + len(group)} (core {len(core)}, rot group {rot} {len(group)}) rem={remaining} calls_today={st['calls_today']}"
           f" wide={winfo.get('fetched', 0)} ({winfo.get('skipped') or ','.join(winfo.get('syms') or [])}; {st.get('wide_calls_today', 0)}/{WIDE_MAX_PER_DAY} today)")
    util.log(JOB, msg + (f" errors={errs}" if errs else ""))
    print(json.dumps({"ok": ok, "errors": errs, "mode": mode, "remaining": remaining}))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(force="--force" in sys.argv))
