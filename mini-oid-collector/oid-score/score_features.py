#!/usr/bin/env python3
"""FEATURES (2026-10-21) - score learning plan steps 1-2: feature registry + score_features snapshots.

Every 15 s, for every ticker a scorer scores, write one flat row with each registered input value and the age of the
data behind it, plus the score that pass produced. Rows go to the archive as table `score_features`
(~/oid-data/archive/score_features/date=<ET date>/part-<writer>-<seq>.jsonl), compacted to Parquet nightly and kept
indefinitely (score_labels attaches outcomes). Stdlib only (runs under /usr/bin/python3 3.9 inside the scorers).

Live: the scorers' Tracker calls FeatureSnap.offer() each pass; rows are flattened and written on a background thread
so the scoring loop never waits on disk. Kill switch: score-config.json  "features": {"enabled": false}  (re-read each pass)
or env OID_SCORE_FEATURES=0. Never raises into the caller.
"""
import json
import os
import queue
import re
import threading
import time
from pathlib import Path

HOME = Path.home()
REGISTRY = Path(os.environ.get("OID_FEATURE_REGISTRY", str(HOME / "oid-data/config/feature-registry.json")))
NEWS_DIR = Path(os.environ.get("OID_NEWS_SENT_DIR", str(HOME / "oid-desk/state/news")))  # sentiment-YYYYMMDD.jsonl (com.oid.desk.news)
SCEN_STATUS = Path(os.environ.get("OID_CHART_SCN_STATUS", str(HOME / "oid-data/chart-scenarios/status-live.json")))
SCEN_FILE = Path(os.environ.get("OID_CHART_SCENARIOS", str(HOME / "oid-desk/desk/chart-bot/scenarios/latest.json")))
SCHEMA_VERSION = "v1"
TABLE = "score_features"
SLOT_S = 15


def archive_root():
    r = os.environ.get("OID_FEATURES_ROOT") or os.environ.get("OID_ARCHIVE_ROOT")
    if r:
        return Path(r).expanduser()
    return Path(os.environ.get("OID_DATA_ROOT", str(HOME / "oid-data"))).expanduser() / "archive"


def enabled(cfg=None):
    if os.environ.get("OID_SCORE_FEATURES", "1") == "0":
        return False
    try:
        return bool(((cfg or {}).get("features") or {}).get("enabled", True))
    except Exception:
        return True


# ------------------------------------------------------------------ registry
_REG = {"m": None, "r": None}


def registry():
    try:
        m = REGISTRY.stat().st_mtime
    except OSError:
        return _REG["r"]
    if m != _REG["m"]:
        try:
            r = json.loads(REGISTRY.read_text())
            for f in r.get("features", []):
                p = f["path"]
                f["_comp"] = None if p.startswith("@") else p.split(".")
            _REG["r"] = r
        except Exception:
            pass
        _REG["m"] = m
    return _REG["r"]


def dig(d, parts):
    for k in parts:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
        if d is None:
            return None
    return d


def _num(v):
    if isinstance(v, float):
        return round(v, 6) if v == v and v not in (float("inf"), float("-inf")) else None
    return v


# ------------------------------------------------------------------ news tone (shadow)
class NewsTone:
    """Tails ~/oid-desk/state/news/sentiment-<YYYYMMDD>.jsonl (mini news scorer). Per ticker: tone sum and count over the
    last 60 min, and the age of the newest item. X posts carry their own weight (0.5)."""

    def __init__(self):
        self.path, self.pos, self.items, self.chk = None, 0, {}, 0.0

    def _poll(self, date, now):
        if now - self.chk < 10:
            return
        self.chk = now
        p = NEWS_DIR / f"sentiment-{date.replace('-', '')}.jsonl"
        if p != self.path:
            self.path, self.pos, self.items = p, 0, {}
        try:
            sz = p.stat().st_size
        except OSError:
            return
        if sz < self.pos:
            self.pos, self.items = 0, {}
        if sz == self.pos:
            return
        try:
            with open(p, "rb") as f:
                f.seek(self.pos)
                data = f.read()
        except OSError:
            return
        end = data.rfind(b"\n")
        if end < 0:
            return
        self.pos += end + 1
        for ln in data[:end].split(b"\n"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            t = r.get("t") or r.get("ts") or r.get("published_ts")
            if isinstance(t, str):
                t = None
            sent = r.get("sent") or r.get("sentiment") or {}
            w = float(r.get("weight") or 1.0)
            if not t or not isinstance(sent, dict):
                continue
            for sym, s in sent.items():
                try:
                    self.items.setdefault(sym, []).append((float(t), float(s) * w))
                except (TypeError, ValueError):
                    continue

    def get(self, sym, date, now):
        self._poll(date, now)
        xs = self.items.get(sym)
        if not xs:
            return None, 0, None
        lo = now - 3600
        win = [s for t, s in xs if lo < t <= now + 1]
        last = max((t for t, _ in xs if t <= now + 1), default=None)
        return (round(sum(win), 4) if win else 0.0), len(win), (round(now - last, 1) if last else None)


# ------------------------------------------------------------------ Chart Bot scenarios (shadow, CB-SCN-V1)
LABEL_DIR = {"BULL_BREAKOUT": 1, "BULL_PULLBACK_HOLD": 1, "RANGE_CHOP": 0, "BEAR_BREAKDOWN": -1, "BEAR_FAILED_RALLY": -1}


def _f(d, *ks):
    for k in ks:
        v = d.get(k) if isinstance(d, dict) else None
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def parse_scenarios(obj):
    """-> {SYM: primary dict}. Accepts {tickers|by_ticker: {SYM: {primary, alternates}|[rows]}}, {SYM: ...} or a
    list of rows with ticker/is_primary/rank (CB-SCN-V1 predictions rows)."""
    out = {}

    def take(sym, v):
        prim = None
        if isinstance(v, dict) and isinstance(v.get("primary"), dict):
            prim = v["primary"]
        elif isinstance(v, dict) and isinstance(v.get("scenarios"), list):
            v = v["scenarios"]
        elif isinstance(v, dict) and (v.get("scenario_label") or v.get("label")):
            prim = v
        if prim is None and isinstance(v, list):
            rows = [x for x in v if isinstance(x, dict)]
            ps = [x for x in rows if x.get("is_primary") in (True, 1, "true", "True")] or \
                sorted(rows, key=lambda x: (x.get("rank") is None, x.get("rank") or 0))
            prim = ps[0] if ps else None
        if prim is not None and sym:
            out[str(sym).upper()] = prim

    if isinstance(obj, list):
        by = {}
        for x in obj:
            if isinstance(x, dict) and x.get("ticker"):
                by.setdefault(x["ticker"], []).append(x)
        for s, v in by.items():
            take(s, v)
        return out
    if not isinstance(obj, dict):
        return out
    body = obj.get("tickers") or obj.get("by_ticker") or obj.get("scenarios") or obj
    if isinstance(body, list):
        return parse_scenarios(body)
    for s, v in body.items():
        if isinstance(s, str) and s.isupper() and len(s) <= 6:
            take(s, v)
    return out


class Scenarios:
    """Reads Chart Bot's latest.json (pushed box -> mini by the desk-state push). Missing file -> all None."""

    def __init__(self, path=None):
        self.path, self.m, self.by, self.t_file, self.chk = Path(path or SCEN_FILE), None, {}, None, 0.0

    def _load(self, now):
        if now - self.chk < 30:
            return
        self.chk = now
        try:
            m = self.path.stat().st_mtime
        except OSError:
            self.m, self.by, self.t_file = None, {}, None
            return
        if m == self.m:
            return
        try:
            obj = json.loads(self.path.read_text())
            self.by = parse_scenarios(obj)
            self.t_file = m
            if isinstance(obj, dict):
                for k in ("generated_ts", "run_ts", "as_of_ts"):
                    if isinstance(obj.get(k), (int, float)):
                        self.t_file = float(obj[k])
                        break
        except Exception:
            self.by = {}
        self.m = m

    def _status(self, now):
        """Mini 30m status job (chart_scn_status.py) -> {SYM: {prediction_id, status, status_asof}}; newer than the file."""
        if now - getattr(self, "schk", 0) < 30:
            return getattr(self, "st", {})
        self.schk = now
        try:
            m = SCEN_STATUS.stat().st_mtime
            if m != getattr(self, "sm", None):
                self.st = (json.loads(SCEN_STATUS.read_text()).get("tickers") or {})
                self.sm = m
        except Exception:
            self.st = {}
        return self.st

    def get(self, sym, px, atr, now):
        self._load(now)
        p = self.by.get(sym)
        if not p:
            return None
        lab = p.get("scenario_label") or p.get("label")
        trig = _f(p, "trigger_price", "trigger")
        inv = _f(p, "invalidation", "stop")
        t1 = _f(p, "target_1", "T1", "t1")
        sc = _f(p, "calibrated_score")
        if sc is not None and sc > 1.0:
            sc = sc / 100.0

        def da(lv):
            return round((lv - px) / atr, 4) if (lv is not None and px and atr) else None
        st = p.get("status") or p.get("trigger_status")
        lv = self._status(now).get(sym) or {}
        if lv.get("prediction_id") and lv.get("prediction_id") == p.get("prediction_id") and lv.get("status"):
            st = lv["status"]
        return {"pid": p.get("prediction_id"), "rlo_atr": da(_f(p, "range_low")), "rhi_atr": da(_f(p, "range_high")),
                "label": lab, "dir": LABEL_DIR.get(lab), "score": sc, "trig_atr": da(trig), "inv_atr": da(inv),
                "t1_atr": da(t1), "status": st, "age_s": round(now - self.t_file, 1) if self.t_file else None,
                "trigger": trig, "invalidation": inv, "t1": t1}


# ------------------------------------------------------------------ flatten one pass
def flatten(row, ctx, reg, lite, extra):
    out = {}
    for f in reg.get("features", []):
        if (lite and not f.get("in_light_rows")) or f.get("alias_of"):
            continue
        p = f["path"]
        if p[0] == "@":
            v = extra.get(p[1:])
        else:
            v = dig(ctx, f["_comp"][1:]) if p.startswith("ctx.") else dig(row, f["_comp"])
        if isinstance(v, (dict, list)):
            v = None
        v = _num(v)
        if v is not None:  # nulls omitted in JSONL (Parquet compaction restores every column)
            out[f["id"]] = v
    return out


class FeatureSnap:
    """One per scorer process (profile = core | light | wide_full). offer() is called for every row of every pass;
    a row is kept at most once per 15 s slot per ticker. live=True -> background writer thread."""

    def __init__(self, profile, writer=None, live=True, root=None, mode="live"):
        self.profile, self.live, self.mode = profile, live, mode
        self.lite = profile == "light"
        self.writer = re.sub(r"[^A-Za-z0-9_.-]", "-", writer or f"score-{profile}")
        self.root = Path(root) if root else archive_root()
        self.last = {}
        self.news = NewsTone() if not self.lite else None
        self.scen = Scenarios() if (not self.lite and mode == "live") else None  # replays: no look-ahead from today's file
        self.q = queue.Queue(maxsize=20000)
        self.buf, self.paths = [], {}
        self.rows = self.errors = self.dropped = 0
        self.ms = 0.0
        if live:
            threading.Thread(target=self._loop, daemon=True, name="score-features").start()

    # called from the scoring loop: cheap (a dict lookup + a queue put)
    def offer(self, date, t, sym, px, row, ctx, version, tag_fn=None):
        slot = int(t // SLOT_S)
        if self.last.get(sym) == slot:
            return
        self.last[sym] = slot
        item = (date, t, sym, px, row, ctx, version, tag_fn)
        if self.live:
            try:
                self.q.put_nowait(item)
            except queue.Full:
                self.dropped += 1
        else:
            self._make(item)

    def _make(self, item):
        date, t, sym, px, row, ctx, version, tag_fn = item
        reg = registry()
        if not reg:
            return
        t0 = time.time()
        comps = row.get("comps") or {}
        extra = {"n_stale": sum(1 for c in comps.values() if (c.get("f") or {}).get("stale")),
                 "n_missing": sum(1 for c in comps.values() if (c.get("f") or {}).get("missing"))}
        if not self.lite:
            if self.news is not None:
                n, k, age = self.news.get(sym, date, t)
                extra.update({"news.net_60m": n, "news.n_60m": k, "news.last_age_s": age})
            if self.scen is not None:
                cs = self.scen.get(sym, px, row.get("atr"), t)
                for k2, v in (cs or {}).items():
                    extra["cs." + k2] = v
        rec = {"snap_id": f"{self.profile}|{sym}|{int(t // SLOT_S) * SLOT_S}|{self.mode}", "profile": self.profile,
               "symbol": sym, "date": date, "slot_t": int(t // SLOT_S) * SLOT_S, "t": round(t, 3),
               "settings_version": version, "registry_version": reg.get("registry_version"), "mode": self.mode,
               "row_kind": "lite" if self.lite else "full"}
        if tag_fn:
            try:
                tg = tag_fn(sym) or {}
                rec["sector_id"], rec["sector"] = tg.get("sector_id"), tg.get("sector")
            except Exception:
                pass
        rec.update(flatten(row, ctx or {}, reg, self.lite, extra))
        ns = int(t * 1e9)
        now = time.time_ns()
        rec.update({"schema_version": SCHEMA_VERSION, "event_ts_ns": ns, "ingest_ts_ns": now, "writer": self.writer})
        # event_ts_iso / ingest_ts_iso / t_pt are derived at compaction (score_features_compact.py) to keep JSONL small
        self.buf.append(rec)
        self.ms += (time.time() - t0) * 1000
        if len(self.buf) >= (500 if self.live else 5000):
            self.flush()

    def _loop(self):
        while True:
            try:
                item = self.q.get(timeout=2.0)
            except queue.Empty:
                self.flush()
                continue
            try:
                self._make(item)
            except Exception:
                self.errors += 1
            if self.q.empty():
                self.flush()

    def _path(self, date):
        p = self.paths.get(date)
        if p is None:
            d = self.root / TABLE / f"date={date}"
            d.mkdir(parents=True, exist_ok=True)
            pat = re.compile(r"^part-" + re.escape(self.writer) + r"-(\d+)\.jsonl$")
            seqs = [int(m.group(1)) for m in (pat.match(f.name) for f in d.iterdir()) if m]
            p = d / f"part-{self.writer}-{(max(seqs) + 1) if seqs else 1}.jsonl"
            self.paths = {date: p}
        return p

    def flush(self):
        if not self.buf:
            return
        rows, self.buf = self.buf, []
        try:
            by = {}
            for r in rows:
                by.setdefault(r["date"], []).append(json.dumps(r, separators=(",", ":"), allow_nan=False))
            for d, lines in by.items():
                with open(self._path(d), "a") as fh:
                    fh.write("\n".join(lines) + "\n")
            self.rows += len(rows)
        except Exception:
            self.errors += 1

    def stats(self):
        return {"rows": self.rows, "errors": self.errors, "dropped": self.dropped, "queue": self.q.qsize(),
                "flatten_ms": round(self.ms, 1)}


def _iso(ns):
    s, r = divmod(int(ns), 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(s)) + f".{r // 1000:06d}Z"


# ------------------------------------------------------------------ experiments (step 4): ablation helpers for replays
SHADOW_COMPONENTS = ("news",)


def ablate(cfg_like, drop=None, weights=None):
    """drop: comma list of components switched off; weights: 'comp=w,comp=w'. Mutates cfg_like['components'].
    Returns a short variant tag for file names / the experiment log."""
    tag = []
    comps = cfg_like.get("components") or {}
    for c in [x for x in (drop or "").split(",") if x]:
        if c not in comps:
            raise SystemExit(f"--drop {c}: not a component ({sorted(comps)})")
        comps[c]["enabled"] = False
        tag.append(f"drop-{c}")
    for kv in [x for x in (weights or "").split(",") if x]:
        k, v = kv.split("=")
        if k not in comps:
            raise SystemExit(f"--weight {k}: not a component")
        comps[k]["weight"] = float(v)
        tag.append(f"w-{k}{v}")
    return "-".join(tag)


def add_one(row, cfg_like, name, news, sym, date, t, weight=0.5, combine=None):
    """Add-one test for a shadow input (only 'news' today): injects a component into a scored row and re-combines.
    news: c = tanh(sum tone 60 min / 2), q = 1; only present when the ticker had scored items in the last 60 min
    (so it never dilutes names without news). Returns the row (mutated)."""
    import math
    if name != "news":
        raise SystemExit(f"--add {name}: only 'news' is wired")
    net, n, age = news.get(sym, date, t)
    if not n:
        return row
    comps = row["comps"]
    comps["news"] = {"x": {"net_60m": net, "n_60m": n}, "f": {"age_s": age}, "c": round(math.tanh(net / 2.0), 4), "q": 1.0, "w": weight}
    c2 = dict(cfg_like)
    c2["components"] = dict(cfg_like["components"], news={"enabled": True, "weight": weight})
    raw, score, cov = combine(comps, c2)
    row["raw"], row["score"], row["coverage"] = raw, score, cov
    return row
