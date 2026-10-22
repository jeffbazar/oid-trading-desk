# Credit spreads vs category betas: daily data series (2026-10-21)

**Status:** built, updates daily (research only, no trading changes)
**Owner:** Rose. **Analysis:** Research Bot runs the two-year spread-vs-correlation backtest from this series.

## What it is
A daily file that other bots can read instead of rebuilding it. It holds credit-spread levels, a spread-regime flag, and rolling betas and correlations for each chip and neocloud category against QQQ, SMH, META, MSFT, GOOGL, AMZN and LRCX.

- **CSV:** `~/oid-data/research/spread-corr/spread_corr_daily.csv`. One row per session from 2024-10-01, with 267 columns.
- **Latest:** `~/oid-data/research/spread-corr/latest.json`. It holds the last row, nested by category and benchmark, plus FRED status and notes.
- **Job:** launchd `com.oid.desk.spread-corr`, Mon–Fri at 13:30 PT. Script: `~/oid-score/research/spread_corr.py`. Log: `~/oid-score/logs/spread-corr.log`.

## Columns
- `hy_oas` and `ig_oas` are the ICE BofA OAS from FRED (BAMLH0A0HYM2, BAMLC0A0CM), forward-filled. `hy_oas_obs_date` is the date of that observation.
- `hyg_ief`, `hyg_lqd` and their `*_chg20_pct` are price ratios from Alpaca SIP daily bars.
- `regime` is `widening`, `flat` or `narrowing`. It is set by where the 20-session % change in HYG/IEF falls in its own trailing 252-session terciles: the bottom tercile is widening.
- `regime_hy_check` compares the HY OAS 20-session change (±15 bp) with the regime and reads agree, partial, disagree or na.
- `crwv_minus_qqq_20d_pct` and `orcl_minus_qqq_20d_pct` are the AI-debt proxy. **They are equity returns, not credit**, because there is no free CDS or bond feed.
- `<category>__<bench>__beta{20,60,120}` and `__corr{20,60,120}` hold the rolling OLS beta and correlation of the equal-weight category basket's daily return on the benchmark's return. A benchmark is excluded from its own basket, so `chip_equip` vs LRCX is ex-LRCX. A value needs at least 75% of the window to have data.

Categories come from the read-through study (`catbeta-20261021.json`): chip_equip, memory, gpu_logic, neocloud, neocloud_heavy_debt (CRWV, WULF, CIFR, APLD, plus CORZ per the desk list) and neocloud_low_debt (NBIS, IREN).

## Caveats
- FRED's CSV endpoint was unreachable from the mini and the box on 10/21 (bot check or timeouts). When FRED fails, the job uses its cache plus the desk market tape's latest OAS print, so OAS history builds up one print a day until a live FRED pull refills it. Until then, the HYG/IEF regime is the main input, and OAS columns are blank before 2026-10-15.
- Alpaca `adjustment=all` makes HYG/LQD/IEF ratios close to total return, not price-only.
- Newer listings (CRWV, SNDK and others) join their baskets later, so basket membership changes over time.

## Reference
Research Bot's 10/21 follow-up (`research-bot-followup_meta_minute_and_credit-20261021.md`, copied next to the data) found that when spreads are widening, the neocloud/builder beta to META rises from 0.40 to 1.28, while the QQQ and SMH betas don't rise. This series lets you watch that live through `neocloud__META__beta20/60` alongside `regime`.
