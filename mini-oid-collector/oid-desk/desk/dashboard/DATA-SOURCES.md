# OID Live Book · Data sources

**Site:** https://bold-tulip.here.now/ · tab **Data sources**  
**Updated:** 2026-10-05  
**Mandate:** Research / paper only · Zero live execution

## Query limits & cost (top bar)

Written to `market-data/latest/api-quotas.json` (Hal or Rose on refresh).

| Vendor | What we show |
|--------|--------------|
| FlashAlpha | plan · used/limit · remaining calls/day |
| X API | credit balance ($) + **today / week / month / total spend** (`x-spend.json`) |
| Unusual Whales | no usage API (NO_METER) |
| Robinhood | research quotes — no $ meter |

## What this page shows

Status of every feed Rose (OID) and Hal (OT2) track, rebuilt into `data-sources.html` on each `rebuild.py` run.

| Column | Meaning |
|--------|---------|
| Source | Vendor / system (FlashAlpha, UW, RH, X, EDGAR, Soft, Dashboard, Hal) |
| Feed | Cache key under `market-data/latest/{feed}.json` (or soft stamp) |
| Owner | Rose · Hal · shared |
| Cadence | Who may pull / when (from QUERY-DEDUP + HAL-CADENCE-V1) |
| TTL | Freshness window (seconds) from QUERY-DEDUP / `cache_io.DEFAULT_TTLS` |
| Last success (PT) | `as_of_pt` from latest cache (or ledger / close-triggers stamp) |
| Status | **OK** within TTL · **STALE** past TTL in RTH · **CARRY** last write held outside RTH (weekend/closed) · **ERROR** `error` set · **NEVER** no file · **DISABLED** routine off |
| Notes | Role / constraints |

## Catalog (Rose + Hal)

| Feed | Owner | TTL | Cadence (summary) |
|------|-------|----:|-------------------|
| `fa-levels` | Rose | 600 | Walls pulse primary; Q5 gated |
| `fa-flow-levels` | Rose | 600 | Sibling of fa-levels when stored separately |
| `fa-soft` | Rose | 1800 | Piggyback after levels |
| `uw-flow-alerts` | Rose | 900 | Near-wall / soft catalyst |
| `uw-net-prem` | Rose | 900 | Near-wall / session wrap |
| `uw-oe` | Rose | 1800 | Near-wall notify (dark pool) |
| `uw-form4` | Rose | 21600 | Premarket + afternoon forced |
| `rh-quotes` | shared | 120 | Scan color + dashboard session/day%; elevate always live |
| `rh-option-marks` | shared | 300 | Q5 + walls + Hal intraday marks |
| `rh-rvol` | Rose | 1800 | Near-wall soft |
| `x-core8` | Rose | — | Drafted weekday `:48` 10–15 ET — **enabled=false** |
| `hal-x-scan` | Hal | 7200 | 8:11–20:11 PT / 2h · 7 days (HAL-X-ALLOWLIST) |
| `live-refresh` | shared | 300 | Piggyback after elevate / invalidate / walls / Hal marks |
| `hal-intraday-marks` | Hal | 900 | `:11/:26/:41/:56` ET, 9–15 weekdays |
| `premarket-edgar` | Rose | 21600 | 8:15 ET RH EDGAR overnight sweep (`premarket-edgar.json`; empty OK restamps) |
| `close-triggers` | shared | 600 | After marks — alerts only, never auto-close |
| `book-triggers` | Rose | 600 | BOOK_TP / BOOK_GIVEBACK soft flags |
| `paper-open` | shared | 0 | On change |
| `api-quotas` | shared | 3600 | FA daily + X credits top bar |
| `x-spend` | Hal | 7200 | X $ today/week/month/total since tracking |
| `market-tape` | shared | 300 | SPY·QQQ·DIA strip; piggyback live_refresh |
| `shay-semi-watch` | Rose | 300 | Shay 2027-PE equity soft watch; piggyback equity quotes |
| `shay-ma-levels` | Rose | 300 | Shay key-levels MA soft watch; spots piggyback; MAs via refresh_shay_ma_levels.py |
| `fred-hy-oas` | shared | 86400 | FRED HY OAS BAMLH0A0HYM2 (public CSV) |
| `fred-ig-oas` | shared | 86400 | FRED IG OAS BAMLC0A0CM (public CSV) |
| `macro-spot` | shared | 300 | 10Y·VIX·WTI·Brent strip; FRED + RH VIX |
| `fidelity-three` | shared | 1800 | RSP−SPY · credit OAS · VTV/VUG proxies |
| `chart-daily` | Chart Bot | — | Weekdays 2:24 PM PT CB-DAILY-V1; sole post-close daily historicals |
| `supply-chain-identity` | Customer/Supplier Bot | — | Identity seed on demand; empty edges ≠ STALE |
| `macro-morning` | Macro Bot | 86400 | Weekday ~5:45 AM PT soft-color pack |
| `peanut-news` | Peanut | — | 5:30a + 5-min 6:11a–1:56p PT; wire/headline lane |
| `desk-catalysts` | Hal | 21600 | Soft calendar; never elevates alone |

**Hal is read-only** on FA/UW cache (QUERY-DEDUP). Elevate / PAPER_CANDIDATE always needs live RH ≤120s.

## Sources of truth

- TTLs / owner matrix: `market-data/QUERY-DEDUP.md` · `market-data/cache_io.py`
- Hal cadence: `HAL-CADENCE-V1.md`
- Hal X allowlist: `HAL-X-ALLOWLIST.md`
- Live files: `market-data/latest/*.json` + `_index.json`
- Soft stamps: `tmp/close-triggers-last.json` · `paper-trades/trades.json` meta

## Rebuild

```bash
python3 /workspace/options-intelligence-desk/dashboard/rebuild.py
# writes index.html + data-sources.html
```
