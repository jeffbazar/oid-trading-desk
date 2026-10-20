"""Hal fast exit watcher on the mini (Jeffrey 2026-10-20). launchd daemon com.oid.desk.hal-exit-watch. NEVER TRADES.

Why: Hal's live trader routine runs every 5-10 min (gaps up to 46 min); HAL-LIVE-VS-PAPER-AUDIT-20261020.md shows
~$4.3k of slippage past stops. This job checks every seat's exit rules every CHECK_S seconds and wakes Hal by
webhook the moment one trips. Hal still decides and sends the close himself.

Inputs (all local to the mini):
  rules   <desk>/paper-trades/hal-live/active-exit-rules.json  (Hal writes it on the box at every entry/exit; the
          box mirror poller pushes it here via POST /v1/desk-state within ~15 s in market hours). Re-read on mtime.
  stock   collector GET /v1/quotes (Alpaca SIP, live trades + NBBO)           -> last, bid, ask, age
  option  collector GET /v1/options (Alpaca OPRA, real-time)                  -> mid, bid, ask, age
          (seats in the rules file are added to the OPRA subscription by quotes/option_marks.desired_contracts)
  5m bar  collector GET /v1/bars timeframe=5Min, fetched once per underlying ~8 s after each 5-min boundary
Rules per seat (each trip names the leg that tripped: option | stock | structure | time | data):
  option_stop      option mid <= option_stop            (bid also reported; decay alone can trip this)
  stock_stop       stock last through stock_stop (stock_stop_dir below|above; default from side)
  target_option    option mid >= target_option
  target_stock     stock last through target_stock (opposite of stock_stop_dir)
  take_half        option mid >= entry_px * (1 + take_half_pct/100) unless seat.half_taken is true
  structure_break  last closed 5-min bar closes through structure.level in structure.dir
  time_stop        PT clock >= time_stop_pt
  preclose_dte     dte <= 8 and PT clock >= 12:40 (pre-close warning)
  quotes_stale     stock or option quote older than STALE_S for STALE_HOLD_S (so a silent feed is not mistaken
                   for "nothing tripped")
Debounce: price rules must hold DEBOUNCE consecutive checks (~2 checks = 2-4 s); time rules fire on first check.
De-dupe: one (seat, rule) fires once; re-fires only while still tripped every REFIRE_S (120 s); max MAX_FIRES (3)
per (seat, rule) per day. A cleared rule that trips again obeys the same cooldown and cap.
Mode: LIVE when both secret files exist in $OID_SECRETS_DIR (HAL_EXIT_WEBHOOK_URL, HAL_EXIT_WEBHOOK_KEY), re-checked
every loop (no restart); otherwise DRY (trips are logged, nothing is POSTed). Force dry: touch <root>/flags/hal-exit-watch.dry.
Log every check and trip: ~/oid-data/hal-exit/YYYYMMDD.jsonl. Status: <desk>/cache/hal-exit-watch.json (heartbeat).
Window: weekdays the desk calls RTH (6:30-1:00 PM PT) plus 15 min after; idle (30 s sleep) otherwise.
Secrets are read from files each loop and never logged or printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import util

JOB = "hal-exit-watch"
VERSION = "1.0.0-20261020"
CHECK_S = float(os.environ.get("HAL_EXIT_CHECK_S", "3"))
IDLE_S = 30.0
DEBOUNCE = 2
REFIRE_S = 120.0
MAX_FIRES = 3
STALE_S = 30.0            # stock / option quote age that counts as stale in market hours
STALE_HOLD_S = 60.0       # must be stale this long before quotes_stale fires
POST_WINDOW_MIN = 15      # keep checking 15 min after the 1:00 PM PT close
PRECLOSE_PT = "12:40"
PRECLOSE_DTE = 8
BAR_DELAY_S = 8           # fetch the 5-min bar this long after the boundary
URL_SECRET = "HAL_EXIT_WEBHOOK_URL"
KEY_SECRET = "HAL_EXIT_WEBHOOK_KEY"
PRICE_RULES = {"option_stop", "stock_stop", "target_option", "target_stock", "take_half"}
LEG = {"option_stop": "option", "target_option": "option", "take_half": "option", "stock_stop": "stock",
       "target_stock": "stock", "structure_break": "structure", "time_stop": "time", "preclose_dte": "time",
       "quotes_stale": "data"}
OCC_RE = re.compile(r"^([A-Z.]{1,6})(\d{6})([CP])(\d{8})$")


# ---------------------------------------------------------------- paths
def rules_path() -> Path:
    return Path(os.environ.get("HAL_EXIT_RULES", str(util.desk() / "paper-trades" / "hal-live" / "active-exit-rules.json")))


def data_dir() -> Path:
    return Path(os.environ.get("HAL_EXIT_DATA", str(Path.home() / "oid-data" / "hal-exit"))).expanduser()


def state_path() -> Path:
    return data_dir() / "state.json"


def status_path() -> Path:
    return util.desk() / "cache" / "hal-exit-watch.json"


def _secret_file(name: str) -> Path:
    return util.secrets_dir() / name


def _read_secret_file(name: str) -> Optional[str]:
    """File only (not env), so Jeffrey can add or rotate it without a restart. Never logged."""
    try:
        v = _secret_file(name).read_text(encoding="utf-8").strip()
        return v or None
    except OSError:
        return None


def mode() -> str:
    if (util.root() / "flags" / f"{JOB}.dry").exists() or os.environ.get("HAL_EXIT_FORCE_DRY") == "1":
        return "dry"
    return "live" if (_read_secret_file(URL_SECRET) and _read_secret_file(KEY_SECRET)) else "dry"


# ---------------------------------------------------------------- time helpers
def now_pt(ts: Optional[float] = None) -> datetime:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), util.PT)


def _hhmm(s: Optional[str]) -> Optional[tuple[int, int]]:
    if not s or not isinstance(s, str) or not re.match(r"^\d{1,2}:\d{2}$", s.strip()):
        return None
    h, m = s.strip().split(":")
    return int(h), int(m)


def _past(pt: datetime, hhmm: Optional[str]) -> bool:
    t = _hhmm(hhmm)
    return bool(t) and (pt.hour, pt.minute) >= t


def in_window(sess: str, pt: datetime) -> bool:
    """RTH per the desk calendar, plus POST_WINDOW_MIN after 1:00 PM PT on a trading day."""
    if sess == "rth":
        return True
    if pt.weekday() >= 5:
        return False
    close = pt.replace(hour=13, minute=0, second=0, microsecond=0)
    if close <= pt < close + timedelta(minutes=POST_WINDOW_MIN):
        # only if today was a trading day: the desk calendar said rth at 12:59
        return _session_at(close - timedelta(minutes=1)) == "rth"
    return False


def _session_at(pt: datetime) -> str:
    try:
        util.session()  # puts desk/quotes on sys.path
        import mini_client  # type: ignore
        return mini_client.current_session(pt)
    except Exception:  # noqa: BLE001
        return "closed"


# ---------------------------------------------------------------- rules file
def load_rules(path: Optional[Path] = None) -> tuple[list[dict], dict]:
    """Accepts Hal's seed {"owner","account","updated_at","seats":[]} and the v1 schema. Bad seats are skipped
    with a reason (never raise)."""
    p = path or rules_path()
    meta: dict[str, Any] = {"path": str(p), "exists": p.exists()}
    try:
        meta["mtime"] = p.stat().st_mtime
        meta["file_age_s"] = round(time.time() - p.stat().st_mtime, 1)
    except OSError:
        return [], meta
    d = util.read_json(p)
    if not isinstance(d, dict):
        meta["error"] = "unreadable or not an object"
        return [], meta
    meta.update(version=d.get("version", 1), updated_at=d.get("updated_at"), owner=d.get("owner"))
    seats, skipped = [], []
    for i, s in enumerate(d.get("seats") or []):
        ok, why = _valid_seat(s)
        if ok:
            seats.append(_normalize_seat(s, d))
        else:
            skipped.append({"i": i, "seat_id": (s or {}).get("seat_id") if isinstance(s, dict) else None, "why": why})
    meta["skipped"] = skipped
    return seats, meta


def _valid_seat(s: Any) -> tuple[bool, str]:
    if not isinstance(s, dict):
        return False, "not an object"
    if not s.get("seat_id"):
        return False, "seat_id missing"
    if str(s.get("status", "open")).lower() not in ("open", "active"):
        return False, f"status {s.get('status')}"
    if not s.get("underlying"):
        return False, "underlying missing"
    legs = s.get("legs")
    if s.get("occ_symbol") and not OCC_RE.match(str(s["occ_symbol"]).upper()):
        return False, "occ_symbol not OCC"
    if legs:
        for lg in legs:
            if not isinstance(lg, dict) or not OCC_RE.match(str(lg.get("occ_symbol", "")).upper()):
                return False, "legs[].occ_symbol not OCC"
    return True, ""


def _normalize_seat(s: dict, doc: dict) -> dict:
    s = dict(s)
    s["underlying"] = str(s["underlying"]).upper()
    if s.get("occ_symbol"):
        s["occ_symbol"] = str(s["occ_symbol"]).upper()
    s.setdefault("account", doc.get("account"))
    side = str(s.get("side") or "long_call").lower()
    s["side"] = side
    bull = not (side.endswith("put") or side in ("put_debit_spread", "call_credit_spread", "short_stock"))
    s["_bull"] = bull
    if not s.get("stock_stop_dir"):
        s["stock_stop_dir"] = "below" if bull else "above"
    if s.get("dte") is None:
        s["dte"] = _dte_from_occ(s.get("occ_symbol") or ((s.get("legs") or [{}])[0].get("occ_symbol")))
    return s


def _dte_from_occ(occ: Optional[str]) -> Optional[int]:
    m = OCC_RE.match(str(occ or "").upper())
    if not m:
        return None
    exp = datetime.strptime(m.group(2), "%y%m%d").date()
    return (exp - now_pt().date()).days


def seat_contracts(s: dict) -> list[str]:
    if s.get("legs"):
        return [str(lg["occ_symbol"]).upper() for lg in s["legs"]]
    return [s["occ_symbol"]] if s.get("occ_symbol") else []


# ---------------------------------------------------------------- market data (local collector)
def _mc():
    util.session()
    import mini_client  # type: ignore
    return mini_client


def fetch_stocks(syms: list[str]) -> dict:
    if not syms:
        return {}
    try:
        r = _mc().fetch_mini(syms, timeout=3.0)
        return r.get("quotes") or {}
    except Exception as e:  # noqa: BLE001
        util.log(JOB, f"stock fetch failed: {type(e).__name__}")
        return {}


def fetch_options(occs: list[str]) -> dict:
    if not occs:
        return {}
    try:
        util.session()
        import option_marks  # type: ignore
        return (option_marks.fetch_options(occs, timeout=3.0) or {}).get("rows") or {}
    except Exception as e:  # noqa: BLE001
        util.log(JOB, f"option fetch failed: {type(e).__name__}")
        return {}


def fetch_5m_close(sym: str, bar_end: datetime) -> Optional[dict]:
    """Last CLOSED 5-min SIP bar ending at bar_end (aware dt). Returns {t, c, end_pt} or None."""
    mc = _mc()
    start = (bar_end - timedelta(minutes=10)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = bar_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        _st, data, _lat = mc._http_get_json("/v1/bars", timeout=4.0, auth=True,
                                            params={"symbols": sym, "timeframe": "5Min", "start": start, "end": end})
    except Exception as e:  # noqa: BLE001
        util.log(JOB, f"bars fetch {sym} failed: {type(e).__name__}")
        return None
    bars = ((data or {}).get("bars") or {}).get(sym) or []
    want = (bar_end - timedelta(minutes=5)).astimezone(timezone.utc)
    for b in reversed(bars):
        try:
            t = datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if t == want:
            return {"t": b["t"], "c": b.get("c"), "end_pt": bar_end.astimezone(util.PT).strftime("%H:%M")}
    return None


def _num(x: Any) -> Optional[float]:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def option_view(s: dict, opt_rows: dict) -> dict:
    """Seat-level option mark. Single leg: mid/bid/ask/age of the contract. Multi-leg: sum(ratio*mid), bid side =
    what the position sells for at the touch (long legs at bid, short legs at ask), age = oldest leg."""
    occs = seat_contracts(s)
    if not occs:
        return {}
    if not s.get("legs"):
        r = opt_rows.get(occs[0]) or {}
        mid = _num(r.get("mid"))
        if mid is None:
            mid = _num(r.get("mark"))
        return {"mid": mid, "bid": _num(r.get("bid")), "ask": _num(r.get("ask")), "age_s": _num(r.get("age_s")),
                "quote_age_s": _num(r.get("quote_age_s")), "seeded": r.get("seeded"), "occ": occs[0]}
    mid = bid = 0.0
    ages = []
    for lg in s["legs"]:
        r = opt_rows.get(str(lg["occ_symbol"]).upper()) or {}
        ratio = float(lg.get("ratio", 1))
        m, b, a = _num(r.get("mid")), _num(r.get("bid")), _num(r.get("ask"))
        if m is None or b is None or a is None:
            return {"mid": None, "bid": None, "age_s": None, "legs_missing": True}
        mid += ratio * m
        bid += ratio * (b if ratio > 0 else a)
        ages.append(_num(r.get("age_s")) or 0)
    return {"mid": round(mid, 4), "bid": round(bid, 4), "age_s": max(ages) if ages else None, "occ": "+".join(occs)}


def stock_view(s: dict, stock_rows: dict) -> dict:
    r = stock_rows.get(s["underlying"]) or {}
    last = _num(r.get("last"))
    if last is None:
        last = _num(r.get("mid"))
    return {"last": last, "bid": _num(r.get("bid")), "ask": _num(r.get("ask")), "age_s": _num(r.get("age_s")),
            "trade_age_s": _num(r.get("trade_age_s"))}


# ---------------------------------------------------------------- rule evaluation
def evaluate(s: dict, st: dict, op: dict, bar: Optional[dict], pt: datetime) -> dict[str, dict]:
    """-> {rule: observed values} for every rule tripped on this check."""
    out: dict[str, dict] = {}
    last, mid, bid = st.get("last"), op.get("mid"), op.get("bid")
    o_ctx = {"option_mid": mid, "option_bid": bid, "option_ask": op.get("ask"), "option_age_s": op.get("age_s")}
    s_ctx = {"stock_last": last, "stock_bid": st.get("bid"), "stock_ask": st.get("ask"), "stock_age_s": st.get("age_s")}
    below = s["stock_stop_dir"] == "below"
    ss = _num(s.get("stock_stop"))
    stock_stop_hit = last is not None and ss is not None and ((below and last <= ss) or (not below and last >= ss))
    stop = _num(s.get("option_stop"))
    if mid is not None and stop is not None and mid <= stop:
        out["option_stop"] = {**o_ctx, **s_ctx, "level": stop, "bid_below_stop": bid is not None and bid <= stop,
                              "stock_stop": ss, "stock_stop_also_hit": stock_stop_hit,
                              "cause": "stock moved through its stop too" if stock_stop_hit else
                                       "option mark only (stock still inside its stop: decay / IV / spread)"}
    if stock_stop_hit:
        out["stock_stop"] = {**s_ctx, **o_ctx, "level": ss, "dir": s["stock_stop_dir"]}
    tgt = _num(s.get("target_option"))
    if mid is not None and tgt is not None and mid >= tgt:
        out["target_option"] = {**o_ctx, **s_ctx, "level": tgt}
    ts_ = _num(s.get("target_stock"))
    if last is not None and ts_ is not None and ((below and last >= ts_) or (not below and last <= ts_)):
        out["target_stock"] = {**s_ctx, **o_ctx, "level": ts_}
    entry, pct = _num(s.get("entry_px")), _num(s.get("take_half_pct"))
    if mid is not None and entry and pct and not s.get("half_taken"):
        lvl = round(entry * (1 + pct / 100.0), 4)
        if mid >= lvl:
            out["take_half"] = {**o_ctx, **s_ctx, "level": lvl, "entry_px": entry, "pnl_pct": round((mid / entry - 1) * 100, 1)}
    stc = s.get("structure") or {}
    lvl = _num(stc.get("level"))
    if bar and lvl is not None and bar.get("c") is not None:
        d = str(stc.get("dir") or ("below" if s["_bull"] else "above")).lower()
        c = float(bar["c"])
        if (d == "below" and c < lvl) or (d == "above" and c > lvl):
            out["structure_break"] = {"bar_5m_close": c, "bar_t": bar.get("t"), "bar_end_pt": bar.get("end_pt"),
                                      "level": lvl, "dir": d, **s_ctx}
    if s.get("time_stop_pt") and _past(pt, s["time_stop_pt"]):
        out["time_stop"] = {"time_stop_pt": s["time_stop_pt"], "now_pt": pt.strftime("%H:%M:%S"), **o_ctx, **s_ctx}
    dte = s.get("dte")
    if dte is not None and dte <= PRECLOSE_DTE and _past(pt, PRECLOSE_PT):
        out["preclose_dte"] = {"dte": dte, "warn_at_pt": PRECLOSE_PT, "now_pt": pt.strftime("%H:%M:%S"), **o_ctx, **s_ctx}
    return out


# ---------------------------------------------------------------- de-dupe
def decide(state: dict, key: str, tripped: bool, rule: str, now: float) -> bool:
    """Update the (seat, rule) state for this check and return True when a webhook should fire now."""
    e = state.setdefault(key, {"consec": 0, "fires": 0, "last_fire": 0.0, "first_trip": None, "cleared_at": None})
    if not tripped:
        if e["consec"]:
            e["cleared_at"] = now
        e["consec"] = 0
        return False
    e["consec"] += 1
    if e["first_trip"] is None:
        e["first_trip"] = now
    if rule in PRICE_RULES and e["consec"] < DEBOUNCE:
        return False
    if e["fires"] >= MAX_FIRES:
        return False
    if e["fires"] and now - e["last_fire"] < REFIRE_S:
        return False
    e["fires"] += 1
    e["last_fire"] = now
    return True


# ---------------------------------------------------------------- webhook
def payload(s: dict, rule: str, obs: dict, fire_n: int, first_trip: Optional[float], meta: dict, md: str) -> dict:
    ages = [a for a in (obs.get("stock_age_s"), obs.get("option_age_s")) if a is not None]
    now = time.time()
    return {
        "source": "mini:hal-exit-watch", "event": "exit_rule_tripped", "status": "trigger", "mode": md,
        "seat_id": s["seat_id"], "account": s.get("account"), "underlying": s["underlying"],
        "occ_symbol": s.get("occ_symbol") or "+".join(seat_contracts(s)) or None, "side": s.get("side"), "qty": s.get("qty"),
        "rule": rule, "leg": LEG.get(rule, "?"), "observed": obs,
        "quote_age_s": round(max(ages), 2) if ages else None,
        "fire_n": fire_n, "max_fires": MAX_FIRES, "refire_s": REFIRE_S,
        "first_tripped_at": util.utc_iso(first_trip) if first_trip else None,
        "ts": util.utc_iso(now), "ts_pt": util.now_pt_str(now),
        "rules_updated_at": meta.get("updated_at"), "watcher_version": VERSION,
        "detail": _detail(s, rule, obs), "never_trades": True,
        "note": "Exit alert only. The watcher places no orders; Hal decides and sends the close.",
    }


def _detail(s: dict, rule: str, o: dict) -> str:
    f = lambda v: "n/a" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))  # noqa: E731
    base = f"{s['seat_id']} {s['underlying']} {s.get('occ_symbol') or ''} {rule} ({LEG.get(rule)})"
    if rule == "option_stop":
        return f"{base}: mid {f(o.get('option_mid'))} <= stop {f(o.get('level'))}, bid {f(o.get('option_bid'))}; {o.get('cause')}"
    if rule in ("stock_stop", "target_stock"):
        return f"{base}: last {f(o.get('stock_last'))} vs {f(o.get('level'))}"
    if rule in ("target_option", "take_half"):
        return f"{base}: mid {f(o.get('option_mid'))} >= {f(o.get('level'))}"
    if rule == "structure_break":
        return f"{base}: 5m close {f(o.get('bar_5m_close'))} {o.get('dir')} {f(o.get('level'))} (bar ending {o.get('bar_end_pt')} PT)"
    if rule == "quotes_stale":
        return f"{base}: stock age {f(o.get('stock_age_s'))}s, option age {f(o.get('option_age_s'))}s"
    return f"{base}: now {o.get('now_pt')} PT"


def post(body: dict) -> int:
    url, key = _read_secret_file(URL_SECRET), _read_secret_file(KEY_SECRET)
    if not (url and key):
        return 0
    req = urllib.request.Request(url, data=json.dumps(body, default=str).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                          "User-Agent": "oid-mini-hal-exit-watch/1"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        try:
            util.log(JOB, f"webhook HTTP {e.code}: {e.read()[:200]!r}")
        except Exception:  # noqa: BLE001
            pass
        return e.code
    except Exception as e:  # noqa: BLE001
        util.log(JOB, f"webhook error {type(e).__name__}")
        return -1


# ---------------------------------------------------------------- logging
def jlog(row: dict, ts: Optional[float] = None) -> None:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    p = d / f"{now_pt(ts).strftime('%Y%m%d')}.jsonl"
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------- one check
class Watcher:
    def __init__(self, *, force_window: bool = False, rules_file: Optional[Path] = None, no_post: bool = False):
        self.force_window = force_window
        self.rules_file = rules_file
        self.no_post = no_post
        self.state = util.read_json(state_path()) or {}
        if self.state.get("day") != now_pt().strftime("%Y-%m-%d"):
            self.state = {"day": now_pt().strftime("%Y-%m-%d"), "rules": {}, "stale_since": {}}
        self.bars: dict[str, dict] = {}       # underlying -> last closed 5m bar
        self.bar_fetched: dict[str, str] = {}  # underlying -> bar_end iso already fetched
        self.last_mode: Optional[str] = None

    def _bars(self, unds: list[str], pt: datetime) -> None:
        m = pt.minute - pt.minute % 5
        bar_end = pt.replace(minute=m, second=0, microsecond=0)
        if (pt - bar_end).total_seconds() < BAR_DELAY_S:
            bar_end -= timedelta(minutes=5)
        key = bar_end.isoformat()
        for u in unds:
            if self.bar_fetched.get(u) == key:
                continue
            b = fetch_5m_close(u, bar_end)
            self.bar_fetched[u] = key  # one try per bar; a missed bar is logged as bar=None
            if b:
                self.bars[u] = b

    def check(self) -> dict:
        now = time.time()
        pt = now_pt(now)
        md = "dry" if self.no_post else mode()
        if md != self.last_mode:
            util.log(JOB, f"mode {md} (webhook secret files {'present' if md == 'live' else 'absent or dry flag'})")
            self.last_mode = md
        seats, meta = load_rules(self.rules_file)
        unds = sorted({s["underlying"] for s in seats})
        occs = sorted({o for s in seats for o in seat_contracts(s)})
        stock_rows = fetch_stocks(unds)
        opt_rows = fetch_options(occs)
        self._bars([u for u in unds if any((x.get("structure") or {}).get("level") is not None for x in seats if x["underlying"] == u)], pt)
        rs = self.state.setdefault("rules", {})
        stale_since = self.state.setdefault("stale_since", {})
        summary = []
        live_keys = set()
        for s in seats:
            sv, ov = stock_view(s, stock_rows), option_view(s, opt_rows)
            tripped = evaluate(s, sv, ov, self.bars.get(s["underlying"]), pt)
            # data health
            stale = []
            if sv.get("age_s") is None or sv["age_s"] > STALE_S:
                stale.append("stock")
            if seat_contracts(s) and (ov.get("age_s") is None or ov["age_s"] > STALE_S):
                stale.append("option")
            if stale:
                stale_since.setdefault(s["seat_id"], now)
                if now - stale_since[s["seat_id"]] >= STALE_HOLD_S:
                    tripped["quotes_stale"] = {"stale": stale, "stock_age_s": sv.get("age_s"), "option_age_s": ov.get("age_s"),
                                               "stale_for_s": round(now - stale_since[s["seat_id"]], 1)}
            else:
                stale_since.pop(s["seat_id"], None)
            fired = []
            for rule in sorted(LEG):
                key = f"{s['seat_id']}|{rule}"
                live_keys.add(key)
                if decide(rs, key, rule in tripped, rule, now):
                    e = rs[key]
                    body = payload(s, rule, tripped[rule], e["fires"], e["first_trip"], meta, md)
                    code = post(body) if md == "live" else None
                    body["http"] = code
                    jlog({"type": "trip", **body}, now)
                    util.log(JOB, f"TRIP[{md}] {body['detail']} fire {e['fires']}/{MAX_FIRES} http={code}")
                    fired.append({"rule": rule, "fire_n": e["fires"], "http": code})
            row = {"type": "check", "ts": util.utc_iso(now), "ts_pt": util.now_pt_str(now), "mode": md,
                   "seat_id": s["seat_id"], "underlying": s["underlying"], "occ": ov.get("occ"),
                   "stock": sv, "option": {k: ov.get(k) for k in ("mid", "bid", "ask", "age_s", "seeded")},
                   "bar_5m": self.bars.get(s["underlying"]), "tripped": sorted(tripped), "fired": fired}
            jlog(row, now)
            summary.append({k: row[k] for k in ("seat_id", "underlying", "occ", "tripped", "fired")} |
                           {"stock_last": sv.get("last"), "stock_age_s": sv.get("age_s"),
                            "option_mid": ov.get("mid"), "option_bid": ov.get("bid"), "option_age_s": ov.get("age_s")})
        for k in [k for k in rs if k not in live_keys]:   # seat closed / removed: forget its state
            rs.pop(k, None)
        if not seats:
            jlog({"type": "check", "ts": util.utc_iso(now), "ts_pt": util.now_pt_str(now), "mode": md, "seats": 0,
                  "rules_exists": meta.get("exists"), "rules_updated_at": meta.get("updated_at")}, now)
        util.atomic_write_json(state_path(), self.state)
        st = {"as_of": util.utc_iso(now), "as_of_pt": util.now_pt_str(now), "version": VERSION, "mode": md,
              "window": "active", "check_s": CHECK_S, "rules": {k: meta.get(k) for k in ("path", "exists", "updated_at", "file_age_s", "skipped", "error")},
              "seats": summary, "never_trades": True}
        util.atomic_write_json(status_path(), st)
        return st

    def idle(self) -> None:
        now = time.time()
        _, meta = load_rules(self.rules_file)
        util.atomic_write_json(status_path(), {"as_of": util.utc_iso(now), "as_of_pt": util.now_pt_str(now),
                                               "version": VERSION, "mode": mode(), "window": "idle (outside RTH + 15 min)",
                                               "rules": {k: meta.get(k) for k in ("exists", "updated_at", "file_age_s")},
                                               "never_trades": True})

    def loop(self) -> None:
        util.log(JOB, f"start v{VERSION} check every {CHECK_S}s; rules {self.rules_file or rules_path()}")
        while True:
            t0 = time.time()
            pt = now_pt(t0)
            try:
                if self.force_window or in_window(util.session(), pt):
                    if self.state.get("day") != pt.strftime("%Y-%m-%d"):
                        self.state = {"day": pt.strftime("%Y-%m-%d"), "rules": {}, "stale_since": {}}
                    self.check()
                    time.sleep(max(0.5, CHECK_S - (time.time() - t0)))
                else:
                    self.idle()
                    time.sleep(IDLE_S)
            except Exception as e:  # noqa: BLE001
                util.log(JOB, f"check error {type(e).__name__}: {str(e)[:200]}")
                time.sleep(CHECK_S)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Hal fast exit watcher (never trades)")
    ap.add_argument("cmd", nargs="?", default="loop", choices=["loop", "once", "status", "mode"])
    ap.add_argument("--force-window", action="store_true", help="test: check even outside RTH")
    ap.add_argument("--rules", help="test: alternate rules file")
    ap.add_argument("--no-post", action="store_true", help="never POST (dry) regardless of secret files")
    ap.add_argument("--count", type=int, default=1, help="once: number of checks")
    a = ap.parse_args(argv)
    if a.cmd == "mode":
        print(mode())
        return 0
    if a.cmd == "status":
        print(json.dumps(util.read_json(status_path()) or {"status": "never ran"}, indent=1))
        return 0
    w = Watcher(force_window=a.force_window, rules_file=Path(a.rules) if a.rules else None, no_post=a.no_post)
    if a.cmd == "loop":
        w.loop()
        return 0
    for i in range(a.count):
        t0 = time.time()
        r = w.check()
        print(json.dumps({"i": i, "mode": r["mode"], "seats": r["seats"]}, default=str))
        if i < a.count - 1:
            time.sleep(max(0.5, CHECK_S - (time.time() - t0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
