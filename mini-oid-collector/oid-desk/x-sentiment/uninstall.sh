#!/bin/bash
for J in x-sentiment x-sentiment-scorecard x-sentiment-corr; do
  launchctl bootout "gui/$(id -u)/com.oid.desk.$J" 2>/dev/null || true; rm -f "$HOME/Library/LaunchAgents/com.oid.desk.$J.plist"
done
