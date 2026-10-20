#!/usr/bin/env python3
"""Score-change + episode logging for the OID direction score (settings v1.1-20261020).

LOGGING ONLY: score math is unchanged (score_lib.combine). Research/log only - never places orders,
never calls paid APIs. Used by the live daemon (fast pass every cadence_pt.change_refresh_s seconds),
by score_replay_changes.py (replay of a session from 5 s bars) and by daily_scorecard.py.

Live outputs (append-only, ~/oid-data/score):
  changes-YYYYMMDD.jsonl   one row whenever a ticker's integer score changes (plus the first score seen each session)
  episodes-YYYYMMDD.jsonl  one row when a score ends: start/stop ts + price, peak/trough during the hold
                           (5 s SIP bars + live last price), context at start and at stop
  changes-state.json       open episodes, so a daemon restart resumes them (gap > 120 s closes them instead)
  episodes-buffered-YYYYMMDD.jsonl  COMPARISON-ONLY shadow: episodes of a buffered (hysteresis) version of the score.
                           The RAW score stays primary everywhere (changes/episodes, latest.json, live page, scorecard);
                           raw change rows carry buffered_score as an extra field.

Context logged on every change / episode start+stop (ctx):
  flow  : aggressor C/P 15 s + 1 m (the live page C/P chips, af15/af60), thin flags, age, UW C/P, lean5/lean15/ask_lean
  rvol_1m, room to call/put wall in ATR, wall age/staleness, momentum state (last ACCEL/DECEL/RESUME + age)
  tape  : the stock's own 60 s / 120 s tape from 5 s bars (ret bp, HH/HL/LH/LL counts, bp per 10 s, volume rising)
  mkt   : SPY/QQQ 60 s / 120 s returns and whether they agree with the score / the stock's tape
"""
import bisect, glob, gzip, json, math, os
from datetime import datetime, timezone
from pathlib import Path
import score_lib as L

V5_DIR = Path(os.environ.get("OID_SCORE_V5_DIR", str(L.HOME / "oid-data/archive/volume_5s")))
MOM_DIR = L.HOME / "oid-desk/state/momentum"
CPH_DIR = L.HOME / "oid-optflow/data/cp-history"
MOM_QUIET_S = 600          # same as the live page: a momentum flag older than 10 min reads "quiet"
RING_S = 200               # keep ~200 s of 5 s bars per symbol in the live ring
CP_BAND = 1.10             # C/P > 1.10 = call side, < 1/1.10 = put side, between = flat
GAP_CLOSE_S = 120          # on restart, open episodes whose last update is older than this are closed (stop_reason daemon_gap)
INDEX = ("SPY", "QQQ")
SESSION_END_HM = (13, 0)


def sgn(v):
    return 0 if not v else (1 if v > 0 else -1)


def utc_str(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def bp(a, b):
    try:
        return round((float(a) / float(b) - 1.0) * 1e4, 2) if (a and b) else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def r4(v):
    return None if v is None else round(float(v), 4)


def session_end_t(date):
    d = datetime.strptime(date, "%Y-%m-%d").replace(hour=SESSION_END_HM[0], minute=SESSION_END_HM[1], tzinfo=L.PT)
    return d.timestamp()


# ------------------------------------------------------------------ 5 s bars
def parse_5s(ln):
    """-> (sym, bar) for an RTH 5 s SIP bar with prices, else None.  bar = [t_start, t_end, o, h, l, c, v, rvol_1m]"""
    if '"rth"' not in ln:
        return None
    try:
        d = json.loads(ln)
    except Exception:
        return None
    if d.get("session") != "rth" or d.get("close") is None:
        return None
    return d["symbol"], [d["bucket_start_ns"] / 1e9, d["bucket_end_ns"] / 1e9, d.get("open"), d.get("high"), d.get("low"),
                         d["close"], d.get("volume") or 0, d.get("rvol_1m_at_end")]


def v5_files(date, root=None):
    return sorted(glob.glob(str(Path(root or V5_DIR) / f"date={date}" / "part-*.jsonl")))


def load_5s(date, root=None, only=None):
    """Whole session of RTH 5 s bars -> {sym: [bar...]} sorted, last write wins per bucket.
    root: volume_5s archive dir (default core V5_DIR; light/wide profile passes archive-wide/volume_5s). only: symbol filter."""
    by = {}
    for p in v5_files(date, root):
        with open(p, "r", errors="replace") as f:
            for ln in f:
                x = parse_5s(ln)
                if x and (only is None or x[0] in only):
                    by.setdefault(x[0], {})[x[1][0]] = x[1]
    return {s: [d[k] for k in sorted(d)] for s, d in by.items()}


class Ring:
    """Recent 5 s bars per symbol (trim=None keeps everything, for replay/scorecard)."""

    def __init__(self, trim=RING_S):
        self.b, self.trim, self._ends = {}, trim, {}

    def add(self, sym, bar):
        q = self.b.setdefault(sym, [])
        if q and q[-1][0] == bar[0]:
            q[-1] = bar
        elif q and bar[0] < q[-1][0]:  # late bucket: insert in order
            i = len(q)
            while i and q[i - 1][0] > bar[0]:
                i -= 1
            if i and q[i - 1][0] == bar[0]:
                q[i - 1] = bar
            else:
                q.insert(i, bar)
        else:
            q.append(bar)
        if self.trim:
            cut = q[-1][1] - self.trim
            while q and q[0][1] < cut:
                q.pop(0)

    def upto(self, sym, t, tail=None):
        q = self.b.get(sym) or []
        if self.trim is None:  # full-day lists (replay/scorecard): bisect on end times
            e = self._ends.get(sym)
            if e is None or len(e) != len(q):
                e = self._ends[sym] = [x[1] for x in q]
            j = bisect.bisect_right(e, t + 0.001)
            return q[max(0, j - tail):j] if tail else q[:j]
        out = [x for x in q if x[1] <= t + 0.001]
        return out[-tail:] if tail else out

    def last(self, sym, t):
        q = self.upto(sym, t, tail=1)
        return q[-1] if q else None

    def tape(self, sym, t, win):
        q = self.upto(sym, t, tail=int(win / 5) + 4)
        if not q:
            return None
        end = q[-1][1]
        w = [x for x in q if x[0] >= end - win - 0.001]
        if not w:
            return None
        prior = [x for x in q if x[1] <= end - win + 0.001]
        ref = prior[-1][5] if prior else (w[0][2] or w[0][5])
        r = bp(w[-1][5], ref)
        hi = [x[3] if x[3] is not None else x[5] for x in w]
        lo = [x[4] if x[4] is not None else x[5] for x in w]
        n = len(w)
        mid = end - win / 2.0
        v1 = sum(x[6] for x in w if x[0] < mid)
        v2 = sum(x[6] for x in w if x[0] >= mid)
        return {"ret_bp": r, "hh": sum(1 for i in range(1, n) if hi[i] > hi[i - 1]), "hl": sum(1 for i in range(1, n) if lo[i] > lo[i - 1]),
                "lh": sum(1 for i in range(1, n) if hi[i] < hi[i - 1]), "ll": sum(1 for i in range(1, n) if lo[i] < lo[i - 1]),
                "speed_bp_10s": round(r / (win / 10.0), 2) if r is not None else None,
                "vol_rising": (v2 > v1) if (v1 or v2) else None, "vol_1st": v1, "vol_2nd": v2, "n": n,
                "covered_s": round(end - (prior[-1][1] if prior else w[0][0])), "lag_s": round(t - end, 1)}


class Tail5s:
    """Incrementally tails today's volume_5s jsonl (oid-quote writer, read-only) into a Ring."""

    def __init__(self, ring, backfill_bytes=4_000_000, root=None, only=None):
        self.ring, self.pos, self.date, self.back = ring, {}, None, backfill_bytes
        self.root, self.only = root, (set(only) if only else None)   # light/wide: own archive dir; SPY/QQQ-only tail of core

    def poll(self, date):
        if date != self.date:
            self.date, self.pos = date, {}
        new = []
        for p in v5_files(date, self.root):
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            pos = self.pos.get(p)
            skip = False
            if pos is None:
                pos = max(0, size - self.back)
                skip = pos > 0
            if size < pos:
                pos, skip = 0, False
            if size == pos:
                self.pos[p] = pos
                continue
            with open(p, "rb") as f:
                f.seek(pos)
                data = f.read(size - pos)
            end = data.rfind(b"\n")
            if end < 0:
                continue
            self.pos[p] = pos + end + 1
            lines = data[:end + 1].decode("utf-8", "replace").split("\n")
            if skip:
                lines = lines[1:]
            for ln in lines:
                x = parse_5s(ln)
                if x and (self.only is None or x[0] in self.only):
                    self.ring.add(*x)
                    new.append(x)
        return new


# ------------------------------------------------------------------ context
def cp_side(cp):
    if cp is None:
        return None
    try:
        cp = float(cp)
    except (TypeError, ValueError):
        return None
    return 1 if cp > CP_BAND else -1 if cp < 1.0 / CP_BAND else 0


def build_ctx(sym, t, px, atr, flow, rvol_1m, walls, mom, ring, extra=None):
    flow = flow or {}
    side = None
    for k, th in (("cp_60s", "thin_60s"), ("cp_15s", "thin_15s")):
        if flow.get(k) is not None and not flow.get(th):
            side = cp_side(flow[k])
            break
    if side is None:
        ln = flow.get("lean5") or flow.get("lean15") or flow.get("ask_lean")
        side = 1 if ln == "CALL" else -1 if ln == "PUT" else (0 if ln == "FLAT" else None)
    w = walls or {}
    cw, pw = w.get("cw"), w.get("pw")
    room_c = r4((cw - px) / atr) if (cw is not None and px and atr) else None
    room_p = r4((px - pw) / atr) if (pw is not None and px and atr) else None
    tape = {str(win): ring.tape(sym, t, win) for win in (60, 120)} if ring else {}
    mkt = {}
    if ring:
        for s in INDEX:
            mkt[s] = {str(win): (ring.tape(s, t, win) or {}).get("ret_bp") for win in (60, 120)}
        for win in ("60", "120"):
            xs = [mkt[s][win] for s in INDEX if mkt[s].get(win) is not None]
            mkt["avg_" + win] = round(sum(xs) / len(xs), 2) if xs else None
            st = (tape.get(win) or {}).get("ret_bp")
            mkt["agrees_stock_" + win] = (sgn(mkt["avg_" + win]) == sgn(st)) if (xs and st and sgn(mkt["avg_" + win])) else None
    ctx = {"flow": flow, "flow_dir": side, "rvol_1m": rvol_1m, "surge": (rvol_1m >= 3) if rvol_1m is not None else None,
           "walls": {"cw": cw, "pw": pw, "gf": w.get("gf"), "age_s": w.get("age_s"), "stale": w.get("stale"), "src": w.get("src"),
                     "as_of_pt": w.get("as_of_pt")},
           "room_call_atr": room_c, "room_put_atr": room_p, "mom": mom or {"state": None}, "tape": tape, "mkt": mkt}
    if extra:
        ctx.update(extra)
    return ctx


def agree(score, ctx):
    """Agreement of context with the score's direction (None when score is 0 or input missing/flat)."""
    d = sgn(score)

    def a(x):
        return None if (d == 0 or not x) else (x == d)

    def rs(v):
        return sgn(v) if v is not None else None

    tp, mk = ctx.get("tape") or {}, ctx.get("mkt") or {}
    room = ctx.get("room_call_atr") if d > 0 else ctx.get("room_put_atr") if d < 0 else None
    return {"cp": a(ctx.get("flow_dir")), "stock_tape_60": a(rs((tp.get("60") or {}).get("ret_bp"))),
            "stock_tape_120": a(rs((tp.get("120") or {}).get("ret_bp"))), "market_60": a(rs(mk.get("avg_60"))),
            "market_120": a(rs(mk.get("avg_120"))), "room_dir_atr": room, "surge": ctx.get("surge"),
            "mom_state": (ctx.get("mom") or {}).get("state")}


def ctx_live(r, row, ring, t):
    """Context from a live page state row (127.0.0.1:8791/state.json)."""
    a15, a60 = r.get("af15") or {}, r.get("af60") or {}
    flow = {"cp_15s": a15.get("cp"), "thin_15s": a15.get("thin"), "net_k_15s": a15.get("net_k"), "n_15s": a15.get("n"),
            "cp_60s": a60.get("cp"), "thin_60s": a60.get("thin"), "net_k_60s": a60.get("net_k"), "n_60s": a60.get("n"),
            "age_s": r.get("af_age"), "stale": r.get("af_stale"), "uw_cp": r.get("cp"), "lean5": r.get("lean5"),
            "lean15": r.get("lean15"), "ask_lean": r.get("ask_lean"), "src": "live_page"}
    W = r.get("walls") or {}
    lv = W.get("lv") or {}
    g = lambda k: (lv.get(k) or {}).get("px")
    walls = {"cw": g("cw"), "pw": g("pw"), "gf": g("gf"), "age_s": W.get("age_s"), "stale": W.get("stale"), "src": W.get("src"),
             "as_of_pt": W.get("as_of_pt")}
    m = r.get("mom") or {}
    mom = {"state": m.get("st"), "raw": m.get("raw"), "since_t": m.get("t"), "since_pt": m.get("since_pt"),
           "age_s": round(t - m["t"]) if m.get("t") else None, "prov": m.get("prov")} if m else {"state": None}
    return build_ctx(r["sym"], t, row["px"], row.get("atr"), flow, r.get("rvol"), walls, mom, ring,
                     extra={"day_rvol": r.get("day_rvol"), "chg_pct": r.get("chg"),
                            "vdir": r.get("vdir"), "cpdir": r.get("cpdir")})   # WIDECP: live-page volume + C/P direction arrows


# ------------------------------------------------------------------ replay sources (logged files only, no lookahead)
class Sources:
    """Read-only historical inputs for a date: 5 s bars, optflow cp-history (15 s), momentum events, logged score rows."""

    def __init__(self, date, need_bars=True):
        self.date = date
        d = date.replace("-", "")
        self.bars = load_5s(date) if need_bars else {}
        self.cph = []
        for p in (CPH_DIR / f"{date}.jsonl", CPH_DIR / f"{date}.jsonl.gz"):
            if not p.exists():
                continue
            op = gzip.open if p.suffix == ".gz" else open
            with op(p, "rt") as f:
                for ln in f:
                    try:
                        x = json.loads(ln)
                    except Exception:
                        continue
                    if "t" in x and "u" in x:
                        self.cph.append((x["t"] + 15, x["u"]))   # sample usable once its 15 s slot closes
            break
        self.cph.sort(key=lambda x: x[0])
        self.cph_t = [x[0] for x in self.cph]
        self.mom = {}
        p = MOM_DIR / f"events-{d}.jsonl"
        if p.exists():
            for ln in p.open():
                try:
                    e = json.loads(ln)
                except Exception:
                    continue
                te = L._pt_t(e.get("time_pt"))
                if te and e.get("symbol") and e.get("kind"):
                    self.mom.setdefault(e["symbol"], []).append((te, e["kind"], e.get("time_pt")))
        for v in self.mom.values():
            v.sort()
        self.rows = {}
        p = L.OUT / f"scores-{d}.jsonl"
        if p.exists():
            for ln in p.open():
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                self.rows.setdefault(r["sym"], []).append(r)
        for v in self.rows.values():
            v.sort(key=lambda r: r["t"])

    def snap(self, sym, t):
        best = None
        for r in self.rows.get(sym) or []:
            if r["t"] <= t + 0.001:
                best = r
            else:
                break
        return best

    def flow_at(self, sym, t):
        import bisect
        i = bisect.bisect_right(self.cph_t, t) - 1
        if i < 0:
            return {"src": "cp-history", "missing": True}, None
        tt, u = self.cph[i]
        x = u.get(sym) or {}
        f15, f60 = x.get("15") or [None] * 6, x.get("60") or [None] * 6
        flow = {"cp_15s": f15[0], "thin_15s": f15[0] is None, "why_15s": f15[5], "cp_60s": f60[0], "thin_60s": f60[0] is None,
                "why_60s": f60[5], "n_15s": f15[4], "n_60s": f60[4], "age_s": round(t - tt), "src": "cp-history",
                "uw_cp": None, "lean5": None, "lean15": None, "ask_lean": None}
        score_flow = None
        if f60[0] is not None:
            score_flow = {"x": {"cp": f60[0], "thin": False, "net_k": None, "cov": None},
                          "f": {"src": "alpaca-opra-aggressor-1m", "age_s": round(t - tt), "stale": (t - tt) > 60}}
        return flow, score_flow

    def mom_at(self, sym, t):
        last = None
        for te, k, tp in self.mom.get(sym) or []:
            if te <= t + 0.001:
                last = (te, k, tp)
            else:
                break
        if not last:
            return {"state": "quiet", "raw": None, "since_t": None, "age_s": None}
        age = t - last[0]
        return {"state": last[1] if age <= MOM_QUIET_S else "quiet", "raw": last[1], "since_t": last[0], "since_pt": last[2], "age_s": round(age)}

    @staticmethod
    def walls_from_snap(row, t, cfg):
        if not row:
            return None
        c = row.get("comps") or {}
        wx, wf = (c.get("walls") or {}).get("x") or {}, (c.get("walls") or {}).get("f") or {}
        fx, ff = (c.get("flip") or {}).get("x") or {}, (c.get("flip") or {}).get("f") or {}
        if not wx and not fx:
            return None
        a0 = wf.get("age_s") if wf.get("age_s") is not None else ff.get("age_s")
        age = None if a0 is None else round(a0 + (t - row["t"]))
        return {"cw": wx.get("cw"), "pw": wx.get("pw"), "gf": fx.get("gf"), "gf_ok": bool(ff.get("gf_ok")), "gf_status": ff.get("gf_status"),
                "stale": bool(age is not None and age > cfg.get("staleness", {}).get("walls_stale_s", 1200)), "age_s": age,
                "src": wf.get("src") or ff.get("src"), "as_of_pt": wf.get("as_of") or ff.get("as_of")}


# ------------------------------------------------------------------ buffered shadow score (comparison only)
BUFFER_BAND = 0.15


def buffered(prev, raw, band=BUFFER_BAND, mx=3):
    """Hysteresis shadow of the integer score: it only moves when raw clears the .5 cutoff by an extra `band`
    (e.g. +1 -> +2 needs raw > 1.65, +1 -> 0 needs raw < 0.35). COMPARISON ONLY - the raw score stays primary."""
    if raw is None:
        return prev
    r = int(math.copysign(math.floor(abs(raw) + 0.5), raw)) if raw else 0
    if prev is None:
        return r
    if raw > prev + 0.5 + band or raw < prev - 0.5 - band:
        return max(-mx, min(mx, r))
    return prev


# ------------------------------------------------------------------ change / episode tracker
def comps_compact(row):
    return {k: [c.get("c"), c.get("q"), c.get("w")] for k, c in (row.get("comps") or {}).items()}


class Tracker:
    """Raw score = PRIMARY (changes-*.jsonl, episodes-*.jsonl). If shadow=True a second, comparison-only tracker follows
    the buffered score and writes only episodes-buffered-*.jsonl (raw change rows carry buffered_score as a field)."""

    def __init__(self, out, mode="live", persist=True, shadow=True, prefix="", band=BUFFER_BAND, tag="", tag_fn=None):
        """tag: file-name tag for a separate score profile ("wide" -> changes-wide-*, episodes-wide-*, episodes-wide-buffered-*,
        changes-wide-state.json). tag_fn(sym) -> dict merged into every change/episode row (score_profile, sector...)."""
        self.out, self.mode, self.persist, self.prefix, self.band = Path(out), mode, persist, prefix, band
        self.tag, self.tag_fn = tag, tag_fn
        self.ep, self.date, self.seen, self.buf = {}, None, set(), {}
        self.n_changes, self.n_eps, self.last_save = 0, 0, 0
        self.shadow = Tracker(out, mode, persist=False, shadow=False, prefix="buffered", band=band, tag=tag, tag_fn=tag_fn) if shadow else None

    def _f(self, kind, date):
        return self.out / f"{kind}{'-' + self.tag if self.tag else ''}{'-' + self.prefix if self.prefix else ''}-{date.replace('-', '')}.jsonl"

    def _w(self, kind, date, rows):
        if not rows or (self.prefix and kind == "changes"):   # shadow tracker writes episodes only
            return
        with self._f(kind, date).open("a") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")

    # -- persistence (live only)
    def state_path(self):
        return self.out / f"changes{'-' + self.tag if self.tag else ''}-state.json"

    def resume(self, date, now):
        if not self.persist:
            return
        try:
            st = json.loads(self.state_path().read_text())
        except Exception:
            return
        if st.get("date") != date:
            return
        self.date, self.seen = date, set(st.get("seen") or [])
        self.buf = st.get("buf") or {}
        if self.shadow is not None:
            self.shadow.date, self.shadow.seen = date, set(st.get("seen") or [])
            seps = st.get("shadow_ep") or {}
            for s, e in seps.items():
                if now - (e.get("last_t") or 0) > GAP_CLOSE_S:
                    self.shadow._close(e, e["last_t"], e["last_px"], None, None, "daemon_gap")
                    self.buf.pop(s, None)
                else:
                    self.shadow.ep[s] = e
        eps = st.get("ep") or {}
        stale = {s: e for s, e in eps.items() if now - (e.get("last_t") or 0) > GAP_CLOSE_S}
        self.ep = {s: e for s, e in eps.items() if s not in stale}
        for s, e in stale.items():
            self._close(e, e["last_t"], e["last_px"], None, None, "daemon_gap")
        return len(self.ep), len(stale)

    def save(self, now=None, force=False):
        if not self.persist or self.date is None:
            return
        now = now or 0
        if not force and now - self.last_save < 30:
            return
        p = self.state_path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"date": self.date, "saved_t": now, "seen": sorted(self.seen), "ep": self.ep, "buf": self.buf,
                                   "shadow_ep": self.shadow.ep if self.shadow is not None else {}}, separators=(",", ":")))
        tmp.replace(p)
        self.last_save = now

    # -- prices
    def bars(self, items):
        if self.shadow is not None:
            self.shadow.bars(items)
        for sym, b in items:
            e = self.ep.get(sym)
            if not e or b[0] < e["t0"] - 0.001:
                continue
            h = b[3] if b[3] is not None else b[5]
            lo = b[4] if b[4] is not None else b[5]
            if h > e["hi"]:
                e["hi"], e["hi_t"] = h, b[1]
            if lo < e["lo"]:
                e["lo"], e["lo_t"] = lo, b[1]
            e["n_bars"] = e.get("n_bars", 0) + 1

    # -- main entry
    def observe(self, date, t, sym, px, row, ctx, version):
        if self.date != date:
            if self.ep:
                self.close_all(None, "date_roll")
            self.date, self.seen, self.buf = date, set(), {}
        bsc = None
        if self.shadow is not None:  # comparison-only buffered shadow
            bsc = buffered(self.buf.get(sym), row.get("raw"), self.band)
            self.buf[sym] = bsc
            self.shadow.observe(date, t, sym, px, dict(row, score=bsc), ctx, version)
        e = self.ep.get(sym)
        score = row["score"]
        if e is not None:
            if px > e["hi"]:
                e["hi"], e["hi_t"] = px, t
            if px < e["lo"]:
                e["lo"], e["lo_t"] = px, t
            e["last_t"], e["last_px"], e["n"] = t, px, e["n"] + 1
            if score == e["score"]:
                return None
            self._close(e, t, px, score, ctx, "score_change")
        reason = "score_change" if e is not None else ("first_seen" if sym not in self.seen else "resume_after_gap")
        self.seen.add(sym)
        ch = {"kind": "score_change", "sym": sym, "date": date, "score": score, "prev_score": e["score"] if e else None,
              "raw": row.get("raw"), "prev_raw": e["raw"] if e else None, "t": round(t, 1), "t_utc": utc_str(t), "t_pt": L.pt_str(t),
              "px": r4(px), "atr": row.get("atr"), "coverage": row.get("coverage"), "stale": row.get("stale"), "missing": row.get("missing"),
              "settings_version": version, "config_version": row.get("config_version"), "mode": self.mode, "trigger": "fast",
              "prev_start_t": round(e["t0"], 1) if e else None, "prev_start_utc": utc_str(e["t0"]) if e else None,
              "prev_start_pt": L.pt_str(e["t0"]) if e else None, "prev_duration_s": round(t - e["t0"], 1) if e else None,
              "prev_start_px": e["px0"] if e else None, "prev_ret_bp": bp(px, e["px0"]) if e else None,
              "start_reason": reason, "agree": agree(score, ctx), "comps": row.get("comps"), "ctx": ctx}
        if self.shadow is not None:
            ch["buffered_score"] = bsc
            ch["buffered_band"] = self.band
        if self.tag_fn is not None:
            ch.update(self.tag_fn(sym) or {})
        self._w("changes", date, [ch])
        self.n_changes += 1
        self.ep[sym] = {"sym": sym, "date": date, "score": score, "raw": row.get("raw"), "t0": t, "px0": r4(px), "hi": px, "hi_t": t,
                        "lo": px, "lo_t": t, "last_t": t, "last_px": px, "n": 1, "n_bars": 0, "start_reason": reason,
                        "version": version, "comps0": comps_compact(row), "ctx0": ctx}
        return ch

    def _close(self, e, t, px, next_score, ctx_stop, reason):
        d = sgn(e["score"])
        pk, tr = bp(e["hi"], e["px0"]), bp(e["lo"], e["px0"])
        ret = bp(px, e["px0"])
        row = {"kind": "score_episode", "sym": e["sym"], "date": e["date"], "score": e["score"], "dir": d, "raw_start": e["raw"],
               "start_t": round(e["t0"], 1), "start_utc": utc_str(e["t0"]), "start_pt": L.pt_str(e["t0"]),
               "stop_t": round(t, 1), "stop_utc": utc_str(t), "stop_pt": L.pt_str(t), "duration_s": round(t - e["t0"], 1),
               "start_px": e["px0"], "stop_px": r4(px), "ret_bp": ret, "gain_bp": (round(ret * d, 2) + 0.0 if (d and ret is not None) else None),
               "peak_px": r4(e["hi"]), "peak_t": round(e["hi_t"], 1), "peak_pt": L.pt_str(e["hi_t"]), "peak_bp": pk,
               "trough_px": r4(e["lo"]), "trough_t": round(e["lo_t"], 1), "trough_pt": L.pt_str(e["lo_t"]), "trough_bp": tr,
               "mfe_bp": (pk + 0.0 if d > 0 else -tr + 0.0 if d < 0 else None) if (pk is not None and tr is not None) else None,
               "mae_bp": (tr + 0.0 if d > 0 else -pk + 0.0 if d < 0 else None) if (pk is not None and tr is not None) else None,
               "next_score": next_score, "start_reason": e.get("start_reason"), "stop_reason": reason, "n_obs": e["n"],
               "n_5s_bars": e.get("n_bars", 0), "price_src": "5s SIP bars (high/low) + score-pass last price",
               "settings_version": e.get("version"), "mode": self.mode, "comps_start": e.get("comps0"),
               "agree_start": agree(e["score"], e.get("ctx0") or {}), "ctx_start": e.get("ctx0"), "ctx_stop": ctx_stop}
        if self.prefix:
            row.update({"kind": "score_episode_buffered_shadow", "shadow": True, "buffered_band": self.band,
                        "note": "comparison-only shadow; the raw score is primary"})
        if self.tag_fn is not None:
            row.update(self.tag_fn(e["sym"]) or {})
        self._w("episodes", e["date"], [row])
        self.n_eps += 1
        return row

    def close_all(self, t, reason, px_by=None):
        if self.shadow is not None:
            self.shadow.close_all(t, reason, px_by)
        out = []
        for s, e in list(self.ep.items()):
            tt = t if t is not None else e["last_t"]
            px = (px_by or {}).get(s) or e["last_px"]
            out.append(self._close(e, tt, px, None, None, reason))
        self.ep = {}
        self.save(force=True)
        return out


# ------------------------------------------------------------------ secondary check: move +5/15/30/60 s after each change
FWD_HORIZONS = (5, 15, 30, 60)


def forward_moves(changes, bars, horizons=FWD_HORIZONS, t_end=None):
    """Post-session companion to changes-YYYYMMDD.jsonl (no lookahead in the live log; computed after the fact).

    changes: score_change rows; bars: {sym: [5 s bar...]} from load_5s.  Base = close of the last 5 s bar ending at or
    before the change; +h = close of the last bar ending at or before change+h (must end after the change, and not
    past t_end).  ret_bp = raw move, gain_bp = move signed to the score (None for score 0).  Granularity is 5 s."""
    ends = {s: [b[1] for b in bl] for s, bl in bars.items()}
    out = []
    for c in changes:
        s, t = c.get("sym"), c.get("t")
        bl, e = bars.get(s) or [], ends.get(s) or []
        if t is None or not bl:
            continue
        i0 = bisect.bisect_right(e, t + 0.001) - 1
        base = bl[i0][5] if i0 >= 0 else None
        d = sgn(c.get("score"))
        row = {"kind": "score_change_fwd", "sym": s, "date": c.get("date"), "t": c.get("t"), "t_pt": c.get("t_pt"),
               "score": c.get("score"), "prev_score": c.get("prev_score"), "change_px": c.get("px"), "base_px": r4(base),
               "base_bar_end_t": round(bl[i0][1], 1) if i0 >= 0 else None, "price_src": "5s SIP bar closes", "fwd": {}}
        for h in horizons:
            tt = t + h if t_end is None else min(t + h, t_end)
            j = bisect.bisect_right(e, tt + 0.001) - 1
            if base is None or j <= i0 or (t_end is not None and t + h > t_end + 0.001):
                row["fwd"][str(h)] = None
                continue
            r = bp(bl[j][5], base)
            row["fwd"][str(h)] = {"px": r4(bl[j][5]), "bar_end_t": round(bl[j][1], 1), "ret_bp": r,
                                  "gain_bp": (round(r * d, 2) + 0.0) if (d and r is not None) else None}
        out.append(row)
    return out
