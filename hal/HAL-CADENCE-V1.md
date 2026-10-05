# Hal (OT2) desk cadence V1 — 2026-09-19

Jeffrey: mirror Rose’s **intraday** data habit (not only open) + scan X for trader insights **through the day including weekends**.

## Rose reference (OID — from Rose 2026-09-19)

Cadence/dedup: `market-data/QUERY-DEDUP.md` (Hal = **read-only** on FA/UW; elevate needs live RH ≤120s).

| Time (ET) | Pass |
|-----------|------|
| 8:15 | Premarket EDGAR + Form-4 |
| 9:45 | First-hour (FA/UW soft + marks) |
| 10:15 | Opening intelligence (full walls) |
| */5 9:00–15:55 | Q5 qualifier (marks; FA gated) |
| 11:45 / 12:45 / 13:45 / 14:45 | Walls pulse (**primary FA writer**) |
| 10:19+10:49 … 15:19+15:49 | NVDA driver watch |
| 15:15 | Afternoon validation |
| 15:50 | Close carry |
| Marks | Q5 + walls + elevate → `dashboard/live_refresh.py` |
| Dashboard every-5m | **disabled** |
| X Core-8 | drafted, **enabled=false** (weekday :48 10–15 ET intent) |

## Hal routines
| Routine | Schedule | Role |
|---------|----------|------|
| Premarket analysis | 8:00 ET weekdays | Brief + Hal seat refresh |
| Market open analysis | 9:35 ET weekdays | Open brief + marks/Greeks/triggers |
| **Hal intraday marks** | :11/:26/:41/:56 ET, 9–15 weekdays | Marks + Greeks + soft triggers; quiet unless material |
| **Hal RH watch** | :05/:35 ET, RTH weekdays | Soft A annotation only. Read Rose `rh-quotes` (TTL 120s). No `get_equity_quotes` for Tech∪chip while that file is fresh. See `RH-QUOTES-READER.md`. |
| Paper book P&L | 4:05 ET weekdays | EOD Hal P&L / close-carry |
| **Hal X trader scan** | 8:11–20:11 PT every 2h, **7 days** | Trader/options X insights; notify only on high signal |

Research / paper only · zero RH execution.
