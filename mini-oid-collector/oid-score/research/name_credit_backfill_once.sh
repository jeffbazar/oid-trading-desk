#!/bin/bash
# One-shot (10/22 00:10 PT, after the X day budget resets): 7-day X backfill of CDS prints, then unloads itself.
/Users/jake/oid-quote/venv/bin/python /Users/jake/oid-score/research/name_credit.py --backfill --x-only
rc=$?
if [ $rc -eq 0 ]; then mv /Users/jake/Library/LaunchAgents/com.oid.desk.name-credit-backfill.plist /Users/jake/oid-data/research/name-credit/ 2>/dev/null; launchctl bootout gui/$(id -u)/com.oid.desk.name-credit-backfill 2>/dev/null; fi
exit $rc
