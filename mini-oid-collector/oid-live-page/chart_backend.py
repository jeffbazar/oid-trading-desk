#!/usr/bin/env python3
"""OID live page CHART backend (2026-10-20). Read-only research tool; never writes, never places orders.

Spawned by livepage.py (one long-lived child, run with the oid-desk venv python because it needs duckdb).
Protocol: one JSON request per stdin line -> one JSON reply per stdout line.
  request  {"id": n, "sym": "NVDA", "iv": "1m", "range": "1D", "ext": 1, "since": null, "cur_walls": {...}}
  reply    {"id": n, "ok": true, "data": {...}}  or  {"id": n, "ok": false, "error": "..."}

Data per interval (see Field Guide page 30):
  15s  <- 5-second buckets (volume_5s), Parquet for past days, live JSONL for today, aggregated 3:1
  1m   <- bars_1m (Parquet past days; today = live websocket JSONL + final REST copy, final wins);
          Sector watch days with no archive fall back to the bar store JSON (regular hours only)
  5m / 15m / 1h / 1d <- Parquet rollups for past days; today (and Sector watch days without Parquet) rolled up from 1m here
  score <- ~/oid-data/score changes-*.jsonl (live) > replay-*/changes-*.jsonl > scores-*.jsonl / backfill-scores-*.jsonl
  C/P   <- ~/oid-optflow/data/cp-history(-wide)/YYYY-MM-DD.jsonl[.gz]
  walls <- ~/oid-data/walls-history/walls-YYYYMMDD.jsonl (livepage recorder) + walls carried in score rows + the live level
Everything is aligned onto the bar grid: the value shown on a bar is the last value known at that bar's close.
"""
import gzip
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

ET, PT, UTC = ZoneInfo("America/New_York"), ZoneInfo("America/Los_Angeles"), timezone.utc
HOME = Path.home()
HERE = Path(__file__).resolve().parent
ROOT = {"core": HOME / "oid-data/archive", "wide": HOME / "oid-data/archive-wide"}
STORE = {"core": HOME / "oid-desk/desk/cache/bars/store", "wide": HOME / "oid-quote/cache/bars-wide/store"}
SCORE_DIR = HOME / "oid-data/score"
CP_DIR = {"core": HOME / "oid-optflow/data/cp-history", "wide": HOME / "oid-optflow/data/cp-history-wide"}
WALL_HIST = HOME / "oid-data/walls-history"
MOM_LOG = HOME / "oid-data/archive/momentum_state"            # MOMSTATE: live page change log (JSONL, 90 days)
MOM_PQ = HOME / "oid-data/archive/parquet/momentum_state"     # MOMSTATE: Parquet copy (forever)
MOM_EV = HOME / "oid-desk/state/momentum"                     # momentum engine events-YYYYMMDD.jsonl (derive fallback)
MOM_CODE = {"accelerate": 3, "resume": 2, "decelerate": 1, "quiet": 0}
MOM_QUIET_S = 600   # same rule as the live page: no new flag for 10 min -> quiet
IV_S = {"15s": 15, "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
RANGE_D = {"1D": 0, "1W": 6, "1M": 30, "3M": 91, "YTD": None, "1Y": 365}
MAX_BARS = int(os.environ.get("OID_CHART_MAX_BARS", "4000"))
TODAY_TTL = 3.0
IDLE_EXIT_S = float(os.environ.get("OID_CHART_IDLE_EXIT_S", "900"))   # no request for 15 min -> exit, free memory
HIST_TTL = 600.0
WALL_MAX_AGE = 4 * 86400   # same rule as the live page: never draw walls older than 4 days
SESS = {"pre": "p", "rth": "r", "post": "a"}

DB = duckdb.connect()
DB.execute("SET threads=2")
DB.execute("SET memory_limit='256MB'")

COLS_1M = ("{symbol:'VARCHAR',bar_start_ns:'BIGINT',open:'DOUBLE',high:'DOUBLE',low:'DOUBLE',close:'DOUBLE',"
           "volume:'BIGINT',session:'VARCHAR',final:'BOOLEAN',ingest_ts_ns:'BIGINT'}")
COLS_5S = ("{symbol:'VARCHAR',bucket_start_ns:'BIGINT',open:'DOUBLE',high:'DOUBLE',low:'DOUBLE',close:'DOUBLE',"
           "volume:'BIGINT',vwap:'DOUBLE',session:'VARCHAR',ingest_ts_ns:'BIGINT'}")


def log(m):
    sys.stderr.write(f"[chart {datetime.now(PT).strftime('%H:%M:%S')}] {m}\n")
    sys.stderr.flush()


def et_day(ts):
    return datetime.fromtimestamp(ts, ET).strftime("%Y-%m-%d")


def day_bounds(d):
    """ET calendar day -> (start epoch, end epoch)."""
    a = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=ET)
    return a.timestamp(), (a + timedelta(days=1)).timestamp()


def sess_of(ts):
    t = datetime.fromtimestamp(ts, ET)
    m = t.hour * 60 + t.minute
    return "r" if 570 <= m < 960 else ("p" if m < 570 else "a")


def r4(x):
    return None if x is None else round(float(x), 4)


# ---------------------------------------------------------------- partition listings (cached 60 s)
_LS = {}


def part_dates(tier, table, kind):
    """kind 'pq' -> dates with Parquet files, 'js' -> dates with live JSONL."""
    k = (tier, table, kind)
    hit = _LS.get(k)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    base = ROOT[tier] / ("parquet/" + table if kind == "pq" else table)
    out = {}
    try:
        for p in base.iterdir():
            if not p.name.startswith("date="):
                continue
            fs = sorted(str(f) for f in p.glob("*.parquet" if kind == "pq" else "*.jsonl"))
            if fs:
                out[p.name[5:]] = fs
    except OSError:
        pass
    _LS[k] = (time.time(), out)
    return out


_STJ = {}


def store_bars(tier, sym):
    """Bar store JSON (regular-hours 1-min, ~25 sessions) -> {date: [(t,o,h,l,c,v,'r',1)]}."""
    p = STORE[tier] / f"{sym}-1m.json"
    try:
        m = p.stat().st_mtime
    except OSError:
        return {}
    hit = _STJ.get(p)
    if hit and hit[0] == m:
        return hit[1]
    out = {}
    try:
        for b in json.loads(p.read_text()).get("bars") or []:
            t = datetime.strptime(b["t"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
            out.setdefault(b.get("d") or et_day(t), []).append((t, b["o"], b["h"], b["l"], b["c"], b.get("v") or 0, "r", 1))
    except Exception as e:
        log(f"store {p.name}: {e}")
    if len(_STJ) > 40:
        _STJ.clear()
    _STJ[p] = (m, out)
    return out


def tier_of(sym):
    if (STORE["core"] / f"{sym}-1m.json").exists() or _core_has(sym):
        return "core"
    if (STORE["wide"] / f"{sym}-1m.json").exists():
        return "wide"
    return None


_CORE_SYMS = {"t": 0, "s": set()}


def _core_has(sym):
    if time.time() - _CORE_SYMS["t"] > 3600:
        try:
            d = part_dates("core", "bars_1d", "pq")
            last = sorted(d)[-1]
            _CORE_SYMS["s"] = {r[0] for r in DB.execute(f"select distinct symbol from read_parquet({d[last]!r})").fetchall()}
        except Exception:
            pass
        _CORE_SYMS["t"] = time.time()
    return sym in _CORE_SYMS["s"]


# ---------------------------------------------------------------- bar queries
def q_1m(files, sym, t0, t1, js):
    src = (f"read_json({files!r}, format='newline_delimited', columns={COLS_1M}, ignore_errors=true)" if js
           else f"read_parquet({files!r}, union_by_name=true)")
    sql = (f"select bar_start_ns, open, high, low, close, volume, session, coalesce(final,false) f from {src} "
           f"where symbol=? and bar_start_ns>=? and bar_start_ns<? and close is not null "
           f"qualify row_number() over (partition by bar_start_ns order by coalesce(final,false) desc, ingest_ts_ns desc nulls last)=1 "
           f"order by bar_start_ns")
    rows = DB.execute(sql, [sym, int(t0 * 1e9), int(t1 * 1e9)]).fetchall()
    return [(r[0] / 1e9, r[1], r[2], r[3], r[4], r[5] or 0, SESS.get(r[6], sess_of(r[0] / 1e9)), 1 if r[7] else 0) for r in rows]


def q_tf_pq(files, sym, t0, t1, daily=False):
    sess = "'rth'" if daily else "session"
    sql = (f"select bar_start_ns, open, high, low, close, volume, {sess} from read_parquet({files!r}, union_by_name=true) "
           f"where symbol=? and bar_start_ns>=? and bar_start_ns<? and close is not null "
           f"qualify row_number() over (partition by bar_start_ns order by ingest_ts_ns desc nulls last)=1 order by bar_start_ns")
    rows = DB.execute(sql, [sym, int(t0 * 1e9), int(t1 * 1e9)]).fetchall()
    return [(r[0] / 1e9, r[1], r[2], r[3], r[4], r[5] or 0, SESS.get(r[6], "r"), 1) for r in rows]


def q_15s(files, sym, t0, t1, js):
    src = (f"read_json({files!r}, format='newline_delimited', columns={COLS_5S}, ignore_errors=true)" if js
           else f"read_parquet({files!r}, union_by_name=true)")
    sql = (f"with d as (select bucket_start_ns bs, arg_max(open, ingest_ts_ns) op, arg_max(high, ingest_ts_ns) hi, "
           f"arg_max(low, ingest_ts_ns) lo, arg_max(close, ingest_ts_ns) cl, arg_max(volume, ingest_ts_ns) vo, "
           f"arg_max(vwap, ingest_ts_ns) vw, min(session) se from {src} where symbol=? and bucket_start_ns>=? and bucket_start_ns<? "
           f"group by bucket_start_ns) "
           f"select (bs // 15000000000) * 15 t, arg_min(op, bs) filter (where op is not null), "
           f"max(hi), min(lo), arg_max(cl, bs) filter (where cl is not null), sum(vo), "
           f"sum(vw*vo) filter (where vw is not null and vo>0) / nullif(sum(vo) filter (where vw is not null and vo>0),0), "
           f"min(se) from d group by 1 order by 1")
    out = []
    for t, o, h, l, c, v, vw, s in DB.execute(sql, [sym, int(t0 * 1e9), int(t1 * 1e9)]).fetchall():
        s = SESS.get(s, sess_of(t))
        if o is not None and c is not None:
            out.append((float(t), o, h if h is not None else max(o, c), l if l is not None else min(o, c), c, v or 0, s, 0))
        elif vw is not None:   # pre/post 5 s buckets carry only a VWAP (no prices): flag 2 = VWAP-priced
            out.append((float(t), vw, vw, vw, vw, v or 0, s, 2))
        elif out and out[-1][6] == s and t - out[-1][0] <= 120:   # no prints: flat bar at the last close (flag 3)
            pc = out[-1][4]
            out.append((float(t), pc, pc, pc, pc, v or 0, s, 3))
    return out


def rollup(bars, iv):
    """1-min bars -> 5m/15m/1h (session-bounded, 1h anchored 9:30 ET) or 1d (regular hours only)."""
    sec = IV_S[iv]
    g = {}
    order = []
    for b in bars:
        t, s = b[0], b[6]
        if iv == "1d":
            if s != "r":
                continue
            k = day_bounds(et_day(t))[0]
        elif iv == "1h":
            d0 = day_bounds(et_day(t))[0]
            anchor = d0 + 9.5 * 3600
            k = anchor + math.floor((t - anchor) / 3600) * 3600
            ss = d0 + {"p": 4 * 3600, "r": 9.5 * 3600, "a": 16 * 3600}[s]
            k = max(k, ss)
        else:
            k = math.floor(t / sec) * sec
        key = (k, s if iv != "1d" else "r")
        x = g.get(key)
        if x is None:
            g[key] = [k, b[1], b[2], b[3], b[4], b[5], key[1], 4]
            order.append(key)
        else:
            x[2] = max(x[2], b[2]); x[3] = min(x[3], b[3]); x[4] = b[4]; x[5] += b[5]
    return [tuple(g[k]) for k in order]


def merge_k(bars, k):
    """Server-side downsampling: merge k consecutive bars (never across an ET day)."""
    out, cur, n = [], None, 0
    for b in bars:
        if cur is not None and (n >= k or et_day(b[0]) != et_day(cur[0])):
            out.append(tuple(cur)); cur = None
        if cur is None:
            cur, n = list(b), 1
        else:
            cur[2] = max(cur[2], b[2]); cur[3] = min(cur[3], b[3]); cur[4] = b[4]; cur[5] += b[5]; n += 1
    if cur is not None:
        out.append(tuple(cur))
    return out


def bars_for_dates(sym, tier, iv, dates, t0, t1, today):
    """Return (bars, sources set) for the given ET dates."""
    srcs = set()
    out = []
    if iv == "15s":
        pq, js = part_dates(tier, "volume_5s", "pq"), part_dates(tier, "volume_5s", "js")
        pf = [f for d in dates if d != today and d in pq for f in pq[d]]
        jf = [f for d in dates if (d == today or d not in pq) and d in js for f in js[d]]
        if pf:
            out += q_15s(pf, sym, t0, t1, False); srcs.add("volume_5s parquet")
        if jf:
            out += q_15s(jf, sym, t0, t1, True); srcs.add("volume_5s live jsonl")
        out.sort(key=lambda b: b[0])
        return out, srcs
    pq1, js1 = part_dates(tier, "bars_1m", "pq"), part_dates(tier, "bars_1m", "js")
    if iv == "1m":
        need = dates
    else:
        pqt = part_dates(tier, "bars_" + iv, "pq")
        hd = [d for d in dates if d != today and d in pqt]
        if hd:
            out += q_tf_pq([f for d in hd for f in pqt[d]], sym, t0, t1, iv == "1d"); srcs.add(f"bars_{iv} parquet")
        need = [d for d in dates if d not in hd]
    m1 = []
    pf = [f for d in need if d != today and d in pq1 for f in pq1[d]]
    jf = [f for d in need if (d == today or d not in pq1) and d in js1 for f in js1[d]]
    if pf:
        m1 += q_1m(pf, sym, t0, t1, False); srcs.add("bars_1m parquet")
    if jf:
        m1 += q_1m(jf, sym, t0, t1, True); srcs.add("bars_1m live+final jsonl")
    have = {et_day(b[0]) for b in m1}
    miss = [d for d in need if d not in have and d not in pq1 and d not in js1]
    if miss:
        st = store_bars(tier, sym)
        for d in miss:
            if d in st:
                m1 += [b for b in st[d] if t0 <= b[0] < t1]; srcs.add("bar store json (regular hours)")
    m1.sort(key=lambda b: b[0])
    if iv == "1m":
        return m1, srcs
    if m1:
        srcs.add(f"rolled up from 1m here")
    out += rollup(m1, iv)
    out.sort(key=lambda b: b[0])
    return out, srcs


def avail(tier, sym):
    """Earliest ET date with data for each interval (directory listing; honest range)."""
    a = {}
    v5 = set(part_dates(tier, "volume_5s", "pq")) | set(part_dates(tier, "volume_5s", "js"))
    a["15s"] = min(v5) if v5 else None
    m1 = set(part_dates(tier, "bars_1m", "pq")) | set(part_dates(tier, "bars_1m", "js"))
    st = store_bars(tier, sym)
    if st:
        m1 |= set(st)
    f = min(m1) if m1 else None
    for iv in ("1m", "5m", "15m", "1h", "1d"):
        a[iv] = f
    if tier == "core":
        d1 = part_dates(tier, "bars_1d", "pq")
        if d1:
            a["1d"] = min(min(d1), f or "9999")
    return a


def last_data_day(tier, iv):
    tab = "volume_5s" if iv == "15s" else "bars_1m"
    ds = set(part_dates(tier, tab, "pq")) | set(part_dates(tier, tab, "js"))
    return max(ds) if ds else et_day(time.time())


# ---------------------------------------------------------------- incremental file readers (score / C/P)
class Tail:
    """Parse an append-only JSONL once, then only the new bytes. fn(dict, state) folds rows into state."""

    def __init__(self, path, fn, init):
        self.path, self.fn, self.init = path, fn, init
        self.off, self.ino, self.state, self.mt = 0, None, init(), None

    def get(self):
        p = self.path
        try:
            stt = p.stat()
        except OSError:
            return None
        if (stt.st_mtime, stt.st_size) == self.mt:
            return self.state
        if p.suffix == ".gz":
            self.state = self.init()
            with gzip.open(p, "rt") as fh:
                for line in fh:
                    self._one(line)
        else:
            if stt.st_ino != self.ino or stt.st_size < self.off:
                self.off, self.ino, self.state = 0, stt.st_ino, self.init()
            with open(p, "rb") as fh:
                fh.seek(self.off)
                buf = fh.read()
            cut = buf.rfind(b"\n")
            if cut >= 0:
                for line in buf[:cut].split(b"\n"):
                    self._one(line)
                self.off += cut + 1
        self.mt = (stt.st_mtime, stt.st_size)
        return self.state

    def _one(self, line):
        try:
            d = json.loads(line)
        except Exception:
            return
        try:
            self.fn(d, self.state)
        except Exception:
            pass


_TAILS = {}


def tail(path, fn, init):
    t = _TAILS.get(path)
    if t is None:
        if len(_TAILS) > 60:
            _TAILS.clear()
        t = _TAILS[path] = Tail(path, fn, init)
    return t.get()


def _score_init():
    return {"s": {}, "w": {}}


def _wall_from_row(d):
    """Walls the score saw: ctx.walls (change rows) or comps.walls/flip (grid rows). as_of = t - age_s."""
    t = d.get("t")
    cw = pw = gf = age = src = None
    w = (d.get("ctx") or {}).get("walls")
    if isinstance(w, dict) and (w.get("cw") is not None or w.get("pw") is not None):
        cw, pw, gf, age, src = w.get("cw"), w.get("pw"), w.get("gf"), w.get("age_s"), w.get("src")
    else:
        c = d.get("comps") or {}
        wx = ((c.get("walls") or {}).get("x") or {})
        fx = ((c.get("flip") or {}).get("x") or {})
        ff = ((c.get("walls") or {}).get("f") or {})
        cw, pw, gf, age, src = wx.get("cw"), wx.get("pw"), fx.get("gf"), ff.get("age_s"), ff.get("src")
    if cw is None and pw is None and gf is None:
        return None
    return (round(t - (age or 0), 1), cw, pw, gf, f"score row ({src or '?'})")


def _score_fold(d, st):
    sym, t = d.get("sym"), d.get("t")
    if not sym or t is None or d.get("score") is None:
        return
    st["s"].setdefault(sym, []).append((float(t), int(d["score"]), d.get("raw")))
    w = _wall_from_row(d)
    if w:
        L = st["w"].setdefault(sym, [])
        if not L or L[-1][1:4] != w[1:4]:
            L.append(w)


def score_files(kind, ymd):
    """Preference order per day. kind core | light | full."""
    if kind == "core":
        c = [SCORE_DIR / f"changes-{ymd}.jsonl", SCORE_DIR / f"replay-{ymd}/changes-{ymd}.jsonl",
             SCORE_DIR / f"scores-{ymd}.jsonl", SCORE_DIR / f"backfill-scores-{ymd}.jsonl"]
    elif kind == "light":
        c = [SCORE_DIR / f"changes-wide-{ymd}.jsonl", SCORE_DIR / f"replay-{ymd}-wide/changes-wide-{ymd}.jsonl"]
    else:
        c = [SCORE_DIR / f"changes-widefull-{ymd}.jsonl", SCORE_DIR / f"replay-{ymd}-widefull/changes-widefull-{ymd}.jsonl"]
    return [p for p in c if p.exists() and p.stat().st_size > 0]


SRC_LABEL = {"changes": "live change log", "replay": "5 s replay change log", "scores": "15-min grid (scores-*.jsonl)",
             "backfill": "15-min backfill grid"}


def score_series(kind, sym, dates):
    pts, walls, used = [], [], []
    for d in dates:
        ymd = d.replace("-", "")
        fs = score_files(kind, ymd)
        if not fs:
            continue
        p = fs[0]
        st = tail(p, _score_fold, _score_init)
        if not st:
            continue
        pts += st["s"].get(sym, [])
        walls += st["w"].get(sym, [])
        tag = "replay" if "replay-" in str(p) else "backfill" if "backfill" in p.name else "scores" if p.name.startswith("scores-") else "changes"
        used.append(f"{d}: {SRC_LABEL[tag]}")
    pts.sort(key=lambda x: x[0])
    return pts, walls, used


def _mom_init():
    return {}


def _mom_fold(d, st):
    sym, stt, ns = d.get("symbol"), d.get("state"), d.get("event_ts_ns")
    if not sym or stt not in MOM_CODE or ns is None:
        return
    st.setdefault(sym, []).append((ns / 1e9, MOM_CODE[stt], d.get("since_ep")))


def _momev_fold(d, st):
    if d.get("basis") != "bar_close" or d.get("kind") not in ("accelerate", "resume", "decelerate"):
        return
    sym = d.get("symbol")
    if not sym or sym == "MARKET":
        return
    try:
        t = datetime.strptime(d["time_pt"], "%Y-%m-%d %I:%M:%S %p PT").replace(tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
    except Exception:
        return
    st.setdefault(sym, []).append((t, MOM_CODE[d["kind"]], t))


def _mom_derived(sym, d):
    """Derived from the engine's bar-close events: state = last event kind, quiet after 10 min, quiet from the 9:30 ET open."""
    ev = MOM_EV / f"events-{d.replace('-', '')}.jsonl"
    if not ev.exists():
        return None
    st = tail(ev, _momev_fold, _mom_init) or {}
    e = sorted(st.get(sym, []))
    out = [(day_bounds(d)[0] + 9.5 * 3600, 0, None)]   # 9:30 AM ET open
    for i, x in enumerate(e):
        out.append(x)
        nxt = e[i + 1][0] if i + 1 < len(e) else None
        if nxt is None or nxt - x[0] > MOM_QUIET_S:
            out.append((x[0] + MOM_QUIET_S, 0, x[0] + MOM_QUIET_S))
    return out


def mom_series(sym, dates):
    """MOMSTATE. Per day: live change log (JSONL, else its Parquet copy) from its first row on; before the first logged
    row (e.g. 10/20, logging began after the close) the state is derived from the engine's bar-close events."""
    pts, used = [], []
    for d in dates:
        got, lab = [], None
        dj = MOM_LOG / f"date={d}"
        parts = sorted(dj.glob("part-*.jsonl")) if dj.exists() else []
        for f in parts:
            st = tail(f, _mom_fold, _mom_init)
            if st and sym in st:
                got += st[sym]
        if got:
            lab = "live change log"
        else:
            pq = MOM_PQ / f"date={d}"
            if pq.exists() and any(pq.glob("*.parquet")):
                try:
                    rows = DB.execute("SELECT event_ts_ns, state, since_ep FROM read_parquet(?) WHERE symbol = ? ORDER BY event_ts_ns",
                                      [str(pq / "*.parquet"), sym]).fetchall()
                    got = [(r[0] / 1e9, MOM_CODE[r[1]], r[2]) for r in rows if r[1] in MOM_CODE]
                    lab = "Parquet change log" if got else None
                except Exception as e:
                    log(f"mom parquet {d}: {type(e).__name__}")
        got.sort(key=lambda x: x[0])
        first = got[0][0] if got else None
        der = _mom_derived(sym, d)
        if der and (first is None or der[0][0] < first):
            der = [x for x in der if first is None or x[0] < first]
            if der:
                pts += der
                used.append(f"{d}: derived from engine events (bar closes)" + (f" until {datetime.fromtimestamp(first, ZoneInfo('America/Los_Angeles')):%-I:%M %p} PT" if first else ""))
        if got:
            pts += got
            used.append(f"{d}: {lab}")
    pts.sort(key=lambda x: x[0])
    return pts, used


def _cp_init():
    return {}


def _cp_fold(d, st):
    if d.get("hdr"):
        return
    t = d.get("t")
    for sym, u in (d.get("u") or {}).items():
        a, b = u.get("15"), u.get("60")
        st.setdefault(sym, []).append((float(t), a[0] if a and a[5] is None else None, b[0] if b and b[5] is None else None,
                                       a[4] if a else None, b[4] if b else None))


def cp_series(tier, sym, dates):
    pts, used = [], []
    for d in dates:
        for p in (CP_DIR[tier] / f"{d}.jsonl", CP_DIR[tier] / f"{d}.jsonl.gz"):
            if p.exists():
                st = tail(p, _cp_fold, _cp_init)
                if st and sym in st:
                    pts += st[sym]
                    used.append(d)
                break
    pts.sort(key=lambda x: x[0])
    return pts, used


def _wh_init():
    return {}


def _wh_fold(d, st):
    sym, a = d.get("sym"), d.get("as_of")
    if sym and a is not None:
        st.setdefault(sym, []).append((float(a), d.get("cw"), d.get("pw"), d.get("gf"), d.get("src") or "walls-history"))


def wall_events(sym, tier, dates, cur, score_walls):
    ev = list(score_walls)
    used = set()
    if score_walls:
        used.add("score rows")
    # include the 4 days before the range so a level that was already standing carries in
    if dates:
        d0 = datetime.strptime(dates[0], "%Y-%m-%d")
        pre = [(d0 - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4, 0, -1)]
    else:
        pre = []
    for d in pre + list(dates):
        p = WALL_HIST / f"walls-{d.replace('-', '')}.jsonl"
        if p.exists():
            st = tail(p, _wh_fold, _wh_init)
            if st and sym in st:
                ev += st[sym]
                used.add("walls-history")
    if cur and cur.get("t") is not None:
        ev.append((float(cur["t"]), cur.get("cw"), cur.get("pw"), cur.get("gf"), cur.get("src") or "live"))
        used.add("live level")
    ev.sort(key=lambda e: e[0])
    out = []
    for e in ev:
        if out and out[-1][1:4] == e[1:4]:
            continue
        out.append(e)
    return out, sorted(used)


# ---------------------------------------------------------------- alignment onto the bar grid
def align_steps(bars, pts, iv_s, val_fn, rth_only=True):
    """For each bar: state at bar close (last point with t < bar end); plus hi/lo of the states active in the bar."""
    out = []
    j, n = 0, len(pts)
    cur = None
    cur_day = None
    for b in bars:
        t0 = b[0]
        t1 = t0 + iv_s
        day = et_day(t0)
        if day != cur_day:
            cur, cur_day = None, day
            ds0 = day_bounds(day)[0]
            while j < n and pts[j][0] < ds0:
                j += 1
        hi = lo = None
        if cur is not None:
            hi = lo = val_fn(cur)
        nch = 0
        while j < n and pts[j][0] < t1:
            if pts[j][0] >= ds0:
                cur = pts[j]
                v = val_fn(cur)
                if v is not None:
                    hi = v if hi is None else max(hi, v)
                    lo = v if lo is None else min(lo, v)
                nch += 1
            j += 1
        if cur is None or (rth_only and iv_s < 86400 and b[6] != "r"):
            out.append(None)
            continue
        out.append((cur, hi, lo, nch))
    return out


def walls_on_grid(bars, ev, iv_s):
    out = []
    j, n, cur = 0, len(ev), None
    for b in bars:
        t1 = b[0] + iv_s
        while j < n and ev[j][0] < t1:
            cur = ev[j]
            j += 1
        if cur is None or t1 - cur[0] > WALL_MAX_AGE:
            out.append(None)
        else:
            out.append([cur[1], cur[2], cur[3]])
    return out


# ---------------------------------------------------------------- request
_HIST = {}
_TODAY = {}


def dates_between(a, b):
    d = datetime.strptime(a, "%Y-%m-%d")
    e = datetime.strptime(b, "%Y-%m-%d")
    out = []
    while d <= e:
        if d.weekday() < 5:
            out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def build(req):
    t_start = time.time()
    sym = str(req.get("sym") or "").upper()
    iv = req.get("iv") or "1m"
    rng = req.get("range") or "1D"
    ext = bool(int(req.get("ext", 1)))
    if iv not in IV_S or rng not in RANGE_D:
        raise ValueError("bad iv/range")
    tier = tier_of(sym)
    if tier is None:
        raise ValueError(f"no stored bars for {sym}")
    today = et_day(time.time())
    av = avail(tier, sym)
    last_day = last_data_day(tier, iv)
    ld = datetime.strptime(last_day, "%Y-%m-%d")
    if RANGE_D[rng] is None:
        want_from = f"{ld.year}-01-01"
    else:
        want_from = (ld - timedelta(days=RANGE_D[rng])).strftime("%Y-%m-%d")
    first = av.get(iv) or last_day
    frm = max(want_from, first)
    clipped = frm > want_from
    dates = dates_between(frm, last_day)
    t0 = day_bounds(dates[0])[0] if dates else time.time()
    t1 = day_bounds(last_day)[1]
    hist_dates = [d for d in dates if d != today]
    live_dates = [d for d in dates if d == today]
    srcs = set()
    hk = (sym, iv, tuple(hist_dates))
    h = _HIST.get(hk)
    if h is None or time.time() - h[0] > HIST_TTL:
        hb, hs = bars_for_dates(sym, tier, iv, hist_dates, t0, t1, today) if hist_dates else ([], set())
        h = _HIST[hk] = (time.time(), hb, hs)
        if len(_HIST) > 48:
            _HIST.pop(next(iter(_HIST)))
    bars = list(h[1]); srcs |= h[2]
    if live_dates:
        tk = (sym, iv)
        tb = _TODAY.get(tk)
        if tb is None or time.time() - tb[0] > TODAY_TTL:
            a, b2 = day_bounds(today)
            lb, ls = bars_for_dates(sym, tier, iv, live_dates, a, b2, today)
            tb = _TODAY[tk] = (time.time(), lb, ls)
            if len(_TODAY) > 48:
                _TODAY.pop(next(iter(_TODAY)))
        bars += tb[1]; srcs |= tb[2]
    if not ext and iv != "1d":
        bars = [b for b in bars if b[6] == "r"]
    iv_s = IV_S[iv]
    k = 1
    if len(bars) > MAX_BARS:
        k = math.ceil(len(bars) / MAX_BARS)
        bars = merge_k(bars, k)
    span = iv_s * k if iv != "1d" else 86400 * k
    # score lanes
    sdates = sorted({et_day(b[0]) for b in bars})
    lanes = {}
    score_used = {}
    sw_all = []
    kinds = ["core"] if tier == "core" else ["light", "full"]
    for kind in kinds:
        pts, sw, used = score_series(kind, sym, sdates)
        score_used[kind] = used
        sw_all += sw
        al = align_steps(bars, pts, span, lambda p: p[1])
        lanes[kind] = [None if a is None else [a[0][1], a[0][2], a[1], a[2], a[3], round(a[0][0], 1)] for a in al]
    cpts, cp_used = cp_series(tier, sym, sdates)
    cal15 = align_steps(bars, [(p[0], p[1], p[3]) for p in cpts if p[1] is not None], span, lambda p: p[1])
    cal60 = align_steps(bars, [(p[0], p[2], p[4]) for p in cpts if p[2] is not None], span, lambda p: p[1])
    cp = [None if (a is None and c is None) else [a[0][1] if a else None, c[0][1] if c else None,
                                                    a[0][2] if a else None, c[0][2] if c else None] for a, c in zip(cal15, cal60)]
    mom, mom_used = [None] * len(bars), []
    if tier == "core":
        mpts, mom_used = mom_series(sym, sdates)
        mal = align_steps(bars, mpts, span, lambda p: p[1])
        mom = [None if a is None else [a[0][1], round(a[0][2], 1) if a[0][2] else None, a[3], a[1], a[2]] for a in mal]
    ev, wsrc = wall_events(sym, tier, sdates, req.get("cur_walls"), sw_all)
    wg = walls_on_grid(bars, ev, span)
    since = req.get("since")
    i0 = 0
    if since is not None:
        since = float(since)
        while i0 < len(bars) and bars[i0][0] < since:
            i0 += 1
    out_b = [[b[0], r4(b[1]), r4(b[2]), r4(b[3]), r4(b[4]), int(b[5]), b[6], b[7]] for b in bars[i0:]]
    notes = []
    if clipped:
        notes.append(f"{iv} data on this machine starts {first}; {rng} asked for {want_from}")
    if k > 1:
        notes.append(f"downsampled on the server: 1 bar = {k} x {iv} (max {MAX_BARS} bars per chart)")
    if iv == "15s" and any(b[7] == 2 for b in bars):
        notes.append("pre/post 15 s bars are priced from the 5 s VWAP only (the 5 s archive keeps no pre/post prices)")
    if tier == "wide" and iv == "15s":
        notes.append("Sector watch 5 s buckets start 10/20 3:08 PM PT (after hours); first full session 10/21")
    data = {
        "sym": sym, "tier": tier, "iv": iv, "range": rng, "ext": int(ext), "k": k, "span_s": span,
        "from": frm, "to": last_day, "want_from": want_from, "avail": av, "today": today,
        "bars": out_b, "i0": i0, "n_total": len(bars),
        "score": {kk: v[i0:] for kk, v in lanes.items()},
        "cp": cp[i0:], "walls": wg[i0:], "mom": mom[i0:],
        "wall_events": [[round(e[0], 1), e[1], e[2], e[3], e[4]] for e in ev if e[0] >= t0 - WALL_MAX_AGE][-200:],
        "sources": {"bars": sorted(srcs), "score": score_used, "cp": cp_used, "walls": wsrc,
                    "mom": mom_used if tier == "core" else ["momentum engine covers core names only"]},
        "notes": notes, "gen_ms": round((time.time() - t_start) * 1000, 1),
        "scn": scn_for(sym),  # CHARTSCN
    }
    return data


SCN_FILE = HOME / "oid-desk/desk/chart-bot/scenarios/latest.json"   # CHARTSCN: box -> mini desk-state push
SCN_LIVE = HOME / "oid-data/chart-scenarios/status-live.json"        # CHARTSCN: mini 30-min status job
_SCN = {}


def _jcache(p):
    try:
        m = p.stat().st_mtime
    except OSError:
        return None
    c = _SCN.get(str(p))
    if not c or c[0] != m:
        try:
            c = _SCN[str(p)] = (m, json.loads(p.read_text()))
        except Exception:
            return None
    return c[1]


def scn_for(sym):
    """CHARTSCN: Chart Bot CB-SCN-V1 primary for sym (shadow / display only) -> levels + status, else None."""
    doc = _jcache(SCN_FILE)
    v = ((doc or {}).get("tickers") or {}).get(sym)
    p = (v or {}).get("primary")
    if not p:
        return None
    st, sa, ssrc = p.get("status"), p.get("status_asof"), "chart-bot latest.json"
    lv = ((_jcache(SCN_LIVE) or {}).get("tickers") or {}).get(sym) or {}
    alts = [{"label": a.get("label"), "status": a.get("status"), "score": a.get("calibrated_score")}
            for a in ((v or {}).get("alternates") or [])]  # CBSTATUS 10/21
    if lv.get("prediction_id") == p.get("prediction_id") and lv.get("status"):
        st, sa, ssrc = lv["status"], lv.get("status_asof") or sa, "mini 30m status job"
        alts = [{"label": a.get("label"), "status": a.get("status"), "score": a.get("calibrated_score")}
                for a in (lv.get("alternates") or [])] or alts
    return {"label": p.get("label"), "dir": p.get("direction"), "score": p.get("calibrated_score"),
            "trig": p.get("trigger_price"), "t1": p.get("target_1"), "t2": p.get("target_2"), "inv": p.get("invalidation"),
            "rlo": p.get("range_low"), "rhi": p.get("range_high"), "rule": p.get("trigger_rule"), "status": st,
            "status_asof": sa, "status_src": ssrc, "run": doc.get("run_ts_pt"), "asof": doc.get("asof_bar_date"),
            "pid": p.get("prediction_id"), "alts": alts}


def main():
    log("chart backend up")
    import select
    while True:
        r, _, _ = select.select([sys.stdin], [], [], IDLE_EXIT_S)
        if not r:
            log(f"idle {IDLE_EXIT_S:.0f} s: exiting (livepage restarts it on the next chart request)")
            return
        line = sys.stdin.readline()
        if not line:
            return
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            if req.get("op") == "ping":
                rep = {"id": rid, "ok": True, "data": {"pong": True}}
            else:
                rep = {"id": rid, "ok": True, "data": build(req)}
        except Exception as e:
            log(f"error: {type(e).__name__}: {(str(e).splitlines() or [''])[0][:300]}")
            rep = {"id": rid, "ok": False, "error": str(e)[:200]}
        sys.stdout.write(json.dumps(rep, separators=(",", ":"), allow_nan=False, default=str) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
