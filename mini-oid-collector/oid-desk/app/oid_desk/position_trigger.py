"""Position trigger guard on the mini (Jeffrey 2026-10-14, arch review R1). launchd interval job, 30 s.

NEVER TRADES. Reads the open paper seats (paper-trades/paper-open.json, pushed from the box via desk-state), the
mini's live stock quotes (cache/mini-quotes.json) and OPRA marks (cache/mini-option-quotes.json, private, used
here only; never published). When a rule fires it:
  * writes market-data/latest/position-triggers.json (current state for every open seat), and
  * touches state/position-trigger.flag (mtime = last new trigger) and appends an event that alerts.py posts
    to the webhook (status "trigger") within 60 s.
The bots (Rose / Hal) still decide; this only removes the 5-15 min blind spot between routine runs.

Rules (CLOSE-TRIGGERS-V1 subset, spot-based so they work even when option quotes are thin):
  INVALIDATE    put spread: spot >= faWalls.flip   | call spread: spot <= faWalls.flip   (hard thesis fail)
  WALL_BREAK    put spread: spot <  faWalls.pw     | call spread: spot >  faWalls.cw     (target zone, review)
  LOSS_BACKSTOP mark <= entry * (1 - L); L = 0.60 Hal verticals, 0.25 Rose short-dated (needs fresh OPRA mark)
  GIVEBACK      peak MFE >= +50% and current pnl >= +25% but gave back >= half of MFE (needs fresh OPRA mark)
Debounce: a rule must hold 2 consecutive checks. Re-alert the same (seat, rule) at most every 30 min.
Regular hours only (OPRA/flip levels are RTH concepts). Kill switch: oidctl disable position-trigger.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any, Optional

from . import util

JOB = "position-trigger"
DEBOUNCE = 2
REPEAT_S = 1800
SPOT_MAX_AGE = 30
MARK_MAX_AGE = 120
LOSS = {"hal": 0.60, "rose": 0.25}
CONTRACT_RE = re.compile(r"^(?P<u>[A-Z.]+)\s+(?P<exp>\d{4}-\d{2}-\d{2})\s+(?P<a>[\d.]+)/(?P<b>[\d.]+)\s+(?P<cp>put|call)\s+(?P<kind>debit|credit)\s+spread", re.I)


def _occ(u: str, exp: str, cp: str, k: float) -> str:
    d = datetime.strptime(exp, "%Y-%m-%d")
    return f"{u}{d:%y%m%d}{'P' if cp.lower() == 'put' else 'C'}{int(round(k * 1000)):08d}"


def _q(rows: dict, sym: str, max_age: float) -> Optional[dict]:
    r = rows.get(sym) if isinstance(rows, dict) else None
    if not isinstance(r, dict) or r.get("age_s") is None or r["age_s"] > max_age:
        return None
    return r


def evaluate_seat(seat: dict, spot_rows: dict, opt_rows: dict) -> tuple[list[str], dict]:
    m = CONTRACT_RE.match(str(seat.get("contract") or ""))
    info: dict[str, Any] = {"id": seat.get("id"), "agent": seat.get("agent"), "symbol": seat.get("symbol"),
                            "contract": seat.get("contract")}
    if not m:
        info["skip"] = "contract not parsed (only verticals supported)"
        return [], info
    u, cp, kind = m["u"].upper(), m["cp"].lower(), m["kind"].lower()
    a, b = float(m["a"]), float(m["b"])
    bearish = (cp == "put") == (kind == "debit")
    walls = seat.get("faWalls") or {}
    sq = _q(spot_rows, u, SPOT_MAX_AGE)
    spot = (sq.get("mid") or sq.get("last")) if sq else None
    info.update(spot=spot, bearish=bearish, flip=walls.get("flip"), pw=walls.get("pw"), cw=walls.get("cw"))
    fired = []
    if spot is not None:
        if walls.get("flip") is not None and ((bearish and spot >= walls["flip"]) or (not bearish and spot <= walls["flip"])):
            fired.append("INVALIDATE")
        if bearish and walls.get("pw") is not None and spot < walls["pw"]:
            fired.append("WALL_BREAK")
        if not bearish and walls.get("cw") is not None and spot > walls["cw"]:
            fired.append("WALL_BREAK")
    else:
        info["spot_stale"] = True
    # Vertical mark from OPRA (long leg = higher strike for put debit / lower strike for call debit)
    hi, lo = max(a, b), min(a, b)
    long_k, short_k = (hi, lo) if cp == "put" else (lo, hi)
    if kind == "credit":
        long_k, short_k = short_k, long_k
    lq = _q(opt_rows, _occ(u, m["exp"], cp, long_k), MARK_MAX_AGE)
    shq = _q(opt_rows, _occ(u, m["exp"], cp, short_k), MARK_MAX_AGE)
    entry = seat.get("entryDebit") or seat.get("entryCredit")
    if lq and shq and lq.get("mid") is not None and shq.get("mid") is not None and entry:
        mark = round(lq["mid"] - shq["mid"], 4) if kind == "debit" else round(shq["mid"] - lq["mid"], 4)
        pnl = (mark - entry) / entry if kind == "debit" else (entry - mark) / entry
        peak = seat.get("peakMark")
        mfe = ((peak - entry) / entry) if (peak and kind == "debit") else None
        info.update(mark=mark, pnl_pct=round(pnl * 100, 1), mfe_pct=round(mfe * 100, 1) if mfe is not None else None)
        lim = LOSS.get(str(seat.get("agent") or "").lower(), 0.6)
        if pnl <= -lim:
            fired.append("LOSS_BACKSTOP")
        if mfe is not None and mfe >= 0.5 and pnl >= 0.25 and (mfe - pnl) >= 0.5 * mfe:
            fired.append("GIVEBACK")
    else:
        info["mark_stale"] = True
    return fired, info


def tick(dry: bool = False, force_session: Optional[str] = None) -> dict:
    sess = force_session or util.session()
    desk = util.desk()
    sf = util.root() / "state" / "position-trigger-state.json"
    st = util.read_json(sf) or {}
    po = util.read_json(desk / "paper-trades" / "paper-open.json") or {}
    seats = [s for s in (po.get("seats") or []) if str(s.get("status", "open")).lower() == "open"]
    spot_rows = (util.read_json(desk / "cache" / "mini-quotes.json") or {}).get("quotes") or {}
    opt_rows = (util.read_json(desk / "cache" / "mini-option-quotes.json") or {}).get("quotes") or {}
    now = time.time()
    rows, events = [], []
    for seat in seats:
        fired, info = evaluate_seat(seat, spot_rows, opt_rows) if sess == "rth" else ([], {"id": seat.get("id"), "skip": f"session {sess}"})
        info["fired"] = fired
        rows.append(info)
        for rule in fired:
            k = f"{seat.get('id')}:{rule}"
            s = st.setdefault(k, {"n": 0, "sent_at": 0})
            s["n"] += 1
            if s["n"] >= DEBOUNCE and now - s.get("sent_at", 0) >= REPEAT_S:
                s["sent_at"] = now
                events.append({"source": f"mini:trigger:{seat.get('id')}", "status": "trigger",
                               "detail": f"{rule} {seat.get('agent')} {seat.get('contract')} spot={info.get('spot')} "
                                         f"flip={info.get('flip')} pw={info.get('pw')} cw={info.get('cw')} "
                                         f"mark={info.get('mark')} pnl%={info.get('pnl_pct')} (paper alert only; bots decide)",
                               "age": None, "ts": util.now_pt_str()})
        for k in [k for k in st if k.startswith(f"{seat.get('id')}:") and k.split(":", 1)[1] not in fired]:
            st[k]["n"] = 0
    if not dry:
        util.write_feed("position-triggers", source="mini position guard (paper-open + mini quotes)",
                        writer="mini:oid_desk.position_trigger", symbols=sorted({r.get("symbol") for r in rows if r.get("symbol")}),
                        payload={"session": sess, "seats": rows, "never_trades": True}, ttl_seconds=120)
        if events:
            with open(util.root() / "state" / "position-trigger-events.jsonl", "a") as fh:
                for e in events:
                    fh.write(json.dumps(e) + "\n")
            (util.root() / "state" / "position-trigger.flag").write_text(json.dumps(events[-1]) + "\n")
            for e in events:
                util.log(JOB, f"TRIGGER {e['detail']}")
        util.atomic_write_json(sf, st)
    return {"session": sess, "seats": rows, "events": events}


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="OID mini position trigger guard (never trades)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force-rth", action="store_true", help="test: evaluate as if RTH (use with --dry)")
    a = ap.parse_args(argv)
    print(json.dumps(tick(dry=a.dry, force_session="rth" if a.force_rth else None), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
