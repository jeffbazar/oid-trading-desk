#!/usr/bin/env python3
"""PATTERNS (2026-10-21): live chart-pattern detector, SHADOW ONLY (never feeds a live score or a trade).

One streaming engine per (ticker, interval). Feed it closed bars in time order with Engine.step(bar); it returns the
records for every state change. The same engine runs live (pattern_daemon.py), in replays and in the backtest
(pattern_learn.py), so live, replay and base rates all use identical rules. Standard library only, deterministic.

Bars are tuples (t_start_epoch, o, h, l, c, v, session_date_ET, vwap_src) - vwap_src = the 1-min bar's vw (else None).
Intervals: 1m (the mini's own 1-min SIP bars), 5m and 30m (rolled from those 1-min bars on ET :00/:05/:30 boundaries).

Patterns (direction = what the pattern predicts: +1 up, -1 down, 0 neutral context):
  range (0)             tight range / ATR compression: forming after W/2 tight bars, confirmed after W; a close outside
                        ends it as completed with break_dir (+1/-1) and opens a breakout/breakdown (graded)
  bull_flag / bear_flag strong pole then a tight range under half the pole; trigger = flag edge, target = edge + pole
  breakout / breakdown  close beyond a confirmed range edge (target = edge + range height, invalidation = range middle)
                        or beyond a key level (prior-session high/low, 30-min opening range) - target 3 bar-ATR (2 on 30m)
                        vol_confirm = bar volume >= 1.5x the last 20 bars (rvol)
  failed_breakout / failed_breakdown  a breakout that closes back inside within 5 bars -> the other way
  head_shoulders / inv_head_shoulders  5 alternating pivots; neckline = mean of the two troughs (peaks);
                        target = neckline -/+ (head - neckline), invalidation = right shoulder +/- 0.25 ATR
  double_top / double_bottom  2 pivots within 0.5 ATR, middle pivot >= 1.5 ATR away; trigger = middle pivot
  vwap_reclaim / vwap_loss  (1m, 5m) close crosses session VWAP after 3 closes on the other side
  higher_low / lower_high   trend shift: in a down (up) leg a new pivot low (high) holds above (below) the last one
  gap_up / gap_down     (5m, first bar of the session) open >= 0.6% from the prior close; predicts the FILL:
                        trigger = first 5-min bar's low (high), target = prior close, status open/filled
States: forming -> confirmed -> triggered -> completed (target touched) | failed (closing invalidation) | expired.
"""
import math
from collections import Counter

DETECTOR_VERSION = "pat-v1-20261021"
IV_MIN = {"1m": 1, "5m": 5, "30m": 30}
CFG = {"1m": {"k": 3, "W": 20, "hz": 30, "cool": 10, "kl_t": 3.0},
       "5m": {"k": 3, "W": 12, "hz": 24, "cool": 6, "kl_t": 3.0},
       "30m": {"k": 2, "W": 10, "hz": 26, "cool": 4, "kl_t": 2.0}}
SHORT = {"range": "RNG", "bull_flag": "FLAG", "bear_flag": "FLAG", "breakout": "BO", "breakdown": "BD",
         "failed_breakout": "FBO", "failed_breakdown": "FBD", "head_shoulders": "H&S", "inv_head_shoulders": "iH&S",
         "double_top": "DT", "double_bottom": "DB", "vwap_reclaim": "VWAP+", "vwap_loss": "VWAP-",
         "higher_low": "HL", "lower_high": "LH", "gap_up": "GAP", "gap_down": "GAP"}
PATTERNS = list(SHORT)
T, O, H, L, C, V, D, VW = range(8)


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def clip01(x):
    return round(max(0.0, min(1.0, x)), 3)


class Engine:
    def __init__(self, sym, iv, atr_day=None):
        self.sym, self.iv = sym, iv
        c = CFG[iv]
        self.k, self.W, self.hz, self.cool, self.kl_t = c["k"], c["W"], c["hz"], c["cool"], c["kl_t"]
        self.ivs = IV_MIN[iv] * 60
        self.atr_day = atr_day
        self.B, self.off, self.i = [], 0, -1          # bars (trimmed), absolute index of B[0], absolute index of last bar
        self.tr, self.atr, self.vwap = [], None, []
        self.piv = []                                  # [(abs_idx, 'H'|'L', price)]
        self.act = {}                                  # family -> detection dict
        self.last_new = {}
        self.d = None
        self.pdc = self.pdh = self.pdl = None
        self.shi = self.slo = None
        self.s0 = None                                 # abs index of the session's first bar
        self.orh = self.orl = None
        self.or_done = False
        self.pv = self.vv = 0.0

    # ------------------------------------------------------------- helpers
    def b(self, j):
        return self.B[j - self.off]

    def win(self, a, z):  # bars abs a..z inclusive
        return self.B[max(0, a - self.off): z - self.off + 1]

    def rvol(self):
        vs = [b[V] for b in self.win(self.i - 20, self.i - 1) if b[V]]
        if len(vs) < 5:
            return None
        m = sum(vs) / len(vs)
        return _r(self.b(self.i)[V] / m, 2) if m > 0 else None

    def atr5(self):
        t = self.tr[-5:]
        return sum(t) / len(t) if t else None

    # ------------------------------------------------------------- main
    def step(self, bar, emit=True):
        out = []
        self.i += 1
        self.B.append(bar)
        if len(self.B) > 1400:
            cut = len(self.B) - 700
            self.B = self.B[cut:]
            self.vwap = self.vwap[cut:]
            self.off += cut
        prev = self.B[-2] if len(self.B) > 1 else None
        new_sess = bar[D] != self.d
        if new_sess:
            if self.d is not None and prev is not None:
                self.pdc, self.pdh, self.pdl = prev[C], self.shi, self.slo
            self.d, self.shi, self.slo, self.s0 = bar[D], bar[H], bar[L], self.i
            self.orh, self.orl, self.or_done = bar[H], bar[L], False
            self.pv = self.vv = 0.0
        else:
            self.shi, self.slo = max(self.shi, bar[H]), min(self.slo, bar[L])
        # opening range = first 30 min of the session (1m/5m only)
        if self.iv != "30m" and not self.or_done:
            if bar[T] - self.b(self.s0)[T] < 1800:
                self.orh, self.orl = max(self.orh, bar[H]), min(self.orl, bar[L])
            else:
                self.or_done = True
        pc = prev[C] if prev is not None else bar[C]
        tr = max(bar[H] - bar[L], abs(bar[H] - pc), abs(bar[L] - pc))
        self.tr.append(tr)
        if len(self.tr) > 40:
            self.tr = self.tr[-40:]
        if self.atr is None:
            if len(self.tr) >= 14:
                self.atr = sum(self.tr[-14:]) / 14
        else:
            self.atr = (self.atr * 13 + tr) / 14
        px = bar[VW] if bar[VW] else (bar[H] + bar[L] + bar[C]) / 3
        self.pv += px * (bar[V] or 0)
        self.vv += bar[V] or 0
        self.vwap.append(self.pv / self.vv if self.vv > 0 else bar[C])
        newp = self._pivots()
        if self.atr is None or self.atr <= 0:
            return out
        broke = self._update(bar, out)
        self._detect(bar, out, broke, newp, new_sess, prev)
        return out if emit else []

    def _pivots(self):
        k, p = self.k, self.i - self.k
        if p - k < self.off:
            return None
        w = self.win(p - k, p + k)
        bp = self.b(p)
        added = None
        hs = [x[H] for x in w]
        ls = [x[L] for x in w]
        if bp[H] >= max(hs) and bp[H] > max(hs[:k]):
            added = self._addp(p, "H", bp[H]) or added
        if bp[L] <= min(ls) and bp[L] < min(ls[:k]):
            added = self._addp(p, "L", bp[L]) or added
        return added

    def _addp(self, p, kind, price):
        if self.piv and self.piv[-1][1] == kind:
            last = self.piv[-1]
            if (kind == "H" and price > last[2]) or (kind == "L" and price < last[2]):
                self.piv[-1] = (p, kind, price)
                return kind
            return None
        self.piv.append((p, kind, price))
        if len(self.piv) > 12:
            self.piv = self.piv[-12:]
        return kind

    # ------------------------------------------------------------- records
    def _rec(self, det, state, bar, extra=None):
        r = {"ts": bar[T] + self.ivs, "ticker": self.sym, "interval": self.iv, "pattern": det["pattern"],
             "direction": det["dir"], "state": state, "det_id": det["id"],
             "key_levels": {"trigger": _r(det.get("trig")), "target": _r(det.get("tgt")), "invalidation": _r(det.get("inv"))},
             "confidence_raw": det.get("conf"), "horizon": {"bars": det["hz"], "minutes": det["hz"] * IV_MIN[self.iv]},
             "detector_version": DETECTOR_VERSION, "px": _r(bar[C]), "atr_bar": _r(self.atr), "detected_ts": det["ts0"],
             "bar_t": bar[T]}
        if det.get("lv"):
            r["key_levels"].update({k: _r(v) if isinstance(v, (int, float)) else v for k, v in det["lv"].items()})
        for k in ("rvol", "vol_confirm", "source", "gap_pct", "fill_status"):
            if det.get(k) is not None:
                r[k] = det[k]
        if extra:
            r.update(extra)
        return r

    def _new(self, fam, pattern, d, trig, tgt, inv, conf, bar, out, state="confirmed", lv=None, hz=None, **kw):
        det = {"id": f"{self.sym}-{self.iv}-{pattern}-{int(bar[T])}", "fam": fam, "pattern": pattern, "dir": d,
               "trig": trig, "tgt": tgt, "inv": inv, "conf": clip01(conf), "state": state, "i0": self.i, "ti": None,
               "hz": hz or self.hz, "ts0": bar[T] + self.ivs, "lv": lv or {}, "xmax": bar[H], "xmin": bar[L]}
        det.update(kw)
        self.act[fam] = det
        self.last_new[fam] = self.i
        out.append(self._rec(det, state, bar))
        if state == "triggered":
            det["ti"] = self.i
        elif state == "confirmed" and d and trig is not None and ((bar[C] > trig) if d > 0 else (bar[C] < trig)):
            det["state"], det["ti"] = "triggered", self.i
            out.append(self._rec(det, "triggered", bar))
        return det

    def _end(self, fam, det, state, bar, out, **extra):
        det["state"] = state
        out.append(self._rec(det, state, bar, extra or None))
        self.act.pop(fam, None)

    def can(self, fam):
        return fam not in self.act and self.i - self.last_new.get(fam, -10 ** 9) >= self.cool

    # ------------------------------------------------------------- lifecycle of active detections
    def _update(self, bar, out):
        broke = None
        a, c, h, l = self.atr, bar[C], bar[H], bar[L]
        for fam, det in list(self.act.items()):
            if det["i0"] == self.i:
                continue
            det["xmax"], det["xmin"] = max(det["xmax"], h), min(det["xmin"], l)
            age = self.i - det["i0"]
            if fam == "range":
                hi, lo = det["lv"]["range_hi"], det["lv"]["range_lo"]
                eps = 0.05 * a
                if c > hi + eps or c < lo - eps:
                    if det["state"] == "confirmed":
                        broke = (1 if c > hi else -1, hi, lo, det["n"])
                        self._end(fam, det, "completed", bar, out, break_dir=1 if c > hi else -1)  # range resolved by a break
                    else:
                        self._end(fam, det, "failed", bar, out, reason="left range before confirming")
                    continue
                det["lv"]["range_hi"], det["lv"]["range_lo"] = max(hi, h), min(lo, l)
                if det["lv"]["range_hi"] - det["lv"]["range_lo"] > 2.0 * a:
                    self._end(fam, det, "failed", bar, out, reason="range widened")
                    continue
                det["n"] += 1
                if det["state"] == "forming" and det["n"] >= self.W:
                    det["state"] = "confirmed"
                    out.append(self._rec(det, "confirmed", bar))
                elif age > self.hz:
                    self._end(fam, det, "expired", bar, out)
                continue
            sg, Tg, G, I = det["dir"], det["trig"], det["tgt"], det["inv"]
            if fam == "gap" and det.get("fill_status") == "open" and ((l <= G) if sg < 0 else (h >= G)):
                det["fill_status"] = "filled"
            if det["state"] in ("forming", "confirmed"):
                if (c > Tg) if sg > 0 else (c < Tg):
                    det["state"], det["ti"] = "triggered", self.i
                    out.append(self._rec(det, "triggered", bar))
                elif I is not None and ((c < I) if sg > 0 else (c > I)):
                    self._end(fam, det, "failed", bar, out, reason="invalidated before trigger")
                elif age > det["hz"]:
                    self._end(fam, det, "expired", bar, out, reason="never triggered")
                continue
            # triggered
            if (h >= G) if sg > 0 else (l <= G):
                self._end(fam, det, "completed", bar, out)
                continue
            if fam == "break" and self.i - det["ti"] <= 5 and ((c < Tg) if sg > 0 else (c > Tg)):
                ext = det["xmax"] if sg > 0 else det["xmin"]
                self._end(fam, det, "failed", bar, out, reason="closed back inside")
                if "fail" not in self.act:
                    lo, hi = det["lv"].get("range_lo"), det["lv"].get("range_hi")
                    tgt = (lo if sg > 0 else hi) if lo is not None else (Tg - (G - Tg))
                    rv = self.rvol()
                    self._new("fail", "failed_breakout" if sg > 0 else "failed_breakdown", -sg, Tg, tgt,
                              ext + 0.1 * a * sg, 0.5 + 0.25 * (1 if (rv or 0) >= 1.5 else 0), bar, out, state="triggered",
                              rvol=rv, vol_confirm=bool(rv and rv >= 1.5), source=det.get("source"))
                continue
            if I is not None and ((c < I) if sg > 0 else (c > I)):
                self._end(fam, det, "failed", bar, out, reason="closing invalidation")
                continue
            if self.i - det["ti"] > det["hz"]:
                self._end(fam, det, "expired", bar, out)
        return broke

    # ------------------------------------------------------------- new detections
    def _detect(self, bar, out, broke, newp, new_sess, prev):
        a, c, i, W = self.atr, bar[C], self.i, self.W
        # gap (5m engine, first bar of a session)
        if self.iv == "5m" and new_sess and self.pdc and self.can("gap"):
            g = (bar[O] - self.pdc) / self.pdc
            big = abs(g) >= 0.006 and (self.atr_day is None or abs(bar[O] - self.pdc) >= 0.25 * self.atr_day)
            if big:
                sg = -1 if g > 0 else 1
                trig, inv = (bar[L], bar[H] + 0.1 * a) if g > 0 else (bar[H], bar[L] - 0.1 * a)
                filled = (bar[L] <= self.pdc) if g > 0 else (bar[H] >= self.pdc)
                if not filled:
                    self._new("gap", "gap_up" if g > 0 else "gap_down", sg, trig, self.pdc, inv,
                              0.4 + 0.3 * min(1, abs(g) / 0.03), bar, out, hz=77, lv={"prior_close": self.pdc},
                              gap_pct=_r(g * 100, 2), fill_status="open")
        # breakout from a confirmed range that broke this bar
        if broke and self.can("break"):
            d, hi, lo, n = broke
            lvl = hi if d > 0 else lo
            rv = self.rvol()
            vc = bool(rv and rv >= 1.5)
            self._new("break", "breakout" if d > 0 else "breakdown", d, lvl, lvl + d * (hi - lo), (hi + lo) / 2,
                      0.35 + 0.25 * vc + 0.2 * min(1, n / (2 * W)) + 0.2 * min(1, (rv or 0) / 3), bar, out,
                      state="triggered", lv={"range_hi": hi, "range_lo": lo}, rvol=rv, vol_confirm=vc, source="range")
        # breakout through a key level
        if prev is not None and not new_sess and self.can("break"):
            lv = [("prior_high", self.pdh, 1), ("prior_low", self.pdl, -1)]
            if self.iv != "30m" and self.or_done:
                lv += [("opening_range_high", self.orh, 1), ("opening_range_low", self.orl, -1)]
            for name, x, d in lv:
                if x is None:
                    continue
                if (prev[C] <= x < c) if d > 0 else (prev[C] >= x > c):
                    rv = self.rvol()
                    vc = bool(rv and rv >= 1.5)
                    self._new("break", "breakout" if d > 0 else "breakdown", d, x, x + d * self.kl_t * a, x - d * a,
                              0.35 + 0.25 * vc + 0.2 * min(1, (rv or 0) / 3), bar, out, state="triggered",
                              lv={"level": x, "level_name": name}, rvol=rv, vol_confirm=vc, source=name)
                    break
        # range / flag
        m = W // 2
        if i - self.off >= m + 2 * W:
            w = self.win(i - m + 1, i)
            hi, lo = max(x[H] for x in w), min(x[L] for x in w)
            hgt = hi - lo
            a5 = self.atr5()
            tight = hgt <= 1.5 * a and a5 is not None and a5 < 0.8 * a
            if tight:
                pole = self.b(i - m)[C] - self.b(i - m - W)[C]
                if abs(pole) >= 3 * a and hgt <= 0.5 * abs(pole) and self.can("flag"):
                    d = 1 if pole > 0 else -1
                    trig, inv = (hi, lo) if d > 0 else (lo, hi)
                    self._new("flag", "bull_flag" if d > 0 else "bear_flag", d, trig, trig + pole, inv,
                              0.4 + 0.3 * min(1, abs(pole) / (6 * a)) + 0.3 * (1 - hgt / (0.5 * abs(pole))), bar, out,
                              lv={"pole": _r(pole), "flag_hi": hi, "flag_lo": lo})
                if self.can("range"):
                    self._new("range", "range", 0, None, None, None, 0.4 + 0.6 * (1 - hgt / (1.5 * a)), bar, out,
                              state="forming", lv={"range_hi": hi, "range_lo": lo}, n=m, hz=3 * W)
        # pivot patterns (only when a pivot was just added / replaced)
        if newp:
            P = self.piv
            if len(P) >= 3 and self.can("double"):
                (i1, k1, p1), (i2, k2, p2), (i3, k3, p3) = P[-3:]
                if k3 == "H" and k1 == "H" and abs(p3 - p1) <= 0.5 * a and min(p1, p3) - p2 >= 1.5 * a and i3 - i1 >= 2 * self.k + 2:
                    top = (p1 + p3) / 2
                    self._new("double", "double_top", -1, p2, p2 - (top - p2), max(p1, p3) + 0.25 * a,
                              0.4 + 0.3 * (1 - abs(p3 - p1) / (0.5 * a)) + 0.3 * min(1, (top - p2) / (3 * a)), bar, out,
                              lv={"peak1": p1, "peak2": p3, "neckline": p2})
                elif k3 == "L" and k1 == "L" and abs(p3 - p1) <= 0.5 * a and p2 - max(p1, p3) >= 1.5 * a and i3 - i1 >= 2 * self.k + 2:
                    bot = (p1 + p3) / 2
                    self._new("double", "double_bottom", 1, p2, p2 + (p2 - bot), min(p1, p3) - 0.25 * a,
                              0.4 + 0.3 * (1 - abs(p3 - p1) / (0.5 * a)) + 0.3 * min(1, (p2 - bot) / (3 * a)), bar, out,
                              lv={"trough1": p1, "trough2": p3, "neckline": p2})
            if len(P) >= 5:
                (_, k1, p1), (_, k2, p2), (_, k3, p3), (_, k4, p4), (_, k5, p5) = P[-5:]
                if self.can("hs"):
                    if k5 == "H" and p3 >= max(p1, p5) + 0.5 * a and abs(p1 - p5) <= a and abs(p2 - p4) <= a:
                        nk = (p2 + p4) / 2
                        self._new("hs", "head_shoulders", -1, nk, nk - (p3 - nk), p5 + 0.25 * a,
                                  0.4 + 0.3 * (1 - abs(p1 - p5) / a) + 0.3 * min(1, (p3 - nk) / (4 * a)), bar, out,
                                  lv={"neckline": nk, "head": p3, "left_shoulder": p1, "right_shoulder": p5})
                    elif k5 == "L" and p3 <= min(p1, p5) - 0.5 * a and abs(p1 - p5) <= a and abs(p2 - p4) <= a:
                        nk = (p2 + p4) / 2
                        self._new("hs", "inv_head_shoulders", 1, nk, nk + (nk - p3), p5 - 0.25 * a,
                                  0.4 + 0.3 * (1 - abs(p1 - p5) / a) + 0.3 * min(1, (nk - p3) / (4 * a)), bar, out,
                                  lv={"neckline": nk, "head": p3, "left_shoulder": p1, "right_shoulder": p5})
                if self.can("shift"):
                    # P = L1 H1 L2 H2 L3 : down leg (H2<H1, L2<L1) then L3 > L2 -> higher low
                    if k5 == "L" and p4 < p2 and p3 < p1 and p5 > p3 + 0.25 * a:
                        self._new("shift", "higher_low", 1, p4, p4 + (p4 - p5), p5 - 0.1 * a,
                                  0.4 + 0.3 * min(1, (p5 - p3) / a) + 0.3 * min(1, (p2 - p4) / a), bar, out,
                                  lv={"pivot_low": p5, "prior_low": p3, "pivot_high": p4})
                    elif k5 == "H" and p4 > p2 and p3 > p1 and p5 < p3 - 0.25 * a:
                        self._new("shift", "lower_high", -1, p4, p4 - (p5 - p4), p5 + 0.1 * a,
                                  0.4 + 0.3 * min(1, (p3 - p5) / a) + 0.3 * min(1, (p4 - p2) / a), bar, out,
                                  lv={"pivot_high": p5, "prior_high": p3, "pivot_low": p4})
        # VWAP reclaim / loss (session VWAP; 1m and 5m)
        if self.iv != "30m" and i - self.s0 >= 5 and self.can("vwap"):
            vw = self.vwap[-1]
            back = [(self.b(j)[C], self.vwap[j - self.off]) for j in range(i - 3, i)]
            lo10 = min(x[L] for x in self.win(max(self.s0, i - 10), i))
            hi10 = max(x[H] for x in self.win(max(self.s0, i - 10), i))
            rv = self.rvol()
            if c > vw and all(x < y for x, y in back):
                dep = max(vw - lo10, a)
                self._new("vwap", "vwap_reclaim", 1, vw, vw + dep, lo10, 0.4 + 0.3 * min(1, (rv or 0) / 2) + 0.3 * min(1, dep / (2 * a)),
                          bar, out, state="triggered", lv={"vwap": vw}, rvol=rv, vol_confirm=bool(rv and rv >= 1.5))
            elif c < vw and all(x > y for x, y in back):
                dep = max(hi10 - vw, a)
                self._new("vwap", "vwap_loss", -1, vw, vw - dep, hi10, 0.4 + 0.3 * min(1, (rv or 0) / 2) + 0.3 * min(1, dep / (2 * a)),
                          bar, out, state="triggered", lv={"vwap": vw}, rvol=rv, vol_confirm=bool(rv and rv >= 1.5))

    def active(self):
        return [dict(d) for d in self.act.values()]


# ------------------------------------------------------------------ bars
def bars_1m(rows):
    """score_lib 1-min bar dicts (t ISO, ts epoch, d, o,h,l,c,v, vw) -> tuples."""
    out = []
    for b in rows:
        ts = b.get("ts")
        if ts is None or b.get("c") is None:
            continue
        out.append((float(ts), b["o"], b["h"], b["l"], b["c"], float(b.get("v") or 0), b.get("d"), b.get("vw")))
    return out


def roll(b1, iv):
    """1-min tuples -> iv bars (bucket = epoch // ivs; ET :00/:05/:30 align with UTC). The last bucket may be partial:
    callers decide whether it is complete. VWAP source = volume-weighted 1-min vw where present."""
    s = IV_MIN[iv] * 60
    out, cur = [], None
    for b in b1:
        k = (int(b[T]) // s) * s
        if cur is None or k != cur[0]:
            if cur:
                out.append(cur)
            cur = [k, b[O], b[H], b[L], b[C], b[V], b[D], 0.0, 0.0]
        else:
            cur[H], cur[L], cur[C] = max(cur[H], b[H]), min(cur[L], b[L]), b[C]
            cur[V] += b[V]
        if b[VW]:
            cur[7] += b[VW] * b[V]
            cur[8] += b[V]
    if cur:
        out.append(cur)
    return [(x[0], x[1], x[2], x[3], x[4], x[5], x[6], (x[7] / x[8]) if x[8] else None) for x in out]


# ------------------------------------------------------------------ grading (shared by the backtest and the nightly grader)
def grade(rec_trig, b1, start_idx=None):
    """rec_trig = the detection's 'triggered' record. b1 = 1-min tuples (all sessions, time order).
    From the first 1-min bar starting at/after the trigger record's ts, for horizon.minutes market minutes:
    target touched (high/low) -> target_hit; a 1-min CLOSE beyond invalidation -> invalidated (same bar: invalidated
    first only if the close is beyond it and the target was not touched before that minute); else expired.
    Entry = the trigger record's px (the detecting bar's close). Returns dict or None if no bars after.
    RRFIX 10/21: a setup whose target is on the wrong side of entry (or at it), e.g. price gapped past the trigger and
    past the measured-move target, is NOT graded: outcome "rejected_wrong_side" (final, excluded from every rate).
    Same for an entry already beyond invalidation (no risk left to measure). rr = |target-entry| / |entry-invalidation|.
    Secondary 1:1 grade (outcome_1r): target = entry +/- stop distance, same bars, same invalidation rule."""
    d = rec_trig["direction"]
    kl = rec_trig["key_levels"]
    G, I, e = kl.get("target"), kl.get("invalidation"), rec_trig.get("px")
    if not d or G is None or e is None:
        return None
    reward = (G - e) * d
    risk = (e - I) * d if I is not None else None
    if reward <= 0 or (risk is not None and risk <= 0):
        return {"outcome": "rejected_wrong_side", "final": True, "reject_reason": "target on wrong side of entry" if reward <= 0
                else "entry beyond invalidation", "entry": e, "target": G, "invalidation": I}
    rr = round(reward / risk, 3) if risk else None
    G1 = (e + d * risk) if risk else None
    ts = rec_trig["ts"]
    if start_idx is None:
        lo, hi = 0, len(b1)
        while lo < hi:
            mid = (lo + hi) // 2
            if b1[mid][T] < ts:
                lo = mid + 1
            else:
                hi = mid
        start_idx = lo
    n = rec_trig["horizon"]["minutes"]
    seg = b1[start_idx: start_idx + n]
    if not seg:
        return None
    mfe = mae = 0.0
    out, t_out = "expired", None
    o1 = "expired" if G1 is not None else None
    for b in seg:
        if out == "expired":  # MFE/MAE run to the measured-move outcome only (unchanged meaning)
            fav = (b[H] - e) if d > 0 else (e - b[L])
            adv = (e - b[L]) if d > 0 else (b[H] - e)
            mfe, mae = max(mfe, fav), max(mae, adv)
        if o1 == "expired":
            if (b[H] >= G1) if d > 0 else (b[L] <= G1):
                o1 = "target_hit"
            elif (b[C] < I) if d > 0 else (b[C] > I):
                o1 = "invalidated"
        if out == "expired":
            if (b[H] >= G) if d > 0 else (b[L] <= G):
                out, t_out = "target_hit", b[T] + 60
            elif I is not None and ((b[C] < I) if d > 0 else (b[C] > I)):
                out, t_out = "invalidated", b[T] + 60
        if out != "expired" and o1 != "expired":
            break
    full = len(seg) >= n or out != "expired"
    atr = rec_trig.get("atr_bar") or None
    return {"outcome": out, "final": full, "minutes_to_outcome": round((t_out - ts) / 60, 1) if t_out else None,
            "mfe_bp": round(mfe / e * 1e4, 1), "mae_bp": round(mae / e * 1e4, 1),
            "mfe_atr": round(mfe / atr, 2) if atr else None, "mae_atr": round(mae / atr, 2) if atr else None,
            "n_1m": len(seg), "rr": rr, "outcome_1r": o1 if (o1 and (full or o1 != "expired")) else None}


def rate_key(pattern, iv, d):
    return f"{pattern}|{iv}|{d:+d}" if d else f"{pattern}|{iv}|0"


def aggregate(graded):
    """[(rec_trig, grade)] -> {key: stats}."""
    agg = {}
    rej = Counter()
    for r, g in graded:
        if not g or not g["final"]:
            continue
        k = rate_key(r["pattern"], r["interval"], r["direction"])
        if g.get("outcome") not in ("target_hit", "invalidated", "expired"):  # RRFIX: rejected_wrong_side etc. never count
            rej[k] += 1
            continue
        a = agg.setdefault(k, {"pattern": r["pattern"], "interval": r["interval"], "direction": r["direction"],
                               "n": 0, "target_hit": 0, "invalidated": 0, "expired": 0, "_tt": [], "_tr": [],
                               "_mfe": [], "_mae": [], "_vc": [0, 0], "_rr": [], "_1r": [0, 0]})
        a["n"] += 1
        a[g["outcome"]] += 1
        # GRADEFIX 10/21: label files drop None fields, so an "expired" label has no minutes_to_outcome key
        mto = g.get("minutes_to_outcome")
        if mto is not None:
            a["_tr"].append(mto)
            if g["outcome"] == "target_hit":
                a["_tt"].append(mto)
        if g.get("rr") is not None:
            a["_rr"].append(g["rr"])
        if g.get("outcome_1r") in ("target_hit", "invalidated", "expired"):
            a["_1r"][0] += 1
            a["_1r"][1] += g["outcome_1r"] == "target_hit"
        a["_mfe"].append(g["mfe_bp"])
        a["_mae"].append(g["mae_bp"])
        if r.get("vol_confirm"):
            a["_vc"][0] += 1
            a["_vc"][1] += g["outcome"] == "target_hit"
    med = lambda xs: (sorted(xs)[len(xs) // 2] if xs else None)
    for a in agg.values():
        a["rate"] = round(a["target_hit"] / a["n"], 4) if a["n"] else None
        a["med_min_to_hit"], a["med_min_to_resolve"] = med(a.pop("_tt")), med(a.pop("_tr"))
        a["med_mfe_bp"], a["med_mae_bp"] = med(a.pop("_mfe")), med(a.pop("_mae"))
        vc = a.pop("_vc")
        a["n_vol_confirm"], a["rate_vol_confirm"] = vc[0], (round(vc[1] / vc[0], 4) if vc[0] else None)
        a["low_n"] = a["n"] < 20
        rr = a.pop("_rr")  # RRFIX 10/21: payoff + secondary 1:1 grade
        a["med_rr"] = round(med(rr), 3) if rr else None
        a["breakeven"] = round(1 / (1 + a["med_rr"]), 4) if a["med_rr"] else None
        o1 = a.pop("_1r")
        a["n_1r"], a["hit_1r"] = o1[0], o1[1]
        a["rate_1r"] = round(o1[1] / o1[0], 4) if o1[0] else None
    for k, n in rej.items():
        if k in agg:
            agg[k]["n_rejected_wrong_side"] = n
    return dict(sorted(agg.items()))


def prob_for(rates_doc, pattern, iv, d):
    """-> (prob_est, prob_source, n, extra). Live hit rate replaces backtest once live n >= 20; both kept."""
    if not d:
        return None, "none (neutral context pattern)", None, {}
    k = rate_key(pattern, iv, d)
    bt = ((rates_doc or {}).get("backtest") or {}).get(k) or {}
    lv = ((rates_doc or {}).get("live") or {}).get(k) or {}
    ex = {"prob_backtest": bt.get("rate"), "n_backtest": bt.get("n"), "prob_live": lv.get("rate"), "n_live": lv.get("n")}
    if lv.get("n", 0) >= 20:
        return lv["rate"], "live", lv["n"], ex
    if bt.get("n"):
        ex["prob_note"] = "n<20: low sample" if bt["n"] < 20 else None
        return bt["rate"], "backtest", bt["n"], ex
    return None, "backtest (no samples)", 0, ex
