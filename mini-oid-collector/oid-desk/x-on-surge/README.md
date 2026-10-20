# Phase 3 — x_on_surge (on-surge X recent search)

Jeffrey go 2026-10-19. Caps **$5/day**, **$100/month**, automatic stop.

## What it does
- Tails `~/oid-data/archive/surges` for new single-name surges (ETFs skipped; sweeps later).
- Calls `GET /2/tweets/search/recent` (15-min lookback) under `budget_guard`.
- Writes `posts_raw`, `post_query_hits`, `item_filter`, `fetch_log`.
- Starts at EOF (no catch-up of the morning's 160+ surges) unless `--catch-up`.

## Kill switch
```bash
touch ~/oid-data/state/x/STOP          # hard stop (budget_guard.stopped)
# or
# set fetch_enabled=false in ~/oid-data/config/x-on-surge-config.json  (hot-reloaded)
launchctl bootout gui/$(id -u)/com.oid.desk.x-on-surge   # stop process
```
Resume: `rm ~/oid-data/state/x/STOP` and/or set `fetch_enabled=true`, then kickstart.

## Status / logs
- `~/oid-data/state/x/status.json`
- `~/oid-data/state/x/budget.json`
- `~/oid-desk/logs/x-on-surge.log` / `.err`
- Archive: `~/oid-data/archive/{posts_raw,post_query_hits,item_filter,fetch_log}/date=YYYY-MM-DD/`

## Install (from mars → mini)
Copy package to mini, then `~/oid-vns-stage/x-on-surge/install.sh` or the shipped path.
