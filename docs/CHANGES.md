# Changes in the new site

This is a separate local dashboard for the public OID paper desk. It preserves the source site's data and mandates. It does not change the hosted production site, brokerage state, or trader risk rules.

## Interface and workflow

- **Daily Desk:** A compact operating view of the reported flat/open book, macro context, relevant evidence and source quality.
- **Evidence:** Imported technical/MA observations, watches, events, news, trader claims and source records, with ticker drilldowns and provenance. Production already has Chart and Map pages; their existing observations are imported rather than presented as newly computed analysis.
- **Trade journal:** Reported closed/invalidated/expired paper-ticket rows, filters and export. Account NAV and a cash-flow-adjusted fund return cannot be inferred from cumulative ticket debits.
- **Bot Operations:** Reported current feed ownership and cadence alongside proposed five-role operating prompts and source recommendations. Copied prompts are readable/downloadable; they are not installed bot schedules.
- **Changes:** A visible before/after log backed by `changes.json` and the production audit.

## Data and application layer

Eight allowlisted public resources are preserved and normalized for the local snapshot API. Each import retains source page/cells and clocks rather than silently replacing old market dates with collection time. The local API supplies source data, prompts, registry, changes and CSV export. Manual public-source sync updates the import; it does not become a live brokerage collector.

SQLite stores append-only paper review notes on imported trade/evidence rows independently of source records. A note retains snapshot context; the API rejects a new write against a supplied snapshot that changed after inspection and recognizes identical completed retries. SSE informs connected local clients when a snapshot version or review state changes. SSE's connection and two-second disk check are application health, not a two-second financial-data feed.

## Findings made visible

The imported snapshot has zero open Rose/Hal seats. The old page's open-quote warning and AFTER-HOURS/LIVE label do not establish current exposure or live market connectivity. Marks, macro judgment, chart session, page-build and collection times are distinct. Quota conflicts, calendar age, insufficient chart history, unbuilt feeds and the map's zero evidenced edges remain explicit. Row-level accounting and timing flags identify reported P&L discrepancies, credit-spread signs, excursion times outside holding intervals and an imprecise exit time without changing the source ledger.

No supplier relationship, forecast probability, settlement outcome, account return or execution authority is invented. Existing soft alerts remain soft; review notes never auto-close positions or place orders.

Implementation status for each item is recorded in `changes.json`. Verification and run instructions are in the project README and `API.md`.

## 2026-10-04: Durable box copy and production alignment

- Copied the project into `/workspace/oid-trading-desk` with tests preserved.
- **Chart cadence corrected:** Chart Bot is a weekday collector (Robinhood daily bars, 37-name Tech∪chip play, ~2:24 PM PT after the cash close), not a one-shot history. Audit, change log and the Bot Operations prompt text are updated. Preserved public raw files are unchanged.
- Added `SETUP-VS-PRODUCTION.md` (implemented locally / published production / proposed or N/A, including every teammate N/A item), `API-INVENTORY.md` (connected APIs, who may call what, FlashAlpha Growth shared quota, one X credit pool, Google Calendar and FlashAlpha OAuth `needsAuth`), `QUERY-ARCHITECTURE.md` (mermaid diagram, owner/reader split, duplicate-query risks, archive path) and `HANDBOOK-ERRATA.md` (Edition 1.0 corrections).
- Added `data/live-bridge.md`, which documents how this project archives from the live `market-data/latest/` cache and the eight public here.now resources for backtesting, without redistributing licensed data.
- Recorded Hal's `desk-catalysts` refresh (2026-10-04 9:45 PM PT, 30 events, no FlashAlpha calls) and Peanut's production registry (X/web only, shared X pool).
- No collectors installed, no schedules changed, no vendor quota used, no orders placed. The hosted site is not modified by this project.

## 2026-10-05: Rose owns shared RH equity quotes

- **Resolved** the Hal vs Rose Tech∪chip `get_equity_quotes` duplicate (Jeffrey + Rose, 2026-10-05). Rose (`dashboard/refresh_marks.py`) is the sole writer of `market-data/latest/rh-quotes.json` (writer string `refresh_marks.py`, `owner: rose`, TTL 120s, 38 Tech∪chip+index symbols).
- Hal reads that file for soft tape and wall-distance color. The `:05`/`:35` ET pulse stays Soft A annotation only and must not call `get_equity_quotes` for the union while `rh-quotes` is fresh. Elevate / invalidate still requires live Robinhood ≤120s, never the cache.
- Reader note: `hal/RH-QUOTES-READER.md`. Query diagram, handbook errata, API inventory, setup-vs-production, and the equity-quote registry entry match that contract.
- No collector cutover, no Vercel change, no vendor calls, no orders. Live production collectors remain on `options-intelligence-desk`.

## 2026-10-05: Production cutover and rh-quotes piggyback

- Box production root is `/workspace/oid-trading-desk`. `/workspace/options-intelligence-desk` is a symlink to that tree. Publish slug stays bold-tulip-nejq. swift-dune stays review-only. Note: `CUTOVER-20261005.md`.
- Duplicates #2 closed. `cache_io.piggyback_rh_quotes` feeds `refresh_market_tape.py` (SPY · QQQ · DIA plus RSP / VTV / VUG) and `refresh_support_map.py` (primary + extended book, NVDA on the primary book). `live_refresh.py` is tape cache-first. None of those builders write `rh-quotes`.
- `refresh_marks.py` unwraps a local equity-quotes file and is the only writer (`owner: rose`, TTL 120s). `support_notify_diff.py` emits soft distance lines and does not write quotes.
- `docs_pages.py` / `rebuild.py` render Architecture and Setup with the blotter nav. Those pages are already on bold-tulip. This package does not publish and does not call Robinhood.
- Gitignore keeps new `market-data/latest` vendor dumps, `supply-chain.db`, secrets, `tmp/`, backup trees, and `paper-trades/` out of the PR. The live paper ledger is omitted.
