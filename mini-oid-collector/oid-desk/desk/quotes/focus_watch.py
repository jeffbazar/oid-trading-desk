#!/usr/bin/env python3
"""OID 5-second spot-vs-wall FOCUS watch (Jeffrey 2026-10-09). Research / paper only - ZERO execution.

Only names under an active buy/sell look are watched (Jeffrey's standing rule):
  * any OPEN Rose/Hal paper seat in paper-trades/trades.json (auto), plus
  * manual entries in config/focus-watch.json (elevate / Soft A / close review), with optional
    extra levels and an invalidation (e.g. 5-minute close below X).
Background walls stay on the slow FlashAlpha cadence: walls are READ from
market-data/latest/fa-levels.json (payload.levels[SYM]) - this process never calls FlashAlpha,
Robinhood or any broker/API. Prices come from cache/mini-quotes.json (quotes/mini_poller.py, ~5 s).

Every 5 s (RTH) it writes cache/focus-watch.json (state + per-symbol readings) and appends events to
cache/focus-watch-events.jsonl:
  approach (within approach_pct) · touch · cross_up / cross_down (tick) ·
  close5_above / close5_below (5-min close through a level, bars built from the 5 s ticks) ·
  hold2_above / hold2_below (two consecutive 5-min closes beyond a wall = clean break/hold) ·
  invalidation_tick_breach (early warning) · invalidation_5m_close (the real exit signal) ·
  wall_roll · walls_stale · walls_missing · no_5s_quote · quotes_stale.
Events are de-duplicated per symbol+level(+price)+event per ET session (state persisted in
cache/focus-watch-state.json, so restarts don't re-fire). Consumers: quotes/focus_watch_digest.py.

  scripts/focus-watch.sh start|stop|restart|status|once|selftest
Stdlib only, single process.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OID = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")
INTERVAL_S = float(os.environ.get("OID_FOCUS_POLL_S", "5"))
IDLE_INTERVAL_S = float(os.environ.get("OID_FOCUS_IDLE_S", "30"))
LOG_MAX_BYTES = 2_000_000
EVENTS_MAX_BYTES = 5_000_000
BAR_S = 300
SEVERITY = {
    "invalidation_5m_close": "high", "invalidation_tick_breach": "medium",
    "close5_above": "medium", "close5_below": "medium", "hold2_above": "high", "hold2_below": "high",
    "cross_up": "medium", "cross_down": "medium", "touch": "medium", "approach": "low",
    "wall_roll": "medium", "walls_stale": "low", "walls_missing": "low", "no_5s_quote": "low",
    "quotes_stale": "medium", "invalidation_approach": "medium",
}
WALL_KINDS = ("call_wall", "put_wall", "call_wall_fixed", "put_wall_fixed")

_stop = False


def _on_signal(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def pt_stamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, PT).strftime("%Y-%m-%d %-I:%M:%S %p PT")


def et_date(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, ET).strftime("%Y-%m-%d")


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _iso_epoch(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)
        fh.write("\n")
    os.replace(tmp, path)


def bars_rvol(sym: str):
    """5m/15m bars + RVOL read (quotes/mini_bars.py -> cache/bars/summary.json). File-only; None if missing/old."""
    try:
        sys.path.insert(0, str(OID / "quotes"))
        import mini_bars  # noqa: E402
        return mini_bars.summary_for(sym)
    except Exception:
        return None


def _rvol_note(sym: str) -> str:
    r = bars_rvol(sym)
    if not r:
        return ""
    return (f" | vol: session RVOL {r.get('session_rvol')} ({r.get('rvol_label')}), last 5m bar {r.get('last5_et')} ET "
            f"RVOL {r.get('last5_rvol')} [{r.get('source')}]")


def default_session(epoch: float) -> str:
    try:
        sys.path.insert(0, str(OID / "quotes"))
        sys.path.insert(0, str(OID / "paper-trades"))
        import mini_client as mc  # noqa: E402
        return mc.current_session(datetime.fromtimestamp(epoch, ET))
    except Exception:
        d = datetime.fromtimestamp(epoch, ET)
        m = d.hour * 60 + d.minute
        return "rth" if d.weekday() < 5 and 570 <= m < 960 else "closed"


class FocusWatch:
    def __init__(self, root: Path = OID, *, session_fn=default_session, log_fn=None):
        self.root = root
        self.cfg_path = root / "config" / "focus-watch.json"
        self.mini_path = root / "cache" / "mini-quotes.json"
        self.levels_path = root / "market-data" / "latest" / "fa-levels.json"
        self.focus_levels_path = root / "market-data" / "latest" / "fa-focus-levels.json"
        self.trades_path = root / "paper-trades" / "trades.json"
        self.out_path = root / "cache" / "focus-watch.json"
        self.events_path = root / "cache" / "focus-watch-events.jsonl"
        self.state_path = root / "cache" / "focus-watch-state.json"
        self.session_fn = session_fn
        self.log = log_fn or (lambda m: None)
        self._cfg_cache = (0.0, {})
        self._seats_cache = (0.0, 0.0, [])
        st = read_json(self.state_path) or {}
        self.state = {
            "session_date": st.get("session_date"),
            "fired": st.get("fired") or {},
            "sides": st.get("sides") or {},
            "bars": st.get("bars") or {},
            "walls": st.get("walls") or {},
            "quotes_stale_since": st.get("quotes_stale_since"),
            "last_quotes_stale_event": st.get("last_quotes_stale_event") or 0,
        }
        self.events_written = 0

    # ---------- inputs ----------
    def config(self, now: float) -> dict:
        t, cfg = self._cfg_cache
        if now - t > 30 or not cfg:
            cfg = read_json(self.cfg_path) or {}
            self._cfg_cache = (now, cfg)
        return cfg

    def open_seats(self, now: float) -> list[dict]:
        t, mtime, seats = self._seats_cache
        try:
            m = self.trades_path.stat().st_mtime
        except OSError:
            return seats
        if m == mtime and now - t < 60:
            return seats
        d = read_json(self.trades_path)
        if d is None:
            return seats  # mid-write; keep last good
        rows = d.get("trades") if isinstance(d, dict) else d
        seats = []
        for r in rows or []:
            if isinstance(r, dict) and str(r.get("status") or "").lower() == "open":
                sym = str(r.get("underlying") or r.get("symbol") or "").upper().strip()
                if sym:
                    seats.append({"id": r.get("id"), "symbol": sym, "agent": r.get("agent") or r.get("desk"),
                                  "contract": r.get("contract"), "invalidation": r.get("invalidation")})
        self._seats_cache = (now, m, seats)
        return seats

    def focus_list(self, now: float, cfg: dict) -> dict[str, dict]:
        today = datetime.fromtimestamp(now, PT).strftime("%Y-%m-%d")
        out: dict[str, dict] = {}
        for e in cfg.get("symbols") or []:
            sym = str(e.get("symbol") or "").upper().strip()
            if not sym or e.get("enabled") is False:
                continue
            if e.get("expires") and str(e["expires"]) < today:
                continue
            f = out.setdefault(sym, {"symbol": sym, "sources": [], "seats": [], "custom": [], "invalidation": None})
            f["sources"].append(e.get("look") or "manual")
            if e.get("reason"):
                f["reason"] = e["reason"]
            if e.get("seat"):
                f["seats"].append(e["seat"])
            f["custom"].extend(e.get("levels") or [])
            if e.get("invalidation"):
                f["invalidation"] = e["invalidation"]
        if cfg.get("auto_include_open_seats", True):
            for s in self.open_seats(now):
                f = out.setdefault(s["symbol"], {"symbol": s["symbol"], "sources": [], "seats": [], "custom": [],
                                                 "invalidation": None})
                if "open_paper_seat" not in f["sources"]:
                    f["sources"].append("open_paper_seat")
                if s["id"] and s["id"] not in f["seats"]:
                    f["seats"].append(s["id"])
                f.setdefault("seat_detail", []).append({k: s.get(k) for k in ("id", "agent", "contract")})
        return out

    # ---------- events ----------
    def emit(self, now, sym, event, *, level=None, price=None, spot=None, note="", key_extra="", focus=None):
        kp = (level or {}).get("kp", price)
        key = f"{sym}|{(level or {}).get('name', '-')}@{kp if kp is not None else '-'}|{event}{key_extra}"
        if key in self.state["fired"]:
            return None
        self.state["fired"][key] = round(now, 1)
        ev = {
            "id": f"FW-{datetime.fromtimestamp(now, PT).strftime('%Y%m%d-%H%M%S')}-{sym}-{event}",
            "epoch": round(now, 3), "ts_pt": pt_stamp(now), "session_date": self.state["session_date"],
            "symbol": sym, "event": event, "severity": SEVERITY.get(event, "low"),
            "level": (level or {}).get("name"), "level_kind": (level or {}).get("kind"), "level_price": price,
            "spot": spot,
            "dist_pct": round((spot - price) / price * 100, 3) if (spot is not None and price) else None,
            "seats": (focus or {}).get("seats") or [], "note": note,
            "mandate": "research/paper only - not an order",
        }
        try:
            if self.events_path.exists() and self.events_path.stat().st_size > EVENTS_MAX_BYTES:
                self.events_path.replace(self.events_path.with_suffix(".jsonl.1"))
            with self.events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev) + "\n")
        except OSError as e:
            self.log(f"event write error {e}")
        self.events_written += 1
        self.log(f"EVENT {sym} {event} level={ev['level']}@{price} spot={spot} {note}")
        return ev

    # ---------- core ----------
    def build_levels(self, sym: str, focus: dict, fa: dict | None) -> list[dict]:
        levels = []
        if fa:
            for k, kind in (("call_wall", "call_wall"), ("put_wall", "put_wall"), ("gamma_flip", "gamma_flip")):
                p = _f(fa.get(k))
                if p:
                    lv = {"name": kind, "kind": kind, "price": round(p, 4), "source": "fa-levels"}
                    if kind == "gamma_flip":  # live flip drifts every refresh: same level within a 0.5% bucket
                        import math
                        lv["kp"] = f"~b{round(math.log(p) / 0.005)}"
                    levels.append(lv)
        for c in focus.get("custom") or []:
            p = _f(c.get("price"))
            if not p:
                continue
            dup = next((l for l in levels if abs(l["price"] - p) < 0.01), None)
            if dup:
                dup.setdefault("aliases", []).append(c.get("name"))
                if c.get("note"):
                    dup["note"] = c["note"]
                continue
            levels.append({"name": c.get("name") or f"lvl_{p}", "kind": c.get("kind") or "custom",
                           "price": round(p, 4), "source": "config", "note": c.get("note")})
        inv = focus.get("invalidation")
        if inv and _f(inv.get("price")):
            levels.append({"name": f"invalidation_{inv['price']}", "kind": "invalidation",
                           "price": round(_f(inv["price"]), 4), "side": inv.get("side", "below"),
                           "basis": inv.get("basis", "5m_close"), "source": "config", "note": inv.get("note")})
        return levels

    def _side(self, spot, price, band):
        if spot > price + band:
            return "above"
        if spot < price - band:
            return "below"
        return "at"

    def _finalize_bar(self, now, sym, bar, levels, focus):
        bars = self.state["bars"].setdefault(sym, {"cur": None, "closed": []})
        closed = bars["closed"]
        prev_close = closed[-1]["c"] if closed else None
        rec = {"start_pt": pt_stamp(bar["b"] * BAR_S), "b": bar["b"], "o": bar["o"], "h": bar["h"], "l": bar["l"],
               "c": bar["c"], "n": bar["n"], "partial": bar.get("partial", False)}
        closed.append(rec)
        del closed[:-12]
        c = rec["c"]
        bar_label = datetime.fromtimestamp(bar["b"] * BAR_S, PT).strftime("%-I:%M")
        end_label = datetime.fromtimestamp((bar["b"] + 1) * BAR_S, PT).strftime("%-I:%M %p PT")
        for lv in levels:
            p = lv["price"]
            if lv["kind"] == "invalidation":
                breach = c < p if lv.get("side", "below") == "below" else c > p
                if breach and lv.get("basis", "5m_close") == "5m_close":
                    self.emit(now, sym, "invalidation_5m_close", level=lv, price=p, spot=c, focus=focus,
                              note=f"5-min bar {bar_label}-{end_label} closed {c} {'<' if lv.get('side','below')=='below' else '>'} {p}"
                                   f"{' (partial bar: watch started mid-bar)' if rec['partial'] else ''}. {lv.get('note') or ''}".strip())
                continue
            if prev_close is not None:
                if prev_close <= p < c:
                    self.emit(now, sym, "close5_above", level=lv, price=p, spot=c, focus=focus,
                              note=f"5-min close {c} through {lv['name']} {p} (prev close {prev_close}); bar ends {end_label}" + _rvol_note(sym))
                elif prev_close >= p > c:
                    self.emit(now, sym, "close5_below", level=lv, price=p, spot=c, focus=focus,
                              note=f"5-min close {c} under {lv['name']} {p} (prev close {prev_close}); bar ends {end_label}" + _rvol_note(sym))
            if lv["kind"] in WALL_KINDS and len(closed) >= 2:
                a, b2 = closed[-2]["c"], closed[-1]["c"]
                fired = self.state["fired"]
                base = f"{sym}|{lv['name']}@{lv.get('kp', p)}|"
                if a > p and b2 > p and (base + "cross_up" in fired or base + "close5_above" in fired):
                    self.emit(now, sym, "hold2_above", level=lv, price=p, spot=c, focus=focus,
                              note=f"two straight 5-min closes above {lv['name']} {p} ({a}, {b2}) after crossing it = break + hold" + _rvol_note(sym))
                if a < p and b2 < p and (base + "cross_down" in fired or base + "close5_below" in fired):
                    self.emit(now, sym, "hold2_below", level=lv, price=p, spot=c, focus=focus,
                              note=f"two straight 5-min closes below {lv['name']} {p} ({a}, {b2}) after breaking it" + _rvol_note(sym))

    def tick(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        cfg = self.config(now)
        sd = et_date(now)
        if self.state["session_date"] != sd:
            self.state.update({"session_date": sd, "fired": {}, "sides": {}, "bars": {}})
        session = self.session_fn(now)
        active = session in (cfg.get("sessions") or ["rth"])
        approach_pct = float(cfg.get("approach_pct", 0.3))
        touch_pct = float(cfg.get("touch_pct", 0.03))
        q_stale = float(cfg.get("quote_stale_s", 30))
        w_stale = float(cfg.get("walls_stale_min", 10)) * 60
        alias = {k.upper(): v.upper() for k, v in (cfg.get("quote_alias") or {}).items()}

        mini = read_json(self.mini_path) or {}
        cache_age = now - float(mini.get("written_epoch") or 0)
        quotes = mini.get("quotes") or {}
        fa_doc = read_json(self.levels_path) or {}
        fa_levels = dict(((fa_doc.get("payload") or {}).get("levels")) or {})
        # box-side 5-min focus refresh (quotes/fa_focus_refresh.py): use it when newer than fa-levels
        for k, v in ((read_json(self.focus_levels_path) or {}).get("levels") or {}).items():
            cur = fa_levels.get(k) or {}
            if (_iso_epoch(v.get("as_of")) or 0) > (_iso_epoch(cur.get("as_of")) or 0):
                fa_levels[k] = dict(v, walls_source="fa-focus-levels (box 5-min flow refresh)")
        focus = self.focus_list(now, cfg)
        self.last_focus, self.last_cfg, self.last_session = focus, cfg, session

        cache_ok = cache_age <= q_stale
        if active and not cache_ok:
            if not self.state["quotes_stale_since"]:
                self.state["quotes_stale_since"] = now
            if now - (self.state["last_quotes_stale_event"] or 0) > 600:
                self.state["last_quotes_stale_event"] = now
                self.state["fired"].pop("*|-@-|quotes_stale", None)
                self.emit(now, "*", "quotes_stale", note=f"cache/mini-quotes.json is {cache_age:.0f}s old (> {q_stale:.0f}s); "
                          "focus checks skipped until the 5s poller recovers (scripts/mini-link-up.sh)")
        elif cache_ok:
            self.state["quotes_stale_since"] = None

        readings = {}
        for sym, f in focus.items():
            qsym = alias.get(sym, sym)
            q = quotes.get(qsym) or quotes.get(sym) or {}
            fa = fa_levels.get(sym) or fa_levels.get({v: k for k, v in alias.items()}.get(sym, sym))
            levels = self.build_levels(sym, f, fa)
            spot = _f(q.get("last")) or _f(q.get("mid"))
            q_age = _f(q.get("age_s"))
            fa_asof = (fa or {}).get("as_of")
            fa_age = (now - _iso_epoch(fa_asof)) if _iso_epoch(fa_asof) else None
            flags = []
            if not cache_ok:
                flags.append("QUOTES_STALE_CACHE")
            if spot is None:
                flags.append("NO_5S_QUOTE")
            elif q_age is not None and q_age > q_stale:
                flags.append("QUOTE_STALE_SYMBOL")
            if not fa:
                flags.append("WALLS_MISSING")
            elif fa_age is not None and fa_age > w_stale:
                flags.append("WALLS_STALE")

            # wall roll detection (FA levels only)
            if fa:
                cur = {k: _f(fa.get(k)) for k in ("call_wall", "put_wall")}
                prev = self.state["walls"].get(sym)
                if prev and active:
                    for k in ("call_wall", "put_wall"):
                        if prev.get(k) and cur.get(k) and abs(prev[k] - cur[k]) >= 0.01:
                            self.emit(now, sym, "wall_roll", level={"name": k, "kind": k}, price=cur[k], spot=spot,
                                      focus=f, key_extra=f"|from{prev[k]}",
                                      note=f"FA {k.replace('_', ' ')} rolled {prev[k]} -> {cur[k]} (fa as_of {fa_asof})")
                self.state["walls"][sym] = cur
            if active:
                if "WALLS_MISSING" in flags:
                    self.emit(now, sym, "walls_missing", focus=f, note="no FA levels in fa-levels.json for this name")
                if "WALLS_STALE" in flags:
                    self.emit(now, sym, "walls_stale", focus=f, key_extra=f"|{fa_asof}",
                              note=f"FA walls as_of {fa_asof} are {fa_age/60:.0f} min old; waiting on the slow FA cadence")
                if "NO_5S_QUOTE" in flags:
                    self.emit(now, sym, "no_5s_quote", focus=f,
                              note=f"{qsym} not in mini 5s cache (core-20 allowlist config/stream-quote-allowlist.json)")

            can_eval = active and spot is not None and cache_ok and "QUOTE_STALE_SYMBOL" not in flags
            lv_out = []
            for lv in levels:
                p = lv["price"]
                row = dict(lv)
                if spot is not None:
                    row["dist"] = round(spot - p, 3)
                    row["dist_pct"] = round((spot - p) / p * 100, 3)
                    row["side"] = self._side(spot, p, p * touch_pct / 100)
                lv_out.append(row)
                if not can_eval:
                    continue
                skey = f"{sym}|{lv['name']}@{lv.get('kp', p)}"
                side = row["side"]
                prev_def = self.state["sides"].get(skey)
                if lv["kind"] == "invalidation":
                    breach = spot < p if lv.get("side", "below") == "below" else spot > p
                    if breach:
                        self.emit(now, sym, "invalidation_tick_breach", level=lv, price=p, spot=spot, focus=f,
                                  note=f"tick {spot} through {p} - EARLY WARNING only; exit rule is a 5-min close")
                    elif abs(row["dist_pct"]) <= approach_pct:
                        self.emit(now, sym, "invalidation_approach", level=lv, price=p, spot=spot, focus=f, key_extra=f"|from_{side}",
                                  note=f"{spot} within {abs(row['dist_pct']):.2f}% of invalidation {p}")
                else:
                    if side != "at" and abs(row["dist_pct"]) <= approach_pct:
                        self.emit(now, sym, "approach", level=lv, price=p, spot=spot, focus=f, key_extra=f"|from_{side}",
                                  note=f"{spot} is {abs(row['dist_pct']):.2f}% {'under' if side == 'below' else 'over'} {lv['name']} {p}")
                    crossed = prev_def in ("above", "below") and side in ("above", "below") and side != prev_def
                    if side == "at" or crossed:
                        self.emit(now, sym, "touch", level=lv, price=p, spot=spot, focus=f,
                                  note=f"{spot} touched {lv['name']} {p}")
                    if crossed:
                        ev = "cross_up" if side == "above" else "cross_down"
                        self.emit(now, sym, ev, level=lv, price=p, spot=spot, focus=f,
                                  note=f"tick cross {prev_def}->{side} of {lv['name']} {p} at {spot} (unconfirmed until 5-min close)")
                if side in ("above", "below"):
                    self.state["sides"][skey] = side

            # 5-minute bars from the 5s ticks
            bar_info = None
            if can_eval:
                b = int(now // BAR_S)
                bars = self.state["bars"].setdefault(sym, {"cur": None, "closed": []})
                cur = bars.get("cur")
                if cur and cur["b"] != b:
                    self._finalize_bar(now, sym, cur, levels, f)
                    cur = None
                if not cur:
                    cur = {"b": b, "o": spot, "h": spot, "l": spot, "c": spot, "n": 0,
                           "partial": (now - b * BAR_S) > 2 * INTERVAL_S + 1 and not bars.get("closed")}
                cur["h"] = max(cur["h"], spot)
                cur["l"] = min(cur["l"], spot)
                cur["c"] = spot
                cur["n"] += 1
                bars["cur"] = cur
                last = (bars.get("closed") or [None])[-1]
                bar_info = {"current": {"start_pt": pt_stamp(cur["b"] * BAR_S), "o": cur["o"], "h": cur["h"],
                                        "l": cur["l"], "last": cur["c"], "ticks": cur["n"], "partial": cur.get("partial")},
                            "last_close": last}
            elif self.state["bars"].get(sym):
                bars = self.state["bars"][sym]
                bar_info = {"current": None, "last_close": (bars.get("closed") or [None])[-1]}

            readings[sym] = {
                "symbol": sym, "quote_symbol": qsym, "spot": spot, "bid": _f(q.get("bid")), "ask": _f(q.get("ask")),
                "quote_age_s": q_age, "quote_source": q.get("source"),
                "fa_as_of": fa_asof, "fa_age_min": round(fa_age / 60, 1) if fa_age is not None else None,
                "call_wall": _f((fa or {}).get("call_wall")), "put_wall": _f((fa or {}).get("put_wall")),
                "gamma_flip": _f((fa or {}).get("gamma_flip")),
                "walls_label": ("MISSING" if not fa else "STALE" if "WALLS_STALE" in flags else "FRESH"),
                "walls_source": (fa or {}).get("walls_source") or ("fa-levels (" + str((fa or {}).get("oi_feed")) + ")"),
                "levels": lv_out, "bar5": bar_info, "rvol": bars_rvol(qsym), "flags": flags, "evaluated": can_eval,
                "sources": f.get("sources"), "seats": f.get("seats"), "reason": f.get("reason"),
            }

        out = {
            "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "as_of_pt": pt_stamp(now),
            "written_epoch": round(now, 3), "writer": "quotes/focus_watch.py", "pid": os.getpid(),
            "state": ("active" if cache_ok else "quotes_stale") if active else f"idle ({session})",
            "session": session, "session_date": self.state["session_date"],
            "interval_s": INTERVAL_S if active else IDLE_INTERVAL_S,
            "mini_cache_age_s": round(cache_age, 1), "mini_as_of_pt": mini.get("as_of_pt"),
            "fa_levels_as_of_pt": fa_doc.get("as_of_pt"),
            "focus_symbols": sorted(focus), "readings": readings,
            "fa_refresh": getattr(self, "refresh_status", None),
            "events_today": len([k for k in self.state["fired"]]),
            "events_path": str(self.events_path),
            "rules": {"approach_pct": approach_pct, "touch_pct": touch_pct, "quote_stale_s": q_stale,
                      "walls_stale_min": w_stale / 60, "invalidation": "5-min close from 5s ticks (tick breach = warning only)"},
            "mandate": "Research / paper only. Never places, modifies or cancels Robinhood orders. No FlashAlpha calls.",
        }
        atomic_write_json(self.out_path, out)
        atomic_write_json(self.state_path, self.state)
        return out


# ---------------- daemon ----------------
PID_PATH = OID / "cache" / "focus-watch.pid"
LOG_PATH = OID / "cache" / "focus-watch.log"


def log(msg: str) -> None:
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{pt_stamp(time.time())} {msg}\n")
    except OSError:
        pass


def _refresh_loop(fw: "FocusWatch") -> None:
    """Background thread: 5-min FlashAlpha flow-levels refresh for focus names (quota-aware)."""
    try:
        import fa_focus_refresh as ffr
    except Exception as e:  # noqa: BLE001
        log(f"fa-refresh disabled: import {type(e).__name__}: {e}")
        return
    r = ffr.Refresher(log=log)
    while not _stop:
        try:
            if getattr(fw, "last_focus", None) is not None:
                r.maybe_run(time.time(), fw.last_focus, fw.last_cfg or {}, fw.last_session or "closed")
                st = r.state
                fw.refresh_status = {"mode": st.get("mode"), "last_run_pt": st.get("last_run_pt"),
                                     "calls_today": st.get("calls_today"), "last_error": st.get("last_error"),
                                     "plan": st.get("plan"), "remaining": (st.get("last_account") or {}).get("remaining")}
        except Exception as e:  # noqa: BLE001
            log(f"fa-refresh error {type(e).__name__}: {str(e)[:200]}")
        for _ in range(10):
            if _stop:
                return
            time.sleep(0.5)


def run() -> int:
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))
    fw = FocusWatch(log_fn=log)
    log(f"start pid={os.getpid()} interval={INTERVAL_S}s idle={IDLE_INTERVAL_S}s")
    if os.environ.get("OID_FOCUS_FA_REFRESH", "1") != "0":
        import threading
        threading.Thread(target=_refresh_loop, args=(fw,), daemon=True, name="fa-focus-refresh").start()
    n, last_state, last_summary = 0, None, 0.0
    try:
        while not _stop:
            t0 = time.monotonic()
            interval = INTERVAL_S
            try:
                out = fw.tick()
                interval = out["interval_s"]
                st = (out["state"], tuple(out["focus_symbols"]))
                if st != last_state:
                    log(f"state={out['state']} focus={','.join(out['focus_symbols'])} cache_age={out['mini_cache_age_s']}s")
                    last_state = st
                if time.time() - last_summary > 600:
                    bits = [f"{s}={r['spot']}" for s, r in out["readings"].items()]
                    log(f"summary ticks={n} events_today={out['events_today']} {' '.join(bits)}")
                    last_summary = time.time()
            except Exception as e:
                log(f"tick error {type(e).__name__}: {str(e)[:200]}")
            n += 1
            end = time.monotonic() + max(0.2, interval - (time.monotonic() - t0))
            while not _stop and time.monotonic() < end:
                time.sleep(max(0.0, min(0.5, end - time.monotonic())))
    finally:
        log(f"stop pid={os.getpid()} ticks={n}")
        try:
            if PID_PATH.read_text().strip() == str(os.getpid()):
                PID_PATH.unlink()
        except OSError:
            pass
    return 0


# ---------------- synthetic self-test (temp dir; never touches live cache) ----------------
def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="focus-selftest-"))
    for d in ("config", "cache", "market-data/latest", "paper-trades"):
        (tmp / d).mkdir(parents=True)
    (tmp / "config" / "focus-watch.json").write_text(json.dumps({
        "approach_pct": 0.3, "touch_pct": 0.03, "quote_stale_s": 30, "walls_stale_min": 90, "sessions": ["rth"],
        "symbols": [{"symbol": "AMZN", "seat": "TEST-SEAT", "levels": [{"name": "cw_260", "price": 260}],
                     "invalidation": {"price": 255.5, "side": "below", "basis": "5m_close"}}]}))
    (tmp / "paper-trades" / "trades.json").write_text(json.dumps({"trades": [
        {"id": "HAL-TEST", "status": "open", "symbol": "NFLX", "agent": "Hal"}]}))
    t0 = datetime(2026, 10, 9, 10, 0, 2, tzinfo=ET).timestamp()  # 7:00:02 AM PT
    fa_asof = datetime.fromtimestamp(t0 - 600, ET).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

    def put_levels(cw=260):
        (tmp / "market-data/latest/fa-levels.json").write_text(json.dumps({"payload": {"levels": {
            "AMZN": {"call_wall": cw, "put_wall": 250, "gamma_flip": 252.07, "as_of": fa_asof},
            "NFLX": {"call_wall": 72, "put_wall": 70, "gamma_flip": 71.58,
                     "as_of": "2026-10-08T20:00:00Z"}}}}))

    def put_quote(now, amzn, age=0.5, nflx=71.5):
        (tmp / "cache/mini-quotes.json").write_text(json.dumps({"written_epoch": now - age, "quotes": {
            "AMZN": {"last": amzn, "age_s": 0.1, "source": "mini"}, "NFLX": {"last": nflx, "age_s": 0.1, "source": "mini"}}}))

    put_levels()
    fw = FocusWatch(tmp, session_fn=lambda e: "rth")
    # (offset_s, AMZN price, note)
    path = [(0, 258.40), (5, 258.90), (10, 259.30),      # approach 260 (0.27%)
            (15, 259.95), (20, 260.20), (25, 260.40),    # touch + cross_up
            (300, 260.50), (305, 260.60),                # bar0 close 260.40 above (prev none)
            (600, 260.70), (605, 260.30),                # bar1 close 260.60 -> hold2_above after bar 2 close
            (900, 259.80), (905, 257.00), (910, 255.40), # bar2 close 260.30; tick breach 255.4
            (1195, 256.00),                              # recovers inside bar -> no 5m invalidation
            (1200, 255.90), (1490, 255.30),              # bar3 close 256.00 (no inv); bar4 closes 255.30
            (1500, 255.20), (1505, 255.10)]              # bar4 finalize -> invalidation_5m_close
    for off, px in path:
        put_quote(t0 + off, px)
        fw.tick(t0 + off)
    # repeat a touch to prove de-dup
    put_quote(t0 + 1510, 260.0)
    fw.tick(t0 + 1510)
    # wall roll
    put_levels(cw=257.5)
    put_quote(t0 + 1515, 255.0)
    fw.tick(t0 + 1515)
    # stale cache
    put_quote(t0 + 1520, 255.0, age=45)
    out = fw.tick(t0 + 1520)

    evs = [json.loads(l) for l in (tmp / "cache/focus-watch-events.jsonl").read_text().splitlines()]
    got = [(e["symbol"], e["level"], e["event"]) for e in evs]
    expect = [
        ("AMZN", "call_wall", "approach"), ("AMZN", "call_wall", "touch"), ("AMZN", "call_wall", "cross_up"),
        ("AMZN", "call_wall", "hold2_above"), ("AMZN", "invalidation_255.5", "invalidation_tick_breach"),
        ("AMZN", "invalidation_255.5", "invalidation_5m_close"), ("AMZN", "call_wall", "wall_roll"),
        ("*", None, "quotes_stale"), ("NFLX", None, "walls_stale"),
    ]
    missing = [e for e in expect if e not in got]
    inv5 = [e for e in evs if e["event"] == "invalidation_5m_close"]
    touches = [e for e in evs if e["event"] == "touch" and e["level"] == "call_wall" and e["level_price"] == 260]
    ok = (not missing and len(inv5) == 1 and abs(inv5[0]["spot"] - 255.30) < 1e-9 and len(touches) == 1
          and out["state"] == "quotes_stale")
    for e in evs:
        print(f"  {e['ts_pt']:>26}  {e['symbol']:5} {e['event']:26} {str(e['level']):20} {e['level_price']}  spot={e['spot']}  {e['note'][:90]}")
    print(json.dumps({"selftest": "PASS" if ok else "FAIL", "events": len(evs), "missing": missing,
                      "inv5_count": len(inv5), "inv5_close": inv5[0]["spot"] if inv5 else None,
                      "touch_260_count": len(touches), "final_state": out["state"], "tmp": str(tmp)}, indent=1))
    return 0 if ok else 1


def once() -> int:
    out = FocusWatch(log_fn=log).tick()
    print(json.dumps({k: out[k] for k in ("as_of_pt", "state", "session", "mini_cache_age_s", "focus_symbols")}, indent=1))
    for s, r in out["readings"].items():
        print(f"{s}: spot={r['spot']} flags={r['flags']}")
        for lv in r["levels"]:
            print(f"   {lv['name']:22} {lv['price']:>10}  dist={lv.get('dist')}  ({lv.get('dist_pct')}%)  {lv.get('side')}")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    raise SystemExit(once() if "--once" in sys.argv else run())
