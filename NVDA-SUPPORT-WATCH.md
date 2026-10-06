# OID universe support / good-low soft watch

Jeffrey preference (2026-09-23): track **key-name** demand dips near dealer **put walls** (gamma flip secondary). Soft color only — never elevate on support alone.

## Coverage
- **Primary (FA walls):** SPY, QQQ, NVDA, TSLA, PLTR, GOOGL, NFLX, META, AMZN, AMD, CBRS, INTC, TSM
- **Extended:** MU, BE, MRVL, NBIS, IREN, CRWV, SNDK, AVGO, ASML — shown when walls exist; else `WALLS_DATA_INSUFFICIENT` (never invent)

## Files
- Soft watch: `paper-trades/universe-support-watch.json` (blotter soft section; multi-symbol)
- Snapshot feed: `market-data/latest/support-map.json`
- Notify: routine **OID support levels watch** (weekdays :05/:20/:35/:50 PT, ~6:05 AM–1:50 PM PT)
- NVDA driver watch still has NVDA-specific support trigger as belt+suspenders

## Good-low band
Within ~0.5% of FA put wall, OR testing put/flip with put held.

Research / paper only — zero RH execution.

## Quote piggyback (Duplicates #2)
- Builder: `dashboard/refresh_support_map.py` — reads fresh `rh-quotes` via `cache_io.piggyback_rh_quotes` first.
- Never writes `rh-quotes` (Rose `refresh_marks.py` / `live_refresh.py` sole writer).
- Smoke: `python3 dashboard/refresh_support_map.py --check-piggyback` · `--dry-run`.
- Notify diff / dedup / journal: `python3 dashboard/support_notify_diff.py` (after a non-dry builder run; no feed writes). Routine prompt: `automations/oid-support-levels-watch-prompt.md`.

## Last support-levels run
- 2026-10-05 1:53 PM PT — AH soft map rebuild; FA walls STALE_CARRY (writer oid-support-levels-watch, age ~3171s); RH quotes live_pull (writer oid-support-levels-watch, age ~1s, ah_ext). nearSupportNow: SPY, NFLX, IREN, GOOG. notify=false. Soft color only.
