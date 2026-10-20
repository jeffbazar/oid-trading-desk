#!/bin/bash
# launchd com.oid.desk.score-grade (every 15 min): fill outcomes, then refresh the daily summary. Research only.
cd "$(dirname "$0")" || exit 1
/usr/bin/python3 score_outcomes.py
D=$(date +%Y-%m-%d)
/usr/bin/python3 score_report.py --mode live --date "$D" --daily --quiet 2>/dev/null || true
/usr/bin/python3 score_report.py --mode all --ablate --quiet 2>/dev/null || true
