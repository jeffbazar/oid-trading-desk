# Chart Bot (`chart-daily` / CB-DAILY-V1)

Soft observation only. Never elevates. Never opens a seat. Forecasts stay null until a registered validated model exists.

## Cadence

- Routine: `chart-daily-refresh`
- Weekdays **2:24 PM PT** after the cash close
- Weekend / holiday: keep the last completed session (not an outage)

## Universe

- Id: `RH-TECH-CHIP-20261004`
- Robinhood Tech ∪ chip play — **37** names
- **GOOG** Class C only (no GOOGL)
- Benchmarks: **QQQ** and **SMH** (both on the lists)
- **SOXX** not fetched — N/A

## Sole writer (do not duplicate)

Robinhood MCP `get_equity_historicals`:

- interval: day
- bounds: regular
- adjustment: split
- start: ~2024-01-01Z
- ≈ one call per symbol per weekday (~37/day)

Chart does **not** share the Rose / Hal live quote pulse.

## Outputs

| Path | Role |
|------|------|
| `chart-bot/observations/{SYMBOL}.json` | Per-name observation |
| `chart-bot/latest/chart-daily-observations.json` | Rollup |
| `market-data/latest/chart-daily-observations.json` | Data-sources copy |
| https://bold-tulip-nejq.here.now/chart.html | Public Chart page |

Live desk compute is this tree. `/workspace/options-intelligence-desk/chart-bot/` reaches it through the 2026-10-05 symlink (`CUTOVER-20261005.md`).

## Indicators

- EMA9 / EMA21, SMA50 / SMA200 — Shay lineage (`refresh_shay_ma_levels`)
- SMA20, ATR14 — engineering only, unvalidated as signals
- `total_trend`: Bullish / Bearish / Hold / UNAVAILABLE
- RS: 20-session close-to-close vs QQQ and SMH (shared dates, no forward-fill)

## Material handoff (Jeffrey 2026-10-05)

After each successful weekday refresh, forward **material** changes to Rose and Hal:

- trend flips among Bullish / Bearish / Hold / UNAVAILABLE
- newly insufficient history

Quiet if nothing material changed. Soft color only — never a ticket.

## Not applicable yet

Databento · Massive · 5/15/60-min bars · weekly bars · 1-min RVOL · pattern detector · SOXX · forecasts / probabilities · push receiver · changes API

## Status snapshot (last write)

- Calculated: 2026-10-04 2:33 PM PT
- Last completed session: **2026-10-02**
- Counts: Bullish 24 · Bearish 6 · Hold 5 · UNAVAILABLE 2 (SKHY, SPCX — insufficient 200-bar history, not a failed pull)

See also `feed-registry.json` in this folder and desk docs `QUERY-ARCHITECTURE.md`, `API-INVENTORY.md`, `SETUP-VS-PRODUCTION.md`.
