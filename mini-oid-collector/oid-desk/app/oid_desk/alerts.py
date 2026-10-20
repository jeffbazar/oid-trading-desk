"""Push alarm-state changes to the OID alert webhook (Jeffrey 2026-10-13). Replaces 5-min agent polling.

Reads market-data/latest/mini-status.json (written every 60 s by the status job). Per source:
  bad  = stale | down | failed (collector unreachable/not ok, status file itself older than 300 s)
  edgar is judged by its intended ET slots (mini-desk.json edgar.due_et): bad only when the latest slot's
        59-min window has closed and the feed's payload.slot doesn't match it (overrides the 7200 s TTL).
Debounce: a new state must hold for DEBOUNCE consecutive checks before it is sent.
Repeat suppression: the same (source, status) is not re-sent within 30 min. A recovery ("ok") is sent only
after a bad state was sent. Disabled jobs (known gaps / holds) never alert.
POST JSON {source, status, age, detail, ts} with Authorization: Bearer <OID_ALERT_WEBHOOK_KEY>. Key never logged.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Optional

from . import util

JOB = "alerts"
URL = "https://api2.cursor.sh/automations/webhook/47fdd072-99e5-5374-b0e6-77994c65409a"
DEBOUNCE = 2
SUPPRESS_S = 1800
STATUS_MAX_AGE = 300
SKIP = {"benzinga", "publish"}
OUTBOX = "alerts-outbox.jsonl"     # PROPOSAL: failed POSTs are queued and retried next tick (max 24 h)
SELFHEAL_MAX_AGE = 300             # PROPOSAL: alerts watches selfheal (selfheal watches alerts)


def post(body: dict) -> int:
    """Primary channel (Grok Bot webhook) plus any extra channels from config/mini-desk.json "alert_channels"
    (10/14 arch R5 hook, e.g. a phone push service Jeffrey picks later). Returns the PRIMARY status code;
    extra channels are best-effort and never block or fail the primary."""
    code = _post_webhook(body)
    for ch in (util.desk_config("mini-desk.json").get("alert_channels") or []):
        try:
            _send_extra(ch, body)
        except Exception as e:  # noqa: BLE001
            util.log(JOB, f"extra channel {ch.get('name')} failed: {type(e).__name__}")
    return code


def _send_extra(ch: dict, body: dict) -> None:
    """Channel spec: {"name", "type": "json_webhook"|"ntfy", "url", "secret": <secret file name or null>,
    "min_status": ["stale","down","failed","degraded","giveup","trigger"]}. Secret value is read from the
    secrets dir and never logged."""
    if not ch.get("enabled", True):
        return
    want = ch.get("min_status")
    if want and body.get("status") not in want:
        return
    hdr = {"User-Agent": "oid-mini-alerts/1"}
    sec = util.read_secret(ch["secret"]) if ch.get("secret") else None
    if ch.get("type") == "ntfy":
        data = f"{body.get('source')} {body.get('status')}: {body.get('detail')}".encode()
        hdr["Title"] = f"OID {body.get('status')}"
        if sec:
            hdr["Authorization"] = f"Bearer {sec}"
    else:
        data = json.dumps(body).encode()
        hdr["Content-Type"] = "application/json"
        if sec:
            hdr["Authorization"] = f"Bearer {sec}"
    req = urllib.request.Request(ch["url"], data=data, method="POST", headers=hdr)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10) as r:
        util.log(JOB, f"extra channel {ch.get('name')} -> {r.status}")


ACCEPTED_STATUS = {"stale", "down", "failed", "degraded", "recovered", "test", "red", "amber", "restarted"}


def normalize(body: dict) -> dict:
    """2026-10-15 fix: the webhook rejected status "trigger" and age null with HTTP 400. Any status outside the
    accepted set becomes "degraded" (original status / rule kept in detail), age becomes a number, and position
    triggers post as source mini:position-trigger."""
    b = dict(body)
    st = str(b.get("status") or "")
    if st not in ACCEPTED_STATUS:
        src = str(b.get("source") or "")
        if src.startswith("mini:trigger:"):
            b["detail"] = f"POSITION TRIGGER seat={src.split(':', 2)[2]}: {b.get('detail')}"
            b["source"] = "mini:position-trigger"
        else:
            b["detail"] = f"[{st.upper()}] {b.get('detail')}"
        b["status"] = "degraded"
    try:
        b["age"] = float(b["age"]) if b.get("age") is not None else 0
    except (TypeError, ValueError):
        b["age"] = 0
    b["detail"] = str(b.get("detail") or "")[:900]
    return b


def _post_webhook(body: dict) -> int:
    body = normalize(body)
    key = util.read_secret("OID_ALERT_WEBHOOK_KEY")
    if not key:
        raise RuntimeError("OID_ALERT_WEBHOOK_KEY missing")
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                          "User-Agent": "oid-mini-alerts/1"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        try:
            util.log(JOB, f"webhook HTTP {e.code}: {e.read()[:200]!r}")
        except Exception:  # noqa: BLE001
            pass
        return e.code


def edgar_state(now: Optional[datetime] = None) -> tuple[str, str]:
    now = now or datetime.now(util.ET)
    cfg = util.desk_config("mini-desk.json").get("edgar") or {}
    slots = []
    for back in range(0, 7):
        day = now - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        for hhmm in cfg.get("due_et") or ["08:15"]:
            h, m = map(int, hhmm.split(":"))
            st = day.replace(hour=h, minute=m, second=0, microsecond=0)
            if st + timedelta(minutes=59) <= now:
                slots.append((st, day.strftime("%Y-%m-%d ") + hhmm))
        if slots:
            break
    if not slots:
        return "ok", "no closed slot"
    want = max(slots)[1]
    got = ((util.read_json(util.desk() / "market-data" / "latest" / "premarket-edgar-mini.json") or {}).get("payload") or {}).get("slot")
    return ("ok", f"slot {got}") if (got or "") >= want else ("stale", f"missed slot {want} ET (last {got})")


def current() -> dict[str, dict]:
    p = util.desk() / "market-data" / "latest" / "mini-status.json"
    out: dict[str, dict] = {}
    age = time.time() - p.stat().st_mtime if p.exists() else None
    if age is None or age > STATUS_MAX_AGE:
        out["status"] = {"status": "stale", "age": age, "detail": "mini-status.json not updating"}
        return out
    pl = (util.read_json(p) or {}).get("payload") or {}
    for r in pl.get("jobs") or []:
        j = r.get("job")
        if not r.get("enabled") or j in SKIP or r.get("state") == "disabled":
            continue
        st = r.get("state")
        detail = f"{r.get('heartbeat')} ttl={r.get('ttl_s')} session={pl.get('session')}"
        if j == "edgar":
            st, detail = edgar_state()
        out[j] = {"status": st, "age": r.get("age_s"), "detail": detail}
    if pl.get("session") == "rth" and "macro-public" in out:  # Fix 10/14: VIX on fallback = degraded
        vix = ((util.read_json(util.desk() / "market-data" / "latest" / "macro-public.json") or {}).get("payload") or {}).get("vix") or {}
        if vix.get("provider") != "flashalpha_live":
            out["vix"] = {"status": "degraded", "age": None,
                          "detail": f"VIX provider={vix.get('provider')} fallback_used={bool(vix.get('fallback_used'))} errors={list((vix.get('errors') or {}).keys())}"}
        else:
            out["vix"] = {"status": "ok", "age": None, "detail": f"VIX provider={vix.get('provider')}"}
    sh = util.root() / "state" / "selfheal-state.json"  # PROPOSAL: heartbeat-of-the-heartbeat
    if not (util.root() / "flags" / "selfheal.disabled").exists() and util.ext_bucket(pl.get("session") or "closed") in ("rth", "ext"):
        sh_age = time.time() - sh.stat().st_mtime if sh.exists() else None
        out["selfheal"] = {"status": "ok" if sh_age is not None and sh_age <= SELFHEAL_MAX_AGE else "stale",
                           "age": sh_age, "detail": "selfheal-state.json age"}
    hl = (pl.get("collector") or {})
    col = hl
    out["collector"] = {"status": "ok" if col.get("ok") or pl.get("session") == "closed" else "failed",
                        "age": None, "detail": f"collector {col.get('status')}"}
    return out


def tick(dry: bool = False) -> list[dict]:
    sf = util.root() / "state" / "alerts-state.json"
    st = util.read_json(sf) or {}
    now = time.time()
    sent = []
    cur = current()
    if "status" in cur and len(cur) == 1:  # status file dead: keep other sources' state as-is
        pass
    for src, c in cur.items():
        s = st.setdefault(src, {"sent": "ok", "sent_at": 0, "cand": None, "n": 0})
        stat = "ok" if c["status"] == "ok" else c["status"]
        if stat == s["sent"]:
            s["cand"], s["n"] = None, 0
            continue
        s["n"] = s["n"] + 1 if s["cand"] == stat else 1
        s["cand"] = stat
        if s["n"] < DEBOUNCE:
            continue
        if stat != "ok" and s.get("last_bad") == stat and now - s.get("last_bad_at", 0) < SUPPRESS_S:
            s["sent"], s["cand"], s["n"] = stat, None, 0  # repeat within 30 min: suppressed
            continue
        body = {"source": f"mini:{src}", "status": "recovered" if stat == "ok" else stat,
                "age": c.get("age"), "detail": c.get("detail"), "ts": util.now_pt_str()}
        try:
            code = 0 if dry else post(body)
        except Exception:  # noqa: BLE001  PROPOSAL: network error no longer crashes the tick
            code = 0
        if not dry and not 200 <= code < 300:
            _queue(body)
        util.log(JOB, f"POST {body['source']} {body['status']} -> {code}")
        if True:  # PROPOSAL: state advances either way; failed POSTs live in the outbox
            s["sent"], s["sent_at"], s["cand"], s["n"] = stat, now, None, 0
            if stat != "ok":
                s["last_bad"], s["last_bad_at"] = stat, now
            sent.append(body)
    sent += drain_events(dry)
    sent += retry_outbox(dry)
    util.atomic_write_json(sf, st)
    return sent


def _queue(body: dict) -> None:
    with open(util.root() / "state" / OUTBOX, "a") as fh:
        fh.write(json.dumps(dict(body, queued_at=time.time())) + "\n")


def drain_events(dry: bool) -> list[dict]:
    """PROPOSAL: forward selfheal restart/giveup events (no debounce: each is a real action)."""
    if dry:
        return []
    lines = []
    for fn in ("selfheal-events.jsonl", "position-trigger-events.jsonl"):  # 10/14: + position triggers
        p = util.root() / "state" / fn
        if p.exists():
            lines += p.read_text().splitlines()
            p.write_text("")
    out = []
    for ln in lines:
        try:
            body = json.loads(ln)
        except ValueError:
            continue
        try:
            code = post(body)
        except Exception:  # noqa: BLE001
            code = 0
        util.log(JOB, f"POST {body['source']} {body['status']} -> {code}")
        if not 200 <= code < 300:
            _queue(body)
        out.append(body)
    return out


def retry_outbox(dry: bool) -> list[dict]:
    """PROPOSAL: webhook down / Grok Bot platform hiccup -> keep the alert and retry; drop after 24 h."""
    p = util.root() / "state" / OUTBOX
    if not p.exists() or dry:
        return []
    keep, out = [], []
    for ln in p.read_text().splitlines():
        try:
            body = json.loads(ln)
        except ValueError:
            continue
        if time.time() - body.get("queued_at", 0) > 86400:
            continue
        b = {k: v for k, v in body.items() if k != "queued_at"}
        b["detail"] = f"(delayed) {b.get('detail')}"
        try:
            code = post(b)
        except Exception:  # noqa: BLE001
            code = 0
        (out if 200 <= code < 300 else keep).append(body)
    p.write_text("".join(json.dumps(x) + "\n" for x in keep))
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID mini alert pusher")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--test-degraded", action="store_true")
    a = ap.parse_args(argv)
    if a.test or a.test_degraded:
        code = post({"source": "mini:vix" if a.test_degraded else "mini:alerts", "status": "degraded" if a.test_degraded else "test", "age": 0,
                     "detail": "TEST: OID mini alert sender " + ("degraded (VIX fallback) test POST" if a.test_degraded else "test POST"), "ts": util.now_pt_str()})
        util.log(JOB, f"test POST -> {code}")
        print(json.dumps({"test_http": code}))
        return 0 if 200 <= code < 300 else 1
    print(json.dumps({"sent": tick(dry=a.dry)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
