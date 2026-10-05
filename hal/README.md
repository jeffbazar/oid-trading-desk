# Hal - Options Trader 2 (OID package)

Research / alerts / paper only. Never place, modify, cancel, or exercise Robinhood orders unless Jeffrey separately names a live Agentic ticket.

**GitHub path:** `hal/` under https://github.com/jeffbazar/oid-trading-desk  
**Local prep:** `/workspace/oid-trading-desk/hal/` (folder drop; no PR unless Jeffrey asks)  
**As of:** 2026-10-05 ~10:27 AM PT

## Package contents

| File | What |
|------|------|
| `README.md` | This overview |
| `registry.json` | Machine-readable feeds + duplicate flag |
| `HAL-CADENCE-V1.md` | Routines / marks / X scan clock |
| `HAL-X-ALLOWLIST.md` | 11 X trader handles + mute rules |
| `FA-READER.md` | Hal as FlashAlpha reader (Rose writes walls) |
| `DESK-CATALYSTS.md` | Soft calendar Hal owns |
| `DUPLICATE-RH-QUOTES.md` | **Open:** Hal RH watch vs Rose live pulse |

## Feeds (`market-data/latest/`)

| Feed | File | Cadence | Notes |
|------|------|---------|-------|
| `hal-intraday-marks` | `hal-marks.json` | Weekday RTH `:11/:26/:41/:56` ET | Marks held Hal seats only. Flat book = idle. |
| `hal-rh-watch` | `hal-rh-watch-pulse.json` | Weekday RTH `:05/:35` ET | Soft tape on Tech ∪ chip play. Never elevates alone. **⚠ duplicates Rose live pulse quotes — see DUPLICATE-RH-QUOTES.md** |
| `hal-x-scan` | `hal-x-scan.json` | Every 2h 8:11 AM–8:11 PM PT | 11 allowlisted X accounts; shared X credits. |
| `desk-catalysts` | `desk-catalysts.json` | Soft calendar (Hal owns) | Soft color only; never elevates alone. |
| FA walls | (read Rose `fa-levels`) | As Rose writes | Hal is FA reader; any Hal burn logs on shared FlashAlpha pool. |

## Duplicate to fix (do not fork)

Rose live book pulse and Hal `:05/:35` watch pulse both quote Tech ∪ chip play. **One writer** should own `rh-quotes`; the other reads. Details in `DUPLICATE-RH-QUOTES.md`.

## Not applicable for Hal

- Databento / Massive bars, 5/15/60-minute / weekly / pattern / forecast collectors
- Deployed 60s quote cadence (design target only; marks stay on the 15-minute clock)
- Second EDGAR / Form-4 / Benzinga collector (Rose / Peanut)
- Live Robinhood order path

## Soft A standing avoids

WDC / STX / SNDK Soft A avoid unless Jeffrey lifts it. Live Google discussion is GOOG (Class C), not GOOGL (Rose may still hold GOOGL paper Soft A — no stack).

## Authority

Paper elevate only when Path A/B + chase/earnings gates clear. Soft color (news, X, walls, chart, macro) never elevates alone. Chat-notify Jeffrey on each new Hal paper seat.
