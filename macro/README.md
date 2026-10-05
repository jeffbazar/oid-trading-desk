# Macro Bot (OID package)

Research / soft color only. Never place, modify, cancel, or exercise orders. Clear deltas go to Jeffrey plus Rose and Hal as soft color for qualifying options and longs — not as tickets.

## Feeds (`market-data/latest/`)

| Feed | File | Cadence | Notes |
|------|------|---------|-------|
| `macro-morning` | `macro-morning.json` | Weekdays ~5:45 AM PT pack; ~6:14 AM PT file mirror | `daily_macro` + `macro_tech` (−2…+2) and seven `metric_scores`. Soft color only. |
| `macro-econ-calendar` | `macro-econ-calendar.json` | Weekdays ~5:50 AM PT day card + one-shot post-prints | Clear-delta prints only to Rose/Hal. |
| `macro-x-tech` | `macro-x-scan.json` | Hourly weekdays 9:10–3:10 ET | Clear deltas only; quiet otherwise. Shared X credits. |

## Seven metric inputs

`10Y_yield`, `oil_WTI_Brent` (front-month futures primary; FRED/EIA spot secondary lag only), `USD_DXY_or_USDJPY`, `VIX`, `NQ_vs_ES`, `credit_HYG_day`, `event_calendar`. Scores are evidence, not addends. Conflict order: event print → 10Y → NQ vs ES → oil day% → VIX → dollar.

## Sources

Public Yahoo quote pages and official BLS / BEA / Census / EIA release pages (no key). Google Calendar for the econ calendar. X from the shared credit pool (same pool as Peanut / Hal).

## Not applicable yet

- Trading Economics frozen consensus
- CME FedWatch
- Databento
- FRED HY/IG OAS as the credit input (use HYG day instead)
- 2Y / real yields
- 15-minute material-change check / three briefs a day
- Versioned release records, API, push receiver
- FlashAlpha, Unusual Whales, Robinhood quote calls

## Authority

Soft color only. Never elevates a seat. Producers cannot open positions.
