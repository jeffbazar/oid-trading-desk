#!/usr/bin/env python3
"""PATTERNS (2026-10-21): shared I/O for the shadow pattern detector (universe, bars, base rates, context, archive).
Shadow only: nothing here is read by a live score or by any trading code."""
import glob
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import patterns as PT
import score_lib as L

HOME = Path.home()
ARCH = Path(os.environ.get("OID_ARCHIVE_ROOT", str(HOME / "oid-data/archive")))
PDIR = Path(os.environ.get("OID_PATTERNS_DIR", str(HOME / "oid-data/patterns")))
RATES = PDIR / "base-rates.json"
LIVE = PDIR / "live.json"
try:
    from zoneinfo import ZoneInfo
    PTZ, ET = ZoneInfo("America/Los_Angeles"), ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    PTZ = ET = None


def pt_str(t):
    return datetime.fromtimestamp(t, PTZ).strftime("%Y-%m-%d %-I:%M:%S %p PT")


def log(msg):
    print(f"{time.strftime('%Y-%m-%d %I:%M:%S %p PT')} {msg}", flush=True)


def wide_paths():
    import score_wide as W
    return W.setup(L.load_config())


def universe():
    """-> [(sym, tier, store)]: core = every 1-min file in the core bar store; sector = the wide allow-list (not in core)."""
    core = sorted(Path(p).name[:-8] for p in glob.glob(str(L.STORE / "*-1m.json")))
    out = [(s, "core", None) for s in core]
    try:
        P, paths = wide_paths()
        syms = json.loads(paths["universe"].read_text()).get("symbols") or []
        cs = set(core)
        out += [(s, "wide", paths["store"]) for s in syms if s not in cs]
    except Exception as e:
        log(f"wide universe unavailable: {type(e).__name__}: {e}")
    return out


def hist_1m(sym, store=None, before=None, after=None):
    """All stored 1-min bars (history file) as tuples, optionally only sessions < before / >= after. Drops the cache."""
    rows = L._hist(sym, store)
    out = []
    for b in rows:
        d = b.get("d")
        if not d or (before and d >= before) or (after and d < after) or b.get("c") is None:
            continue
        out.append((L.iso_t(b["t"]), b["o"], b["h"], b["l"], b["c"], float(b.get("v") or 0), d, b.get("vw")))
    L._HIST.pop(sym if store is None else (str(store), sym), None)
    out.sort(key=lambda x: x[0])
    return out


def day_1m(sym, date, store=None, live_only=True):
    return PT.bars_1m(L.load_day_bars(sym, date, store=store, hist_fallback=not live_only))


def daily_atr(b1, n=14):
    days = {}
    for b in b1:
        x = days.setdefault(b[6], [b[2], b[3], b[4]])
        x[0], x[1], x[2] = max(x[0], b[2]), min(x[1], b[3]), b[4]
    ks = sorted(days)
    trs = []
    for i, k in enumerate(ks):
        h, l, c = days[k]
        pc = days[ks[i - 1]][2] if i else None
        trs.append(max(h - l, abs(h - pc) if pc else 0, abs(l - pc) if pc else 0))
    trs = trs[-n:]
    return sum(trs) / len(trs) if trs else None


WARM_SESS = {"1m": 1, "5m": 3, "30m": 12}


def warm(sym, b_hist):
    """Engines for one ticker, warmed silently on the sessions before the day (pivots, ATR, prior high/low/close)."""
    sess = sorted({b[6] for b in b_hist})
    atr_d = daily_atr(b_hist)
    eng = {}
    for iv in PT.IV_MIN:
        keep = set(sess[-WARM_SESS[iv]:])
        b1 = [b for b in b_hist if b[6] in keep]
        e = PT.Engine(sym, iv, atr_d)
        for b in (b1 if iv == "1m" else PT.roll(b1, iv)):
            e.step(b, emit=False)
        e.act.clear()
        eng[iv] = e
    return eng


# ------------------------------------------------------------------ base rates
_R = {"m": None, "d": None}


def rates():
    try:
        m = RATES.stat().st_mtime
    except OSError:
        return None
    if _R["m"] != m:
        try:
            _R["d"], _R["m"] = json.loads(RATES.read_text()), m
        except Exception:
            return _R["d"]
    return _R["d"]


# ------------------------------------------------------------------ context (score values + momentum state at that moment)
class LiveCtx:
    def __init__(self):
        self.t, self.sc, self.mom = 0, {}, {}

    def refresh(self, now):
        if now - self.t < 20:
            return
        self.t = now
        sc = {}
        for kind, f in (("core", "latest.json"), ("light", "latest-wide.json"), ("full", "latest-widefull.json")):
            try:
                d = json.loads((L.OUT / f).read_text())
                if now - float(d.get("as_of") or 0) > 600:
                    continue
                for s, v in (d.get("by_sym") or {}).items():
                    if isinstance(v, dict) and v.get("s") is not None:
                        sc.setdefault(s, {})[kind] = v.get("s")
            except Exception:
                pass
        self.sc = sc
        mom = {}
        try:
            st = json.loads(urllib.request.urlopen(L.STATE_URL, timeout=3).read())
            for r in st.get("rows") or []:
                m = r.get("mom")
                if isinstance(m, dict) and m.get("st"):
                    mom[r.get("sym")] = m.get("st")
        except Exception:
            pass
        self.mom = mom

    def get(self, sym, ts):
        s = self.sc.get(sym) or {}
        return {"score_core": s.get("core"), "score_light": s.get("light"), "score_full": s.get("full"),
                "mom": self.mom.get(sym), "ctx_src": "live"}


class ReplayCtx:
    """Replays: scores from the day's score_features Parquet (needs duckdb; else none). No momentum (not archived in RTH)."""

    def __init__(self, date):
        self.by = {}
        try:
            import duckdb
            q = (f"select symbol, profile, t, score from read_parquet('{ARCH}/parquet/score_features/date={date}/*.parquet') "
                 "where score is not null order by symbol, t")
            for s, prof, t, sc in duckdb.sql(q).fetchall():
                self.by.setdefault((s, prof), ([], []))
                self.by[(s, prof)][0].append(t)
                self.by[(s, prof)][1].append(sc)
        except Exception as e:
            log(f"replay ctx: no score_features parquet ({type(e).__name__}); context left empty")

    def get(self, sym, ts):
        import bisect
        o = {"ctx_src": "replay (score_features parquet; momentum not archived in RTH)", "mom": None}
        for prof, k in (("core", "score_core"), ("light", "score_light"), ("wide_full", "score_full")):
            x = self.by.get((sym, prof))
            if x:
                j = bisect.bisect_right(x[0], ts) - 1
                o[k] = x[1][j] if j >= 0 else None
        return o


# ------------------------------------------------------------------ enrich + archive
def enrich(rec, rd, ctx, mode):
    p, src, n, ex = PT.prob_for(rd, rec["pattern"], rec["interval"], rec["direction"])
    rec.update(prob_est=p, prob_source=src, prob_n=n, **{k: v for k, v in ex.items() if v is not None})
    rec["ctx"] = ctx.get(rec["ticker"], rec["ts"]) if ctx else None
    rec["mode"] = mode
    rec["rec_id"] = rec["det_id"] + ":" + rec["state"]
    rec["t_pt"] = pt_str(rec["ts"])
    return rec


class Writer:
    def __init__(self, writer):
        self.writer, self.day, self.path = writer, None, None

    def _open(self, day):
        d = ARCH / "patterns" / f"date={day}"
        d.mkdir(parents=True, exist_ok=True)
        if self.writer.startswith("replay"):
            self.path = d / f"part-patterns-{self.writer}-1.jsonl"
            self.path.write_text("")
        else:
            seqs = [int(p.stem.rsplit("-", 1)[1]) for p in d.glob(f"part-patterns-{self.writer}-*.jsonl")
                    if p.stem.rsplit("-", 1)[1].isdigit()]
            self.path = d / f"part-patterns-{self.writer}-{(max(seqs) + 1) if seqs else 1}.jsonl"
        self.day = day

    def write(self, day, recs):
        if not recs:
            return
        if day != self.day:
            self._open(day)
        with open(self.path, "a") as fh:
            for r in recs:
                fh.write(json.dumps({k: v for k, v in r.items() if v is not None}, separators=(",", ":")) + "\n")


def seen_ids(day, writer="live"):
    out = set()
    for p in (ARCH / "patterns" / f"date={day}").glob(f"part-patterns-{writer}-*.jsonl"):
        for ln in p.read_text().splitlines():
            try:
                out.add(json.loads(ln)["rec_id"])
            except Exception:
                pass
    return out


def compact(det, rd):
    p, src, n, ex = PT.prob_for(rd, det["pattern"], det.get("iv") or det.get("interval"), det["dir"])
    return {"id": det["id"], "pattern": det["pattern"], "iv": det.get("iv"), "dir": det["dir"], "state": det["state"],
            "trig": PT._r(det.get("trig")), "tgt": PT._r(det.get("tgt")), "inv": PT._r(det.get("inv")), "conf": det.get("conf"),
            "prob": p, "src": src, "n": n, "n_live": ex.get("n_live"), "prob_bt": ex.get("prob_backtest"), "ts0": det.get("ts0"),
            "lv": {k: (PT._r(v) if isinstance(v, (int, float)) else v) for k, v in (det.get("lv") or {}).items()}}


def top_of(acts):
    d = [a for a in acts if a["dir"] and a["state"] in ("confirmed", "triggered")]
    if not d:
        return None
    return sorted(d, key=lambda a: (a["prob"] if a["prob"] is not None else -1, PT.IV_MIN.get(a["iv"], 0), a["conf"] or 0),
                  reverse=True)[0]


def write_live(engs, rd, now, mode="live", note=None):
    by = {}
    for sym, eng in engs.items():
        acts = []
        for iv, e in eng.items():
            for d in e.act.values():
                d = dict(d)
                d["iv"] = iv
                acts.append(compact(d, rd))
        if not acts:
            continue
        acts.sort(key=lambda a: (a["dir"] != 0, a["prob"] if a["prob"] is not None else -1), reverse=True)
        by[sym] = {"top": top_of(acts), "n_active": sum(1 for a in acts if a["dir"] and a["state"] in ("confirmed", "triggered")),
                   "active": acts[:6]}
    doc = {"as_of": round(now, 1), "as_of_pt": pt_str(now), "mode": mode, "detector_version": PT.DETECTOR_VERSION,
           "shadow_only": True, "note": note or "shadow only: never feeds a live score or a trade", "n_syms": len(by), "by_sym": by}
    PDIR.mkdir(parents=True, exist_ok=True)
    tmp = LIVE.with_name(".live.json.tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    tmp.replace(LIVE)
    return doc
