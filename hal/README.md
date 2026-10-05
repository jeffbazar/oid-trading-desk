# Hal - Options Trader 2 (OID package)

Research / alerts / paper only. Never place, modify, cancel, or exercise Robinhood orders unless Jeffrey separately names a live Agentic ticket.

**GitHub path:** `hal/` under https://github.com/jeffbazar/oid-trading-desk  
**Local prep:** `/workspace/oid-trading-desk/hal/` (folder drop; live collectors stay on the bot box)  
**As of:** 2026-10-05 (Jeffrey + Rose: Rose owns `rh-quotes`)

## Package contents

| File | What |
|------|------|
| `README.md` | This overview |
| `registry.json` | Machine-readable feeds; `rh-quotes` owner Rose, Hal reader |
| `HAL-CADENCE-V1.md` | Routines / marks / X scan clock |
| `HAL-X-ALLOWLIST.md` | 11 X trader handles + mute rules |
| `FA-READER.md` | Hal as FlashAlpha reader (Rose writes walls) |
| `RH-QUOTES-READER.md` | Hal reads Rose `rh-quotes` (TTL 120s). Soft A annotate only |
| `DESK-CATALYSTS.md` | Soft calendar Hal owns |
| `DUPLICATE-RH-QUOTES.md` | **Resolved 2026-10-05:** Rose sole writer; Hal reads |

## Feeds (`market-data/latest/`)

| Feed | File | Cadence | Notes |
|------|------|---------|-------|
| `hal-intraday-marks` | `hal-marks.json` | Weekday RTH `:11/:26/:41/:56` ET | Marks held Hal seats only. Flat book = idle. |
| `rh-quotes` | `rh-quotes.json` | Rose `refresh_marks.py`, TTL 120s | **Read only.** Owner Rose. Tech∪chip + indexes (38). Soft tape / wall-distance color. See `RH-QUOTES-READER.md`. |
| `hal-rh-watch` | `hal-rh-watch-pulse.json` | Weekday RTH `:05/:35` ET | Soft A structure annotation on Rose quotes. Never elevates alone. **No `get_equity_quotes` for the Tech∪chip union when `rh-quotes` is fresh.** |
| `hal-x-scan` | `hal-x-scan.json` | Every 2h 8:11 AM–8:11 PM PT | 11 allowlisted X accounts; shared X credits. |
| `desk-catalysts` | `desk-catalysts.json` | Soft calendar (Hal owns) | Soft color only; never elevates alone. |
| FA walls | (read Rose `fa-levels`) | As Rose writes | Hal is FA reader; any Hal burn logs on shared FlashAlpha pool. |

## RH quotes (resolved)

Rose (`dashboard/refresh_marks.py`) is the **sole writer** of `market-data/latest/rh-quotes.json` (`owner: rose`, writer string `refresh_marks.py`, TTL 120s). Hal **reads** it for Tech∪chip soft tape and wall-distance color. The `:05`/`:35` ET pulse keeps Soft A annotation and must not call Robinhood `get_equity_quotes` for that union while the file is fresh. Miss or stale: wait for Rose, or one-shot only the missing symbols. Elevate / invalidate still needs a live Robinhood quote ≤120s, never this cache. Details in `RH-QUOTES-READER.md` and `DUPLICATE-RH-QUOTES.md`.

## Not applicable for Hal

- Databento / Massive bars, 5/15/60-minute / weekly / pattern / forecast collectors
- Deployed 60s quote cadence (design target only; marks stay on the 15-minute clock)
- Second EDGAR / Form-4 / Benzinga collector (Rose / Peanut)
- Live Robinhood order path

## Soft A standing avoids

WDC / STX / SNDK Soft A avoid unless Jeffrey lifts it. Live Google discussion is GOOG (Class C), not GOOGL (Rose may still hold GOOGL paper Soft A — no stack).

## Authority

Paper elevate only when Path A/B + chase/earnings gates clear. Soft color (news, X, walls, chart, macro) never elevates alone. Chat-notify Jeffrey on each new Hal paper seat.
