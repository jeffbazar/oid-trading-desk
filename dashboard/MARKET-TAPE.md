# OID Live Book · Market overview strip (Fidelity desert-island 3)

**Site:** https://bold-tulip-nejq.here.now/  
**Updated:** 2026-09-23 (morning status + WTI/Brent fut)  
**Mandate:** Research / paper only · Soft color · Zero execution  
**Video:** YouTube short `jgf3ij05Cgw` — Fidelity guest “desert island 3”

## What the strip shows

Top of **Blotter**, above open seats:

### A. Live indices row
| Symbol | Role |
|--------|------|
| **SPY** | S&P 500 |
| **QQQ** | Nasdaq-100 |
| **DIA** | Dow Jones Industrial Average proxy (labeled DIA) |

Each cell matches ticker style: spot · day% · session badge (`PRE` / `AH` / `RTH` / `CLOSED`).

### B. Macro stress · Fidelity-3 (soft color only)

| Pillar (video) | What we show | Proxy honesty |
|----------------|--------------|---------------|
| **Median earnings growth** of S&P cos (median > cap-weight; equal-weight clearer on economy/jobs) | **RSP−SPY** day% spread + RSP/SPY day% | Equal-weight breadth proxy — **not** true median EPS growth |
| **Credit spreads** (tight → historically more often S&P up next year; very wide often near bottoms; quartile predictive) | FRED **HY OAS** `BAMLH0A0HYM2` + **IG OAS** `BAMLC0A0CM`: level, Δ vs ~1y, percentile & quartile vs ~10y | Real credit OAS from FRED public CSV (no API key) |
| **Valuation spreads** = cheap vs expensive gap; blowout = fear; measure vs history | **VTV/VUG** price ratio + day spread; percentile vs ~10y Yahoo daily | ETF value/growth proxy — **not** a vendor quant valuation-spread series |

Soft card tones: calm / neutral / warm / stress — **never** a trade signal or auto action.


### C. Rates · Vol · Oil (macro spot)

| Cell | What we show | Source honesty |
|------|--------------|----------------|
| **10Y Treasury** | US10Y yield % + day Δ in **bp** | FRED `DGS10` daily (optional UW yield-curve overlay). **Not** a T-bill. Yahoo `^TNX` unused (egress 429). |
| **VIX** | Spot + day % | Robinhood `get_index_quotes` / day historicals (`instrument_id` VIX). Yahoo `^VIX` unused. |
| **WTI fut** | Futures mark **$/bbl** + day % | Preferred: Macro Bot `oil_note`, `tmp/oil-futures.json`, investing.com/oilprice scrape, or sibling computerUse dump. Yahoo `CL=F` unused (egress 429). |
| **Brent fut** | Futures mark **$/bbl** + day % | Same path as WTI (`BZ=F` unused). |
| **WTI / Brent spot (FRED)** | Secondary note / optional cells | FRED `DCOILWTICO` / `DCOILBRENTEU` lagged daily spot — labeled **not** live futures. |

If futures unavailable: keep FRED oil primary with clear lag label. Soft only · co-watch with Hormuz / geopolitics soft notes · never elevate on macro alone.

### D. Morning macro status (Daily Macro · Macro Tech)

Soft-color cards **between** Rates·Vol·Oil and Fidelity-3. Seeded each weekday morning (~6 AM PT).

| Card | What we show |
|------|----------------|
| **Daily Macro** | Tone class (`soft-calm` / `soft-neutral` / `soft-warm` / `soft-stress`) · short label · score **−2..+2** · **1–3 news driver bullets** |
| **Macro Tech** | Same shape — Nasdaq/tech tone vs SPY |

**Daily Macro score (soft):** start 0; VIX day% ≥+5% → −1; VIX ≤−5% → +1; SPY day% ≤−0.75% → −1; ≥+0.75% → +1; HY OAS Q4 → −1; Q1 → +0; WTI fut day% ≥+3% (geo oil spike) → −1; ≤−3% → +0. Clamp −2..+2.

**Macro Tech score:** start 0; QQQ−SPY (pp) ≤−0.3 → −1; ≥+0.3 → +1; QQQ ≤−1% → −1; ≥+1% → +1; VIX day% ≥+5% → −1. Clamp −2..+2.

**Tone map:** +2/+1 → calm · 0 → neutral · −1 → warm · −2 → stress.

**News drivers:** newest `tmp/macro-soft-*.json` (e.g. Hormuz UKMTO) + Macro Bot morning JSON. Always include the top driver that explains the color. Macro Bot may set contested warm at score 0 when geo two-way (oil soft vs Hormuz re-escalation).

**metric_scores[]** (from Macro Bot weekday pack, first full deliverable next trading AM): each row `{metric, tech_score −2…+2, note?}` for 10Y_yield · oil_WTI_Brent · USD_DXY_or_USDJPY · VIX · NQ_vs_ES · credit_HYG_day · event_calendar — neg = Nasdaq headwind, pos = tailwind. Also `rates_note` / `usd_note` / `vol_note` beside `oil_note`.

Builder: `dashboard/macro_morning.py` · Feed: `market-data/latest/macro-morning.json` (TTL **21600s** / ~6h) · Automation prompt: `scripts/automation-prompts/oid-macro-morning.md` (cron `13 6 * * 1-5` PT).

## Quote piggyback (Duplicates #2)

`refresh_market_tape.py` reads fresh shared `market-data/latest/rh-quotes.json` first (`cache_io.piggyback_rh_quotes`, TTL 120s). Covered SPY·QQQ·DIA·RSP·VTV·VUG skip a second `get_equity_quotes`. Misses only: pass `--equity-quotes-file` (Rose `refresh_marks` / `live_refresh` remains sole `rh-quotes` writer). Smoke: `python3 dashboard/refresh_market_tape.py --check-piggyback`.

## Data plumbing

| File | Writer | TTL |
|------|--------|----:|
| `market-data/latest/market-tape.json` | `dashboard/refresh_market_tape.py` | 300s |
| `market-data/latest/macro-spot.json` | `dashboard/refresh_market_tape.py` (+ `macro_spot.py`) | 300s |
| `market-data/latest/macro-morning.json` | `dashboard/macro_morning.py` (Macro Bot ingest or `--recompute`) | 21600s |
| `market-data/latest/fidelity-three.json` | same | 1800s |
| `market-data/latest/fred-hy-oas.json` | same (sibling stamp) | 86400s |
| `market-data/latest/fred-ig-oas.json` | same | 86400s |

```bash
# Symbols for RH get_equity_quotes (seats + tape)
python3 dashboard/live_refresh.py --emit-symbols

# Or tape-only symbols
python3 dashboard/refresh_market_tape.py --emit-symbols

# After MCP get_equity_quotes → save JSON:
python3 dashboard/refresh_market_tape.py \
  --equity-quotes-file tmp/market-tape-quotes.json

# Full Hal/OID marks path (applies seats + refreshes strip + rebuild)
python3 dashboard/live_refresh.py \
  --equity-quotes-file tmp/….json \
  --publish
```

**FRED (no key):**  
`https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2`  
`https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLC0A0CM`

**Valuation history:** Yahoo chart API 10y daily closes for VTV & VUG (ratio percentile). Falls back gracefully if blocked.

## Upgrades (later — not this pass)

1. **True median EPS growth** — FactSet / Bloomberg / S&P CapIQ median YoY EPS for S&P universe (replace RSP−SPY).
2. **True valuation-spread quant** — vendor cheap-vs-expensive dispersion (e.g. top/bottom decile forward P/E or composite value factor spread) vs history.
3. Optional **Macro Bot** path to own cadence / narrative on these three (FYI only).

## Preserve

Hal UI tabs Blotter | Data sources | Trader intel | Events · slim rows · Qty/Total · In/Out · Earn chips · section totals · BOOK_TP · session badges — unchanged.

## Disclaimer

Research / paper tracking only. Soft macro color for desk context. Zero Robinhood order placement from OID.

## Related: Shay equity watch
`live_refresh --emit-symbols` also pulls Shay semi symbols (via `refresh_marks --list-symbols`) so one equity quote batch feeds seats + tape + Shay since-post tracking.


## Morning macro status + oil futures (2026-09-23)

See **§C** (WTI/Brent **fut** primary; FRED spot secondary) and **§D** (Daily Macro · Macro Tech indicator math + driver rules). Feed `macro-morning.json` · builder `macro_morning.py` · weekday cron prompt `scripts/automation-prompts/oid-macro-morning.md` (`13 6 * * 1-5` PT). Soft color only · never elevates · zero RH orders.
