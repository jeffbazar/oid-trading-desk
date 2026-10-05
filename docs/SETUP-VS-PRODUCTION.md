# Setup vs production: what is real

Adapted 2026-10-05 (PT) for the durable desk copy at `/workspace/oid-trading-desk`. Research/paper only. Alert-only close language. Zero Robinhood orders.

**Sources:** the live desk at `/workspace/options-intelligence-desk/` (`dashboard/data_sources.py` `FEED_CATALOG`), live caches in `market-data/latest/`, `market-data/QUERY-DEDUP.md`, teammate registry packages (Chart, C&S, Hal, Macro), and the published site https://bold-tulip-nejq.here.now/. No collector was installed, scheduled or run for this document beyond folding registry text. No vendor quota was used for order tools.

**Column meanings**
- **Implemented locally:** what this project (`oid-trading-desk`) does on the box: importer, local server, SQLite review notes, SSE.
- **Published production:** what the live desk's routines actually write, and what the here.now site shows.
- **Proposed / N/A:** in the handbook, prompts or `source-registry.json` but **not deployed**. Every N/A item from the teammate registry is tagged **N/A**.

> **Chart package (folded 2026-10-05).** Feed `chart-daily` / `chart-daily-observations`, owner Chart Bot, rule **CB-DAILY-V1**, routine `chart-daily-refresh` weekdays **2:24 PM PT** after cash close. Universe **RH-TECH-CHIP-20261004** (37; GOOG Class C only; QQQ+SMH benchmarks on lists; SOXX not fetched). Sole writer of post-close daily historicals — does **not** share Rose/Hal live quote pulse. Preserved `data/raw/` snapshots remain immutable evidence of earlier page text.

## 1. By bot

### Chart Bot
| Implemented locally | Published production | Proposed / N/A |
| --- | --- | --- |
| Imports the published chart page. Review notes can attach to chart rows. | `chart-daily` / `chart-daily-observations.json`: Robinhood `get_equity_historicals` **daily bars only** (interval day, bounds regular, adjustment split, start ~2024-01-01Z; ~37 calls/weekday). Outputs under `chart-bot/observations/{SYMBOL}.json`, `chart-bot/latest/`, copy to `market-data/latest/` for the data-sources row; site https://bold-tulip-nejq.here.now/chart.html. Indicators: EMA9/21, SMA50/200 (Shay lineage); SMA20 + ATR14 engineering-only/unvalidated; `total_trend` Bullish/Bearish/Hold/UNAVAILABLE; RS 20-session vs QQQ and SMH. Soft only; never elevates; forecasts null; pattern detector off. Last write 2026-10-04 2:33 PM PT (session 2026-10-02). SKHY/SPCX lack 200 bars = insufficient history, not failure. | **N/A:** Databento · Massive · 5/15/60-min bars · weekly bars · 1-min RVOL · pattern detector · SOXX · forecasts/probabilities · push receiver · changes API |

### Customer/Supplier Bot
| Implemented locally | Published production | Proposed / N/A |
| --- | --- | --- |
| Imports the Map page (companies vs funds, 0 edges). | `supply-chain-identity.json` **identity snapshot only** (`collector: false`). Cadence: on demand / identity seed — **no weekday collector loop**. Path: RH MCP watchlist inventory Tech∪chip (37 after dedupe); `get_sec_filing_index` when filing evidence needed (shared, not second EDGAR). Paper store `supply-chain/supply-chain.db`. Counts: **37 entities / 37 instruments / 0 relationships / 0 claims**. Empty edges = unknown exposure, not failed (softOnly, TTL none — empty ≠ STALE). One Alphabet = **GOOG Class C** only. SKHY and MH ticker-only/unverified legal name. Last write 2026-10-04 4:57 PM PT. Site: data-sources + map.html. Soft color / empty map never opens a seat; profit probabilities null. | **N/A:** Benzinga · FactSet · EIA · Form4 · issuer-IR · policy feed · immutable Postgres · read API · push receiver · FA/UW/X for map · live orders · elevating from business events |

### Peanut (News Alerts)
| Implemented locally | Published production | Proposed / N/A |
| --- | --- | --- |
| Imports `peanut-news.json` + news-archive. | Feed **`peanut-news`**: weekdays **5:30 AM PT** premarket + **every 5 min 6:11 AM–1:56 PM PT**. Universe RH Tech∪chip (~37). Sources: **X news search + public web only** (shared X pool). **No FA / UW / RH quote calls.** Outputs: chat + Rose/Hal alerts; `market-data/latest/peanut-news.json` → Live Book marquee (alerts after prior RTH close) + `news-archive.html`. Quiet scans do not rewrite the file (stamp = last alert). **Lane split:** Peanut = wire/headline; X Summarizer = X-edge — do not double-count. On-disk: feed + `dashboard/peanut_news.py` present; package path `peanut/` **not created yet**. | **N/A:** SEC · IR · Form 4 · policy feed · Benzinga websocket · immutable revisions · read API. Map/identity is **C&S**, not Peanut. |

### Macro Bot
| Implemented locally | Published production | Proposed / N/A |
| --- | --- | --- |
| Imports the macro strip and judgment as published. | **`macro-morning`:** weekday ~**5:45 AM PT** soft-color pack (`daily_macro` + `macro_tech` −2…+2; seven `metric_scores`: 10Y_yield, oil_WTI_Brent, USD_DXY_or_USDJPY, VIX, NQ_vs_ES, credit_HYG_day, event_calendar). Writes chat + Rose/Hal priority and `market-data/latest/macro-morning.json` (~6:14 AM PT file writer). Today's row **2026-10-05 5:50 AM PT**. **`macro-econ-calendar`:** weekday ~5:50 AM PT day card + one-shot post-prints on clear deltas (Google Calendar; MCP may be needsAuth — official-release fallback). **`macro-x-tech`:** hourly weekdays 9:10–3:10 ET; clear deltas only to Jeffrey + Rose + Hal. Sources: public Yahoo quote pages + official BLS/BEA/Census/EIA (no key); X from shared pool. **No FA / UW / RH quote calls.** Soft color / research only; never orders. | **N/A:** Trading Economics frozen consensus · CME FedWatch · Databento · FRED HY/IG OAS as credit (uses HYG day) · 2Y / real yields · 15-min material-change check / three briefs a day · versioned release records · API · push receiver |

### Hal
| Implemented locally | Published production | Proposed / N/A |
| --- | --- | --- |
| Imports Hal rows and lessons. | **`hal-intraday-marks` / `hal-marks`:** RH option marks on held Hal seats every 15 min RTH (`:11/:26/:41/:56` ET). Flat book = idle. **`hal-rh-watch`:** Tech∪chip soft tape `:05/:35` ET — **duplicates** Rose live book pulse (one writer to `rh-quotes` later; flagged). **`fa-levels`:** Hal reads Rose file; any Hal FA burn logs against shared pool. **`hal-x-scan`:** Hal only, every 2h, 11 allowlisted accounts, shared X credits. **`desk-catalysts`:** Hal owns soft calendar; restamped **2026-10-05 ~7:38 AM PT** (30 events); never elevates alone. Authority: research/alerts/paper only — never place/modify/cancel/exercise RH unless Jeffrey separately names a live Agentic ticket. | **N/A:** Databento/Massive bars · 60s quote cadence (design only) · second EDGAR/Form-4 collector (Rose owns) · Benzinga · live RH order path. Handbook FA/UW reader-only stands. |

### Rose (OID)
| Implemented locally | Published production | Proposed / N/A |
| --- | --- | --- |
| Imports Rose rows, watches and closed ledger. | **Primary FA writer** (`fa-levels`: walls pulse + Q5 gated). UW flow/Form 4 when runs pull. **Live RH quotes for elevate/invalidate ≤120 s**. Live RH book pulse both accounts. `support-map` every 15 min. Paper ledger. Site publisher via `dashboard/live_refresh.py` + `publish.sh` (bold-tulip-nejq). | **NOT_BUILT (no writer):** `fa-soft` · `uw-oe` · `rh-rvol`. Rose X Core-8 drafted but **disabled**. |

## 2. By layer

| Layer | Implemented locally | Published production | Proposed / N/A |
| --- | --- | --- | --- |
| Vendor calls | None (public-page import only) | Robinhood, FlashAlpha, UW, X, FRED CSV, Yahoo public, official BLS/BEA/Census/EIA (see API-INVENTORY) | Databento, Massive, Benzinga, FactSet, Trading Economics, CME FedWatch: **N/A** |
| Shared cache | Bridge documented in `data/live-bridge.md` | `market-data/latest/{feed}.json` with `cache_io.py` read-before-pull. Chart = sole post-close daily historicals writer. | Immutable dated snapshot bundles for backtesting: **not built** |
| Publication | Local server on 127.0.0.1:8768 | here.now static site (bold-tulip-nejq), rebuilt by `rebuild.py` / `live_refresh.py` | Push/receiver/outbox, record API: **N/A** |
| Coverage speed | n/a | RH ≤120 s gate at elevate. Hal marks every 15 min. Watch :05/:35 | 5–10 s Rose / 10–30 s Hal / Hal 60s quote cadence: **targets only** |
| Forecasts | null | null (Chart / C&S profit probs null) | Calibrated models: **N/A** until validated |

## 3. Known production gaps (kept visible)
- `fa-soft`, `uw-oe`, `rh-rvol`: NOT_BUILT, no writer.
- Duplicate RH Tech+chip quoting (Rose live book pulse vs Hal `hal-rh-watch`). Fix: one writer to `rh-quotes`; the other reads.
- Chart does not share that live pulse — post-close history only; do not duplicate `get_equity_historicals`.
- Handbook five-bot guide put Map under News; production owner is **Customer/Supplier Bot**.
- Google Calendar MCP may be `needsAuth` (Macro falls back to official calendar).
- GitHub/Origin repo for this project: blocked until Jeffrey connects (README still notes waiting).
