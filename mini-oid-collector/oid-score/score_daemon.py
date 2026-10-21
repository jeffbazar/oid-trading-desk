#!/usr/bin/env python3
"""OID composite direction score - live daemon (launchd com.oid.desk.score).

Research/log only: never places orders, never calls paid APIs, zero FlashAlpha calls.
Reads the local live page state (127.0.0.1:8791/state.json) + bar/norm/VIX/tide files + 5 s SIP bars (read-only).
Writes:
  ~/oid-data/score/scores-YYYYMMDD.jsonl   append-only, one row per (symbol, scheduled slot | vol_surge event)  [unchanged]
  ~/oid-data/score/latest.json            badge feed for the private live page (refreshed ~60 s in RTH)          [unchanged]
  ~/oid-data/score/daemon-state.json      slots done / events seen / VIX session-open reference                [unchanged]
  ~/oid-data/score/changes-YYYYMMDD.jsonl  v1.1: one row per score change (fast pass every cadence_pt.change_refresh_s)
  ~/oid-data/score/episodes-YYYYMMDD.jsonl v1.1: one row per ended score hold (start/stop, peak/trough, context)
  ~/oid-data/score/changes-state.json     v1.1: open episodes (restart-safe)
"""
import json, os, sys, time, traceback, urllib.request
from datetime import datetime
import score_lib as L
import score_engine as E
import score_changes as SC
import score_features as SF  # FEATURES 2026-10-21

LOOP_S = 5
FORCE_OPEN = os.environ.get("OID_SCORE_FORCE_OPEN") == "1"   # test/benchmark only (with OID_SCORE_OUT pointed at a scratch dir)


def log(msg):
    print(f"{datetime.now(L.PT).strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def get_state():
    with urllib.request.urlopen(L.STATE_URL, timeout=5) as r:
        return json.loads(r.read())


def load_ds():
    try:
        return json.loads((L.OUT / "daemon-state.json").read_text())
    except Exception:
        return {}


def save_json(p, obj):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    tmp.replace(p)


class Ctx:
    """Per-pass cache of bars/ATR for the session."""

    def __init__(self):
        self.date, self.atr, self.prev_close, self.bars, self.bars_t = None, {}, {}, {}, 0

    def refresh(self, date, syms, now):
        if date != self.date:
            self.date, self.atr, self.prev_close, self.bars = date, {}, {}, {}
        for s in syms:
            if s not in self.atr:
                self.atr[s], self.prev_close[s] = L.daily_atr(s, date)
        if now - self.bars_t >= 20:
            for s in syms:
                self.bars[s] = L.load_day_bars(s, date)
            self.bars_t = now


def universe(state, cfg):
    ex = set(cfg.get("exclude") or [])
    return [r for r in state.get("rows") or [] if r.get("kind") != "ext" and r.get("sym") not in ex and r.get("mode") == "live"]


def score_rows(rows, t, date, cfg, ctx, mkt, trigger, slot=None, events=None):
    out = []
    for r in rows:
        sym, px = r["sym"], r.get("last")
        if px is None:
            continue
        ev = (events or {}).get(sym)
        out.append(E.make_row(sym, t, float(px), date, cfg, ctx.bars.get(sym), ctx.atr.get(sym), L.walls_from_row(r),
                              L.flow_from_row(r, t, cfg), mkt, "live", trigger, slot=slot, event=ev,
                              extra={"rvol_1m": r.get("rvol"), "day_rvol": r.get("day_rvol"), "chg_pct": r.get("chg")}))
    return out


def append(date, rows):
    if not rows:
        return
    p = L.OUT / f"scores-{date.replace('-', '')}.jsonl"
    with p.open("a") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


class Changes:
    """v1.1 fast pass: re-score every change_refresh_s on live price/volume/flow, log changes + episodes (logging only)."""

    def __init__(self):
        self.ring = SC.Ring()
        self.tail = SC.Tail5s(self.ring)
        self.trk = SC.Tracker(L.OUT, mode="live")
        self.feat = None  # FEATURES: score_features snapshots (15 s)
        self.last, self.resumed, self.cpu, self.n, self.stat_t, self.stat_c = 0.0, None, 0.0, 0, time.time(), 0

    def due(self, now, cfg):
        fs = float(cfg["cadence_pt"].get("change_refresh_s") or 0)
        return fs > 0 and (cfg.get("changes") or {}).get("enabled", True) and now - self.last >= fs - 0.25

    def run(self, now, date, rows, cfg, ctx, mkt):
        self.last = now
        c0 = time.process_time()
        self.trk.band = self.trk.shadow.band = float((cfg.get("changes") or {}).get("buffer_band", SC.BUFFER_BAND))
        if self.resumed != date:
            r = self.trk.resume(date, now)
            self.resumed = date
            if r:
                log(f"changes: resumed {r[0]} open episodes, closed {r[1]} after gap")
        self.trk.bars(self.tail.poll(date))
        byr = {r["sym"]: r for r in rows}
        if SF.enabled(cfg):  # FEATURES
            if self.feat is None:
                self.feat = SF.FeatureSnap("core")
        else:
            self.feat = None
        fe = self.feat
        for row in score_rows(rows, now, date, cfg, ctx, mkt, "fast"):
            r = byr[row["sym"]]
            cx = SC.ctx_live(r, row, self.ring, now)
            if fe is not None:
                try:
                    fe.offer(date, now, row["sym"], row["px"], row, cx, cfg["config_version"])
                except Exception:
                    pass
            self.trk.observe(date, now, row["sym"], row["px"], row, cx, cfg["config_version"])
        self.trk.save(now)
        self.cpu += time.process_time() - c0
        self.n += 1
        if now - self.stat_t >= 900:
            c = self.trk.n_changes - self.stat_c
            log(f"changes: {c} change rows in last {round((now - self.stat_t) / 60)} min, {self.n} passes, "
                f"fast-pass cpu {round(self.cpu / max(1, self.n) * 1000, 1)} ms/pass, open episodes {len(self.trk.ep)}"
                + (f", features {self.feat.stats()}" if self.feat is not None else ""))
            self.stat_t, self.stat_c, self.cpu, self.n = now, self.trk.n_changes, 0.0, 0

    def session_end(self, now):
        if self.trk.ep:
            n = len(self.trk.close_all(now, "session_end"))
            log(f"changes: session end, closed {n} episodes (episodes total {self.trk.n_eps}, change rows {self.trk.n_changes})")


def main():
    L.OUT.mkdir(parents=True, exist_ok=True)
    ds = load_ds()
    ctx = Ctx()
    ch = Changes()
    last_badge = 0
    cfg_m = None
    log("score daemon start (research/log only)" + (" [FORCE_OPEN test mode]" if FORCE_OPEN else ""))
    while True:
        try:
            m = L.CONFIG.stat().st_mtime
            if m != cfg_m:
                cfg, cfg_m = L.load_config(), m
                log(f"config {cfg['config_version']} (change_refresh_s={cfg['cadence_pt'].get('change_refresh_s')})")
            now = time.time()
            dt = datetime.fromtimestamp(now, L.PT)
            date = dt.strftime("%Y-%m-%d")
            st = get_state()
            if not (st.get("market_open") or FORCE_OPEN):
                try:
                    if ch.resumed != date:
                        r = ch.trk.resume(date, now)
                        ch.resumed = date
                        if r:
                            log(f"changes: resumed {r[0]} open episodes, closed {r[1]} after gap")
                    ch.session_end(now)
                except Exception as e:
                    log(f"changes session-end error {type(e).__name__}: {e}")
                time.sleep(30)
                continue
            if ds.get("date") != date:
                ds = {"date": date, "slots": [], "events": [], "vix_open": None}
            rows = universe(st, cfg)
            syms = sorted({r["sym"] for r in rows} | {"SPY", "QQQ"})
            ctx.refresh(date, syms, now)
            vix = L.vix_now(now, cfg, ds.get("vix_open"))
            if ds.get("vix_open") is None:
                try:
                    ds["vix_open"] = json.loads((L.LATEST / "vix-live.json").read_text())["payload"]["value"]
                except Exception:
                    pass
            mkt = E.market_inputs(now, date, cfg, ctx.bars, ctx.atr, vix)
            wrote = []
            # scheduled slots (fire within 120 s of the slot)
            for t, hm, trig in E.schedule(cfg, date):
                if hm in ds["slots"] or not (t <= now < t + 120):
                    continue
                out = score_rows(rows, now, date, cfg, ctx, mkt, trig, slot=hm)
                append(date, out)
                ds["slots"].append(hm)
                wrote.append(f"{hm} {trig} {len(out)}")
            # vol_surge events (event-driven, the symbol that surged)
            if cfg["cadence_pt"].get("vol_surge", True):
                for e in (st.get("vol_surge") or {}).get("events") or []:
                    k = f"{e.get('symbol')}|{e.get('engine_pt')}"
                    if k in ds["events"] or not str(e.get("engine_pt") or "").startswith(date):
                        continue
                    ds["events"].append(k)
                    r = next((x for x in rows if x["sym"] == e.get("symbol")), None)
                    if not r:
                        continue
                    ev = {k2: e.get(k2) for k2 in ("engine_pt", "level", "level_price", "dir", "rvol_1m", "vol_60s", "dry_run")}
                    out = score_rows([r], now, date, cfg, ctx, mkt, "vol_surge", slot=dt.strftime("%H:%M"), events={r["sym"]: ev})
                    append(date, out)
                    wrote.append(f"vol_surge {r['sym']}")
            if wrote:
                save_json(L.OUT / "daemon-state.json", ds)
                log("logged: " + "; ".join(wrote))
            # v1.1 change/episode logging (isolated: an error here never blocks slot logging or the badge)
            if ch.due(now, cfg):
                try:
                    ch.run(now, date, rows, cfg, ctx, mkt)
                except Exception as e:
                    log(f"changes error {type(e).__name__}: {e}")
                    traceback.print_exc(limit=3)
            # badge feed (not logged)
            if now - last_badge >= cfg["cadence_pt"].get("badge_refresh_s", 60):
                live = score_rows(rows, now, date, cfg, ctx, mkt, "badge")
                save_json(L.OUT / "latest.json", {"as_of": round(now, 1), "as_of_pt": L.pt_str(now), "config_version": cfg["config_version"],
                                                    "kind": "live_badge", "market": mkt,
                                                    "by_sym": {r["sym"]: E.summary(r) for r in live}})
                last_badge = now
        except Exception as e:
            log(f"error {type(e).__name__}: {e}")
            traceback.print_exc(limit=3)
            time.sleep(15)
        time.sleep(LOOP_S)


if __name__ == "__main__":
    sys.exit(main())
