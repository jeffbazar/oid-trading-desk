# API inventory: what the desk actually uses

As of 2026-10-05 (PT). Research/paper only. **No `place_*`, `cancel_*` or `exercise_*` tool is called by any desk bot.** MCP status comes from the box's dynamic tool catalog. Quota figures come from `market-data/latest/api-quotas.json` and `x-spend.json`. No FlashAlpha `get_account` call was spent for this document.

## Summary

| API / MCP | Namespace / access | Status | Plan / budget | Who may call | Who reads the file instead |
| --- | --- | --- | --- | --- | --- |
| Robinhood | `user-robinhood-trading` (MCP) | ready | Broker data, no metered quota recorded | **Rose:** sole writer of `rh-quotes` via `dashboard/refresh_marks.py` (writer string `refresh_marks.py`, `owner: rose`, TTL 120s, 38 Tech∪chip+index symbols, scan/soft tape). Also live quotes at elevate/invalidate (≤120 s, never from `rh-quotes`), live book pulse (both accounts), `support-map` quotes, `live_refresh.py` marks and tape, Form-4/EDGAR path ownership. **Hal:** reads `rh-quotes` for Tech∪chip soft tape (`read_fresh`); `hal-rh-watch` at `:05`/`:35` ET is Soft A annotation only — **no `get_equity_quotes` for that union when `rh-quotes` is fresh** (miss/stale: wait, or one-shot only missing symbols). `hal-intraday-marks` on held seats every 15 min RTH (`:11/:26/:41/:56` ET; flat = idle). **Chart Bot:** sole `get_equity_historicals` daily-bar pull (interval day, bounds regular, adjustment split, start ~2024-01-01Z; one call/symbol/weekday ≈37/day; do not duplicate elsewhere). **C&S:** RH MCP watchlist inventory Tech∪chip (37 after dedupe); `get_sec_filing_index` when filing evidence needed (shared path, not second EDGAR). **Macro: no RH quote calls.** | Macro, Peanut (no RH calls). Hal reads Rose `fa-levels`, `rh-quotes`, and other shared files rather than re-pulling FA/UW or fresh Tech∪chip equity quotes. |
| FlashAlpha (keyed) | `user-flashalpha-keyed`, `user-flashalpha-api` | ready | **Growth plan, one shared hard daily limit** (2,500/day per last `get_account`, verified 2026-10-01). Treat remaining as scarce. Non-Rose callers get a working budget of about 5 calls/day, logged on Rose | **Rose only** (walls pulse, Q5 gated, opening/FH once-if-miss, NVDA-driver if miss). Hal **reads** `fa-levels`; any Hal FA burn logs against the shared pool. Chart / Macro / C&S / Peanut: **none** | Hal (reader-only per handbook), Macro (none), Chart (none), C&S (none) |
| FlashAlpha (OAuth) | `user-flashalpha` | **needsAuth** | Same account family. Do not assume it is usable | none until connected | n/a |
| Unusual Whales | `user-unusual-whales` | ready | Plan quota not recorded in `api-quotas.json` | **Rose only**, when runs pull (`get_flow_alerts`, `get_market_tide` + `get_flow_per_strike`, `get_insider_transactions` for Form 4). Chart / Macro / C&S / Hal: no UW writer path | Hal (read `uw-*` files) |
| X API | `user-X` | ready | **One credit pool** across Hal, Macro, X Summarizer, Startup Hunter and Peanut. About **$55.72 left** per Hal's note. | Hal `hal-x-scan` every 2h (11 allowlisted accounts) · Macro `macro-x-tech` hourly 9:10–3:10 ET weekdays (clear deltas only) · Peanut 5:30 AM + 5-min scans · X Summarizer · Startup Hunter · Rose `x-core8` **disabled**. Chart / C&S: no X | Everyone else reads `hal-x-scan.json` / `peanut-news.json` / Macro chat notes |
| FRED public CSV | HTTPS, no key | ok | None | `refresh_market_tape.py` / `live_refresh.py` (`fred-hy-oas`, `fred-ig-oas`, DGS10, DCOIL* secondary) | Macro does **not** use FRED HY/IG as its credit input (uses HYG day) |
| Yahoo public pages | HTTPS, no key | ok for Macro | None. Note: `live_refresh` macro-spot avoids Yahoo quotes (egress 429) but uses Yahoo chart history for valuation proxy | **Macro Bot** morning pack + econ/calendar context; `fidelity-three` valuation history | — |
| Official BLS / BEA / Census / EIA / Fed | HTTPS, no key | ok | None | **Macro Bot** (release values, event calendar). C&S: EIA is **N/A / not_entitled** for map | — |
| SEC EDGAR (public) | HTTPS | via Rose | None | Rose `premarket-edgar` 08:15 ET (Form 4 universe owner). C&S may use RH `get_sec_filing_index` for evidenced edges only (shared, not a second collector). **Peanut / Hal: N/A** as Form-4 writers | — |
| Google Calendar | `user-Google-calendar` | **needsAuth** in this box session | — | Macro `macro-econ-calendar` ~5:50 AM PT reads Jeffrey's calendar. If unavailable, Macro falls back to official-release calendar | — |
| here.now publish | `dashboard/publish.sh` → here.now skill, slug `bold-tulip-nejq` | ok | — | **Only `dashboard/live_refresh.py` / Rose** (single publisher loop). Chart page + data-sources + map rebuild via `rebuild.py` then publish | All bots read the published pages. This project imports eight public resources read-only |
| GitHub / Origin | `cursor-github`, `cursor-origin` | listed | — | **Blocked:** no repo is created for this project until Jeffrey connects/approves | — |

## Chart Bot API contract (CB-DAILY-V1)
- Tool: Robinhood `get_equity_historicals` only.
- Params: interval `day`, bounds `regular`, adjustment `split`, start ~`2024-01-01Z`.
- Cadence: weekdays 2:24 PM PT after cash close (`chart-daily-refresh`); ≈ one call per symbol per weekday (~37/day). Weekend/holiday keep last completed session.
- Outputs: `chart-bot/observations/{SYMBOL}.json` · `chart-bot/latest/chart-daily-observations.json` · copied to `market-data/latest/chart-daily-observations.json` · site https://bold-tulip-nejq.here.now/chart.html
- Indicators: EMA9/21, SMA50/200 (Shay lineage); SMA20 + ATR14 engineering only / unvalidated; `total_trend` Bullish/Bearish/Hold/UNAVAILABLE; RS 20-session vs QQQ and SMH.
- Soft only. Never elevates. Forecasts null. Pattern detector off.

## Peanut API contract
- Sources: X news search + public web only (shared X credit pool). **No FA, UW, or RH quote calls.**
- Cadence: weekdays 5:30 AM PT premarket + every 5 min 6:11 AM–1:56 PM PT.
- Universe: RH Tech ∪ chip play (~37).
- Outputs: chat + Rose/Hal alerts; `market-data/latest/peanut-news.json` → Live Book marquee + `news-archive.html`.
- **Lane split:** Peanut owns wire/headline; X Summarizer owns X-edge — do not double-count.
- **N/A:** SEC, IR, Form 4, policy feed, Benzinga websocket, immutable revisions, read API.
- Package path `peanut/` not yet on disk; production logic is `dashboard/peanut_news.py` + the latest feed file.

## Not connected / N/A (do not reference as live)
Databento · Massive · Benzinga · FactSet · Trading Economics (frozen consensus) · CME FedWatch · licensed cash-Treasury/TIPS yields · licensed relationship data · Chart intraday (5/15/60-min) / weekly bars / 1-min RVOL / pattern detector / SOXX / forecasts · Chart/C&S/Macro/Hal push receiver · changes API · Hal 60s quote cadence (design only) · Macro 15-min material-change / three briefs/day / versioned release records / Macro API · C&S immutable Postgres / read API / Form4·issuer-IR·policy feeds.

## Rules that go with every call
1. **Read before pull.** `python3 /workspace/options-intelligence-desk/market-data/cache_io.py get <feed>`. Call the vendor only on a miss, and only if you are the owner for that feed (QUERY-DEDUP owner matrix).
2. **Write back** with `write_feed(...)`, including error records (`error` set, never presented as fresh).
3. **Elevate / invalidate / liquidity gates need live RH**, never cache (≤120 s). `rh-quotes` (TTL 120s) is scan and soft-tape color only. Rose is the sole writer; Hal reads it.
4. **FA:** log every non-Rose call (bot, tool, symbol, PT time) in `api-quotas.json` notes. When the quota is 0, write STALE_CARRY and do not retry.
5. **X:** spend is pooled. Each bot keeps to its own cadence; Hal updates `x-spend.json` after scans.
6. **No order tools.** Zero RH orders. Alerts / research / paper only. Hal never places/modifies/cancels/exercises RH unless Jeffrey separately names a live Agentic ticket.
