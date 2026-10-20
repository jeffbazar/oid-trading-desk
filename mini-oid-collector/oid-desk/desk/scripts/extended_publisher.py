#!/usr/bin/env python3
"""Extended-hours blotter publisher (box-side, research / paper only — zero execution).

Every 5 minutes during PRE (1:00-6:30 AM PT), AH (1:00-5:00 PM PT) and OVERNIGHT (5:00 PM-1:00 AM PT,
Sun night -> Fri morning) on trading days — i.e. outside the 9:03 AM-3:58 PM ET live-refresh routine —
run dashboard/rebuild.py then dashboard/publish.sh (which re-imports + repackages dist-prod).
Session gate = quotes/mini_client.current_session() (NYSE holidays + overnight-before-trading-day).

Inputs are files only: cache/mini-quotes.json (5 s mini poller), market-data/latest/*, paper-trades/*.
No Robinhood (or any broker) API calls. Publishes ONLY to swift-dune-cs3e (never bold-tulip).
Holds cache/publish.lock (flock) across rebuild+publish; publish.sh honours it, so routines/agents queue.

  scripts/extended-publisher.sh start|stop|status|once|restart
"""
from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

OID = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OID / "quotes"))
sys.path.insert(0, str(OID / "paper-trades"))
import mini_client as mc  # noqa: E402

CACHE = OID / "cache"
PID_PATH = CACHE / "extended-publisher.pid"
LOG_PATH = CACHE / "extended-publisher.log"
STATE_PATH = CACHE / "extended-publisher.json"
LOCK_PATH = Path(os.environ.get("OID_PUBLISH_LOCK", str(CACHE / "publish.lock")))
INTERVAL_S = float(os.environ.get("OID_EXT_PUBLISH_S", "300"))
LOCK_WAIT_S = float(os.environ.get("OID_EXT_LOCK_WAIT_S", "120"))
SLUG = "swift-dune-cs3e"  # production redesign slug; bold-tulip-nejq is frozen
ACTIVE_SESSIONS = ("pre", "ah", "overnight")
LOG_MAX_BYTES = 2_000_000

_stop = False


def _on_signal(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def log(msg: str) -> None:
    line = f"{mc._pt_stamp()} {msg}\n"
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def active_session() -> str | None:
    s = mc.current_session()
    # Mac mini single-publisher mode (MINI-MIGRATION-PLAN phase 5): OID_PUBLISH_ALL_SESSIONS=1 also publishes in RTH.
    # Unset on the box, so box behaviour is unchanged.
    if s == "rth" and os.environ.get("OID_PUBLISH_ALL_SESSIONS") == "1":
        return s
    return s if s in ACTIVE_SESSIONS else None


def _write_state(d: dict) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.replace(tmp, STATE_PATH)


def _tail(text: str, n: int = 300) -> str:
    return " ".join((text or "").strip().split())[-n:]


def cycle(session: str) -> dict:
    """One rebuild + publish under the shared publish lock. Never raises."""
    t0 = time.time()
    res: dict = {"started_pt": mc._pt_stamp(t0), "session": session, "ok": False, "slug": SLUG}
    mini = mc.read_cache()
    res["mini_cache"] = {"fresh_file": mini.get("fresh_file"), "file_age_s": mini.get("file_age_s"),
                         "fresh_symbols": len(mini.get("quotes") or {})}
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lf:
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline or _stop:
                    res["error"] = f"publish lock busy >{LOCK_WAIT_S:.0f}s; skipped this cycle"
                    return res
                time.sleep(2)
        env = dict(os.environ, OID_PUBLISH_LOCK_HELD="1", OID_PUBLISH_SLUG=SLUG)
        env.pop("OID_PUBLISH_DIST", None)  # always the packaged prod dist
        try:
            rb = subprocess.run([sys.executable, str(OID / "dashboard" / "rebuild.py")], cwd=str(OID / "dashboard"),
                                capture_output=True, text=True, timeout=240, env=env)
            res["rebuild_rc"] = rb.returncode
            if rb.returncode != 0:
                res["error"] = "rebuild failed: " + _tail(rb.stderr or rb.stdout)
                return res
            pb = subprocess.run(["bash", str(OID / "dashboard" / "publish.sh")], cwd=str(OID / "dashboard"),
                                capture_output=True, text=True, timeout=300, env=env)
            res["publish_rc"] = pb.returncode
            if pb.returncode != 0:
                res["error"] = "publish failed: " + _tail(pb.stderr or pb.stdout)
                return res
            res["ok"] = True
        except subprocess.TimeoutExpired as e:
            res["error"] = f"timeout: {e.cmd if isinstance(e.cmd, str) else ' '.join(map(str, e.cmd))[-120:]}"
        finally:
            res["elapsed_s"] = round(time.time() - t0, 1)
            fcntl.flock(lf, fcntl.LOCK_UN)
    return res


def run() -> int:
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    CACHE.mkdir(parents=True, exist_ok=True)
    run_lock = open(CACHE / "extended-publisher.run.lock", "w")  # single instance (watchdog + manual start race)
    try:
        fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log(f"another extended-publisher instance is running; pid={os.getpid()} exiting")
        return 0
    PID_PATH.write_text(str(os.getpid()))
    log(f"start pid={os.getpid()} interval={INTERVAL_S:.0f}s sessions={','.join(ACTIVE_SESSIONS)} slug={SLUG}")
    last_gate = None
    n_ok = n_fail = 0
    try:
        while not _stop:
            sess = active_session()
            gate = sess or f"idle({mc.current_session()})"
            if gate != last_gate:
                log(f"gate {gate}")
                last_gate = gate
            next_at = time.time() + INTERVAL_S
            if sess:
                r = cycle(sess)
                if r.get("ok"):
                    n_ok += 1
                else:
                    n_fail += 1
                log(f"publish {'ok' if r.get('ok') else 'FAIL'} session={sess} elapsed={r.get('elapsed_s')}s "
                    f"mini_fresh={r['mini_cache'].get('fresh_symbols')} file_age={r['mini_cache'].get('file_age_s')}s"
                    + (f" err={r.get('error')}" if r.get("error") else ""))
                _write_state({**r, "pid": os.getpid(), "ok_count": n_ok, "fail_count": n_fail,
                              "next_at_pt": mc._pt_stamp(next_at)})
            else:
                # outside extended hours (RTH = routine's job; weekends/holidays = nothing to publish)
                next_at = time.time() + 60
            while not _stop and time.time() < next_at:
                time.sleep(min(1.0, next_at - time.time()))
    finally:
        log(f"stop pid={os.getpid()} ok={n_ok} fail={n_fail}")
        try:
            if PID_PATH.read_text().strip() == str(os.getpid()):
                PID_PATH.unlink()
        except OSError:
            pass
    return 0


def once(force: bool = False) -> int:
    sess = active_session()
    if not sess and not force:
        print(json.dumps({"skipped": True, "session": mc.current_session()}))
        return 0
    r = cycle(sess or mc.current_session())
    log(f"once publish {'ok' if r.get('ok') else 'FAIL'} session={r['session']} elapsed={r.get('elapsed_s')}s"
        + (f" err={r.get('error')}" if r.get("error") else ""))
    print(json.dumps(r, indent=1))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    if "--once" in sys.argv:
        raise SystemExit(once(force="--force" in sys.argv))
    raise SystemExit(run())
