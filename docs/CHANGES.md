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
- The box `.gitignore` excludes `secrets/`, `*.db` (including `supply-chain.db`), `market-data/latest/rh-quotes.json`, and `tmp/`. This PR does not add vendor `latest/` payloads, `paper-trades/trades.json`, or cutover backup trees.

## 2026-10-21: Scaling strategy review

- Added `docs/SCALING-STRATEGY-20261021.md`: a strategy for scaling the discretionary same-day options book with bots (staged automation with measured gates, a deterministic execution and risk layer, the option-leg label and model ladder, the archive and decision-capture plan, ranked data sources, registered setups, UI changes, and an expanded bot roster), with a 30-day and 90-day plan and the owner decisions it needs.
- Added `docs/strategy-2026-10-21/` with the evidence trail: desk, research and UI maps, the vendor fact sheet with corrections, five lens proposals, the judge summary, the synthesis draft and the verification log.
- Review only. No bot, schedule, feed, order authority or vendor plan was changed. Three vendor claims were corrected by the fact-check: Robinhood's agentic account supports single-leg options and its agreement authorizes agent orders; Alpaca retired the pattern-day-trader rule on 2026-06-04; FlashAlpha Basic is 250 requests a day.
- Added section 2.5 to the strategy report: the owner's live fills for 2026-10-20 (eight round trips, nearest-weekly calls, 100 to 400 contracts, holds of 87 seconds to 13 minutes) and the six plan adjustments they imply (nearest-weekly contracts, sizing as a fraction of the real ticket, capacity measurement, per-venue fees, a continuation re-entry setup, automatic fill capture).

## 2026-10-21: Model and hardware plan, UI mockups

- Added `docs/MODEL-AND-HARDWARE-PLAN-20261021.md`: for each bot, the open-weight model and the proprietary model, which is primary and which is the fallback, and which machine it runs on across the hardware already owned (the 64 GB Mac mini, four 8 GB Mac minis, and the 128 GB Mac as a Phase 2 addition). Includes the memory budget at the macOS default wired limit, the serving stack and its determinism limits, monthly cost with the actual cache rates, the gold-set and promotion rules for model swaps, a fallback matrix, and a first-week measurement checklist.
- Added `docs/strategy-2026-10-21/model-plan-sources.md` (eight checked claims, four corrected) and `docs/strategy-2026-10-21/model-plan/` (the research sheets and draft plans behind it).
- Added `docs/strategy-2026-10-21/mockups/`: the three UI mockups from section 9 of the strategy report as design artboards.
- Review only. No model was deployed, no daemon installed, no API key created, no order authority changed.
