#!/usr/bin/env python3
"""OID mini trigger engine: deterministic desk checks, wakes Rose only on events.

Runs once per invocation (launchd StartInterval 60). Stdlib only. Research/alerts only:
it NEVER calls Robinhood, FlashAlpha, UW or any broker, and NEVER places orders.
FA budget impact is zero: walls are read from market-data/latest/fa-levels.json (fa-focus job).

Checks: 5-min closes across gamma flip / seat exit lines; call/put wall rolls (fresh walls only,
>walls_stale_min => no wall event); +10/+20/-10/-25% option-mark bands per open seat (OPRA mids,
live seats flagged verify_on_rh); +20% scale-out due; new paper/live seats; stale/dead feeds;
NVDA peer-driver moves; forwards focus_watch 5-min events. Each event fires once (state file).

vol_surge (2026-10-18): separate fast loop `--vol-surge-loop` (launchd com.oid.desk.volsurge, ~2 s) on the
collector's /v1/live-volume; DRY-RUN unless config vol_surge.live=true AND global live. See VS_DEFAULTS.
Modes: --dry-run (default unless OID_TRIGGERS_MODE=live) logs to events.jsonl only.
  python3 oid_triggers.py [--dry-run|--live] [--force-session] [--desk DIR] [--state DIR]
Webhook: URL+key read from ~/.oid/webhook.env (mode 600) at send time; never logged.
"""
from __future__ import annotations

import argparse, glob, json, os, re, stat, sys, threading, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oid_surges  # noqa: E402  (2026-10-18 v0.5.0: news_surge + surges archive; log-only)

PT = ZoneInfo("America/Los_Angeles")
HERE = Path(__file__).resolve().parent
OPEN = {"open", "live", "paper", "watching"}


def jload(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return default


def now_pt():
    return datetime.now(PT)


def epoch_of(path, key):
    try:
        if key == "mtime":
            return os.path.getmtime(path)
        d = jload(path, {}) or {}
        v = d.get(key)
        return float(v) if v is not None else os.path.getmtime(path)
    except Exception:
        return None


def iso_epoch(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")[:26] + ("+00:00" if str(s).endswith("Z") and "+" not in str(s)[:26] else "")).timestamp()
    except Exception:
        try:
            return datetime.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            return None


# ---------- seats ----------
MON = r"(\d{4})-(\d{2})-(\d{2})"


def occ(sym, exp, right, strike):
    y, m, d = exp.split("-")
    return f"{sym}{y[2:]}{m}{d}{right[0].upper()}{int(round(float(strike) * 1000)):08d}"


def seat_legs(s):
    """Return (legs, kind). legs = [(occ, sign)] where mark = sum(sign*mid). kind debit|credit."""
    if s.get("_occ"):
        return [(s["_occ"], 1)], "debit"
    sym = (s.get("underlying") or s.get("symbol") or "").upper()
    c = str(s.get("contract") or "")
    m = re.search(MON + r"\s+([\d.]+)/([\d.]+)\s+(put|call)", c, re.I)
    if m:
        exp = f"{m[1]}-{m[2]}-{m[3]}"
        a, b, r = float(m[4]), float(m[5]), m[6]
        hi, lo = max(a, b), min(a, b)
        credit = "credit" in c.lower() or "credit" in str(s.get("side", ""))
        if r.lower() == "put":
            short, long_ = (hi, lo) if credit else (lo, hi)
        else:
            short, long_ = (lo, hi) if credit else (hi, lo)
        return [(occ(sym, exp, r, short), 1), (occ(sym, exp, r, long_), -1)] if credit else \
               [(occ(sym, exp, r, long_), 1), (occ(sym, exp, r, short), -1)], ("credit" if credit else "debit")
    m = re.search(MON + r"\s+([\d.]+)\s*(C|P|call|put)\b", c, re.I)
    if m:
        return [(occ(sym, f"{m[1]}-{m[2]}-{m[3]}", m[5], m[4]), 1)], "debit"
    return [], None


def entry_px(s, kind):
    keys = ["entryCredit"] if kind == "credit" else ["entryFill", "entry", "entryPrice", "fillPrice", "entryAsk", "entryMark"]
    for k in keys:
        v = s.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def is_live(s):
    return bool(s.get("live")) or "-LIVE-" in str(s.get("id", "")).upper()


def load_seats(desk):
    """Open seats from every desk ledger the mini receives, plus live RH option positions not covered by a seat.

    desk/trades.json (box layout) and desk/paper-trades/trades.json (desk-state push layout) are both read.
    Seats flagged live (live:true or -LIVE- id) are book=live so their events carry verify_on_rh.
    """
    seats = {}
    po = jload(desk / "paper-trades/paper-open.json", {}) or {}
    rows = list(po.get("seats") or [])
    for rel in ("trades.json", "paper-trades/trades.json"):
        tr = jload(desk / rel, {}) or {}
        rows += (tr.get("trades") or []) if isinstance(tr, dict) else (tr if isinstance(tr, list) else [])
    for s in rows:
        if isinstance(s, dict) and s.get("id") and str(s.get("status", "")).lower() in OPEN:
            seats[s["id"]] = dict(s, _book="live" if is_live(s) else "paper")
    for p in glob.glob(str(desk / "paper-trades/hal-live/*.json")) + glob.glob(str(desk / "paper-trades/rose-live/*.json")):
        s = jload(p, {}) or {}
        if s.get("id") and str(s.get("status", "")).lower() in OPEN:
            s = dict(s, _book="live")
            s.setdefault("symbol", str(s.get("contract", "")).split(" ")[0])
            seats[s["id"]] = s
    # live RH option positions (both accounts) that no open seat covers: mark on OPRA vs RH avg cost
    covered = set()
    for s in seats.values():
        covered |= {o for o, _ in (seat_legs(s)[0] or [])}
    rh = jload(desk / "cache/rh-live-option-positions.json", {}) or {}
    for pos in (rh.get("positions") or []) + (rh.get("agentic_8444") or []):
        occ_ = str(pos.get("occ") or "")
        try:
            qty, avg = float(pos.get("qty") or 0), float(pos.get("avg") or 0)
        except Exception:
            continue
        if not occ_ or occ_ in covered or qty <= 0 or avg <= 0:
            continue
        acct = str(pos.get("acct") or ("8444" if pos in (rh.get("agentic_8444") or []) else ""))
        sid = f"RH-{acct}-{occ_}"
        seats[sid] = {"id": sid, "status": "live", "_occ": occ_, "symbol": re.match(r"[A-Z]+", occ_)[0],
                      "contract": occ_, "entryPrice": avg, "qty": qty, "agent": f"RH acct {acct}", "_book": "live",
                      "_rh_updated": rh.get("updated_at_pt")}
    return seats


# ---------- bars ----------
def closed_bars(desk, sym):
    b = jload(desk / f"cache/bars/{sym}-5m.json", {}) or {}
    return [x for x in (b.get("bars") or []) if not x.get("partial")]


# ---------- engine ----------
class Engine:
    def __init__(self, desk, state_dir, cfg, dry):
        self.desk, self.state_dir, self.cfg, self.dry = desk, state_dir, cfg, dry
        self.state_path = state_dir / "state.json"
        self.st = jload(self.state_path, {}) or {}
        today = now_pt().strftime("%Y-%m-%d")
        if self.st.get("date") != today:  # per-session dedupe; carry seat baseline + walls
            self.st = {"date": today, "fired": {}, "known_seats": self.st.get("known_seats"),
                       "walls": self.st.get("walls", {}), "focus_offset": 0}
        self.events = []

    def fire(self, key, event_type, symbol, seat_id, details, data_stamp):
        if key in self.st["fired"]:
            return
        self.st["fired"][key] = time.time()
        self.events.append({"event_type": event_type, "symbol": symbol, "seat_id": seat_id,
                            "details": details, "data_stamp": data_stamp,
                            "engine_pt": now_pt().strftime("%Y-%m-%d %I:%M:%S %p PT"), "dry_run": self.dry})

    # walls
    def walls(self):
        d = jload(self.desk / "market-data/latest/fa-levels.json", {}) or {}
        return ((d.get("payload") or {}).get("levels") or {})

    def wall_fresh(self, w):
        e = iso_epoch(w.get("as_of")) if w else None
        return e is not None and time.time() - e <= self.cfg["walls_stale_min"] * 60, e

    def check_seats(self, seats, walls, oq):
        bands = sorted(self.cfg["move_bands_pct"])
        maxage = self.cfg["option_quote_max_age_s"]
        for sid, s in seats.items():
            sym = (s.get("underlying") or s.get("symbol") or "").upper()
            legs, kind = seat_legs(s)
            ent = entry_px(s, kind) if kind else None
            mids, stamp, ok = [], None, bool(legs)
            for o, sign in legs:
                q = oq.get(o) or {}
                mid = q.get("mid")
                if mid is None or (q.get("age_s") or 1e9) > maxage:
                    ok = False
                    break
                mids.append(sign * float(mid)); stamp = q.get("quote_time") or stamp
            if ok and ent:
                mark = sum(mids)
                pct = ((ent - mark) / ent if kind == "credit" else (mark - ent) / ent) * 100
                det = {"book": s["_book"], "agent": s.get("agent") or s.get("trader"), "contract": s.get("contract"),
                       "entry": ent, "opra_mark": round(mark, 3), "pnl_pct": round(pct, 1), "kind": kind,
                       "verify_on_rh": s["_book"] == "live"}
                for b in bands:
                    if (b > 0 and pct >= b) or (b < 0 and pct <= b):
                        self.fire(f"move:{sid}:{b}", "position_move", sym, sid, dict(det, band_pct=b), stamp)
                if pct >= self.cfg["scale_out_pct"] and not (s.get("scaleOutDone") or s.get("realizedPnlUsd") or s.get("scaled_out")):
                    self.fire(f"scale:{sid}", "scale_out_due", sym, sid, det, stamp)
            # seat exit lines + flip on 5-min closes
            bars = closed_bars(self.desk, sym)
            if len(bars) >= 2:
                prev, last = bars[-2]["c"], bars[-1]["c"]
                lines = list(self.cfg.get("seat_exit_lines", {}).get(sid, []))
                w = walls.get(sym) or {}
                if w.get("gamma_flip"):
                    lines.append({"price": float(w["gamma_flip"]), "side": "both", "name": "gamma_flip"})
                for ln in lines:
                    p = float(ln["price"]); nm = ln.get("name", "line")
                    dn = prev >= p > last; up = prev <= p < last
                    if (dn and ln.get("side") in ("below", "both")) or (up and ln.get("side") in ("above", "both")):
                        self.fire(f"x:{sid}:{nm}:{bars[-1]['t']}", "close5_cross", sym, sid,
                                  {"line": nm, "price": round(p, 3), "dir": "down" if dn else "up", "close": last, "prev_close": prev,
                                   "bar_pt": bars[-1].get("pt")}, bars[-1]["t"])

    def check_new_seats(self, seats):
        known = self.st.get("known_seats")
        cur = sorted(seats)
        if known is not None:
            for sid in set(cur) - set(known):
                s = seats[sid]
                self.fire(f"new:{sid}", "new_seat", (s.get("symbol") or "").upper(), sid,
                          {"book": s["_book"], "agent": s.get("agent") or s.get("trader"), "contract": s.get("contract")}, None)
            for sid in set(known) - set(cur):
                self.fire(f"gone:{sid}", "seat_closed", None, sid, {"note": "seat no longer open in desk files"}, None)
        self.st["known_seats"] = cur

    def check_walls(self, walls, syms):
        for sym in syms:
            w = walls.get(sym)
            if not w:
                continue
            fresh, e = self.wall_fresh(w)
            prior = self.st["walls"].get(sym)
            curw = {"cw": w.get("call_wall"), "pw": w.get("put_wall")}
            if not fresh:
                continue  # stale walls => no wall-break/roll event
            if prior:
                for k, nm in (("cw", "call_wall"), ("pw", "put_wall")):
                    if prior.get(k) is not None and curw[k] is not None and prior[k] != curw[k]:
                        self.fire(f"roll:{sym}:{k}:{prior[k]}->{curw[k]}:{w.get('as_of')}", "wall_roll", sym, None,
                                  {"wall": nm, "from": prior[k], "to": curw[k], "spot": w.get("underlying_price")}, w.get("as_of"))
            self.st["walls"][sym] = curw

    def check_feeds(self):
        for rel, f in self.cfg["feeds"].items():
            e = epoch_of(self.desk / rel, f["epoch_key"])
            age = None if e is None else time.time() - e
            lvl = "dead" if age is None or age > f["dead_s"] else "stale" if age > f["stale_s"] else None
            prev = self.st.setdefault("feed_level", {}).get(rel)
            if lvl and lvl != prev:
                self.fire(f"feed:{rel}:{lvl}:{int(time.time() // 1800)}", f"feed_{lvl}", None, None,
                          {"feed": rel, "age_s": None if age is None else round(age)}, None)
            if not lvl and prev:
                self.fire(f"feed:{rel}:recovered:{int(time.time())}", "feed_recovered", None, None, {"feed": rel}, None)
            self.st["feed_level"][rel] = lvl

    def prev_closes(self):
        d = jload(self.desk / "market-data/latest/rh-quotes.json", {}) or {}
        q = ((d.get("payload") or {}).get("quotes") or d.get("quotes") or {})
        return {k: (v.get("prev_close") or v.get("previous_close")) for k, v in q.items() if isinstance(v, dict)}

    def check_drivers(self, quotes):
        c = self.cfg.get("nvda_drivers") or {}
        per = c.get("per_peer") or {}
        pcs = None
        for sym in c.get("peers", []):
            mp = float((per.get(sym) or {}).get("move_pct", c["move_pct"]))
            m15p = float((per.get(sym) or {}).get("move15_pct", c["move15_pct"]))
            q = quotes.get(sym) or {}
            last, pc = q.get("last") or q.get("mid"), q.get("prev_close")
            if last and not pc:
                pcs = self.prev_closes() if pcs is None else pcs
                pc = pcs.get(sym)
            if last and pc:
                pct = (float(last) / float(pc) - 1) * 100
                if abs(pct) >= mp:
                    b = int(abs(pct) // mp) * (1 if pct > 0 else -1)
                    self.fire(f"drv:{sym}:{b}", "nvda_driver_move", sym, None,
                              {"day_pct": round(pct, 2), "band": round(b * mp, 2), "last": last}, q.get("quote_time"))
            bars = closed_bars(self.desk, sym)
            if len(bars) >= 4:
                m15 = (bars[-1]["c"] / bars[-4]["c"] - 1) * 100
                if abs(m15) >= m15p:
                    self.fire(f"drv15:{sym}:{bars[-1]['t']}", "nvda_driver_move15", sym, None,
                              {"move15_pct": round(m15, 2), "close": bars[-1]["c"]}, bars[-1]["t"])

    def forward_focus(self, walls):
        p = self.desk / "cache/focus-watch-events.jsonl"
        want = set(self.cfg["forward_focus_events"])
        try:
            size = p.stat().st_size
        except FileNotFoundError:
            return
        off = self.st.get("focus_offset", 0)
        if off > size or off == 0:
            off = size if off == 0 and self.st.get("focus_init") else (0 if off > size else off)
        if not self.st.get("focus_init"):
            self.st["focus_init"] = True; self.st["focus_offset"] = size; return  # start from now
        with open(p) as f:
            f.seek(off)
            for line in f:
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("event") not in want:
                    continue
                sym = ev.get("symbol")
                if "wall" in str(ev.get("level_kind") or ev.get("event")):
                    if not self.wall_fresh(walls.get(sym))[0]:
                        continue  # walls >10 min old: no wall-break event
                self.fire(f"fw:{ev.get('id')}", "focus_" + ev["event"], sym, ",".join(ev.get("seats") or []) or None,
                          {k: ev.get(k) for k in ("level", "level_price", "spot", "note", "ts_pt")}, ev.get("ts_pt"))
            self.st["focus_offset"] = f.tell()

    def run(self):
        seats = load_seats(self.desk)
        walls = self.walls()
        oq = (jload(self.desk / "cache/mini-option-quotes.json", {}) or {}).get("quotes") or {}
        quotes = (jload(self.desk / "cache/mini-quotes.json", {}) or {}).get("quotes") or {}
        syms = sorted({(s.get("underlying") or s.get("symbol") or "").upper() for s in seats.values()} | {"NVDA"})
        for fn in (lambda: self.check_new_seats(seats), lambda: self.check_seats(seats, walls, oq),
                   lambda: self.check_walls(walls, syms), self.check_feeds,
                   lambda: self.check_drivers(quotes), lambda: self.forward_focus(walls)):
            try:
                fn()
            except Exception as e:  # one bad check never blocks the rest
                self.log_err(repr(e))
        return self.events

    def log_err(self, msg):
        with open(self.state_dir / "errors.log", "a") as f:
            f.write(f"{now_pt().isoformat()} {msg}\n")

    def save(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.st, indent=1)); tmp.replace(self.state_path)


# ---------- webhook ----------
def read_env(path):
    p = Path(path).expanduser()
    if not p.exists():
        return None, "webhook.env missing"
    if stat.S_IMODE(p.stat().st_mode) & 0o077:
        return None, "webhook.env must be chmod 600"
    env = {}
    for ln in p.read_text().splitlines():
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
    if not env.get("OID_WEBHOOK_URL") or not env.get("OID_WEBHOOK_KEY"):
        return None, "webhook URL/key not filled in"
    return env, None


def collapse(evs):
    """Drop focus_wall_roll when the engine's own wall_roll for the same symbol+wall+price is in the same batch."""
    own = {(e["symbol"], (e.get("details") or {}).get("wall"), float((e.get("details") or {}).get("to") or 0))
           for e in evs if e["event_type"] == "wall_roll"}
    out = []
    for e in evs:
        d = e.get("details") or {}
        if e["event_type"] == "focus_wall_roll" and (e["symbol"], d.get("level"), float(d.get("level_price") or 0)) in own:
            continue
        out.append(e)
    return out


def batch_body(evs):
    """One POST per run. A single event keeps the original flat shape; several become event_type=batch."""
    slim = [{k: ev[k] for k in ("event_type", "symbol", "seat_id", "details", "data_stamp")} for ev in evs]
    if len(slim) == 1:
        return slim[0]
    syms = sorted({e["symbol"] for e in slim if e["symbol"]})
    return {"event_type": "batch", "symbol": ",".join(syms) or None,
            "seat_id": ",".join(sorted({e["seat_id"] for e in slim if e["seat_id"]})) or None,
            "details": {"count": len(slim), "types": sorted({e["event_type"] for e in slim}), "events": slim},
            "data_stamp": now_pt().strftime("%Y-%m-%d %I:%M:%S %p PT")}


def send(body, env, timeout=15):
    hdr = env.get("OID_WEBHOOK_KEY_HEADER", "Authorization")
    val = env["OID_WEBHOOK_KEY"]
    if hdr.lower() == "authorization" and not val.lower().startswith("bearer "):
        val = "Bearer " + val
    req = urllib.request.Request(env["OID_WEBHOOK_URL"], data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", hdr: val})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status



# ---------- vol_surge (fast loop, 2026-10-18) ----------
# Seconds-level volume surge + level break. Runs as its OWN long-lived process (launchd com.oid.desk.volsurge,
# `oid_triggers.py --vol-surge-loop`, every ~2 s in RTH); the 60 s engine above is untouched. Reads the mini
# collector's GET /v1/live-volume (rolling 60 s SIP print volume vs same-minute 20-session norm). Own dedupe file
# (volsurge-state.json) so the two processes never write the same state. Starts DRY-RUN: it only POSTs when
# config vol_surge.live is true AND global mode is live (OID_TRIGGERS_MODE=live / --live).
VS_DEFAULTS = {
    "enabled": True, "live": False, "interval_s": 2.0,
    "url": "http://127.0.0.1:8787/v1/live-volume", "token_file": "~/oid-quote/secrets/OID_QUOTE_TOKEN",
    "min_rvol_1m": 3.0, "min_shares_60s": 20000, "min_shares_floor_low": 2000, "per_symbol_min_shares_60s": {},
    "skip_open_min": 2, "max_lag_s": 5.0, "max_last_age_s": 15.0, "max_stream_age_s": 5.0,
    "break_buffer_bps": 2.0, "ref_lookback_s": 60, "levels_max_age_min": 30,
    "use_walls": True, "use_flip": True, "use_seat_lines": True, "use_day_extremes": True,
    "symbols": None, "seats_refresh_s": 15, "require_norms_current": True,
    # 2026-10-18 ladder dry run: POST dry-run vol_surge events (tagged dry_run/no-trade) to wake the RH book pull.
    # Separate from `live`: never changes trading behaviour. Off unless notify_dry=true.
    "notify_dry": False, "notify_max_per_day": 20, "notify_dedupe_min": 5.0, "notify_timeout_s": 8.0,
}


def vs_cfg(cfg):
    c = dict(VS_DEFAULTS)
    c.update({k: v for k, v in ((cfg or {}).get("vol_surge") or {}).items() if not str(k).startswith("_")})
    return c


def read_secret_file(path):
    try:
        v = Path(path).expanduser().read_text().strip()
        return v or None
    except Exception:
        return None


def fetch_live_volume(url, token, timeout=2.0):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class VolSurge:
    def __init__(self, desk, state_dir, cfg, dry):
        self.desk, self.state_dir, self.cfg, self.dry = desk, state_dir, cfg, dry
        self.state_path = state_dir / "volsurge-state.json"
        self.st = jload(self.state_path, {}) or {}
        self.events = []
        self._seats_at, self._seats, self._walls = 0.0, {}, {}
        self.ids = oid_surges.SurgeIds()
        self.rows = {}  # surge_id -> live-volume row at fire (archive only; never written to events.jsonl)

    def level_hit(self, sym, row, t):
        """First level vol_surge's price test would accept right now (ignores its once-per-level dedupe)."""
        vc = vs_cfg(self.cfg)
        buf = float(vc["break_buffer_bps"]) / 1e4
        refk = {10: "px_10s_ago", 30: "px_30s_ago"}.get(int(vc["ref_lookback_s"]), "px_60s_ago")
        ref, last = row.get(refk) or row.get("px_60s_ago") or row.get("px_30s_ago"), row.get("last")
        if ref is None or last is None:
            return None
        for name, px, side in self.levels(sym, row, t)[0]:
            up = ref <= px and last >= px * (1 + buf)
            dn = ref >= px and last <= px * (1 - buf)
            if (up and side in ("above", "both")) or (dn and side in ("below", "both")):
                return (name, round(px, 4))
        return None

    def _roll_day(self, t):
        today = datetime.fromtimestamp(t, PT).strftime("%Y-%m-%d")
        if self.st.get("date") != today:
            self.st = {"date": today, "fired": {}}

    def refresh_desk(self, t, force=False):
        vc = vs_cfg(self.cfg)
        if force or t - self._seats_at >= float(vc["seats_refresh_s"]):
            try:
                self._seats = load_seats(self.desk)
            except Exception:
                self._seats = {}
            d = jload(self.desk / "market-data/latest/fa-levels.json", {}) or {}
            self._walls = ((d.get("payload") or {}).get("levels") or {})
            self._seats_at = t

    def levels(self, sym, row, t):
        vc = vs_cfg(self.cfg)
        out = []  # (name, price, side)
        w = self._walls.get(sym) or {}
        e = iso_epoch(w.get("as_of")) if w else None
        fresh = e is not None and t - e <= float(vc["levels_max_age_min"]) * 60
        if fresh:
            if vc["use_walls"]:
                for k in ("call_wall", "put_wall"):
                    if w.get(k):
                        out.append((k, float(w[k]), "both"))
            if vc["use_flip"] and w.get("gamma_flip"):
                out.append(("gamma_flip", float(w["gamma_flip"]), "both"))
        if vc["use_seat_lines"]:
            lines = self.cfg.get("seat_exit_lines") or {}
            for sid, s in self._seats.items():
                if (s.get("underlying") or s.get("symbol") or "").upper() != sym:
                    continue
                for ln in (lines.get(sid) or []):
                    try:
                        out.append((f"seat:{sid}:{ln.get('name', 'line')}", float(ln["price"]), ln.get("side", "both")))
                    except Exception:
                        pass
        if vc["use_day_extremes"]:
            if row.get("ref_high_5m"):
                out.append(("day_high", float(row["ref_high_5m"]), "above"))
            if row.get("ref_low_5m"):
                out.append(("day_low", float(row["ref_low_5m"]), "below"))
        return out, fresh

    def gate(self, live, t):
        """Global skips: off-RTH, first N minutes, half day, stale stream, norms not built for today."""
        vc = vs_cfg(self.cfg)
        slot = live.get("rth_slot", -1)
        if slot is None or slot < 0:
            return "off_rth"
        if slot < int(vc["skip_open_min"]):
            return "open_skip"
        if live.get("half_day"):
            return "half_day"
        st = live.get("stream") or {}
        if not st.get("connected"):
            return "stream_down"
        age = st.get("last_data_age_s")
        if age is None or age > float(vc["max_stream_age_s"]):
            return "stream_stale"
        if vc["require_norms_current"] and not (live.get("norms") or {}).get("current"):
            return "norms_not_current"
        return None

    def check(self, live, t=None):
        t = time.time() if t is None else t
        self._roll_day(t)
        vc = vs_cfg(self.cfg)
        why = self.gate(live, t)
        if why:
            return why
        buf = float(vc["break_buffer_bps"]) / 1e4
        per_min = vc.get("per_symbol_min_shares_60s") or {}
        want = set(vc["symbols"]) if vc.get("symbols") else None
        refk = {10: "px_10s_ago", 30: "px_30s_ago"}.get(int(vc["ref_lookback_s"]), "px_60s_ago")
        for sym, row in (live.get("symbols") or {}).items():
            if want is not None and sym not in want:
                continue
            rv, v60, last = row.get("rvol_1m"), row.get("vol_60s") or 0, row.get("last")
            if rv is None or last is None or rv < float(vc["min_rvol_1m"]):
                continue
            floor = per_min.get(sym)
            if floor is None:  # thin names: floor = their own median 1-min norm, clamped to [min_shares_floor_low, min_shares_60s]
                med = row.get("norm_median_1m")
                floor = vc["min_shares_60s"] if med is None else min(float(vc["min_shares_60s"]), max(float(vc["min_shares_floor_low"]), float(med)))
            if v60 < float(floor):
                continue
            if (row.get("lag_s") or 0) > float(vc["max_lag_s"]) or (row.get("last_age_s") or 1e9) > float(vc["max_last_age_s"]):
                continue
            ref = row.get(refk) or row.get("px_60s_ago") or row.get("px_30s_ago")
            if ref is None:
                continue
            lvls, fresh = self.levels(sym, row, t)
            for name, px, side in lvls:
                up = ref <= px and last >= px * (1 + buf)
                dn = ref >= px and last <= px * (1 - buf)
                if not ((up and side in ("above", "both")) or (dn and side in ("below", "both"))):
                    continue
                key = f"vs:{sym}:{name}" if name in ("day_high", "day_low") else f"vs:{sym}:{name}:{round(px, 2)}"
                if key in self.st["fired"]:
                    continue
                self.st["fired"][key] = t
                seats = sorted(sid for sid, s in self._seats.items() if (s.get("underlying") or s.get("symbol") or "").upper() == sym)
                sid_ = self.ids.make(sym, t, "vol")
                self.rows[sid_] = dict(row, _level=(name, round(px, 4)))
                self.events.append({
                    "event_type": "vol_surge", "surge_id": sid_, "symbol": sym, "seat_id": ",".join(seats) or None,
                    "details": {"level": name, "level_price": round(px, 4), "dir": "up" if up else "down", "last": last,
                                "ref_px": ref, "ref_lookback_s": int(vc["ref_lookback_s"]), "rvol_1m": rv,
                                "pace_rvol_10s": row.get("pace_rvol_10s"), "vol_60s": v60, "norm_1m": row.get("norm_1m"),
                                "vol_10s": row.get("vol_10s"), "lag_s": row.get("lag_s"), "walls_fresh": fresh,
                                "pace_rvol_30s": row.get("pace_rvol_30s"), "day_rvol": row.get("day_rvol"),
                                "px_60s_ago": row.get("px_60s_ago"),
                                "day_high": row.get("day_high"), "day_low": row.get("day_low"),
                                "rth_slot": live.get("rth_slot"), "source": "mini collector /v1/live-volume (Alpaca SIP prints)"},
                    "data_stamp": row.get("last_trade_pt"),
                    "engine_pt": datetime.fromtimestamp(t, PT).strftime("%Y-%m-%d %I:%M:%S %p PT"),
                    "engine": "vol_surge", "dry_run": self.dry})
        return None

    def save(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.st, indent=1)); tmp.replace(self.state_path)


def vol_surge_flush(vs, state, env_file, global_live, vc, arch=None, quotes=None, t=None):
    """Log (always) + POST (only when vol_surge.live and global live) one batch for this tick.
    v0.5.0: each event carries a top-level surge_id and gets one `surges` archive row (inert without ~/oid-data)."""
    evs = collapse(vs.events)
    vs.events = []
    if not evs:
        vs.rows.clear()
        return 0, None
    live = bool(global_live and vc.get("live"))
    status = None
    if live:
        env, why = read_env(env_file)
        if env:
            try:
                status = send(batch_body(evs), env)
            except Exception as e:
                status = f"error:{type(e).__name__}"  # never log URL/key
        else:
            status = f"not_sent:{why}"
    batch_id = f"vs-{now_pt():%Y%m%d-%H%M%S}-{len(evs)}"
    notes = {} if live else vol_surge_notify(vs, state, env_file, vc, evs)
    with open(state / "events.jsonl", "a") as f:
        for i, ev in enumerate(evs):
            ev["batch_id"] = batch_id
            ev["dry_run"] = not live
            if live:
                ev["sent_status"] = status
            if i in notes:
                ev["notify_status"] = notes[i]
            f.write(json.dumps(ev) + "\n")
    vs.save()
    if arch is not None:
        try:
            nmap = {"queued": "queued", "dedupe": "dedupe", "same_tick": "dedupe", "cap": "cap"}
            rows = []
            for i, ev in enumerate(evs):
                row = vs.rows.get(ev.get("surge_id"))
                if row is None:
                    continue
                n = notes.get(i)
                ns_ = "off" if n is None else nmap.get(n, n if str(n).startswith("not_sent:") else f"not_sent:{n}")
                rows.append(oid_surges.surge_row(
                    surge_id=ev["surge_id"], sym=ev["symbol"], trigger="vol", gate="level", t=t or time.time(), row=row,
                    vc=vc, cfg=vs.cfg, crossed=row.get("_level"), notify_status=ns_, quote=(quotes or {}).get(ev["symbol"]),
                    qmax=float(oid_surges.arch_cfg(vs.cfg)["quote_max_age_s"])))
            arch.write(rows)
        except Exception:
            pass
    vs.rows.clear()
    return len(evs), status


def notify_body(ev, test=False):
    """Ladder dry-run wake payload. Flat fields for the routine + the original event in details. No secrets."""
    d = ev.get("details") or {}
    tag = "ladder-dryrun-test" if test else "ladder-dryrun"
    return {"event_type": "vol_surge", "surge_id": ev.get("surge_id"), "symbol": ev.get("symbol"), "seat_id": ev.get("seat_id"),
            "dry_run": True, "test": bool(test), "tag": tag, "trade_action": "none",
            "ticker": ev.get("symbol"), "direction": d.get("dir"), "rvol": d.get("rvol_1m"), "price": d.get("last"),
            "level": d.get("level"), "level_price": d.get("level_price"),
            "time_pt": ev.get("engine_pt"), "data_stamp": ev.get("data_stamp"),
            "details": dict(d, dry_run=True, test=bool(test), tag=tag, trade_action="none")}


def _notify_post(body, env, log_path, timeout):
    try:
        st = send(body, env, timeout=timeout)
    except Exception as e:
        st = f"error:{type(e).__name__}"  # never log URL/key
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps({"pt": now_pt().strftime("%Y-%m-%d %I:%M:%S %p PT"), "ticker": body.get("ticker"),
                                "direction": body.get("direction"), "test": body.get("test"), "status": st}) + "\n")
    except Exception:
        pass
    return st


def vol_surge_notify(vs, state, env_file, vc, evs, now=None, sync=False):
    """Dry-run only: POST each surge (first event per ticker per tick) to the wake webhook, capped per PT day and
    deduped per ticker. Runs the POST on a daemon thread so the 2 s loop never blocks. Returns {event_index: status}."""
    if not vc.get("notify_dry"):
        return {}
    t = time.time() if now is None else now
    n_st = vs.st.setdefault("notify", {"count": 0, "last": {}})
    cap, ded = int(vc.get("notify_max_per_day", 20)), float(vc.get("notify_dedupe_min", 5.0)) * 60
    env, why = read_env(env_file)
    out, seen = {}, set()
    for i, ev in enumerate(evs):
        sym = ev.get("symbol")
        if sym in seen:
            out[i] = "same_tick"; continue
        seen.add(sym)
        if t - float(n_st["last"].get(sym, 0)) < ded:
            out[i] = "dedupe"; continue
        if n_st["count"] >= cap:
            out[i] = "cap"; continue
        if not env:
            out[i] = f"not_sent:{why}"; continue
        n_st["count"] += 1
        n_st["last"][sym] = t
        body = notify_body(ev)
        args = (body, env, state / "notify.jsonl", float(vc.get("notify_timeout_s", 8.0)))
        if sync:
            out[i] = _notify_post(*args)
        else:
            threading.Thread(target=_notify_post, args=args, daemon=True).start()
            out[i] = "queued"
    return out


def notify_test(a, cfg, symbol, direction):
    """Send ONE clearly tagged test payload (test=true, tag=ladder-dryrun-test, trade_action=none). Not logged to events.jsonl."""
    vc = vs_cfg(cfg)
    env, why = read_env(a.env_file)
    if not env:
        print(json.dumps({"sent": False, "why": why})); return 1
    ev = {"symbol": symbol, "surge_id": oid_surges.SurgeIds().make(symbol, time.time(), "vol"), "seat_id": None, "engine_pt": now_pt().strftime("%Y-%m-%d %I:%M:%S %p PT"),
          "data_stamp": None, "details": {"level": "test", "level_price": None, "dir": direction, "last": None,
                                          "rvol_1m": None, "source": "notify self-test (not a real surge)"}}
    state = Path(a.state or os.environ.get("OID_TRIGGERS_STATE", "~/oid-desk/state/triggers")).expanduser()
    body = notify_body(ev, test=True)
    st = _notify_post(body, env, state / "notify.jsonl", float(vc.get("notify_timeout_s", 8.0)))
    print(json.dumps({"sent": True, "status": st, "payload": body}, default=str))
    return 0


def vol_surge_loop(a, cfg_path, global_live):
    import signal
    stop = {"v": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(v=True))
    cfg = jload(cfg_path) or {}
    cfg_m = os.path.getmtime(cfg_path) if os.path.exists(cfg_path) else 0
    desk = Path(a.desk or cfg.get("desk_root", "~/oid-desk/desk")).expanduser()
    state = Path(a.state or os.environ.get("OID_TRIGGERS_STATE", "~/oid-desk/state/triggers")).expanduser()
    state.mkdir(parents=True, exist_ok=True)
    vs = VolSurge(desk, state, cfg, dry=True)
    ns = oid_surges.NewsSurge(state, cfg)
    arch = oid_surges.SurgeArchive(cfg)
    status_path = state / "volsurge-status.json"
    stats = {"started_pt": now_pt().strftime("%Y-%m-%d %I:%M:%S %p PT"), "ticks": 0, "errors": 0, "fired": 0,
             "last_error": None, "last_gate": None, "news_fired": 0, "news_errors": 0, "archive_enabled": None,
             "surges_version": oid_surges.SURGES_VERSION}
    last_status = 0.0
    while not stop["v"]:
        t = time.time()
        try:  # hot-reload config (flip vol_surge.live / thresholds without a restart)
            m = os.path.getmtime(cfg_path)
            if m != cfg_m:
                cfg, cfg_m = (jload(cfg_path) or cfg), m
                vs.cfg = ns.cfg = arch.cfg = cfg
        except Exception:
            pass
        vc = vs_cfg(cfg)
        live_mode = bool(global_live and vc.get("live"))
        vs.dry = not live_mode
        sleep_s = float(vc["interval_s"])
        if not vc.get("enabled"):
            stats["last_gate"] = "disabled"; sleep_s = 30
        elif not a.force_session and not in_rth(cfg):
            stats["last_gate"] = "off_rth"; sleep_s = 20
        else:
            try:
                tok = read_secret_file(vc["token_file"])
                if not tok:
                    raise RuntimeError("token file missing")
                live = fetch_live_volume(vc["url"], tok)
                vs.refresh_desk(t)
                stats["last_gate"] = vs.check(live, t)
                fires, quotes = [], {}
                if stats["last_gate"] is None:
                    try:
                        fires = ns.check(live, t, vc)
                    except Exception:
                        stats["news_errors"] += 1
                stats["archive_enabled"] = arch.enabled()
                want = sorted({f[0] for f in fires} | {e.get("symbol") for e in vs.events if e.get("symbol")})
                if want and stats["archive_enabled"]:
                    quotes = oid_surges.fetch_quotes(oid_surges.arch_cfg(cfg)["quotes_url"], tok, want)
                n, _st = vol_surge_flush(vs, state, a.env_file, global_live, vc, arch=arch, quotes=quotes, t=t)
                if fires:
                    news_surge_log(fires, vs, ns, arch, state, vc, quotes, t)
                    stats["news_fired"] += len(fires)
                stats["fired"] += n
                stats["ticks"] += 1
            except Exception as e:
                stats["errors"] += 1
                stats["last_error"] = f"{now_pt():%H:%M:%S} {type(e).__name__}"  # never log URL/token
        if t - last_status >= 10:
            try:
                tmp = status_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(dict(stats, mode="live" if live_mode else "dry", global_live=bool(global_live),
                                               vol_surge_live_flag=bool(vc.get("live")), updated_pt=now_pt().strftime("%Y-%m-%d %I:%M:%S %p PT"),
                                               updated_epoch=t), indent=1))
                tmp.replace(status_path)
            except Exception:
                pass
            last_status = t
        slept = 0.0
        while slept < sleep_s and not stop["v"]:
            time.sleep(min(0.5, sleep_s - slept)); slept += 0.5
    return 0


def news_surge_log(fires, vs, ns, arch, state, vc, quotes, t):
    """news_surge is LOG-ONLY: archive `surges` rows + state/news-surge-events.jsonl. Never POSTs anywhere."""
    rows = []
    for sym, row, gate in fires:
        try:
            crossed = vs.level_hit(sym, row, t)
        except Exception:
            crossed = None
        rows.append(oid_surges.surge_row(surge_id=vs.ids.make(sym, t, "news"), sym=sym, trigger="news", gate=gate, t=t,
                                         row=row, vc=vc, cfg=vs.cfg, crossed=crossed, notify_status="off",
                                         quote=(quotes or {}).get(sym), qmax=float(oid_surges.arch_cfg(vs.cfg)["quote_max_age_s"])))
    arch.write(rows)
    try:
        with open(state / "news-surge-events.jsonl", "a") as f:
            for r in rows:
                f.write(json.dumps({"engine": "news_surge", "engine_pt": now_pt().strftime("%Y-%m-%d %I:%M:%S %p PT"),
                                    **{k: r[k] for k in ("surge_id", "symbol", "gate", "direction", "rvol_1m", "pace_rvol_10s",
                                                         "shares_60s", "last", "crossed_level", "level_name", "is_etf")}}) + "\n")
    except Exception:
        pass
    ns.save()


def vol_surge_once(a, cfg, global_live):
    """One check against a saved /v1/live-volume JSON (--vol-surge-file) or the live endpoint. Prints events; logs nothing."""
    desk = Path(a.desk or cfg.get("desk_root", "~/oid-desk/desk")).expanduser()
    state = Path(a.state or "/tmp/oid-volsurge-once").expanduser()
    state.mkdir(parents=True, exist_ok=True)
    vs = VolSurge(desk, state, cfg, dry=True)
    vc = vs_cfg(cfg)
    live = jload(a.vol_surge_file) if a.vol_surge_file else fetch_live_volume(vc["url"], read_secret_file(vc["token_file"]))
    vs.refresh_desk(time.time(), force=True)
    gate = vs.check(live, live.get("as_of_epoch") or time.time())
    print(json.dumps({"gate": gate, "events": vs.events, "mode": "dry (once)"}, indent=1, default=str))
    return 0

def in_rth(cfg):
    n = now_pt()
    if n.weekday() >= 5:
        return False
    a, b = cfg["rth_pt"]
    return a <= n.strftime("%H:%M") <= b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--live", action="store_true")
    ap.add_argument("--force-session", action="store_true"); ap.add_argument("--desk"); ap.add_argument("--state")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--env-file", default=os.environ.get("OID_WEBHOOK_ENV", "~/.oid/webhook.env"))
    ap.add_argument("--vol-surge-loop", action="store_true", help="run ONLY the fast vol_surge loop (launchd com.oid.desk.volsurge)")
    ap.add_argument("--vol-surge-once", action="store_true", help="one dry vol_surge check, print events, no log/post")
    ap.add_argument("--vol-surge-file", help="saved /v1/live-volume JSON for --vol-surge-once")
    ap.add_argument("--notify-test", metavar="SYM", help="POST one tagged TEST vol_surge payload (test=true, no trade) and exit")
    ap.add_argument("--notify-test-dir", default="up", choices=["up", "down"])
    a = ap.parse_args()
    cfg = jload(a.config)
    if a.notify_test:
        return notify_test(a, cfg, a.notify_test.upper(), a.notify_test_dir)
    if a.vol_surge_loop or a.vol_surge_once:
        glive = a.live or (os.environ.get("OID_TRIGGERS_MODE") == "live" and not a.dry_run)
        return vol_surge_once(a, cfg, glive) if a.vol_surge_once else vol_surge_loop(a, a.config, glive)
    if not a.force_session and not in_rth(cfg):
        return 0
    live = a.live or (os.environ.get("OID_TRIGGERS_MODE") == "live" and not a.dry_run)
    desk = Path(a.desk or cfg["desk_root"]).expanduser()
    state = Path(a.state or os.environ.get("OID_TRIGGERS_STATE", "~/oid-desk/state/triggers")).expanduser()
    state.mkdir(parents=True, exist_ok=True)
    eng = Engine(desk, state, cfg, dry=not live)
    evs = collapse(eng.run())
    env, why = (read_env(a.env_file) if live and evs else (None, None))
    status = None
    if live and evs:
        if env:
            try:
                status = send(batch_body(evs), env)
            except Exception as e:
                status = f"error:{type(e).__name__}"  # never log URL/key
        else:
            status = f"not_sent:{why}"
    batch_id = f"{now_pt():%Y%m%d-%H%M%S}-{len(evs)}" if evs else None
    with open(state / "events.jsonl", "a") as f:
        for ev in evs:
            ev["batch_id"] = batch_id
            if live:
                ev["sent_status"] = status
            f.write(json.dumps(ev) + "\n")
    eng.save()
    print(f"{now_pt():%H:%M:%S} events={len(evs)} posts={1 if (live and evs) else 0} mode={'live' if live else 'dry'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
