#!/usr/bin/env python3
"""FEATURES (2026-10-21) - score learning plan steps 2-4, nightly side. Runs in the archive venv (pyarrow + duckdb).

  score_learn.py nightly   [--date D]          compact score_features JSONL -> Parquet, then build score_labels (launchd
                                               com.oid.desk.score-labels, weekdays 1:40 PM PT)
  score_learn.py compact   --date D            score_features JSONL -> archive/parquet/score_features/date=D/ (+ manifest)
  score_learn.py labels    --date D [--from-replay]   outcomes for every snapshot + every score change -> score_labels
  score_learn.py scorecard [--week 2026-W43]   weekly model scorecard -> ~/oid-data/score/scorecard-model-<week>.{md,json}
                                               (launchd com.oid.desk.score-model-weekly, Sat 11:00 AM PT)
  score_learn.py registry-page                 Field Guide page 33 from feature-registry.json + a code check
  score_learn.py experiment log ...            append one row to ~/oid-data/score/experiments.jsonl
  score_learn.py experiment ablate --date D --profile core|light --drop flow [--add news]
                                               run baseline + variant replays and log the comparison

Labels (per row, per horizon h in 15s,30s,1m,2m,5m,15m,30m), all from bars that END after t and at or before t+h:
  ret_bp    close of the last bar in the window vs px at t
  dmove_bp  ret_bp signed by the score's direction (score 0 -> +1, i.e. up); hit = dmove_bp > 0 (score != 0 only)
  mfe_bp / mae_bp  best / worst excursion in the score's direction (high/low of the window), mae is <= 0
  *_atr     the same in 14-day ATRs;  tc/tp = call wall / put wall touched;  full = window inside RTH and bars complete
Bars: 5 s SIP closes (core archive volume_5s; sector archive-wide/volume_5s), else 1-min bars (then 15s/30s are null).
No look-ahead: the row's own inputs are all at or before t; labels only ever read bars after t.
"""
import argparse
import bisect
import datetime as dt
import glob
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
sys.path.insert(0, str(HOME / "oid-score"))
DATA = Path(os.environ.get("OID_DATA_ROOT", str(HOME / "oid-data"))).expanduser()
AR = Path(os.environ.get("OID_ARCHIVE_ROOT", str(DATA / "archive"))).expanduser()
REG = Path(os.environ.get("OID_FEATURE_REGISTRY", str(DATA / "config/feature-registry.json")))
SCORE = Path(os.environ.get("OID_SCORE_OUT", str(DATA / "score")))
EXP = SCORE / "experiments.jsonl"
GUIDE = Path(os.environ.get("OID_GUIDE_DOCS", str(HOME / "oid-live-page/guide/docs")))
HZ = [15, 30, 60, 120, 300, 900, 1800]
SV = "v1"
TY = {"float": "float64", "int": "int64", "bool": "bool", "text": "string"}
META = [("snap_id", "string"), ("profile", "string"), ("symbol", "string"), ("date", "string"), ("slot_t", "int64"),
        ("t", "float64"), ("t_pt", "string"), ("settings_version", "string"), ("registry_version", "string"),
        ("mode", "string"), ("row_kind", "string"), ("sector_id", "string"), ("sector", "string")]
COMMON = [("schema_version", "string"), ("event_ts_ns", "int64"), ("event_ts_iso", "string"),
          ("ingest_ts_ns", "int64"), ("ingest_ts_iso", "string"), ("writer", "string")]


def log(*a):
    print(time.strftime("%Y-%m-%d %I:%M:%S %p PT"), *a, flush=True)


def iso(ns):
    if ns is None:
        return None
    s, r = divmod(int(ns), 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(s)) + f".{r // 1000:06d}Z"


def pt(t):
    return time.strftime("%Y-%m-%d %I:%M:%S %p PT", time.localtime(t))


def registry():
    return json.loads(REG.read_text())


def feature_cols(reg=None):
    reg = reg or registry()
    return META + [(f["id"], TY[f["type"]]) for f in reg["features"] if not f.get("alias_of")] + COMMON


def label_cols():
    c = [("label_id", "string"), ("kind", "string"), ("profile", "string"), ("mode", "string"), ("symbol", "string"),
         ("date", "string"), ("t", "float64"), ("t_pt", "string"), ("settings_version", "string"), ("score", "int64"),
         ("prev_score", "int64"), ("raw", "float64"), ("px", "float64"), ("atr", "float64"), ("cw", "float64"),
         ("pw", "float64"), ("bar_src", "string"), ("sector", "string")]
    for h in HZ:
        c += [(f"h{h}_ret_bp", "float64"), (f"h{h}_dmove_bp", "float64"), (f"h{h}_mfe_bp", "float64"),
              (f"h{h}_mae_bp", "float64"), (f"h{h}_dmove_atr", "float64"), (f"h{h}_mfe_atr", "float64"),
              (f"h{h}_mae_atr", "float64"), (f"h{h}_hit", "bool"), (f"h{h}_tc", "bool"), (f"h{h}_tp", "bool"),
              (f"h{h}_n", "int64"), (f"h{h}_full", "bool")]
    return c + COMMON


def arrow_schema(cols, meta):
    import pyarrow as pa
    m = {"string": pa.string(), "int64": pa.int64(), "float64": pa.float64(), "bool": pa.bool_()}
    return pa.schema([(c, m[t]) for c, t in cols], metadata={k: str(v) for k, v in meta.items()})


def coerce(v, t):
    if v is None:
        return None
    try:
        if t == "int64":
            return int(round(v)) if isinstance(v, float) else int(v)
        if t == "float64":
            return float(v)
        if t == "bool":
            return bool(v)
        return v if isinstance(v, str) else json.dumps(v) if isinstance(v, (dict, list)) else str(v)
    except (TypeError, ValueError):
        return None


class PqOut:
    """Streaming Parquet writer (batches of 20k rows) -> <AR>/parquet/<table>/date=D/<table>-D-<pass>.parquet + manifest."""

    def __init__(self, table, date, pass_name, cols, meta):
        import pyarrow.parquet as pq
        self.table, self.date, self.cols = table, date, cols
        self.d = AR / "parquet" / table / f"date={date}"
        self.d.mkdir(parents=True, exist_ok=True)
        self.p = self.d / f"{table}-{date}-{pass_name}.parquet"
        self.tmp = self.p.with_suffix(".parquet.tmp")
        self.sch = arrow_schema(cols, meta)
        self.w = pq.ParquetWriter(str(self.tmp), self.sch, compression="zstd")
        self.buf, self.n = [], 0

    def add(self, row):
        self.buf.append(row)
        if len(self.buf) >= 20000:
            self._flush()

    def _flush(self):
        import pyarrow as pa
        if not self.buf:
            return
        arrays = [pa.array([coerce(r.get(c), t) for r in self.buf], type=self.sch.field(c).type) for c, t in self.cols]
        self.w.write_table(pa.Table.from_arrays(arrays, schema=self.sch))
        self.n += len(self.buf)
        self.buf = []

    def close(self):
        self._flush()
        self.w.close()
        if self.n:
            self.tmp.replace(self.p)
        else:
            self.tmp.unlink()
        manifest(self.table, self.date)
        return self.n


def manifest(table, date):
    import pyarrow.parquet as pq
    d = AR / "parquet" / table / f"date={date}"
    files = []
    for f in sorted(d.glob("*.parquet")):
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for ch in iter(lambda: fh.read(1 << 20), b""):
                h.update(ch)
        files.append({"file": f.name, "rows": pq.ParquetFile(f).metadata.num_rows, "bytes": f.stat().st_size, "sha256": h.hexdigest()})
    m = {"schema_version": SV, "table": table, "date": date, "files": files, "rows": sum(x["rows"] for x in files),
         "written_at_iso": iso(time.time_ns())}
    (d / "_manifest.json").write_text(json.dumps(m, indent=1))
    return m


def iter_lines(paths):
    for p in sorted(paths):
        with open(p, "rb") as f:
            for ln in f:
                if not ln.endswith(b"\n"):
                    break  # writer mid-append
                try:
                    yield json.loads(ln)
                except ValueError:
                    continue


def write_schema_files():
    for t, cols, key in (("score_features", feature_cols(), ["snap_id"]), ("score_labels", label_cols(), ["label_id"])):
        d = AR / t
        d.mkdir(parents=True, exist_ok=True)
        (d / "_schema.json").write_text(json.dumps({"schema_version": SV, "table": t, "key": key,
                                                    "columns": [{"name": c, "type": y} for c, y in cols],
                                                    "source": "score_learn.py (registry-driven, 2026-10-21)"}, indent=1))


# ------------------------------------------------------------------ compact
def compact(date, writers=None):
    reg = registry()
    cols = feature_cols(reg)
    parts = sorted((AR / "score_features" / f"date={date}").glob("part-*.jsonl"))
    if writers:
        parts = [p for p in parts if any(p.name.startswith(f"part-{w}-") for w in writers)]
    if not parts:
        log(f"compact {date}: no score_features JSONL")
        return 0
    groups = {}
    for p in parts:
        w = p.name[5:].rsplit("-", 1)[0]
        groups.setdefault("replay" if w.startswith("score-replay") else "live", []).append(p)
    total = 0
    for g, ps in sorted(groups.items()):
        out = PqOut("score_features", date, g, cols, {"oid.schema_version": SV, "oid.table": "score_features",
                                                     "oid.registry_version": reg.get("registry_version"), "oid.pass": g,
                                                     "oid.source_files": len(ps), "oid.writer": "score_learn"})
        seen = set()
        for r in iter_lines(ps):
            k = r.get("snap_id")
            if k in seen:
                continue
            seen.add(k)
            r.setdefault("t_pt", pt(r["t"]))
            r.setdefault("event_ts_iso", iso(r.get("event_ts_ns")))
            r.setdefault("ingest_ts_iso", iso(r.get("ingest_ts_ns")))
            out.add(r)
        n = out.close()
        total += n
        log(f"compact {date} {g}: {n} rows from {len(ps)} files")
    return total


# ------------------------------------------------------------------ bars + labels
class Bars:
    def __init__(self, date):
        import score_changes as SC
        import score_lib as L
        self.SC, self.L = SC, L
        self.date = date
        self.core = SC.load_5s(date)
        self.wide, self.used = None, {}
        self.cache = {}

    def _wide(self, sym):
        if self.wide is None:
            import score_wide as W
            P, paths = W.setup(self.L.load_config())
            syms, _ = W.universe(P, paths)
            self.wide, self.used = W.grading_bars(self.date, P, paths, syms)
        return self.wide.get(sym)

    def get(self, sym):
        if sym in self.cache:
            return self.cache[sym]
        bl = self.core.get(sym)
        src = "5s"
        if not bl:
            bl = self._wide(sym)
            src = "5s" if bl and (bl[0][1] - bl[0][0]) < 10 else "1m"
        if not bl:
            self.cache[sym] = None
            return None
        te = [b[1] for b in bl]
        hi = [b[3] for b in bl]
        lo = [b[4] for b in bl]
        cl = [b[5] for b in bl]
        self.cache[sym] = (te, hi, lo, cl, src, Sparse(hi, max), Sparse(lo, min))
        return self.cache[sym]


class Sparse:
    def __init__(self, a, fn):
        self.fn, self.t = fn, [list(a)]
        j = 1
        while (1 << j) <= len(a):
            p, h = self.t[-1], 1 << (j - 1)
            self.t.append([fn(p[i], p[i + h]) for i in range(len(a) - (1 << j) + 1)])
            j += 1

    def q(self, i, k):  # [i, k)
        j = (k - i).bit_length() - 1
        return self.fn(self.t[j][i], self.t[j][k - (1 << j)])


def label_row(r, b, t_end):
    t, px, atr, sc = r["t"], r.get("px"), r.get("atr"), r.get("score") or 0
    out = {}
    if not b or not px:
        return out
    te, hi, lo, cl, src, smax, smin = b
    d = 1 if sc >= 0 else -1
    i0 = bisect.bisect_right(te, t + 1e-6)
    step = 5 if src == "5s" else 60
    for h in HZ:
        i1 = bisect.bisect_right(te, t + h + 1e-6)
        if i1 <= i0:
            continue
        mx, mn, c = smax.q(i0, i1), smin.q(i0, i1), cl[i1 - 1]
        ret = (c / px - 1) * 1e4
        up, dn = (mx / px - 1) * 1e4, (mn / px - 1) * 1e4
        dm = d * ret
        mfe, mae = (up, dn) if d > 0 else (-dn, -up)
        ka = (px / atr / 1e4) if atr else None
        out.update({f"h{h}_ret_bp": round(ret, 2), f"h{h}_dmove_bp": round(dm, 2), f"h{h}_mfe_bp": round(mfe, 2),
                    f"h{h}_mae_bp": round(mae, 2), f"h{h}_dmove_atr": round(dm * ka, 4) if ka else None,
                    f"h{h}_mfe_atr": round(mfe * ka, 4) if ka else None, f"h{h}_mae_atr": round(mae * ka, 4) if ka else None,
                    f"h{h}_hit": (dm > 0) if sc else None,
                    f"h{h}_tc": (mx >= r["cw"]) if r.get("cw") else None, f"h{h}_tp": (mn <= r["pw"]) if r.get("pw") else None,
                    f"h{h}_n": i1 - i0, f"h{h}_full": bool(t + h <= t_end and (i1 - i0) >= 0.8 * h / step)})
    out["bar_src"] = src
    return out


def change_files(date, from_replay):
    d = date.replace("-", "")
    live = [("core", SCORE / f"changes-{d}.jsonl"), ("light", SCORE / f"changes-wide-{d}.jsonl"),
            ("wide_full", SCORE / f"changes-widefull-{d}.jsonl")]
    out = [(p, f, "live") for p, f in live if f.exists()]
    if from_replay or not out:
        for p, f in (("core", SCORE / f"replay-{d}" / f"changes-{d}.jsonl"), ("light", SCORE / f"replay-{d}-wide" / f"changes-wide-{d}.jsonl")):
            if f.exists() and not any(x[0] == p for x in out):
                out.append((p, f, "replay"))
    return out


def labels(date, from_replay=False):
    import score_changes as SC
    t_end = SC.session_end_t(date)
    t0 = time.time()
    B = Bars(date)
    cols = label_cols()
    out = PqOut("score_labels", date, "label", cols, {"oid.schema_version": SV, "oid.table": "score_labels", "oid.pass": "label",
                                                      "oid.horizons_s": ",".join(map(str, HZ)), "oid.writer": "score_learn"})
    now = time.time_ns()
    com = {"schema_version": SV, "ingest_ts_ns": now, "ingest_ts_iso": iso(now), "writer": "score-labels"}
    n = {"snap": 0, "change": 0}
    # snapshots: from Parquet if compacted, else JSONL
    pqd = AR / "parquet" / "score_features" / f"date={date}"
    want = ["snap_id", "profile", "mode", "symbol", "t", "settings_version", "score", "raw", "px", "atr", "walls_cw", "walls_pw", "sector"]
    if list(pqd.glob("*.parquet")):
        import pyarrow.parquet as pq
        def snaps():
            for f in sorted(pqd.glob("*.parquet")):
                pf = pq.ParquetFile(f)
                for bt in pf.iter_batches(batch_size=50000, columns=want):
                    yield from bt.to_pylist()
    else:
        def snaps():
            yield from iter_lines((AR / "score_features" / f"date={date}").glob("part-*.jsonl"))
    for r in snaps():
        rr = {"label_id": f"snap|{r['snap_id']}", "kind": "snap", "profile": r["profile"], "mode": r.get("mode"),
              "symbol": r["symbol"], "date": date, "t": r["t"], "t_pt": pt(r["t"]), "settings_version": r.get("settings_version"),
              "score": r.get("score"), "raw": r.get("raw"), "px": r.get("px"), "atr": r.get("atr"), "cw": r.get("walls_cw"),
              "pw": r.get("walls_pw"), "sector": r.get("sector"), "event_ts_ns": int(r["t"] * 1e9), "event_ts_iso": iso(int(r["t"] * 1e9))}
        rr.update(label_row(rr, B.get(r["symbol"]), t_end))
        rr.update(com)
        out.add(rr)
        n["snap"] += 1
    for prof, f, mode in change_files(date, from_replay):
        for c in iter_lines([f]):
            if c.get("kind") != "score_change":
                continue
            wx = ((c.get("comps") or {}).get("walls") or {}).get("x") or {}
            rr = {"label_id": f"change|{prof}|{c['sym']}|{c['t']}|{mode}", "kind": "change", "profile": prof, "mode": mode,
                  "symbol": c["sym"], "date": date, "t": c["t"], "t_pt": c.get("t_pt"), "settings_version": c.get("settings_version"),
                  "score": c.get("score"), "prev_score": c.get("prev_score"), "raw": c.get("raw"), "px": c.get("px"),
                  "atr": c.get("atr"), "cw": wx.get("cw"), "pw": wx.get("pw"), "sector": c.get("sector"),
                  "event_ts_ns": int(c["t"] * 1e9), "event_ts_iso": iso(int(c["t"] * 1e9))}
            rr.update(label_row(rr, B.get(c["sym"]), t_end))
            rr.update(com)
            out.add(rr)
            n["change"] += 1
    rows = out.close()
    st = {"date": date, "rows": rows, "by_kind": n, "wide_bars": B.used, "secs": round(time.time() - t0, 1), "at_pt": pt(time.time())}
    (DATA / "state").mkdir(parents=True, exist_ok=True)
    (DATA / "state" / "score-labels-status.json").write_text(json.dumps(st, indent=1))
    log("labels", json.dumps(st))
    return st


# ------------------------------------------------------------------ weekly scorecard
def week_dates(week):
    y, w = week.split("-W")
    mon = dt.date.fromisocalendar(int(y), int(w), 1)
    return [(mon + dt.timedelta(days=i)).isoformat() for i in range(5)]


def scorecard(week):
    import duckdb
    dates = [d for d in week_dates(week) if list((AR / "parquet" / "score_labels" / f"date={d}").glob("*.parquet"))]
    res = {"week": week, "dates": dates, "generated_pt": pt(time.time()), "by_profile": {}, "experiments": []}
    lines = [f"# Score model scorecard {week}", "", f"Generated {res['generated_pt']}. Days with labels: {', '.join(dates) or 'none'}.", "",
             "Hit = the score's direction was right at that horizon (score 0 excluded). Moves in bp from 5 s closes (1-min on sector names without 5 s bars).", ""]
    if dates:
        con = duckdb.connect()
        src = [str(AR / "parquet" / "score_labels" / f"date={d}" / "*.parquet") for d in dates]
        con.execute(f"CREATE VIEW L AS SELECT * FROM read_parquet({src!r}, union_by_name=true)")
        hs = [60, 300, 900]
        for (prof, mode) in con.execute("SELECT DISTINCT profile, mode FROM L WHERE kind='snap' ORDER BY 1,2").fetchall():
            key = f"{prof}/{mode}"
            res["by_profile"][key] = {}
            lines += [f"## {prof} ({mode})", "", "| |S| | n (5m) | " + " | ".join(f"hit {h // 60}m" for h in hs) + " | mean dmove 5m bp | mean MFE 5m | mean MAE 5m |",
                      "|---|---|" + "---|" * len(hs) + "---|---|---|"]
            for lo_, hi_, lab in ((1, 1, "1"), (2, 2, "2"), (3, 3, "3"), (1, 3, "any")):
                q = (f"SELECT count(h300_hit), " + ", ".join(f"avg(CASE WHEN h{h}_hit THEN 1.0 WHEN h{h}_hit=false THEN 0.0 END)" for h in hs) +
                     ", avg(h300_dmove_bp), avg(h300_mfe_bp), avg(h300_mae_bp) FROM L WHERE kind='snap' AND profile=? AND mode=? AND abs(score) BETWEEN ? AND ?")
                row = con.execute(q, [prof, mode, lo_, hi_]).fetchone()
                res["by_profile"][key][lab] = {"n_5m": row[0], **{f"hit_{h}": row[1 + i] for i, h in enumerate(hs)},
                                               "dmove_5m": row[-3], "mfe_5m": row[-2], "mae_5m": row[-1]}
                f = lambda v, p=False: "—" if v is None else (f"{v * 100:.1f}%" if p else f"{v:.1f}")
                lines.append(f"| {lab} | {row[0]} | " + " | ".join(f(row[1 + i], True) for i in range(len(hs))) + f" | {f(row[-3])} | {f(row[-2])} | {f(row[-1])} |")
            lines.append("")
        cal = con.execute("SELECT profile, round(raw*2)/2 AS b, count(h300_hit), avg(CASE WHEN h300_hit THEN 1.0 WHEN h300_hit=false THEN 0.0 END) "
                          "FROM L WHERE kind='snap' AND score<>0 GROUP BY 1,2 HAVING count(h300_hit)>=30 ORDER BY 1,2").fetchall()
        res["calibration_5m"] = [list(x) for x in cal]
        lines += ["## Calibration (5-min hit rate by raw score, half-point bins, n>=30)", "", "| profile | raw | n | hit 5m |", "|---|---|---|---|"]
        lines += [f"| {p} | {b:+.1f} | {n} | {h * 100:.1f}% |" for p, b, n, h in cal if h is not None]
        cov = con.execute("SELECT profile, bar_src, count(*) FROM L WHERE kind='snap' GROUP BY 1,2 ORDER BY 1,2").fetchall()
        res["bar_sources"] = [list(x) for x in cov]
        lines += ["", "## Data", "", "| profile | bars | snapshots |", "|---|---|---|"] + [f"| {p} | {b} | {n} |" for p, b, n in cov]
    if EXP.exists():
        for ln in EXP.read_text().splitlines():
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if any(d in (e.get("days") or []) for d in week_dates(week)) or (e.get("logged_pt", "")[:10] in week_dates(week)):
                res["experiments"].append(e)
        lines += ["", "## Experiments this week", "", "| id | question | variant | result | verdict |", "|---|---|---|---|---|"]
        lines += [f"| {e.get('id')} | {e.get('question', '')[:90]} | {e.get('variant', '')} | {str(e.get('result', ''))[:140]} | {e.get('verdict', '')} |" for e in res["experiments"]]
    lines += ["", "No model is trained or promoted by this file: it measures the live scores (step 6 of the plan adds challengers)."]
    (SCORE / f"scorecard-model-{week}.json").write_text(json.dumps(res, indent=1, default=str))
    (SCORE / f"scorecard-model-{week}.md").write_text("\n".join(lines) + "\n")
    log(f"scorecard {week}: {len(dates)} days -> {SCORE / f'scorecard-model-{week}.md'}")
    return res


# ------------------------------------------------------------------ experiments
def exp_log(**kw):
    kw.setdefault("logged_pt", pt(time.time()))
    with open(EXP, "a") as f:
        f.write(json.dumps(kw) + "\n")
    log("experiment logged:", kw.get("id"))


def ch_stats(p, B, t_end):
    """Score-change rows -> forward check at 1 m and 5 m (5 s closes): n, hit rate, mean move in the score's direction, by |S|."""
    out = {}
    for c in iter_lines([p]):
        if c.get("kind") != "score_change" or not c.get("score"):
            continue
        lb = label_row({"t": c["t"], "px": c.get("px"), "atr": c.get("atr"), "score": c["score"]}, B.get(c["sym"]), t_end)
        s = abs(c["score"])
        for k in (str(s), "any") + (("2+",) if s >= 2 else ()):
            o = out.setdefault(k, {"n": 0, "h60": [0, 0], "h300": [0, 0], "dm300": 0.0})
            o["n"] += 1
            for h in (60, 300):
                if lb.get(f"h{h}_hit") is not None:
                    o[f"h{h}"][0] += 1
                    o[f"h{h}"][1] += lb[f"h{h}_hit"]
            o["dm300"] += lb.get("h300_dmove_bp") or 0.0
    return {k: {"changes": v["n"], "hit_1m": round(v["h60"][1] / v["h60"][0], 3) if v["h60"][0] else None,
                "hit_5m": round(v["h300"][1] / v["h300"][0], 3) if v["h300"][0] else None,
                "mean_dmove_5m_bp": round(v["dm300"] / max(1, v["h300"][0]), 2)} for k, v in sorted(out.items())}


def ablate(date, profile, drop, add, weight):
    d = date.replace("-", "")
    script = "score_replay_changes.py" if profile == "core" else "score_replay_wide.py"
    tag = "-wide" if profile != "core" else ""
    fname = f"changes{tag}-{d}.jsonl"
    base = SCORE / f"replay-{d}{tag}"
    if not (base / fname).exists():
        subprocess.run(["/usr/bin/python3", str(HOME / "oid-score" / script), date], check=True, cwd=str(HOME / "oid-score"))
    args = ["/usr/bin/python3", str(HOME / "oid-score" / script), date]
    vt = []
    if drop:
        args += ["--drop", drop]; vt.append(f"drop-{drop.replace(',', '-drop-')}")
    if weight:
        args += ["--weight", weight]; vt.append("w-" + weight.replace("=", "").replace(",", "-w-"))
    if add:
        args += ["--add", add]; vt.append(f"add-{add}")
    subprocess.run(args, check=True, cwd=str(HOME / "oid-score"), stdout=subprocess.DEVNULL)
    var = SCORE / (f"replay-{d}{tag}-" + "-".join(vt))
    import score_changes as SC
    B, te = Bars(date), SC.session_end_t(date)
    b, v = ch_stats(base / fname, B, te), ch_stats(var / fname, B, te)
    pp = lambda x, y: round((x - y) * 100, 1) if (x is not None and y is not None) else None
    diff = {k: {"changes": v.get(k, {}).get("changes", 0) - b[k]["changes"], "hit_5m_pp": pp(v.get(k, {}).get("hit_5m"), b[k]["hit_5m"]),
                "hit_1m_pp": pp(v.get(k, {}).get("hit_1m"), b[k]["hit_1m"])} for k in b}
    res = {"baseline": b, "variant": v, "delta": diff}
    exp_log(id=f"abl-{profile}-{d}-{'-'.join(vt)}", kind="ablation", question=f"Does the {profile} score do better without/with: {' '.join(vt)}?",
            profile=profile, variant="-".join(vt), days=[date], versions=json.loads((base / "summary.json").read_text()).get("settings_version") or json.loads((base / "summary.json").read_text()).get("config_version"),
            method=f"{script} replay of {date} (5 s steps), baseline vs variant; every score change to a non-zero score, checked 1 m and 5 m later on 5 s closes (hit = moved the score's way)",
            result=res, verdict="single day - log only; needs 10+ days before any settings change", files=[str(base), str(var)])
    print(json.dumps(res, indent=1))
    return res


# ------------------------------------------------------------------ registry page
def registry_page():
    reg = registry()
    import score_lib as L
    cfg = L.load_config()
    samp = {}
    for prof, pat in (("core", f"replay-*/changes-2*.jsonl"), ("light", f"replay-*-wide/changes-wide-2*.jsonl")):
        fs = sorted(glob.glob(str(SCORE / pat)))
        if fs:
            with open(fs[-1]) as f:
                for i, ln in enumerate(f):
                    if i > 3000:
                        break
                    r = json.loads(ln)
                    if r.get("kind") == "score_change":
                        samp.setdefault(prof, []).append(r)
    import score_features as SF
    unresolved, unreg = [], set()
    reg_paths = {f["path"] for f in reg["features"]}
    for f in reg["features"]:
        if f["path"].startswith("@") or f["status"] == "shadow" and f["source"] in ("chart_scenario", "news_tone"):
            continue
        profs = ["core"] if "core" in f["used_by"] else ["light"]
        ok = any(SF.dig(r if not f["path"].startswith("ctx.") else r.get("ctx"), f["path"].split(".")[f["path"].startswith("ctx."):]) is not None
                 for p in profs for r in samp.get(p, []))
        if not ok:
            unresolved.append(f["id"])

    def leaves(d, pre):
        for k, v in (d or {}).items():
            if isinstance(v, dict):
                yield from leaves(v, f"{pre}{k}.")
            elif not isinstance(v, list):
                yield f"{pre}{k}"
    for r in samp.get("core", [])[:500]:
        for c, cv in (r.get("comps") or {}).items():
            for lf in leaves(cv.get("x") or {}, f"comps.{c}.x."):
                if lf not in reg_paths and not lf.endswith(("vwap", ".vix", "vix_ref", "vix_ref_kind", "vix_stale", "tide_stale", ".cov")):
                    unreg.add(lf)
    comps_cfg = sorted(k for k, v in cfg["components"].items() if v.get("enabled", True))
    comps_off = sorted(k for k, v in cfg["components"].items() if not v.get("enabled", True))
    comps_reg = sorted({f["id"][:-2] for f in reg["features"] if f["id"].endswith("_c") and f["status"] == "in_score"})
    srcs = {s["id"]: s for s in reg["sources"]}
    L_ = [f"# 33 · Feature registry ({reg['registry_version']})", "",
          f"Generated by `score_learn.py registry-page` from `~/oid-data/config/feature-registry.json` on {pt(time.time())}. Do not edit by hand: edit the registry and rerun.", "",
          reg["doc"], "",
          "Every 15 s each scorer writes one `score_features` row per ticker (core: 61 names, full and light: the 144 Sector watch names; light rows are lite: score, its three inputs and ages only). "
          "Nightly (1:40 PM PT, `com.oid.desk.score-labels`) the JSONL is compacted to Parquet and `score_labels` attaches what happened next at 15 s, 30 s, 1 m, 2 m, 5 m, 15 m and 30 m. "
          "Saturday 11:00 AM PT (`com.oid.desk.score-model-weekly`) writes the weekly model scorecard.", "",
          "## Code check", "",
          f"- Components switched on in score-config.json: {', '.join(comps_cfg)}. In the registry (in_score): {', '.join(comps_reg)}. {'Match.' if comps_cfg == comps_reg else '**MISMATCH**'}",
          f"- In score-config.json but switched off: {', '.join(comps_off) or 'none'} (registered as shadow: news -> news_net_60m / news_n_60m).",
          f"- Registry paths with no value in the latest replay change rows (expected for inputs that were missing that day): {', '.join(unresolved) or 'none'}.",
          f"- Raw inputs in change rows that are not registered: {', '.join(sorted(unreg)) or 'none'}.", "",
          "## Sources", "", "| id | source | method | cadence | status | where | note |", "|---|---|---|---|---|---|---|"]
    L_ += [f"| `{s['id']}` | {s['name']} | {s['method']} | {s['cadence']} | {s['status']} | {s['where']} | {s.get('note', '')} |" for s in reg["sources"]]
    for st, title in (("output", "Score outputs"), ("in_score", "Inputs used by a live score"), ("age", "Ages (seconds)"),
                      ("context", "Context (logged, not in any score)"), ("shadow", "Shadow candidates (logged, never in a live score until promoted)")):
        L_ += ["", f"## {title}", "", "| column | path | used by | unit | age column | light rows | description |", "|---|---|---|---|---|---|---|"]
        L_ += [f"| `{f['id']}` | `{f['path']}` | {', '.join(f['used_by'])} | {f['unit']} | {f.get('age') or '—'} | {'yes' if f.get('in_light_rows') else 'no'} | {f['desc']}{' (alias of ' + f['alias_of'] + ')' if f.get('alias_of') else ''} |"
               for f in reg["features"] if f["status"] == st]
    L_ += ["", "## Chart Bot scenarios (shadow source `chart_scenario`, CB-SCN-V1)", "",
           "Chart Bot publishes `chart-bot/scenarios/latest.json` on the box (daily run plus 3 status refreshes): per ticker a primary and up to 3 alternates "
           "with label, direction, calibrated_score, trigger, T1/T2, invalidation, range low/high, ATR distances and status "
           "(active, triggered, target_hit, target2_hit, void, expired, held). The box desk-state push (quotes/mirror_poller.py, about every 60 s when the file changes) "
           "copies it to the mini at `~/oid-desk/desk/chart-bot/scenarios/latest.json`. The snapshotter reads the primary per ticker and logs `cs_*` columns; "
           "the ATR distances are recomputed against the live price each pass. If the file is missing every `cs_*` value is null.", "",
           "**Calibration warning:** primaries' calibrated_score runs hot (about 44% estimated vs 36% realized, a selection effect). Treat `cs_score` as a ranking, not a probability. "
           "Soft colour only: it never elevates a name on its own and is not in any live score.", "",
           "Replays never read `latest.json` (it would be look-ahead for a past day), so `cs_*` is null in replay rows.", ""]
    p = GUIDE / "33-feature-registry.md"
    p.write_text("\n".join(L_) + "\n")
    log(f"registry page -> {p}; unresolved {len(unresolved)}, unregistered {len(unreg)}")
    return unresolved, sorted(unreg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for c in ("nightly", "compact", "labels"):
        x = sp.add_parser(c)
        x.add_argument("--date", default=dt.date.today().isoformat())
        x.add_argument("--from-replay", action="store_true")
        x.add_argument("--weekdays-only", action="store_true")
    x = sp.add_parser("scorecard")
    x.add_argument("--week")
    sp.add_parser("registry-page")
    x = sp.add_parser("experiment")
    x.add_argument("action", choices=["log", "ablate"])
    for k in ("id", "question", "method", "result", "verdict", "versions", "date", "drop", "add", "weight", "variant"):
        x.add_argument(f"--{k}")
    x.add_argument("--days", nargs="*")
    x.add_argument("--files", nargs="*")
    x.add_argument("--profile", default="core")
    a = ap.parse_args()
    if a.cmd in ("nightly", "compact", "labels"):
        if a.weekdays_only and dt.date.fromisoformat(a.date).weekday() >= 5:
            log("weekend, skip"); return
        write_schema_files()
        if a.cmd in ("nightly", "compact"):
            compact(a.date)
        if a.cmd in ("nightly", "labels"):
            labels(a.date, a.from_replay)
    elif a.cmd == "scorecard":
        if not a.week:
            y, w, _ = (dt.date.today() - dt.timedelta(days=0 if dt.date.today().weekday() >= 5 else 7)).isocalendar()
            a.week = f"{y}-W{w:02d}"
        scorecard(a.week)
    elif a.cmd == "registry-page":
        registry_page()
    elif a.action == "log":
        exp_log(id=a.id, kind="study", question=a.question, method=a.method, result=a.result, verdict=a.verdict,
                versions=a.versions, days=a.days or [], files=a.files or [], variant=a.variant)
    else:
        ablate(a.date, a.profile, a.drop, a.add, a.weight)


if __name__ == "__main__":
    main()
