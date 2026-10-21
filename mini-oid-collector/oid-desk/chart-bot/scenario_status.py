#!/usr/bin/env python3
"""CB-SCN-V1 live status board -> chart-bot/scenarios/latest.json (display/shadow only).

Statuses are evaluated on the newest CLOSED bars after each scenario's asof_bar_date: real RH daily bars first, then
completed 30m bars (chart-bot/intraday/30m, from ingest_intraday.py) for sessions with no real daily bar yet.
This NEVER touches predictions.csv / outcomes.csv / scorecard (those are scored by score_outcomes.py on real daily
bars only). Written atomically (temp file + os.replace). Research/paper only.

Portable: stdlib only (Python >= 3.9, zoneinfo), no network, no box paths. External inputs (see SCENARIOS.md,
"Running status-only on another machine"):
  --scenarios PATH   scenarios.jsonl | run.json | latest.json      (default <root>/scenarios/latest/run.json)
  --bars-30m PATH    file or dir of 30m bars (CSV / JSON / JSONL)  (default <root>/intraday/30m/{SYM}.json)
  --daily-bars PATH  file or dir of final daily bars (optional)    (default <root>/bars/{SYM}.json; none if
                     --bars-30m is given and --daily-bars is not)
  --out PATH         status file                                   (default <root>/scenarios/latest.json)
  --root PATH        base dir (or env CB_ROOT; default = this script's directory)
  --now ISO          evaluation clock (testing/replay; default = now)
usage: python3 chart-bot/scenario_status.py [flags]   (or: python3 chart-bot/run_scenarios.py --status-only [flags])
"""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("CB_ROOT") or Path(__file__).resolve().parent).expanduser().resolve()
SCN = ROOT / "scenarios"
PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")
PROV = "rh-quote-close-provisional"
# horizon by label (CB-SCN-V1 vocabulary); used only when an input row lacks horizon_days (latest.json alternates)
HORIZON = {"BULL_BREAKOUT": 10, "BEAR_BREAKDOWN": 10, "BULL_PULLBACK_HOLD": 5, "BEAR_FAILED_RALLY": 5, "RANGE_CHOP": 5}
RULE = {"BULL_BREAKOUT": "close-above", "BEAR_BREAKDOWN": "close-below", "BULL_PULLBACK_HOLD": "touch-below",
        "BEAR_FAILED_RALLY": "touch-above", "RANGE_CHOP": "stay-inside"}


class InputError(ValueError):
    pass


def _r(v, n=2):
    return None if v is None else round(float(v), n)


# ---------------------------------------------------------------- external inputs (portable; stdlib only)
_ALIAS = {"symbol": ("symbol", "sym", "ticker"), "ts": ("ts", "t", "time", "timestamp", "begins_at", "datetime"),
          "date": ("session_date", "date", "day", "session"),
          "open": ("open", "o"), "high": ("high", "h"), "low": ("low", "l"), "close": ("close", "c"),
          "volume": ("volume", "v", "vol"), "source": ("source", "src")}
PROTECTED = {"predictions.csv", "outcomes.csv", "scorecard.json", "scorecard.md", "scenarios.jsonl", "run.json"}


def _get(row: dict, key: str):
    for k in _ALIAS[key]:
        if k in row and row[k] not in (None, ""):
            return row[k]
        ku = k.upper()
        if ku in row and row[ku] not in (None, ""):
            return row[ku]
    return None


def _ts(v, where: str) -> datetime:
    """ISO 8601 with an explicit offset/Z (bar START), or epoch seconds/ms. Naive timestamps are rejected."""
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().lstrip("-").isdigit()):
        x = float(v)
        return datetime.fromtimestamp(x / 1000 if x > 1e11 else x, timezone.utc)
    t = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00").replace("z", "+00:00"))
    if t.tzinfo is None:
        raise InputError(f"{where}: timestamp {v!r} has no timezone (use ISO with Z or an offset, e.g. 2026-10-20T13:30:00Z)")
    return t.astimezone(timezone.utc)


def _files(path: Path) -> list[Path]:
    if path.is_dir():
        fs = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in (".csv", ".json", ".jsonl")
                    and not p.name.startswith("."))
        if not fs:
            raise InputError(f"{path}: no .csv/.json/.jsonl files")
        return fs
    if not path.is_file():
        raise InputError(f"{path}: not found")
    return [path]


def _rows(f: Path) -> list[tuple[dict, str | None]]:
    """(row, file-level symbol) pairs from a CSV, JSONL or JSON file."""
    stem = f.stem.upper()
    file_sym = stem if stem.replace(".", "").replace("-", "").isalnum() and len(stem) <= 8 else None
    if f.suffix.lower() == ".csv":
        with f.open(newline="") as fh:
            return [({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}, file_sym)
                    for r in csv.DictReader(fh)]
    if f.suffix.lower() == ".jsonl":
        return [(json.loads(l), file_sym) for l in f.read_text().splitlines() if l.strip()]
    d = json.loads(f.read_text())
    if isinstance(d, list):
        return [(r, file_sym) for r in d]
    if isinstance(d, dict) and isinstance(d.get("bars"), list):
        sym = d.get("symbol") or d.get("ticker") or file_sym
        return [(r, sym) for r in d["bars"]]
    if isinstance(d, dict) and all(isinstance(v, list) for v in d.values()):  # {"MU": [...], "NVDA": [...]}
        return [(r, k) for k, v in d.items() for r in v]
    raise InputError(f"{f}: unrecognised JSON layout (want a list of rows, {{'symbol','bars'}}, or {{SYM: [rows]}})")


def load_30m(path: Path, rth_only: bool = True) -> tuple[dict[str, list[dict]], dict]:
    """30m bars -> {SYM: [{"t": iso-utc, o,h,l,c,v}] sorted, deduped (last wins)}. ts = bar START.
    Bars not starting on :00/:30 are rejected (wrong interval); with rth_only, bars outside 09:30-16:00 ET are dropped."""
    out: dict[str, dict[str, dict]] = {}
    stats = {"files": 0, "rows": 0, "kept": 0, "dropped_ext_hours": 0, "rejected_misaligned": 0}
    for f in _files(path):
        stats["files"] += 1
        for i, (r, fsym) in enumerate(_rows(f)):
            stats["rows"] += 1
            where = f"{f.name} row {i + 1}"
            sym = (_get(r, "symbol") or fsym or "")
            sym = str(sym).strip().upper()
            if not sym:
                raise InputError(f"{where}: no symbol column and the file name is not a symbol")
            tv = _get(r, "ts")
            if tv is None:
                raise InputError(f"{where}: missing ts")
            t = _ts(tv, where)
            if t.second or t.microsecond or t.minute % 30:
                stats["rejected_misaligned"] += 1
                continue
            e = t.astimezone(ET)
            if rth_only and not ((9, 30) <= (e.hour, e.minute) < (16, 0)):
                stats["dropped_ext_hours"] += 1
                continue
            try:
                bar = {"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": float(_get(r, "open")), "h": float(_get(r, "high")),
                       "l": float(_get(r, "low")), "c": float(_get(r, "close"))}
            except (TypeError, ValueError):
                raise InputError(f"{where}: open/high/low/close must be numbers")
            v = _get(r, "volume")
            bar["v"] = float(v) if v is not None else None
            out.setdefault(sym, {})[bar["t"]] = bar
            stats["kept"] += 1
    return {k: [v[t] for t in sorted(v)] for k, v in out.items()}, stats


def load_daily(path: Path) -> dict[str, list[dict]]:
    """Final daily bars -> {SYM: [{session_date, open, high, low, close, source}] sorted, deduped (last wins)}."""
    out: dict[str, dict[str, dict]] = {}
    for f in _files(path):
        for i, (r, fsym) in enumerate(_rows(f)):
            where = f"{f.name} row {i + 1}"
            sym = str(_get(r, "symbol") or fsym or "").strip().upper()
            d = _get(r, "date")
            if d is None and _get(r, "ts") is not None:
                d = _ts(_get(r, "ts"), where).date().isoformat()  # RH day bars begin 00:00Z on the session date
            if not sym or not d:
                raise InputError(f"{where}: need symbol (or per-symbol file name) and session_date/date")
            try:
                bar = {"session_date": str(d)[:10], "open": float(_get(r, "open")), "high": float(_get(r, "high")),
                       "low": float(_get(r, "low")), "close": float(_get(r, "close")), "source": _get(r, "source")}
            except (TypeError, ValueError):
                raise InputError(f"{where}: open/high/low/close must be numbers")
            out.setdefault(sym, {})[bar["session_date"]] = bar
    return {k: [v[d] for d in sorted(v)] for k, v in out.items()}


def load_scenarios(path: Path) -> dict:
    """scenarios.jsonl | run.json | latest.json (or a dir holding one) -> run.json-shaped dict."""
    if path.is_dir():
        for n in ("scenarios.jsonl", "run.json", "latest.json"):
            if (path / n).is_file():
                path = path / n
                break
        else:
            raise InputError(f"{path}: no scenarios.jsonl / run.json / latest.json")
    if not path.is_file():
        raise InputError(f"{path}: not found")
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        if not rows:
            raise InputError(f"{path}: empty")
        last = {}
        for r in rows:  # keep each ticker's newest run only
            k = (r["asof_bar_date"], r["run_ts_pt"])
            if r["ticker"] not in last or k > last[r["ticker"]]:
                last[r["ticker"]] = k
        names = {}
        for r in rows:
            if (r["asof_bar_date"], r["run_ts_pt"]) != last[r["ticker"]]:
                continue
            f = r.get("features") or {}
            n = names.setdefault(r["ticker"], {"asof_bar_date": r["asof_bar_date"],
                                               "features": {"spot": f.get("spot", r.get("spot")), "atr14": f.get("atr14")},
                                               "scenarios": []})
            n["scenarios"].append({k: v for k, v in r.items() if k != "features"})
        for n in names.values():
            n["scenarios"].sort(key=lambda s: s.get("rank", 99))
        top = max(last.values())
        return {"method_version": rows[0]["method_version"], "run_ts_pt": top[1], "asof_bar_date": top[0],
                "names": dict(sorted(names.items()))}
    d = json.loads(path.read_text())
    if "names" in d:  # run.json
        return d
    if "tickers" in d and all(isinstance(v, dict) and "primary" in v for v in d["tickers"].values()):  # latest.json
        names = {}
        for sym, t in d["tickers"].items():
            scns = []
            for i, x in enumerate([t["primary"]] + list(t.get("alternates") or [])):
                lab = x["label"]
                scns.append({"prediction_id": x["prediction_id"], "scenario_label": lab, "direction": x["direction"],
                             "calibrated_score": x.get("calibrated_score"), "prior_score": x.get("prior_score"),
                             "trigger_price": x.get("trigger_price"), "trigger_rule": x.get("trigger_rule") or RULE[lab],
                             "target_1": x.get("target_1"), "target_2": x.get("target_2"),
                             "invalidation": x.get("invalidation"), "range_lo": x.get("range_low"),
                             "range_hi": x.get("range_high"), "horizon_days": x.get("horizon_days") or HORIZON[lab],
                             "level_source": x.get("level_source"), "is_primary": i == 0,
                             "run_ts_pt": t.get("run_ts_pt"), "bar_source": t.get("bar_source")})
            names[sym] = {"asof_bar_date": t.get("asof_bar_date") or d["asof_bar_date"],
                          "features": {"spot": t.get("spot_asof"), "atr14": t.get("atr14")}, "scenarios": scns}
        return {"method_version": d["method_version"], "run_ts_pt": d["run_ts_pt"], "asof_bar_date": d["asof_bar_date"],
                "names": names}
    raise InputError(f"{path}: not a scenarios.jsonl, run.json or latest.json")


def closed_bars(sym: str, asof: str, now_utc: datetime, daily: list[dict] | None = None,
                m30: list[dict] | None = None, external: bool = False) -> list[dict]:
    """Real daily bars after asof, then completed 30m bars for later sessions. Each bar carries its session + source.
    daily/m30 = pre-loaded external bars; None = read the box files under ROOT (original behaviour)."""
    out, last_daily = [], asof
    if daily is None and not external:
        f = ROOT / "bars" / f"{sym}.json"
        daily = (json.loads(f.read_text()).get("bars") or []) if f.is_file() else []
    for b in daily or []:
        if b["session_date"] <= asof:
            continue
        if b.get("source") == PROV or "provisional" in str(b.get("source") or ""):
            break
        if external and datetime.fromisoformat(b["session_date"] + "T16:00").replace(tzinfo=ET) > now_utc:
            break  # that session has not closed yet on this clock
        out.append({"session": b["session_date"], "o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"],
                    "src": "rh-day-bar" if not external else "ext-day-bar", "end": f"{b['session_date']} 16:00 ET"})
        last_daily = b["session_date"]
    if m30 is None and not external:
        f30 = ROOT / "intraday" / "30m" / f"{sym}.json"
        m30 = (json.loads(f30.read_text()).get("bars") or []) if f30.is_file() else []
    for b in m30 or []:
        t = datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        if t + timedelta(minutes=30) > now_utc:
            continue  # still forming
        sess = t.astimezone(ET).date().isoformat()
        if sess <= last_daily:
            continue
        out.append({"session": sess, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                    "src": "rh-30m" if not external else "ext-30m",
                    "end": (t + timedelta(minutes=30)).astimezone(PT).strftime("%Y-%m-%d %-I:%M %p PT")})
    return out


def status_of(s: dict, bars: list[dict]) -> dict:
    """Same rules as score_outcomes.evaluate, applied bar by bar (daily or 30m):
    close-above/below triggers on a bar close; touch-above/below on high/low; T1/T2 on a touch;
    void = closing stop after trigger (or any close outside the range for RANGE_CHOP); window = horizon_days sessions."""
    lab, rule, H = s["scenario_label"], s["trigger_rule"], int(s["horizon_days"])
    sessions = []
    use = []
    for b in bars:
        if b["session"] not in sessions:
            sessions.append(b["session"])
        if len(sessions) > H:
            break
        use.append(b)
    window_done = len(sessions) > H or (len(sessions) == H and use and use[-1]["src"] in ("rh-day-bar", "ext-day-bar"))
    st = {"status": "active", "status_asof": None, "status_bar_source": None, "last_close": None,
          "sessions_elapsed": len(sessions), "triggered_at": None, "t1_hit_at": None, "t2_hit_at": None, "void_at": None}
    if use:
        st.update(status_asof=use[-1]["end"], status_bar_source=use[-1]["src"], last_close=_r(use[-1]["c"]))
    if rule == "stay-inside":
        lo, hi = s.get("range_lo"), s.get("range_hi")
        for b in use:
            if b["c"] > hi or b["c"] < lo:
                st.update(status="void", void_at=b["end"])
                return st
        if window_done:
            st["status"] = "held"
        return st
    sg = 1 if s["direction"] == "long" else -1
    T, T1, T2, S = s["trigger_price"], s["target_1"], s["target_2"], s["invalidation"]
    beyond = (lambda x, l: x > l) if sg > 0 else (lambda x, l: x < l)
    touch = (lambda b, l: b["h"] >= l) if sg > 0 else (lambda b, l: b["l"] <= l)
    ti = None
    for i, b in enumerate(use):
        if (rule in ("close-above", "close-below") and beyond(b["c"], T)) or \
           (rule == "touch-below" and b["l"] <= T) or (rule == "touch-above" and b["h"] >= T):
            ti = i
            st.update(status="triggered", triggered_at=b["end"])
            break
    if ti is None:
        if window_done:
            st["status"] = "expired"
        return st
    for i in range(ti, len(use)):
        b = use[i]
        same = i == ti
        t1 = T1 is not None and ((beyond(b["c"], T1) or b["c"] == T1) if same else touch(b, T1))
        t2 = T2 is not None and ((beyond(b["c"], T2) or b["c"] == T2) if same else touch(b, T2))
        if st["t1_hit_at"] is None and t1:
            st.update(status="target_hit", t1_hit_at=b["end"])
        if st["t1_hit_at"] is not None and t2:
            st.update(status="target2_hit", t2_hit_at=b["end"])
            return st
        if S is not None and ((b["c"] < S) if sg > 0 else (b["c"] > S)):
            st["void_at"] = b["end"]
            if st["t1_hit_at"] is None:
                st["status"] = "void"
            return st
    if window_done and st["status"] == "triggered":
        st["status"] = "expired"
    return st


def build(now_utc: datetime | None = None, *, scenarios: str | Path | None = None, bars_30m: str | Path | None = None,
          daily_bars: str | Path | None = None, out: str | Path | None = None, rth_only: bool = True) -> dict:
    """No arguments = the original box behaviour (run.json + bars/ + intraday/30m under ROOT -> scenarios/latest.json).
    Any external input switches to portable mode: only the given files are read, nothing else under ROOT is needed."""
    now_utc = now_utc or datetime.now(timezone.utc)
    external = bars_30m is not None or daily_bars is not None
    run = load_scenarios(Path(scenarios).expanduser()) if scenarios is not None else \
        json.loads((SCN / "latest" / "run.json").read_text())
    m30_all, m30_stats = load_30m(Path(bars_30m).expanduser(), rth_only) if bars_30m is not None else (None, None)
    daily_all = load_daily(Path(daily_bars).expanduser()) if daily_bars is not None else None
    out_path = Path(out).expanduser() if out is not None else SCN / "latest.json"
    if out_path.name in PROTECTED:
        raise InputError(f"--out {out_path}: refusing to overwrite an archive/scoring file")
    tickers, no_bars = {}, []
    for sym, n in run["names"].items():
        f, scns = n["features"], n["scenarios"]
        atr = f.get("atr14") or 1.0
        spot = f.get("spot")
        asof = n.get("asof_bar_date") or run["asof_bar_date"]
        if external:
            bars = closed_bars(sym, asof, now_utc, daily=(daily_all or {}).get(sym, []),
                               m30=(m30_all or {}).get(sym, []), external=True)
            if not bars:
                no_bars.append(sym)
        else:
            bars = closed_bars(sym, asof, now_utc)
        prim = next(s for s in scns if s["is_primary"])
        dist = lambda lvl: None if lvl is None or spot is None else _r((lvl - spot) / atr)

        def alt(s):
            a = {"prediction_id": s["prediction_id"], "label": s["scenario_label"], "direction": s["direction"],
                 "calibrated_score": s["calibrated_score"], "trigger_price": s.get("trigger_price"),
                 "trigger_rule": s["trigger_rule"], "invalidation": s.get("invalidation"),
                 "range_low": s.get("range_lo"), "range_high": s.get("range_hi"),
                 "target_1": s.get("target_1"), "target_2": s.get("target_2"), "horizon_days": s.get("horizon_days"),
                 **status_of(s, bars)}
            if s["trigger_rule"] != "stay-inside" and s.get("target_1") is None:
                a["targets_unknown"] = True  # latest.json input carries no alternate T1/T2: target_hit not evaluated
            return a
        tickers[sym] = {
            "method_version": run["method_version"], "run_ts_pt": prim["run_ts_pt"], "asof_bar_date": asof,
            "bar_source": prim["bar_source"], "spot_asof": spot, "atr14": atr,
            "primary": {"prediction_id": prim["prediction_id"], "label": prim["scenario_label"], "direction": prim["direction"],
                        "calibrated_score": prim["calibrated_score"], "prior_score": prim["prior_score"],
                        "trigger_price": prim.get("trigger_price"), "trigger_rule": prim["trigger_rule"],
                        "target_1": prim.get("target_1"), "target_2": prim.get("target_2"), "invalidation": prim.get("invalidation"),
                        "range_low": prim.get("range_lo"), "range_high": prim.get("range_hi"),
                        "horizon_days": prim["horizon_days"], "level_source": prim.get("level_source"),
                        "dist_to_trigger_atr": dist(prim.get("trigger_price")), "dist_to_invalidation_atr": dist(prim.get("invalidation")),
                        **status_of(prim, bars)},
            "alternates": [alt(s) for s in scns if not s["is_primary"]][:3],
        }
    doc = {"method_version": run["method_version"], "run_ts_pt": run["run_ts_pt"], "asof_bar_date": run["asof_bar_date"],
           "status_refreshed_pt": now_utc.astimezone(PT).strftime("%Y-%m-%d %-I:%M:%S %p PT"),
           "status_note": "status is display/shadow only (closed daily bars, then closed 30m bars); scoring stays daily real bars",
           "softOnly": True, "neverElevateAlone": True, "count": len(tickers), "tickers": dict(sorted(tickers.items()))}
    if scenarios is not None or external:
        doc["status_inputs"] = {"scenarios": str(scenarios) if scenarios is not None else "root:scenarios/latest/run.json",
                                "bars_30m": str(bars_30m) if bars_30m is not None else None,
                                "daily_bars": str(daily_bars) if daily_bars is not None else None,
                                "rth_only": rth_only, "bars_30m_stats": m30_stats, "tickers_without_bars": no_bars,
                                "host_note": "portable status-only run (stdlib, no network); not the box archive"}
    write_atomic(out_path, doc)
    doc["_out"] = str(out_path)
    doc["_no_bars"] = no_bars
    return doc


def write_atomic(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.stem + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def add_args(ap) -> None:
    ap.add_argument("--scenarios", metavar="PATH", help="scenarios.jsonl | run.json | latest.json (or a dir holding one)")
    ap.add_argument("--bars-30m", metavar="PATH", help="file or dir of 30m bars: CSV/JSON/JSONL, symbol,ts,open,high,low,close,volume")
    ap.add_argument("--daily-bars", metavar="PATH", help="optional file or dir of FINAL daily bars: symbol,date,open,high,low,close")
    ap.add_argument("--out", metavar="PATH", help="status file to write (default <root>/scenarios/latest.json)")
    ap.add_argument("--root", metavar="PATH", help="base dir (default: env CB_ROOT, else this script's directory)")
    ap.add_argument("--now", metavar="ISO", help="evaluation clock with tz, for tests/replays (default: now)")
    ap.add_argument("--include-ext-hours", action="store_true", help="keep 30m bars outside 09:30-16:00 ET (default: drop)")


def set_root(root: str | Path | None) -> None:
    global ROOT, SCN
    if root:
        ROOT = Path(root).expanduser().resolve()
        SCN = ROOT / "scenarios"


def run_from_args(a) -> dict:
    set_root(a.root)
    now = _ts(a.now, "--now") if a.now else None
    return build(now, scenarios=a.scenarios, bars_30m=a.bars_30m, daily_bars=a.daily_bars, out=a.out,
                 rth_only=not a.include_ext_hours)


if __name__ == "__main__":
    import argparse
    import time
    from collections import Counter
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_args(ap)
    a = ap.parse_args()
    t = time.time()
    try:
        d = run_from_args(a)
    except (InputError, OSError, json.JSONDecodeError, KeyError) as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps({"count": d["count"], "refreshed": d["status_refreshed_pt"], "secs": round(time.time() - t, 2),
                      "primary_status": Counter(v["primary"]["status"] for v in d["tickers"].values()),
                      "out": d["_out"], "tickers_without_bars": d["_no_bars"] if "status_inputs" in d else None}))
