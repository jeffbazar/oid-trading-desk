#!/usr/bin/env python3
"""LIGHT direction score (-3..+3) for the 144 Sector watch names - live daemon (launchd com.oid.desk.score-wide).

Research/log only: never places orders, never calls paid APIs, never subscribes to anything. Reads files the mini already
writes plus the local live page state (127.0.0.1:8791/state.json, wide rows).  stdlib python3 (3.9).

Profile: score-config.json -> profiles.light (own config_version, e.g. light-v1.0-20261021). L.profile_config() copies the
core config and switches off every input not in components_enabled (trend, volume, market), so the SAME calculations,
scales and weights apply and score_lib.combine() divides by the enabled weights only (renormalized to -3..+3):
    s = (1.00*q_t*c_trend + 0.75*q_v*c_volume + 0.75*q_m*c_market) / (1.00 + 0.75 + 0.75)
    raw = clamp(3 * 1.5 * s, -3, 3);  score = raw rounded half away from zero (|raw| >= 0.5 -> 1, >= 1.5 -> 2, >= 2.5 -> 3)
No flip, wall or options-flow inputs (the wide names have none). Market = the core market input unchanged
(SPY/QQQ tape vs VWAP + 15-min return, VIX change, UW market tide).

Inputs per wide name:
  1-min bars  ~/oid-quote/cache/bars-wide/store/live/<SYM>-1m-YYYYMMDD.jsonl  (wide collector tier, closed bars only)
  ATR(14)     daily bars built from ~/oid-quote/cache/bars-wide/store/<SYM>-1m.json (sessions before today)
  rvol norms  ~/oid-quote/cache/bars-wide/live-norms-1m.json (15-min rvol for the volume input)
  price       live page state.json wide row (collector live last), else the last 5 s SIP bar close
  5 s bars    ~/oid-data/archive-wide/volume_5s (peak/trough during holds, own 60/120 s tape) + SPY/QQQ from the core archive
Writes (append-only, ~/oid-data/score):
  changes-wide-YYYYMMDD.jsonl, episodes-wide-YYYYMMDD.jsonl, episodes-wide-buffered-YYYYMMDD.jsonl (comparison-only shadow),
  changes-wide-state.json (restart-safe open holds), latest-wide.json (live page feed, every pass)
Every row carries score_profile=light, profile_version, sector_id, sector.

WIDECP (2026-10-20): second profile "wide_full" (launchd com.oid.desk.score-widefull, OID_SCORE_PROFILE=wide_full,
file tag "widefull": changes-widefull-*, episodes-widefull-*, episodes-widefull-buffered-*, changes-widefull-state.json,
latest-widefull.json). Same six inputs, weights and math as the core score:
  flow  = the Sector watch 1-min aggressor C/P from optflow-wide.json (TICK-TEST classified, trades only), quality x q_tick 0.5
  flip / walls = FlashAlpha levels from ~/oid-live-page/data/fa-walls-wide.json (fetched on surge only, within the FA budget);
          names without levels log flip/walls as missing (shrinks the score toward 0, exactly like a core name without walls)
Both profiles now log the same CONTEXT as the core on every change/episode: C/P 15 s / 1 m (+thin, prints, net), flow lean,
room to the call/put wall in ATR and wall age (when levels exist). The light SCORE still uses only trend, volume and market.
"""
import json, os, resource, sys, time, traceback, urllib.request
from datetime import datetime
from pathlib import Path
import score_lib as L
import score_engine as E
import score_changes as SC
import score_features as SF  # FEATURES 2026-10-21

PROFILE = os.environ.get("OID_SCORE_PROFILE", "light")
CORE_STORE = L.STORE
FORCE_OPEN = os.environ.get("OID_SCORE_FORCE_OPEN") == "1"   # test/benchmark only (with OID_SCORE_OUT pointed at a scratch dir)
BARS_EVERY_S = 20
STAT_S = float(os.environ.get("OID_SCORE_STAT_S", "900"))   # resource/stats log line interval
ATR_MAX_PER_PASS = 40   # spread the once-a-day ATR reads (each ~1.5 MB history file) over the first passes


def log(msg):
    print(f"{datetime.now(L.PT).strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def xp(p):
    return Path(os.path.expanduser(str(p)))


def setup(cfg):
    """-> (P, paths). P = profile settings (core config copy with only the profile's inputs on)."""
    P = L.profile_config(cfg, PROFILE)
    pr = P["profile"]
    paths = {k: xp(pr[k]) for k in ("store", "norms", "v5_dir", "universe", "sectors")}
    L.NORMS = paths["norms"]   # process-local: bar_measures() reads the wide 15-min rvol norms
    return P, paths


def universe(P, paths):
    """-> (symbols, {sym: (sector_id, sector_name)}). WDC/STX/SNDK and SPY/QQQ never scored here."""
    syms = json.loads(paths["universe"].read_text()).get("symbols") or []
    ex = set(P.get("exclude") or []) | set(SC.INDEX)
    sec = {}
    try:
        for g in json.loads(paths["sectors"].read_text()).get("groups") or []:
            for t in g.get("tickers") or []:
                sec.setdefault(t, (g.get("id"), g.get("name")))
    except Exception:
        pass
    return [s for s in syms if s not in ex], sec


def tag_fn(P, sec):
    v, prof = P["config_version"], P["score_profile"]

    def fn(sym):
        g = sec.get(sym) or (None, None)
        return {"score_profile": prof, "profile_version": v, "sector_id": g[0], "sector": g[1]}
    return fn


def enabled(P):
    return {k for k, sp in P["components"].items() if sp.get("enabled", True)}


def score_row(sym, t, px, date, P, bars, atr, mkt, mode, extra=None, walls=None, flow=None):
    """Same make_row/combine as the core; walls/flow are passed only when the profile enables them (light: never).
    Logs only the profile's inputs."""
    on = enabled(P)
    w = walls if ({"flip", "walls"} & on) else None
    f = flow if "flow" in on else None
    row = E.make_row(sym, t, float(px), date, P, bars, atr, w, f, mkt, mode, "fast", extra=extra)
    row["comps"] = {k: c for k, c in row["comps"].items() if k in on}
    row["missing"] = [k for k in row["missing"] if k in on]
    row["stale"] = [k for k in row["stale"] if k in on]
    row["score_profile"] = P["score_profile"]
    return row


def ctx_for(sym, t, px, atr, rvol_1m, ring, extra=None, flow=None, walls=None):
    """Same context as the core change rows. flow = tick-test C/P from the wide live row (WIDECP); walls = on-surge FA levels;
    the momentum engine (ACCEL/DECEL/RESUME) does not run for wide names (logged as state None)."""
    return SC.build_ctx(sym, t, px, atr, flow, rvol_1m, walls, {"state": None, "note": "momentum not tracked for wide names"},
                        ring, extra=extra)


def flow_ctx(wr):
    """WIDECP: context flow block from a wide live-page row (same keys as SC.ctx_live), or None when no C/P."""
    a15, a60 = wr.get("af15") or {}, wr.get("af60") or {}
    if not (a15 or a60):
        return None
    return {"cp_15s": a15.get("cp"), "thin_15s": a15.get("thin"), "net_k_15s": a15.get("net_k"), "n_15s": a15.get("n"),
            "cp_60s": a60.get("cp"), "thin_60s": a60.get("thin"), "net_k_60s": a60.get("net_k"), "n_60s": a60.get("n"),
            "age_s": wr.get("af_age"), "stale": wr.get("af_stale"), "uw_cp": None, "lean5": None, "lean15": None, "ask_lean": None,
            "lean": wr.get("fl"), "cls": "tick", "contracts": wr.get("af_n"), "src": "live_page_wide"}


def score_flow(wr, t, P):
    """WIDECP: score flow input (1-min tick-test C/P) via the core flow_from_row, re-labelled cls=tick."""
    if not (wr.get("af60") or {}).get("cp"):
        return {"x": None, "f": {"missing": True, "why": "no aggressor C/P for symbol"}}
    fl = L.flow_from_row({"af60": wr.get("af60"), "af_age": wr.get("af_age"), "af_stale": wr.get("af_stale")}, t, P)
    if not (fl.get("f") or {}).get("missing"):
        fl["f"]["src"] = "alpaca-opra-tick-1m"
        fl["f"]["cls"] = "tick"
    return fl


def walls_of(wr, t, P):
    """WIDECP: FA levels from the wide live row ("w": cw/pw/gf, ts epoch, gs flip status) -> score/ctx walls dict, else None."""
    w = wr.get("w") or {}
    if not w or w.get("ts") is None or (w.get("cw") is None and w.get("pw") is None and w.get("gf") is None):
        return None
    age = round(t - w["ts"])
    return {"cw": w.get("cw"), "pw": w.get("pw"), "gf": w.get("gf"), "gf_ok": w.get("gs") == "available", "gf_status": w.get("gs"),
            "stale": age > P.get("staleness", {}).get("walls_stale_s", 1200), "age_s": age, "src": "fa-walls-wide", "as_of_pt": w.get("t")}


def synth_1m_as_5s(bars1m, norms_sym):
    """1-min bars -> the 5 s bar layout [t_start, t_end, o, h, l, c, v, rvol_1m] (replay/grading fallback when no
    5 s RTH bars exist). rvol_1m = bar volume / same-minute norm."""
    out = []
    for b in bars1m:
        ts = b.get("ts") if b.get("ts") is not None else L.iso_t(b["t"])
        sl = b.get("slot")
        nv = norms_sym[sl] if (norms_sym and isinstance(sl, int) and 0 <= sl < len(norms_sym)) else None
        out.append([ts, ts + 60, b.get("o"), b.get("h"), b.get("l"), b["c"], b.get("v") or 0,
                    round((b.get("v") or 0) / nv, 3) if nv else None])
    return out


def grading_bars(date, P, paths, syms=None):
    """Bars for peak/trough, held-before-acting and forward checks: wide 5 s RTH bars where present, else 1-min bars
    from the wide store (synthesized to the same layout). -> (bars, {"5s": n, "1m_fallback": n})"""
    bars = SC.load_5s(date, root=paths["v5_dir"])
    nrm = L.norms()
    used = {"5s": 0, "1m_fallback": 0}
    want = syms if syms is not None else list(bars)
    for s in want:
        if bars.get(s):
            used["5s"] += 1
            continue
        b1 = L.load_day_bars(s, date, store=paths["store"])
        if b1:
            bars[s] = synth_1m_as_5s(b1, nrm.get(s))
            used["1m_fallback"] += 1
        L._HIST.pop((str(paths["store"]), s), None)
    return bars, used


# ------------------------------------------------------------------ live daemon
def get_state():
    with urllib.request.urlopen(L.STATE_URL, timeout=5) as r:
        return json.loads(r.read())


def rth_by_clock(now):
    d = datetime.fromtimestamp(now, L.PT)
    return d.weekday() < 5 and (6, 30) <= (d.hour, d.minute) < SC.SESSION_END_HM


class Ctx:
    def __init__(self):
        self.date, self.atr, self.bars, self.bars_t, self.atr_todo = None, {}, {}, 0, []

    def refresh(self, date, syms, now, paths):
        if date != self.date:
            self.date, self.atr, self.bars, self.bars_t = date, {}, {}, 0
            for s in SC.INDEX:
                self.atr[s] = L.daily_atr(s, date)[0]
            self.atr_todo = [s for s in syms]
        if self.atr_todo:   # once a day per name, a few per pass; drop the big history list right after
            for s in self.atr_todo[:ATR_MAX_PER_PASS]:
                self.atr[s] = L.daily_atr(s, date, store=paths["store"])[0]
                L._HIST.pop((str(paths["store"]), s), None)
            self.atr_todo = self.atr_todo[ATR_MAX_PER_PASS:]
        if now - self.bars_t >= BARS_EVERY_S:
            for s in syms:
                if FORCE_OPEN and self.bars.get(s):
                    continue   # test mode: the day's REST bars are loaded once (they never change after hours)
                # live: today's live file only (a few hundred short lines). FORCE_OPEN test mode (after hours): fall back to
                # the day's REST bars from the history file, then drop that big list from memory
                self.bars[s] = L.load_day_bars(s, date, store=paths["store"], hist_fallback=FORCE_OPEN)
                if FORCE_OPEN:
                    L._HIST.pop((str(paths["store"]), s), None)
            for s in SC.INDEX:
                self.bars[s] = L.load_day_bars(s, date)
            self.bars_t = now


def save_json(p, obj):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    tmp.replace(p)


def vix_open_ref(date):
    """VIX session-open reference: the core daemon's (read-only), so both scores use the same market input."""
    try:
        ds = json.loads((L.OUT / "daemon-state.json").read_text())
        return ds.get("vix_open") if ds.get("date") == date else None
    except Exception:
        return None


def main():
    L.OUT.mkdir(parents=True, exist_ok=True)
    ctx = Ctx()
    ring = SC.Ring()
    tails = None
    trk = None
    feat = None  # FEATURES
    cfg_m, uni_m = None, None
    cpu = n = 0
    stat_t, stat_c, resumed = time.time(), 0, None
    own_vix_open = {}
    log(f"score-wide daemon start (profile {PROFILE}, research/log only)" + (" [FORCE_OPEN test mode]" if FORCE_OPEN else ""))
    while True:
        loop_t0 = time.time()
        try:
            m = L.CONFIG.stat().st_mtime
            if m != cfg_m:
                cfg, cfg_m = L.load_config(), m
                P, paths = setup(cfg)
                band = float((P.get("changes") or {}).get("buffer_band", SC.BUFFER_BAND))
                tails = (SC.Tail5s(ring, root=paths["v5_dir"]), SC.Tail5s(ring, only=SC.INDEX))
                uni_m = None
                log(f"profile {P['score_profile']} {P['config_version']} (core {P['core_config_version']}), inputs "
                    f"{sorted(enabled(P))}, change_refresh_s={P['cadence_pt'].get('change_refresh_s')}")
            um = (paths["universe"].stat().st_mtime, paths["sectors"].stat().st_mtime if paths["sectors"].exists() else 0)
            if um != uni_m:
                syms, sec = universe(P, paths)
                uni_m = um
                if trk is None:
                    trk = SC.Tracker(L.OUT, mode="live", band=band, tag=P["profile"].get("file_tag", "wide"), tag_fn=tag_fn(P, sec))
                else:
                    trk.tag_fn = trk.shadow.tag_fn = tag_fn(P, sec)
                log(f"universe {len(syms)} names, {len({v[0] for v in sec.values()})} sectors")
            trk.band = trk.shadow.band = band
            now = time.time()
            date = datetime.fromtimestamp(now, L.PT).strftime("%Y-%m-%d")
            try:
                st = get_state()
                is_open = bool(st.get("market_open"))
            except Exception:
                st, is_open = {}, rth_by_clock(now)
            fs = float(P["cadence_pt"].get("change_refresh_s") or 5)
            if not (is_open or FORCE_OPEN):
                if resumed != date:
                    r = trk.resume(date, now)
                    resumed = date
                    if r:
                        log(f"resumed {r[0]} open holds, closed {r[1]} after gap")
                if trk.ep:
                    k = len(trk.close_all(now, "session_end"))
                    log(f"session end, closed {k} holds (holds total {trk.n_eps}, change rows {trk.n_changes})")
                time.sleep(30)
                continue
            if (P.get("changes") or {}).get("enabled", True) is False or not P["profile"].get("enabled", True):
                time.sleep(30)
                continue
            c0 = time.process_time()
            if resumed != date:
                r = trk.resume(date, now)
                resumed = date
                if r:
                    log(f"resumed {r[0]} open holds, closed {r[1]} after gap")
            new = tails[0].poll(date) + tails[1].poll(date)
            trk.bars(new)
            ctx.refresh(date, syms, now, paths)
            vo = vix_open_ref(date)
            if vo is None:
                if date not in own_vix_open:
                    try:
                        own_vix_open[date] = json.loads((L.LATEST / "vix-live.json").read_text())["payload"]["value"]
                    except Exception:
                        own_vix_open[date] = None
                vo = own_vix_open.get(date)
            mkt = E.market_inputs(now, date, P, ctx.bars, ctx.atr, L.vix_now(now, P, vo))
            wrows = {}
            for g in ((st.get("wide") or {}).get("groups") or []):
                for r in g.get("rows") or []:
                    wrows[r.get("s")] = r
            badge = {}
            fn = trk.tag_fn
            if SF.enabled(cfg):  # FEATURES: score_features snapshots (15 s); light = lite rows
                if feat is None or feat.profile != P["score_profile"]:
                    feat = SF.FeatureSnap(P["score_profile"])
            else:
                feat = None
            for s in syms:
                wr = wrows.get(s) or {}
                lb = ring.last(s, now)
                px = wr.get("p") if ((wr.get("m") == "L" or FORCE_OPEN) and wr.get("p")) else (lb[5] if lb else None)
                if px is None or not ctx.atr.get(s):
                    continue
                rv = wr.get("r") if wr.get("r") is not None else (lb[7] if lb else None)
                wl = walls_of(wr, now, P)
                row = score_row(s, now, px, date, P, ctx.bars.get(s), ctx.atr.get(s), mkt, "live",
                                extra={"rvol_1m": rv, "day_rvol": wr.get("dr"), "chg_pct": wr.get("c")},
                                walls=wl, flow=score_flow(wr, now, P))
                cx = ctx_for(s, now, row["px"], row.get("atr"), rv, ring,
                             extra={"day_rvol": wr.get("dr"), "chg_pct": wr.get("c"), "px_src": "live_last" if wr.get("m") == "L" and wr.get("p") else "5s_close",
                                    "vdir": wr.get("vdir"), "cpdir": wr.get("cpdir")},
                             flow=flow_ctx(wr), walls=wl)
                if feat is not None:
                    try:
                        feat.offer(date, now, s, row["px"], row, cx, P["config_version"], fn)
                    except Exception:
                        pass
                trk.observe(date, now, s, row["px"], row, cx, P["config_version"])
                e = trk.ep.get(s) or {}
                badge[s] = {"s": row["score"], "raw": row["raw"], "cov": row["coverage"], "since_t": round(e["t0"], 1) if e.get("t0") else None,
                            "comps": {k: [c["c"], c["q"], c["w"]] for k, c in row["comps"].items()}, "missing": row["missing"],
                            "sector_id": fn(s).get("sector_id")}
            trk.save(now)
            save_json(L.OUT / f"latest-{P['profile'].get('file_tag', 'wide')}.json", {"as_of": round(now, 1), "as_of_pt": L.pt_str(now), "kind": f"{P['score_profile']}_live",
                                                   "score_profile": P["score_profile"], "config_version": P["config_version"],
                                                   "inputs": sorted(enabled(P)), "refresh_s": fs, "raw_unsmoothed": True,
                                                   "n": len(badge), "by_sym": badge})
            cpu += time.process_time() - c0
            n += 1
            if now - stat_t >= STAT_S:
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024)
                log(f"{trk.n_changes - stat_c} change rows in last {round((now - stat_t) / 60)} min, {n} passes, "
                    f"cpu {round(cpu / max(1, n) * 1000, 1)} ms/pass, open holds {len(trk.ep)}, max RSS {round(rss)} MB"
                    + (f", features {feat.stats()}" if feat is not None else ""))
                stat_t, stat_c, cpu, n = now, trk.n_changes, 0.0, 0
            time.sleep(max(0.2, fs - (time.time() - loop_t0)))
        except Exception as ex:
            log(f"error {type(ex).__name__}: {ex}")
            traceback.print_exc(limit=3)
            time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
