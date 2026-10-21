#!/usr/bin/env python3
"""Single entry point for the Chart Bot scenario layer (CB-SCN-V1). Research/paper only; no orders.

  python3 chart-bot/run_scenarios.py              # compute today's scenarios (as-of = latest real daily bar),
                                                  # score every open prediction, render overlays
  python3 chart-bot/run_scenarios.py --publish    # ...then package + publish the swift-dune Chart page
  python3 chart-bot/run_scenarios.py --date 2026-10-19 --no-png
  python3 chart-bot/run_scenarios.py --status-only  # just refresh statuses in scenarios/latest.json (closed daily/30m bars)
  python3 run_scenarios.py --status-only --scenarios latest.json --bars-30m bars30/ --out status-live.json
                                                  # portable status-only (any machine; stdlib, no network); see SCENARIOS.md

Steps: score_outcomes.score_all -> compute_scenarios.run_live -> score_outcomes.score_all -> render_scenarios (37 PNGs)
       [-> bash dashboard/publish.sh, which re-runs import_snapshot + package_prod_dist; swift-dune only]
Safe to re-run: predictions are append-only and deduped by prediction_id; outcomes.csv is rewritten.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent          # where the modules live (always importable from here)
sys.path.insert(0, str(CODE))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="as-of daily session (default: latest real bar across the universe)")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--status-only", action="store_true",
                    help="only refresh statuses in scenarios/latest.json from the newest closed bars (no new predictions)")
    ap.add_argument("--publish", action="store_true", help="run dashboard/publish.sh after (swift-dune only)")
    import scenario_status as SS
    g = ap.add_argument_group("status-only inputs (portable; only valid with --status-only)")
    SS.add_args(g)
    a = ap.parse_args(argv)
    portable = [k for k in ("scenarios", "bars_30m", "daily_bars", "out", "root", "now") if getattr(a, k) is not None] + \
        (["include_ext_hours"] if a.include_ext_hours else [])
    if portable and not a.status_only:
        ap.error("--" + portable[0].replace("_", "-") + " only applies with --status-only")
    if a.status_only:
        import time
        t = time.time()
        try:
            d = SS.run_from_args(a)
        except (SS.InputError, OSError, json.JSONDecodeError, KeyError) as e:
            print(json.dumps({"status_only": True, "error": f"{type(e).__name__}: {e}"}), file=sys.stderr)
            return 2
        res = {"status_only": True, "refreshed": d["status_refreshed_pt"], "count": d["count"],
               "secs": round(time.time() - t, 2)}
        if "status_inputs" in d or a.out:
            from collections import Counter
            res.update(out=d["_out"], primary_status=dict(Counter(v["primary"]["status"] for v in d["tickers"].values())),
                       tickers_without_bars=d["_no_bars"])
        print(json.dumps(res))
        return 0
    import compute_scenarios as CSN
    import score_outcomes as SO
    SO.score_all()                      # refresh outcomes first so the walk-forward calibrator sees the latest resolutions
    snap = CSN.run_live(a.date)
    card = SO.score_all()
    out = {"run_ts_pt": snap["run_ts_pt"], "asof_bar_date": snap["asof_bar_date"], "bar_source": snap["bar_source"],
           "scenarios": snap["count"], "new_archived": snap["new_archived"], "tickers": snap["tickers"],
           "predictions_total": card.get("predictions"), "resolved": card.get("resolved"),
           "overall_success": (card.get("overall") or {}).get("success_rate"),
           "primary_success": (card.get("primary_only") or {}).get("success_rate")}
    if not a.no_png:
        import render_scenarios as RS
        RS.main(["--run-date", snap["run_date"]])
    SS.set_root(CODE)                   # the full pipeline always works in the code dir (CB_ROOT is status-only)
    SS.build()
    out["latest_json"] = str(CODE / "scenarios" / "latest.json")
    if a.publish:
        r = subprocess.run(["bash", str(ROOT.parent / "dashboard" / "publish.sh")], capture_output=True, text=True)
        out["publish_rc"] = r.returncode
        out["publish_tail"] = (r.stdout + r.stderr)[-600:]
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
