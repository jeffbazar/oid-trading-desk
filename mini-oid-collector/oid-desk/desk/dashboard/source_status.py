#!/usr/bin/env python3
"""OID data-source status checker (Jeffrey 2026-10-10). Research / paper only - zero execution.

Turns the 10/10 data-sources chart (docs/data-source-chart-20261010.*) into an automatic check.
Rows + signals live in config/source-status.json (edit there when fixes land). Each row is
evaluated from real signals: feed-file timestamps (as_of / written_epoch / heartbeat, else mtime)
vs TTL, running processes (pgrep -f), Mac mini reachability (mini-quotes / mini-option-quotes
health block) and FlashAlpha Growth quota (cache/fa-focus-refresh-state.json).

Session aware (paper-trades/market_session.py): TTLs apply in RTH; pre-market, after-hours,
overnight and weekends accept the last-session carry (a write at/after the prior close) and
never alarm on it. Daemon heartbeats ("always") are checked at any hour.

Output: market-data/latest/source-status.json (+ cache/source-status-state.json for the
"was Live before" memory that turns a known gap into a regression alarm).
Never contains quotes (no OPRA / equity prices) - ages, counts and status only.

CLI:
  source_status.py                 compute + write, print summary
  source_status.py --json          compute + write, print full JSON
  source_status.py --if-due        recompute only if due (5 min RTH, hourly otherwise)
  source_status.py --if-due --publish-on-change
                                   watchdog mode: also publish the blotter when the alarm
                                   changes, or in RTH when the published snapshot is >15 min
                                   old (routines stalled). Uses dashboard/publish.sh (lock-safe).
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone, time as dtime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "paper-trades"))
from market_session import ET, NYSE_HOLIDAYS, EARLY_CLOSE, market_session, prior_rth_close  # noqa: E402

PT = ZoneInfo("America/Los_Angeles")
CONFIG = ROOT / "config" / "source-status.json"
OUT = ROOT / "market-data" / "latest" / "source-status.json"
STATE = ROOT / "cache" / "source-status-state.json"
LOCK = ROOT / "cache" / "source-status.lock"
LOG = ROOT / "cache" / "source-status.log"
DUE_RTH_S = 300
DUE_OFF_S = 3600
STALE_PUBLISH_RTH_S = 15 * 60

TONE = {"Live": "live", "Stale-risk": "risk", "Stale": "stale", "Down": "down",
        "Missing": "missing", "Needs purchase": "purchase"}


# ------------------------------------------------------------------ time helpers
def _pt(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, PT).strftime("%a %m/%d %-I:%M %p PT")


def _session(now: datetime) -> str:
    s = market_session(now)
    if s == "closed":
        try:
            sys.path.insert(0, str(ROOT / "quotes"))
            from mini_client import overnight_active  # type: ignore
            if overnight_active(now):
                return "overnight"
        except Exception:  # noqa: BLE001
            pass
    return s


def _is_trading(d) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def _rth_open_today(now: datetime) -> Optional[datetime]:
    et = now.astimezone(ET)
    if not _is_trading(et.date()):
        return None
    return datetime.combine(et.date(), dtime(9, 30), tzinfo=ET)


def _expected_daily_date(now: datetime, due_et: str, max_sessions: int):
    """Oldest ET trading date a daily feed may carry and still be OK."""
    hh, mm = (int(x) for x in due_et.split(":"))
    et = now.astimezone(ET)
    d = et.date()
    # latest trading day whose due time has passed
    for _ in range(30):
        if _is_trading(d) and et >= datetime.combine(d, dtime(hh, mm), tzinfo=ET):
            break
        d -= timedelta(days=1)
        et = datetime.combine(d, dtime(23, 59), tzinfo=ET)
    n = 1
    while n < max(1, max_sessions):
        d -= timedelta(days=1)
        while not _is_trading(d):
            d -= timedelta(days=1)
        n += 1
    return d


# ------------------------------------------------------------------ signal readers
def _parse_iso(s: Any) -> Optional[float]:
    if not isinstance(s, str) or not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _file_ts(path: Path) -> tuple[Optional[float], Optional[dict]]:
    """Best timestamp for a feed file: explicit epoch/ISO fields, else mtime."""
    data = None
    ts = None
    if path.suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
    if isinstance(data, dict):
        for k in ("written_epoch", "heartbeat_epoch", "generated_epoch"):
            v = data.get(k)
            if isinstance(v, (int, float)) and v > 1e9:
                ts = float(v)
                break
        if ts is None:
            for k in ("as_of_iso", "as_of"):
                ts = _parse_iso(data.get(k))
                if ts:
                    break
    if ts is None:
        try:
            ts = path.stat().st_mtime
        except OSError:
            ts = None
    return ts, data if isinstance(data, dict) else None


def _resolve(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else ROOT / q


_PS_CACHE: Optional[str] = None


def _ps() -> str:
    global _PS_CACHE
    if _PS_CACHE is None:
        try:
            _PS_CACHE = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=10).stdout
        except Exception:  # noqa: BLE001
            _PS_CACHE = ""
    return _PS_CACHE


def _proc_running(pattern: str) -> bool:
    me = str(os.getpid())
    for line in _ps().splitlines():
        if pattern in line and "source_status.py" not in line and "pgrep" not in line:
            return True
    return False


def _rel(p: Path) -> str:
    s = str(p)
    for pre in (str(ROOT) + "/", "/workspace/"):
        if s.startswith(pre):
            return s[len(pre):]
    return s


def eval_signal(sig: dict, now: datetime, session: str) -> dict:
    now_ts = now.timestamp()
    out: dict = {"label": sig.get("label"), "required": sig.get("required", True)}
    if "proc" in sig:
        ok = _proc_running(sig["proc"])
        out.update(state="ok" if ok else "down", detail="process running" if ok else "process not running")
        return out
    if "exists" in sig:
        p = _resolve(sig["exists"])
        ok = p.exists()
        ts = p.stat().st_mtime if ok else None
        out.update(state="ok" if ok else "absent", ts=ts, ts_pt=_pt(ts),
                   age_s=round(now_ts - ts) if ts else None, detail="present" if ok else "not found")
        return out
    if "glob" in sig:
        pat = sig["glob"] if sig["glob"].startswith("/") else str(ROOT / sig["glob"])
        cands = sorted(glob.glob(pat), key=lambda x: os.path.getmtime(x))
        path = Path(cands[-1]) if cands else None
    else:
        path = _resolve(sig["path"])
    if path is None or not path.exists():
        out.update(state="absent", detail="no file yet")
        return out
    ts, data = _file_ts(path)
    out["file"] = _rel(path)
    if ts is None:
        out.update(state="absent", detail="unreadable")
        return out
    age = now_ts - ts
    out.update(ts=ts, ts_pt=_pt(ts), age_s=round(age))
    if isinstance(data, dict) and data.get("error"):
        out["writer_error"] = str(data.get("error"))[:160]
    cad = sig.get("cadence", "intraday")
    ttl = float(sig.get("ttl_s") or 600)
    if cad == "always":
        st = "ok" if age <= ttl else ("stale" if age <= 5 * ttl else "down")
        out.update(state=st, detail=f"heartbeat {_age_txt(age)} old (limit {_age_txt(ttl)})")
        return out
    if cad == "daily":
        exp = _expected_daily_date(now, sig.get("due_et", "17:00"), int(sig.get("max_sessions") or 1))
        got = datetime.fromtimestamp(ts, ET).date()
        st = "ok" if got >= exp else "stale"
        out.update(state=st, detail=f"last write {got.isoformat()} (need ≥ {exp.isoformat()})")
        return out
    # intraday
    prior_close = prior_rth_close(now).timestamp()
    carry_ok = ts >= prior_close - max(2 * ttl, 900)
    opened = _rth_open_today(now)
    if session == "rth":
        if age <= ttl:
            out.update(state="ok", detail=f"{_age_txt(age)} old (TTL {_age_txt(ttl)})")
        elif opened and (now - opened).total_seconds() < max(ttl, 900) and carry_ok:
            out.update(state="ok", detail="first minutes of RTH · prior-close carry", carry=True)
        elif age <= 4 * ttl:
            out.update(state="stale", detail=f"{_age_txt(age)} old (TTL {_age_txt(ttl)})")
        else:
            out.update(state="down", detail=f"{_age_txt(age)} old (TTL {_age_txt(ttl)}) during RTH")
        return out
    # pre / ah / overnight / closed: last-session carry is fine
    if age <= ttl or carry_ok:
        out.update(state="ok", carry=age > ttl,
                   detail=(f"{_age_txt(age)} old" if age <= ttl else "carry from last session close") + f" · {session.upper()}")
    else:
        out.update(state="stale", detail=f"older than last session close ({_age_txt(age)}) · {session.upper()}")
    return out


def _age_txt(s: Optional[float]) -> str:
    if s is None:
        return "—"
    s = abs(float(s))
    if s < 90:
        return f"{int(s)}s"
    if s < 5400:
        return f"{int(s // 60)}m"
    if s < 172800:
        return f"{int(s // 3600)}h {int((s % 3600) // 60)}m"
    return f"{int(s // 86400)}d {int((s % 86400) // 3600)}h"


# ------------------------------------------------------------------ extra checks
def check_mini_link(session: str) -> Optional[dict]:
    p = ROOT / "cache" / "mini-quotes.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"label": "Mac mini link", "state": "down", "detail": "mini-quotes.json unreadable", "required": True}
    m = d.get("mini") or {}
    feed = (m.get("stocks_feed") or {})
    ok = bool(m.get("ok")) and feed.get("connected", True)
    nmini = len(d.get("from_mini") or [])
    nsym = len(d.get("symbols") or d.get("unresolved") or []) or 20
    det = f"mini http {m.get('http_status')} · SIP {feed.get('state', '?')} · {nmini} names from mini"
    if m.get("latency_ms") is not None:
        det += f" · {round(m['latency_ms'])} ms"
    if not ok:
        return {"label": "Mac mini link", "state": "down" if session in ("rth", "pre", "ah") else "stale",
                "detail": det + (f" · {m.get('error')}" if m.get("error") else ""), "required": True}
    if session == "rth" and nmini < max(1, int(0.75 * nsym)):
        return {"label": "Mac mini link", "state": "stale", "detail": det + " (RTH expects ≥75% from mini)", "required": True}
    return {"label": "Mac mini link", "state": "ok", "detail": det, "required": True}


def check_opra_link(session: str) -> Optional[dict]:
    p = ROOT / "cache" / "mini-option-quotes.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"label": "OPRA stream", "state": "absent", "detail": "no mini-option-quotes.json", "required": True}
    f = d.get("options_feed") or {}
    ok = bool(d.get("ok")) and d.get("collector_status") in (None, "ok") and f.get("connected", True)
    n = len(d.get("contracts") or [])
    miss = len(d.get("missing") or [])
    det = f"OPRA {f.get('state', '?')} · {n} desk contracts subscribed · {miss} without quote"
    if not ok:
        return {"label": "OPRA stream", "state": "down" if session == "rth" else "stale",
                "detail": det + (f" · {d.get('error')}" if d.get("error") else ""), "required": True}
    if session == "rth" and n and miss > n / 2:
        return {"label": "OPRA stream", "state": "stale", "detail": det, "required": True}
    return {"label": "OPRA stream", "state": "ok", "detail": det, "required": True}


def check_fa_quota(session: str) -> Optional[dict]:
    st = {}
    for p in (ROOT / "cache" / "fa-focus-refresh-state.json",):
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
    acct = st.get("last_account") or {}
    rem, lim = acct.get("remaining"), acct.get("daily_limit")
    if rem is None:
        return {"label": "FA Growth quota", "state": "ok", "detail": "quota not read yet", "required": False}
    det = f"{acct.get('plan', '?')} plan · {rem:,}/{lim:,} calls left" if isinstance(lim, int) else f"{rem} left"
    if st.get("last_error"):
        det += f" · last error: {str(st['last_error'])[:80]}"
    if rem <= 0:
        return {"label": "FA Growth quota", "state": "down", "detail": det + " (exhausted)", "required": True}
    if rem < 100:
        return {"label": "FA Growth quota", "state": "stale", "detail": det + " (low)", "required": True}
    return {"label": "FA Growth quota", "state": "ok", "detail": det, "required": True}


CHECKS = {"mini_link": check_mini_link, "opra_link": check_opra_link, "fa_quota": check_fa_quota}


# ------------------------------------------------------------------ rows
def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def eval_row(n: int, row: dict, now: datetime, session: str, mem: dict) -> dict:
    base = {k: row.get(k) for k in ("id", "feed", "uses_now", "source", "mini", "risk")}
    base["n"] = n
    if row.get("static"):
        st = row["static"]
        base.update(status=st, tone=TONE.get(st, "missing"), known=True, alarm=None, checked=False,
                    detail="configured (not auto-checked) · update config/source-status.json when it lands",
                    signals=[], age_s=None, last_update_pt=None)
        return base
    sigs = [eval_signal(s, now, session) for s in row.get("signals") or []]
    for c in row.get("checks") or []:
        fn = CHECKS.get(c)
        if fn:
            r = fn(session)
            if r:
                sigs.append(r)
    req = [s for s in sigs if s.get("required", True)]
    states = [s["state"] for s in req]
    primary = next((s for s in sigs if s.get("ts")), None)
    ever = (mem.get("ever_live") or {}).get(row["id"])
    if any(s in ("down", "absent") for s in states):
        bad = [s for s in req if s["state"] in ("down", "absent")]
        if row.get("known_missing") and not ever:
            status, alarm, known = "Missing", None, True
        else:
            status, alarm, known = "Down", "red", False
        why = "; ".join(f"{s['label']}: {s.get('detail')}" for s in bad)
    elif any(s == "stale" for s in states):
        bad = [s for s in req if s["state"] == "stale"]
        status, alarm, known = "Stale", "amber", False
        why = "; ".join(f"{s['label']}: {s.get('detail')}" for s in bad)
    else:
        status, alarm, known = ("Stale-risk" if row.get("risk") else "Live"), None, False
        opt_bad = [s for s in sigs if not s.get("required", True) and s["state"] != "ok"]
        carry = any(s.get("carry") for s in req)
        why = "all checks OK" + (" · last-session carry (market closed)" if carry else "")
        if row.get("risk"):
            why += f" · risk: {row['risk']}"
        if opt_bad:
            why += " · secondary: " + "; ".join(f"{s['label']} {s['state']}" for s in opt_bad)
    base.update(status=status, tone=TONE[status], known=known, alarm=alarm, checked=True, detail=why,
                age_s=primary.get("age_s") if primary else None,
                last_update_pt=primary.get("ts_pt") if primary else None,
                last_update_epoch=primary.get("ts") if primary else None,
                signals=[{k: s.get(k) for k in ("label", "state", "detail", "age_s", "ts_pt", "file", "required", "writer_error")
                          if s.get(k) is not None} for s in sigs],
                ever_live_since=ever)
    return base


def compute(now: Optional[datetime] = None, write: bool = True) -> dict:
    global _PS_CACHE
    _PS_CACHE = None
    now = now or datetime.now(timezone.utc)
    session = _session(now)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    mem = _load_state()
    rows = [eval_row(i, r, now, session, mem) for i, r in enumerate(cfg.get("rows") or [], 1)]
    ever = dict(mem.get("ever_live") or {})
    for r in rows:
        if r.get("checked") and r["status"] in ("Live", "Stale-risk") and r["id"] not in ever:
            ever[r["id"]] = now.astimezone(PT).strftime("%Y-%m-%d %-I:%M %p PT")
    red = [r for r in rows if r.get("alarm") == "red"]
    amber = [r for r in rows if r.get("alarm") == "amber"]
    known = [r for r in rows if r.get("known")]
    level = "red" if red else ("amber" if amber else "green")
    counts: dict = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    slim = lambda r: {"n": r["n"], "id": r["id"], "feed": r["feed"], "status": r["status"], "detail": r["detail"]}  # noqa: E731
    out = {
        "feed": "source-status", "version": cfg.get("version"),
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ") if now.tzinfo == timezone.utc else now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of_pt": now.astimezone(PT).strftime("%a %m/%d/%Y %-I:%M %p PT"),
        "written_epoch": now.timestamp(),
        "session": session,
        "cadence": "every 5 min in RTH, hourly otherwise (box watchdog) + on every blotter publish",
        "alarm": {"level": level, "red": [slim(r) for r in red], "amber": [slim(r) for r in amber],
                  "known_missing": [{"n": r["n"], "feed": r["feed"], "status": r["status"]} for r in known],
                  "signature": level + ":" + ",".join(sorted(r["id"] + "=" + r["status"] for r in red + amber))},
        "counts": counts,
        "rows": rows,
        "legend": {"Live": "fresh within TTL (or last-session carry when the market is closed)",
                   "Stale-risk": "fresh now, but structurally at risk (see note) - no alarm",
                   "Stale": "past TTL - amber alarm", "Down": "missing / process dead / way past TTL - red alarm",
                   "Missing": "known gap, not built yet - counted, no alarm until it has been Live once",
                   "Needs purchase": "needs a paid vendor - counted, no alarm"},
        "writer": "dashboard/source_status.py", "config": "config/source-status.json",
        "mandate": "research/paper only · status only, never quotes",
    }
    if write:
        _save_json(OUT, out)
        mem["ever_live"] = ever
        mem["last_compute_epoch"] = now.timestamp()
        mem["last_signature"] = out["alarm"]["signature"]
        _save_json(STATE, mem)
    return out


# ------------------------------------------------------------------ watchdog mode
def _log(msg: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(PT).strftime('%Y-%m-%d %-I:%M:%S %p PT')} {msg}\n")
        if LOG.stat().st_size > 1_000_000:
            LOG.replace(LOG.with_suffix(".log.1"))
    except OSError:
        pass


def _published_signature() -> Optional[str]:
    p = ROOT / "dist-prod" / "data" / "source-status.json"
    try:
        return (json.loads(p.read_text(encoding="utf-8")).get("alarm") or {}).get("signature")
    except (OSError, ValueError):
        return None


def run_if_due(publish_on_change: bool) -> int:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fh = LOCK.open("w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another check in flight
    now = datetime.now(timezone.utc)
    session = _session(now)
    mem = _load_state()
    due_s = DUE_RTH_S if session == "rth" else DUE_OFF_S
    last = float(mem.get("last_compute_epoch") or 0)
    if time.time() - last < due_s - 5:
        return 0
    out = compute(now)
    sig = out["alarm"]["signature"]
    _log(f"computed {session} level={out['alarm']['level']} sig={sig}")
    if not publish_on_change:
        return 0
    pub_sig = _published_signature()
    snap = ROOT / "dist-prod" / "data" / "snapshot.json"
    snap_age = time.time() - snap.stat().st_mtime if snap.exists() else 1e9
    reason = None
    if pub_sig != sig:
        reason = f"alarm changed ({pub_sig} -> {sig})"
    elif session == "rth" and snap_age > STALE_PUBLISH_RTH_S:
        reason = f"published snapshot {int(snap_age // 60)} min old in RTH (routines stalled?)"
    if reason:
        _log(f"publish: {reason}")
        env = dict(os.environ, OID_PUBLISH_LOCK_WAIT_S="120")
        r = subprocess.run(["bash", str(ROOT / "dashboard" / "publish.sh")], capture_output=True, text=True,
                           timeout=420, env=env)
        _log(f"publish rc={r.returncode} {(r.stderr or '').strip()[-200:]}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--if-due", action="store_true")
    ap.add_argument("--publish-on-change", action="store_true")
    a = ap.parse_args(argv)
    if a.if_due:
        return run_if_due(a.publish_on_change)
    out = compute()
    if a.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    else:
        print(f"{out['as_of_pt']} · {out['session']} · alarm {out['alarm']['level']} · {out['counts']}")
        for r in out["rows"]:
            print(f"{r['n']:>2} {r['status']:<14} {r['feed'][:44]:<44} {r['detail'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
