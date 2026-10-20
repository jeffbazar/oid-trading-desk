#!/usr/bin/env python3
"""Box-side 5-second poller: Mac mini collector -> cache/mini-quotes.json (atomic).

Research / paper only. Equities (core-20 allowlist) -> cache/mini-quotes.json.
Per symbol the cache carries source ("mini" | "rh-quotes" | null) + age_s + fresh.

Options (2026-10-10): the same loop also declares the desk's option contracts to the mini
(quotes/option_marks.py: open paper seats + legs, Hal seats, live RH positions, option watch list;
re-pushed on change or hourly) and writes cache/mini-option-quotes.json (bid/ask/mid/last/ts per OCC,
Alpaca OPRA). That file is box-only and never published.
Readers: quotes/mini_client.read_cache(), refresh_marks.py / refresh_market_tape.py overlay.

Run via scripts/mini-poller.sh start|stop|status (nohup). Token never logged.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mini_client as mc  # noqa: E402
import option_marks as om  # noqa: E402

OID = mc.OID
CACHE_DIR = mc.CACHE_PATH.parent
PID_PATH = CACHE_DIR / "mini-poller.pid"
LOG_PATH = CACHE_DIR / "mini-poller.log"
INTERVAL_S = float(os.environ.get("OID_MINI_POLL_S", "5"))
LOG_MAX_BYTES = 2_000_000
SUMMARY_EVERY_S = 600

_stop = False


def _on_signal(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def log(msg: str) -> None:
    line = f"{mc._pt_stamp()} {msg}\n"
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def build_record(symbols: list[str]) -> dict:
    res = mc.get_quotes(symbols)
    t = time.time()
    m = res["mini"]
    return {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
        "as_of_pt": mc._pt_stamp(t),
        "written_epoch": round(t, 3),
        "writer": "quotes/mini_poller.py",
        "source": "oid-mini quote collector (Alpaca SIP 4 AM-8 PM ET / overnight feed 8 PM-4 AM ET, via Tailscale) · fallback rh-quotes",
        "poll_interval_s": INTERVAL_S,
        "session": m.get("session"),
        "max_age_s": m.get("max_age_s"),
        "mini": m,
        "symbols": symbols,
        "from_mini": res["from_mini"],
        "from_rh": res["from_rh"],
        "unresolved": res["unresolved"],
        "rh_age_seconds": res.get("rh_age_seconds"),
        "quotes": res["quotes"],
        "mandate": "Research / paper only · equities only · not an elevate gate",
    }


OPT_DESIRED_EVERY = int(os.environ.get("OID_MINI_OPT_DESIRED_EVERY", "12"))  # polls (~60 s at 5 s)


class OptionPoll:
    """Options side of the poller: refresh desired contracts / push subs periodically, write the OPRA cache."""

    def __init__(self):
        self.desired: dict = {"contracts": []}
        self.last_state = None

    def refresh_desired(self) -> None:
        self.desired = om.desired_contracts()
        try:
            pushed = om.maybe_push(self.desired["contracts"])
        except mc.MiniError as e:
            log(f"options push error {str(e)[:160]}")
            return
        if pushed is not None:
            log(f"options subs pushed n={pushed.get('count')} changed={pushed.get('changed')} "
                f"expired_skipped={len(self.desired.get('expired') or {})}")

    def step(self, n: int) -> None:
        if n % OPT_DESIRED_EVERY == 0:
            self.refresh_desired()
        rec = om.build_cache_record(self.desired["contracts"], desired_info=self.desired)
        om.write_cache(rec)
        state = (rec["ok"], len(rec["quotes"]), len(rec["missing"]))
        if state != self.last_state:
            log(f"options state ok={rec['ok']} rows={len(rec['quotes'])} missing={len(rec['missing'])} err={rec.get('error')}")
            self.last_state = state


def run() -> int:
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))
    symbols = mc.core_symbols()
    log(f"start pid={os.getpid()} interval={INTERVAL_S}s symbols={len(symbols)} url={mc.MINI_BASE_URL}")
    last_state = None
    last_summary = 0.0
    n = 0
    opt = OptionPoll()
    try:
        while not _stop:
            t0 = time.monotonic()
            try:
                if n % 60 == 0:  # pick up allowlist edits every ~5 min
                    symbols = mc.core_symbols() or symbols
                rec = build_record(symbols)
                atomic_write_json(mc.CACHE_PATH, rec)
                m = rec["mini"]
                state = (bool(m.get("ok")), m.get("error") is None, rec["session"],
                         len(rec["from_mini"]) > 0)
                if state != last_state:
                    log(f"state ok={m.get('ok')} http={m.get('http_status')} lat={m.get('latency_ms')}ms "
                        f"session={rec['session']} mini={len(rec['from_mini'])} rh={len(rec['from_rh'])} "
                        f"unresolved={len(rec['unresolved'])} err={m.get('error')}")
                    last_state = state
                if time.time() - last_summary > SUMMARY_EVERY_S:
                    log(f"summary polls={n} lat={m.get('latency_ms')}ms mini={len(rec['from_mini'])} "
                        f"rh={len(rec['from_rh'])} unresolved={len(rec['unresolved'])}")
                    last_summary = time.time()
            except Exception as e:  # keep looping; never include secrets
                log(f"poll error {type(e).__name__}: {str(e)[:200]}")
            try:
                opt.step(n)
            except Exception as e:  # options never block the equity cache
                log(f"options poll error {type(e).__name__}: {str(e)[:200]}")
            n += 1
            sleep_for = max(0.2, INTERVAL_S - (time.monotonic() - t0))
            end = time.monotonic() + sleep_for
            while not _stop and time.monotonic() < end:
                time.sleep(max(0.0, min(0.5, end - time.monotonic())))
    finally:
        log(f"stop pid={os.getpid()} polls={n}")
        try:
            if PID_PATH.read_text().strip() == str(os.getpid()):
                PID_PATH.unlink()
        except OSError:
            pass
    return 0


def once() -> int:
    rec = build_record(mc.core_symbols())
    atomic_write_json(mc.CACHE_PATH, rec)
    try:
        OptionPoll().step(0)
    except Exception as e:
        log(f"options once error {type(e).__name__}: {str(e)[:200]}")
    m = rec["mini"]
    print(json.dumps({"ok": m.get("ok"), "http_status": m.get("http_status"), "latency_ms": m.get("latency_ms"),
                      "session": rec["session"], "from_mini": len(rec["from_mini"]), "from_rh": len(rec["from_rh"]),
                      "unresolved": len(rec["unresolved"]), "error": m.get("error"), "path": str(mc.CACHE_PATH)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(once() if "--once" in sys.argv else run())
