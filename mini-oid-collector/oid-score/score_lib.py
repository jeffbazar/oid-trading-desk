"""OID composite direction score (-3..+3) - shared library.

Research/log only. Never places orders, never calls paid APIs: reads only files the mini's
existing jobs already write (bars, norms, walls caches, VIX, UW tide) and the local live page
state (127.0.0.1:8791/state.json).  stdlib python3 (3.9).

Every component returns {"c": value in [-1,1], "q": quality 0..1, "x": raw measures, "f": flags}.
c is re-computable from x with any config (see c_from_x) so logged history can be re-scored.
"""
import json, math, os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
    PT, ET = ZoneInfo("America/Los_Angeles"), ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    PT = ET = timezone.utc

HOME = Path.home()
DESK = HOME / "oid-desk/desk"
STORE = Path(os.environ.get("OID_SCORE_STORE", str(DESK / "cache/bars/store")))
NORMS = STORE.parent / "live-norms-1m.json"
LATEST = DESK / "market-data/latest"
LIVEPAGE = HOME / "oid-live-page"
CONFIG = Path(os.environ.get("OID_SCORE_CONFIG", str(HOME / "oid-data/config/score-config.json")))
OUT = Path(os.environ.get("OID_SCORE_OUT", str(HOME / "oid-data/score")))
STATE_URL = os.environ.get("OID_SCORE_STATE_URL", "http://127.0.0.1:8791/state.json")
COMPONENTS = ("flip", "walls", "volume", "flow", "trend", "market")


def load_config(path=None):
    return json.loads(Path(path or CONFIG).read_text())


def profile_config(cfg, name):
    """Settings for a named score profile (cfg["profiles"][name]), e.g. "light" = the Sector watch score.
    Same components, calculations, scales and weights as the core config; only the inputs listed in
    components_enabled stay on (the rest are switched off, so combine() divides by the enabled weights only:
    the score is renormalized to the same -3..+3 range). Optional "weights" / "components" override per input.
    The profile's own config_version is stamped on every row it writes. The core config is never modified."""
    import copy
    prof = (cfg.get("profiles") or {}).get(name)
    if not prof:
        raise KeyError(f"no score profile {name!r} in config")
    out = copy.deepcopy({k: v for k, v in cfg.items() if k != "profiles"})
    on = set(prof.get("components_enabled") or [])
    for comp, spec in out["components"].items():
        spec["enabled"] = comp in on
        if comp in (prof.get("weights") or {}):
            spec["weight"] = float(prof["weights"][comp])
        spec.update((prof.get("components") or {}).get(comp) or {})
    out["config_version"] = prof["config_version"]
    out["core_config_version"] = cfg.get("config_version")
    out["score_profile"] = name
    out["profile"] = copy.deepcopy(prof)
    if prof.get("exclude") is not None:
        out["exclude"] = list(prof["exclude"])
    if prof.get("change_refresh_s") is not None:
        out["cadence_pt"]["change_refresh_s"] = prof["change_refresh_s"]
    return out


def clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


def rnd(v, n=4):
    return None if v is None else round(float(v), n)


def pt_str(t):
    return datetime.fromtimestamp(t, PT).strftime("%Y-%m-%d %I:%M:%S %p PT")


def iso_t(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


# ------------------------------------------------------------------ bars / norms / ATR
def load_day_bars(sym, date, store=None, hist_fallback=True):
    """1-min RTH bars for date (YYYY-MM-DD): live jsonl (last write wins per minute), else history store.
    store: bar store dir (default STORE = core; the light/wide profile passes the wide store)."""
    out = {}
    p = Path(store or STORE) / "live" / f"{sym}-1m-{date.replace('-', '')}.jsonl"
    try:
        for ln in p.read_text().splitlines():
            try:
                b = json.loads(ln)
            except Exception:
                continue
            if b.get("d") == date and b.get("c") is not None:
                out[b["t"]] = b
    except OSError:
        pass
    if not out and hist_fallback:
        for b in _hist(sym, store):
            if b.get("d") == date:
                out[b["t"]] = b
    bars = [out[k] for k in sorted(out)]
    for b in bars:
        b["ts"] = iso_t(b["t"])
    return bars


_HIST = {}


def _hist(sym, store=None):
    p = Path(store or STORE) / f"{sym}-1m.json"
    key = sym if store is None else (str(store), sym)   # core keys unchanged
    try:
        m = p.stat().st_mtime
    except OSError:
        return []
    if _HIST.get(key, (None,))[0] != m:
        try:
            _HIST[key] = (m, json.loads(p.read_text()).get("bars") or [])
        except Exception:
            _HIST[key] = (m, [])
    return _HIST[key][1]


def sessions(sym):
    return sorted({b["d"] for b in _hist(sym)})


def daily_atr(sym, before_date, n=14, store=None):
    """ATR(n) of daily bars built from the 1-min history, sessions strictly before before_date."""
    days = {}
    for b in _hist(sym, store):
        d = b.get("d")
        if not d or d >= before_date:
            continue
        x = days.setdefault(d, {"h": b["h"], "l": b["l"], "c": b["c"]})
        x["h"], x["l"], x["c"] = max(x["h"], b["h"]), min(x["l"], b["l"]), b["c"]
    ks = sorted(days)
    trs = []
    for i, k in enumerate(ks):
        d = days[k]
        pc = days[ks[i - 1]]["c"] if i else None
        trs.append(max(d["h"] - d["l"], abs(d["h"] - pc) if pc else 0, abs(d["l"] - pc) if pc else 0))
    trs = trs[-n:]
    return (sum(trs) / len(trs)) if trs else None, (days[ks[-1]]["c"] if ks else None)


_NORMS = {"m": None, "n": {}}


def norms():
    try:
        m = NORMS.stat().st_mtime
    except OSError:
        return {}
    if _NORMS["m"] != m:
        try:
            _NORMS["n"] = json.loads(NORMS.read_text()).get("norms") or {}
        except Exception:
            _NORMS["n"] = {}
        _NORMS["m"] = m
    return _NORMS["n"]


# ------------------------------------------------------------------ raw measures
def bar_measures(sym, bars, t, px, atr, cfg):
    """VWAP, 15m return, up/down volume share and 15m rvol from closed bars before t."""
    cv, ct = cfg["components"]["volume"], cfg["components"]["trend"]
    closed = [b for b in bars if b["ts"] is not None and b["ts"] + 60 <= t + 1]
    if not closed:
        return None
    pv = sum((b.get("vw") or b["c"]) * (b.get("v") or 0) for b in closed)
    vv = sum((b.get("v") or 0) for b in closed)
    vwap = pv / vv if vv else None
    wv, wr = int(cv.get("window_min", 15)), int(ct.get("ret_window_min", 15))
    win = closed[-wv:]
    sv = tv = 0.0
    prev = closed[-wv - 1]["c"] if len(closed) > wv else win[0]["o"]
    for b in win:
        v = float(b.get("v") or 0)
        s = 1 if b["c"] > prev else -1 if b["c"] < prev else 0
        sv += s * v
        tv += v
        prev = b["c"]
    nr = norms().get(sym) or []
    nsum = sum((nr[b["slot"]] or 0) for b in win if isinstance(b.get("slot"), int) and 0 <= b["slot"] < len(nr) and nr[b["slot"]])
    rvol = (tv / nsum) if nsum else None
    ref = closed[-wr - 1]["c"] if len(closed) > wr else closed[0]["o"]
    return {"vwap": vwap, "updn": (sv / tv) if tv else 0.0, "rvol15": rvol, "ret_ref": ref,
            "last_bar_age_s": t - (closed[-1]["ts"] + 60), "n_bars": len(closed),
            "vwap_atr": ((px - vwap) / atr) if (vwap and atr) else None,
            "ret_atr": ((px - ref) / atr) if atr else None}


# ------------------------------------------------------------------ component c from x (re-scorable)
def c_from_x(name, x, p):
    if x is None:
        return 0.0
    if name == "flip":
        return clamp(math.tanh(x["d_atr"] / p.get("scale_atr", 0.3))) if x.get("d_atr") is not None else 0.0
    if name == "walls":
        up, dn = x.get("up_atr"), x.get("dn_atr")
        if up is None or dn is None:
            return 0.0
        if up <= 0:
            return p.get("beyond_wall", 0.3)
        if dn <= 0:
            return -p.get("beyond_wall", 0.3)
        return clamp((up - dn) / (up + dn))
    if name == "volume":
        rv = x.get("rvol15")
        g = clamp(((rv if rv is not None else 1.0) - p.get("rvol_lo", 0.8)) / p.get("rvol_span", 1.2), 0.0, 1.0)
        return clamp((x.get("updn") or 0.0) * (0.4 + 0.6 * g))
    if name == "flow":
        cp = x.get("cp")
        if cp and cp > 0 and not x.get("thin"):
            return clamp(math.log(cp) / math.log(p.get("cp_log_base", 3.0)))
        lean = x.get("uw_lean")
        v = p.get("uw_lean_value", 0.5)
        return v if lean == "CALL" else -v if lean == "PUT" else 0.0
    if name == "trend":
        return _trend_c(x.get("vwap_atr"), x.get("ret_atr"), p)
    if name == "market":
        parts = market_parts(x, p)
        return sum(parts.values()) / len(parts) if parts else 0.0
    raise KeyError(name)


def _trend_c(vwap_atr, ret_atr, p):
    a = math.tanh(vwap_atr / p.get("vwap_scale_atr", 0.15)) if vwap_atr is not None else None
    b = math.tanh(ret_atr / p.get("ret_scale_atr", 0.10)) if ret_atr is not None else None
    xs = [v for v in (a, b) if v is not None]
    return clamp(sum(xs) / len(xs)) if xs else 0.0


def market_parts(x, p, trend_p=None):
    tp = trend_p or p.get("_trend") or {}
    parts = {}
    idx = [_trend_c(m.get("vwap_atr"), m.get("ret_atr"), tp) for m in (x.get("idx") or {}).values() if m]
    if idx:
        parts["tape"] = sum(idx) / len(idx)
    if x.get("vix_chg_pct") is not None and not x.get("vix_stale"):
        parts["vix"] = -math.tanh(x["vix_chg_pct"] / p.get("vix_scale_pct", 5.0))
    if x.get("tide_delta") is not None and not x.get("tide_stale"):
        parts["tide"] = math.tanh(x["tide_delta"] / p.get("tide_scale_usd", 5e7))
    return parts


def q_from_f(name, f, cfg):
    """Quality 0..1 from stored flags (re-computable with alternate staleness params)."""
    s = cfg.get("staleness", {})
    p = cfg["components"].get(name, {})
    if not f or f.get("missing"):
        return 0.0
    q = 1.0
    if name in ("flip", "walls"):
        if name == "flip" and not f.get("gf_ok"):
            q *= p.get("q_low_conf_flip", 0.5)
        if f.get("stale"):
            q *= s.get("q_stale_walls", 0.5)
    elif name == "flow":
        if f.get("src") == "uw":
            q *= p.get("q_uw", 0.5)
        if f.get("cls") == "tick":   # WIDECP: Sector watch C/P is tick-test classified (no quotes); core rows never carry cls
            q *= p.get("q_tick", 0.5)
        if f.get("stale"):
            q *= s.get("q_stale_other", 0.5)
    elif name == "market":
        q *= min(1.0, f.get("n_parts", 0) / 3.0)
    elif f.get("stale"):
        q *= s.get("q_stale_other", 0.5)
    return round(q, 3)


def combine(comps, cfg):
    """Weighted sum -> raw float (clamped) and integer -3..+3. Missing/stale inputs shrink toward 0."""
    sc = cfg.get("scale", {})
    mx = sc.get("max_abs", 3)
    num = den = qden = 0.0
    for name, spec in cfg["components"].items():
        if not spec.get("enabled", True) or name not in comps:
            continue
        w = float(spec.get("weight", 1.0))
        c = comps[name]
        num += w * c["q"] * c["c"]
        den += w
        qden += w * c["q"]
    if sc.get("missing", "shrink") == "renormalize":
        s = num / qden if qden else 0.0
    else:
        s = num / den if den else 0.0
    raw = clamp(mx * sc.get("gain", 1.5) * s, -mx, mx)
    score = int(math.copysign(math.floor(abs(raw) + 0.5), raw)) if raw else 0
    return round(raw, 3), score, round(qden / den, 3) if den else 0.0


def rescore(row, cfg):
    """Re-score a logged row under another config (weights, on/off, scales, staleness)."""
    comps = {}
    tp = cfg["components"].get("trend", {})
    for name, spec in cfg["components"].items():
        old = (row.get("comps") or {}).get(name)
        if old is None:
            continue
        p = dict(spec)
        if name == "market":
            p["_trend"] = tp
        comps[name] = {"c": c_from_x(name, old.get("x"), p), "q": q_from_f(name, old.get("f"), cfg)}
    return combine(comps, cfg)


# ------------------------------------------------------------------ build all components for one symbol
def build_components(sym, t, px, atr, bm, walls, flow, mkt, cfg):
    C = cfg["components"]
    st = cfg.get("staleness", {})
    out = {}
    # 1 flip
    gf = (walls or {}).get("gf")
    if gf is not None and atr:
        x = {"gf": gf, "d_atr": (px - gf) / atr}
        f = {"gf_ok": bool(walls.get("gf_ok")), "stale": bool(walls.get("stale")), "age_s": walls.get("age_s"),
             "src": walls.get("src"), "as_of": walls.get("as_of_pt"), "gf_status": walls.get("gf_status")}
        if walls.get("lookahead"):
            f["lookahead"] = True
    else:
        x, f = None, {"missing": True, "why": "no gamma flip" if walls else "no walls for symbol"}
    out["flip"] = {"x": x, "f": f}
    # 2 walls headroom
    cw, pw = (walls or {}).get("cw"), (walls or {}).get("pw")
    if cw is not None and pw is not None and atr:
        x = {"cw": cw, "pw": pw, "up_atr": (cw - px) / atr, "dn_atr": (px - pw) / atr}
        f = {"stale": bool(walls.get("stale")), "age_s": walls.get("age_s"), "src": walls.get("src"), "as_of": walls.get("as_of_pt")}
        if walls.get("lookahead"):
            f["lookahead"] = True
    else:
        x, f = None, {"missing": True, "why": "no call/put wall"}
    out["walls"] = {"x": x, "f": f}
    # 3 volume pressure
    if bm:
        out["volume"] = {"x": {"updn": bm["updn"], "rvol15": bm["rvol15"]},
                         "f": {"stale": bm["last_bar_age_s"] > st.get("bars_stale_s", 180), "bar_age_s": round(bm["last_bar_age_s"]), "n_bars": bm["n_bars"]}}
    else:
        out["volume"] = {"x": None, "f": {"missing": True, "why": "no closed bars yet"}}
    # 4 options flow
    out["flow"] = flow or {"x": None, "f": {"missing": True, "why": "no flow"}}
    # 5 trend
    if bm and bm.get("vwap_atr") is not None:
        out["trend"] = {"x": {"vwap": bm["vwap"], "vwap_atr": bm["vwap_atr"], "ret_atr": bm["ret_atr"]},
                        "f": {"stale": bm["last_bar_age_s"] > st.get("bars_stale_s", 180)}}
    else:
        out["trend"] = {"x": None, "f": {"missing": True, "why": "no bars/ATR"}}
    # 6 market regime
    if mkt:
        parts = market_parts(mkt, C["market"], C["trend"])
        out["market"] = {"x": mkt, "f": {"n_parts": len(parts), "parts": {k: round(v, 3) for k, v in parts.items()}}}
        if not parts:
            out["market"]["f"]["missing"] = True
    else:
        out["market"] = {"x": None, "f": {"missing": True}}
    tp = C.get("trend", {})
    for name, comp in out.items():
        p = dict(C.get(name, {}))
        if name == "market":
            p["_trend"] = tp
        comp["c"] = round(c_from_x(name, comp["x"], p), 4)
        comp["q"] = q_from_f(name, comp["f"], cfg)
        comp["w"] = C.get(name, {}).get("weight", 1.0) if C.get(name, {}).get("enabled", True) else 0.0
        if comp["x"]:
            comp["x"] = {k: (rnd(v, 4) if isinstance(v, float) else v) for k, v in comp["x"].items()}
    return out


def flow_from_row(r, t, cfg):
    """Options flow from the live page row: Alpaca OPRA aggressor 1m C/P (preferred) else UW 5m/15m lean."""
    a = r.get("af60") or {}
    st = cfg.get("staleness", {})
    if a.get("cp") is not None and not a.get("thin", True):
        age = r.get("af_age")
        return {"x": {"cp": a.get("cp"), "thin": False, "net_k": a.get("net_k"), "cov": a.get("cov")},
                "f": {"src": "alpaca-opra-aggressor-1m", "age_s": age, "stale": bool(r.get("af_stale")) or (age is not None and age > st.get("flow_stale_s", 60))}}
    lean = r.get("lean5") or r.get("lean15")
    if lean in ("CALL", "PUT", "FLAT"):
        return {"x": {"uw_lean": lean, "which": "5m" if r.get("lean5") else "15m", "net5_m": r.get("net5_m"), "net15_m": r.get("net15_m")},
                "f": {"src": "uw", "stale": r.get("lean5") is None}}
    return {"x": None, "f": {"missing": True, "why": "no aggressor/UW flow for symbol"}}


def walls_from_row(r):
    W = r.get("walls") or {}
    L = W.get("lv") or {}
    if not L:
        return None
    g = lambda k: (L.get(k) or {}).get("px")
    return {"cw": g("cw"), "pw": g("pw"), "gf": g("gf"), "gf_ok": bool(W.get("gf_ok")), "gf_status": W.get("gf_status"),
            "stale": bool(W.get("stale")), "age_s": W.get("age_s"), "src": W.get("src"), "as_of_pt": W.get("as_of_pt")}


# ------------------------------------------------------------------ walls straight from cache files (backfill)
def walls_from_files():
    files = [("fa-walls-pulse", LIVEPAGE / "data/fa-walls-pulse.json"), ("fa-focus-levels", LATEST / "fa-focus-levels.json"),
             ("fa-levels", LATEST / "fa-levels.json"), ("fa-flow-levels", LATEST / "fa-flow-levels.json")]
    best = {}
    for src, p in files:
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        fa = d.get("as_of_pt") or d.get("as_of")
        if src == "fa-walls-pulse":
            L = d.get("levels") if isinstance(d.get("levels"), dict) and "SPY" not in d else d
        elif src == "fa-focus-levels":
            L = d.get("levels") or {}
        else:
            L = (d.get("payload") or {}).get("levels") if src == "fa-levels" else (d.get("payload") or {})
        if not isinstance(L, dict):
            continue
        for sym, v in L.items():
            if not isinstance(v, dict):
                continue
            lv = v.get("levels") if isinstance(v.get("levels"), dict) else v
            cw, pw, gf = lv.get("call_wall", lv.get("live_call_wall")), lv.get("put_wall", lv.get("live_put_wall")), lv.get("gamma_flip", lv.get("live_gamma_flip"))
            t = iso_t(v.get("as_of")) or _pt_t(v.get("fetched_pt")) or _pt_t(fa) or iso_t(fa)
            if t is None or (cw is None and pw is None and gf is None):
                continue
            try:
                rec = {"cw": None if cw is None else float(cw), "pw": None if pw is None else float(pw), "gf": None if gf is None else float(gf),
                       "gf_status": lv.get("gamma_flip_status") or v.get("gamma_flip_status"), "t": t, "src": src}
            except (TypeError, ValueError):
                continue
            rec["gf_ok"] = rec["gf_status"] == "available"
            if sym not in best or t > best[sym]["t"]:
                best[sym] = rec
    return best


def _pt_t(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %I:%M:%S %p PT", "%Y-%m-%d %I:%M %p PT"):
        try:
            return datetime.strptime(str(s), fmt).replace(tzinfo=PT).timestamp()
        except Exception:
            pass
    return None


# ------------------------------------------------------------------ market regime inputs
def tide_delta(t, window_min):
    """Change in UW market-tide (net call - net put premium) over the last window_min, using only points <= t."""
    try:
        d = json.loads((LATEST / "uw-market-tide.json").read_text())
    except Exception:
        return None, None
    ser = []
    for p in (d.get("payload") or {}).get("series_5m") or []:
        ts = iso_t(p.get("ts"))
        if ts is None or ts > t:
            continue
        ser.append((ts, (p.get("net_call_premium") or 0) - (p.get("net_put_premium") or 0)))
    if len(ser) < 2:
        return None, None
    ser.sort()
    last = ser[-1]
    base = next((v for ts, v in reversed(ser) if ts <= last[0] - window_min * 60), ser[0][1])
    return last[1] - base, t - last[0]


def vix_now(t, cfg, open_ref=None):
    """VIX % change vs prior close (vix-live value; prev_close from vix-agent only if that file is from today),
    else vs the daemon's first VIX reading of the session (open_ref)."""
    try:
        v = json.loads((LATEST / "vix-live.json").read_text())
    except Exception:
        return None
    try:
        a = json.loads((LATEST / "vix-agent.json").read_text())
    except Exception:
        a = {}
    val = (v.get("payload") or {}).get("value")
    vt = iso_t((v.get("payload") or {}).get("index_feed_as_of")) or iso_t(v.get("as_of"))
    at = iso_t(a.get("as_of"))
    today = datetime.fromtimestamp(t, PT).date()
    pc, ref = None, None
    if at and datetime.fromtimestamp(at, PT).date() == today:
        pc, ref = (a.get("payload") or {}).get("prev_close"), "prev_close"
    if not pc and open_ref:
        pc, ref = open_ref, "session_open"
    if not val or not pc:
        return None
    age = t - vt if vt else None
    return {"vix": val, "vix_ref": pc, "vix_ref_kind": ref, "vix_chg_pct": (val / pc - 1) * 100,
            "vix_age_s": round(age) if age is not None else None,
            "vix_stale": bool(age is None or age > cfg.get("staleness", {}).get("vix_stale_s", 900))}


def now_t():
    return time.time()
