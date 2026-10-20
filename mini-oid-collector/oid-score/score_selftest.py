#!/usr/bin/env python3
"""Dry self-test of the live path (no RTH needed): one pass over the current live-page state, nothing written
except to OID_SCORE_OUT (defaults to a temp dir)."""
import json, os, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("OID_SCORE_OUT", tempfile.mkdtemp(prefix="oid-score-test-"))
import score_lib as L, score_engine as E, score_daemon as D
cfg = L.load_config()
st = D.get_state()
rows = D.universe(st, cfg)
date = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y-%m-%d")
ctx = D.Ctx()
now = time.time()
ctx.refresh(date, sorted({r["sym"] for r in rows} | {"SPY", "QQQ"}), now)
vix = L.vix_now(now, cfg)
mkt = E.market_inputs(now, date, cfg, ctx.bars, ctx.atr, vix)
out = D.score_rows(rows, now, date, cfg, ctx, mkt, "selftest")
from collections import Counter
print("rows", len(out), "dist", dict(sorted(Counter(r["score"] for r in out).items())))
print("market", json.dumps({k: v for k, v in mkt.items() if k != "idx"}), "idx", mkt.get("idx"))
for r in out:
    if r["sym"] in ("NVDA", "META", "QQQ", "AMD"):
        print(r["sym"], r["score"], r["raw"], "cov", r["coverage"], "stale", r["stale"], "missing", r["missing"],
              {k: (c["c"], c["q"]) for k, c in r["comps"].items()})
