# OID Dashboard Live Refresh (every ~5 min RTH)

**Schedule:** Mon–Fri, PT cron `*/5 6-16` (= RTH 09:30–16:00 ET via 6–12 PT **plus** AH 16:00–19:55 ET via 13–16 PT). Draft/disabled — piggyback Q5 + walls-pulse remain primary. Extended 2026-09-22 for AH coverage.

**Goal:** Keep https://swift-dune-cs3e.here.now/ marks fresh vs paper cost basis. Options **and** equities every cycle.

## Prompt body

You are Rose’s OID dashboard live-refresh. Research / paper only. NEVER place, modify, or cancel Robinhood orders. Quotes only.

1. Read `/workspace/options-intelligence-desk/paper-trades/trades.json`. If open seats = 0 and no Leopold watches, exit quietly.
2. Emit ids: `python3 /workspace/options-intelligence-desk/dashboard/live_refresh.py --emit-ids`.
3. REQUIRED: Robinhood MCP option quotes for those instrument_ids → `/workspace/options-intelligence-desk/tmp/oid-live-quotes.json`.
4. Emit symbols: `python3 /workspace/oid-trading-desk/dashboard/live_refresh.py --emit-symbols`.
5. REQUIRED every cycle: Robinhood MCP equity quotes for those symbols → `/workspace/options-intelligence-desk/tmp/oid-live-equity.json` (batch >20 OK if closes omit).
6. `python3 /workspace/oid-trading-desk/dashboard/live_refresh.py --quotes-file /workspace/oid-trading-desk/tmp/oid-live-quotes.json --equity-quotes-file /workspace/oid-trading-desk/tmp/oid-live-equity.json --publish` (use these exact absolute paths; NEVER /workspace/tmp/ — it holds stale 9/21 leftovers. live_refresh now refuses files >20 min old and refresh_marks refuses quotes whose trade date is not current, exit 3)
7. After publish, check critical feeds only: `rh-quotes`, `rh-option-marks`, `market-tape`. Soft/never feeds (uw-form4, fa-soft, uw-oe, uw-flow-alerts, fa-flow-levels, x-core8) must NOT page.
8. If any critical feed is still STALE past TTL after this full refresh: WakeParent / notify Rose once with feeds + ages + blotter link. Dedupe same STALE set within the clock hour. Otherwise quiet unless seats changed or book P&L moved a lot.
9. Cost basis = entryAsk ×100. Label quote age / delayed. Zero execution.
