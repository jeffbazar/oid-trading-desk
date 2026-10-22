# De-grossing gauge study, 2026-10-22 (research only)
Data: yfinance daily adjusted closes, 2017-01-03 to 2026-10-22, plus yfinance earnings dates and EPS surprise. Train = pre-2024, holdout = 2024-01-01 to 2026-10-22. Scripts: `gauges.py` → `analysis.py` → `beats.py` → `chart_and_stats.py`. Spec: `SPEC.md`. Chart: `degrossing_gauge.png`.

## Universe & caveats
There are 74 tickers: NVDA AMD INTC AVGO QCOM TXN MU AMAT LRCX KLAC ASML TSM ADI MRVL NXPI MCHP ON MPWR TER SWKS ENTG MKSI COHR LITE CIEN ANET CSCO GLW KEYS AAPL MSFT GOOGL AMZN META NFLX ORCL CRM ADBE INTU NOW IBM DELL HPE HPQ SMCI WDC STX NTAP CRDO VRT ARM PLTR SNOW CRWV NBIS IREN APLD WULF CIFR SNPS CDNS PANW CRWD FTNT ZS DDOG NET MDB TEAM SHOP TSLA AMKR SNDK ALAB.
- PSTG returned no data and QRVO only has data from 2026-10-02, so both were dropped. NBIS history starts 2024-10-21.
- **Survivorship bias:** every name is a 2026 survivor. Delisted and acquired names (XLNX, JNPR, ANSS, etc.) are missing. A name only joins the basket once it has 252 days of history.
- "Crowded" here means 12-1 price momentum, not ownership. As of the 9/30 rebalance, CRWV lands in the *uncrowded* tercile. Current crowded basket: SNDK MU LITE WDC STX DELL AMD.
- MTUM rebalances twice a year, so its momentum tilt lags.
- Yahoo earnings dates and consensus are vendor data. Session timing was inferred from the timestamp: 1,968 after close, 382 before open, 66 ambiguous (2-day reaction used).

## 1. Today (10/22) vs history
| gauge | daily | 10d sum | trigger line | record low (10d) |
|---|---|---|---|---|
| GVIP−SPY | −2.11% | −5.30% | −3.27% | −8.98% (3/2020) |
| MTUM−SPY | −2.49% | −8.05% | −4.07% | −9.99% (2021, 7/2026) |
| MTUM−USMV | −4.74% | −12.77% | −4.68% | −13.70% (7/2026) |
| Crowded−uncrowded | −6.06% | −16.61% | −11.95% | −27.4% (7/2026) |

GVIP lost to SPY on all 6 SPY-down days since 10/8, so there is **no exhaustion flag**. The episode has been open since its 10/14 first trigger (window start 10/01).

## 2. Episodes (`episodes.csv`)
An episode is any trigger day (10d sum ≤ the pre-2024 2.5th percentile for MTUM−SPY, GVIP−SPY or MTUM−USMV), with trigger days merged when ≤10 trading days apart. That gives **33 episodes: 23 train, 10 holdout (one still open)**.
- **Caught:** Q4 2018 (3 clusters, MTUM−USMV), Mar 2020, Sep 2019 momentum crash, Nov 2020 vaccine rotation, Feb–Mar 2021, Jan–Jun 2022 (5 clusters), Jan 2023 junk rally, Jul–Aug 2024 yen carry (7/18–8/7), Feb–Mar 2025, Apr 2025 tariff (MTUM−USMV only), Nov 2025, and in 2026: Feb, Mar, Jul–Aug (18 trigger days, the biggest on record), late Aug and Oct (open).
- **Missed: Jan 2025 DeepSeek.** It was a one-day shock: crowded−uncrowded fell −19.4% on 1/27, but MTUM−SPY's 10d sum bottomed at only +0.1%. A 10-day window can't see a one-day shock.
- Without MTUM−USMV, the tariff drop and Q4 2018 are also missed. **MTUM−USMV is the best detector of the four.**

## 3. Exhaustion signals (`signal_results.csv`, `signals_all_rules.csv`)
I tested 24 rules: 4 gauges × (A: last k SPY-down days with gauge ≥0, k=2/3/4; B: down-day w-sum turns positive, w=3/5/10). Each fires once per episode. Results are excess forward returns vs the unconditional mean. Unconditional QQQ +10d is +0.80% in train and +0.94% in holdout.

| rule (picked on train) | set | n | QQQ +10d xs | QQQ +20d xs | SMH +10d xs | crowded +10d xs | QQQ +10d >0 | relapse ≤20d |
|---|---|---|---|---|---|---|---|---|
| MTUM−SPY B3 (train best, n≥10) | train | 20 | +2.08pp (t 1.9) | +1.09 | +2.09 | +3.68 | 75% | 65% |
|  | holdout | 9 | **−1.96pp** | +0.83 | −2.77 | −4.66 | 33% | 44% |
| GVIP−SPY A2 (2nd) | train | 18 | +1.94pp (t 1.5) | +0.85 | +3.26 | +1.54 | 67% | 44% |
|  | holdout | 8 | +0.14pp | +3.09 (t 1.5) | −1.59 | −4.09 | 63% | 38% |
| MTUM−USMV A2 | train | 12 | +1.58pp | +2.87 (t 2.1) | +1.85 | +2.58 | 83% | 33% |
|  | holdout | 5 | −2.40pp | +0.24 | −4.56 | −5.99 | 40% | 40% |
| CVU B3 | train | 22 | +2.03pp (t 1.9) | 0.00 | +3.43 | +1.73 | 73% | 59% |
|  | holdout | 9 | −1.35pp | +0.73 | −3.49 | −4.90 | 56% | 44% |

**Read:** in train, every leading rule beat normal QQQ returns by about 2pp over 10 days, but none reached t ≥ 2 at 10d. **None held up out of sample.** In 2024–26, the crowded basket *underperformed* its own unconditional return after nearly every flag; its normal 10d return was +3.25%, a very high bar. Relapse rate ("false signal") ran 33–65%. Most rules showed QQQ +20d slightly positive in holdout, the only consistent sign. All n are small, and episodes overlap in regime.

## 4. Beats sold during de-grossing (`beats_rebound_summary.csv`)
These are stock-episode pairs where the stock had a positive EPS surprise and a negative reaction inside the episode window. Returns are measured from the episode end (GVIP−SPY A2 flag date, or the last trigger if no flag), as excess vs the equal-weight universe.
- **All:** n=278 across 29 episodes. Excess was +0.25pp at +5d (SE 0.29), +0.06pp at +10d (SE 0.36), and −0.50pp at +20d (SE 0.52).
- **Holdout:** n=89 across 8 episodes: +0.70 / +0.34 / −0.88pp.
- **Comparison:** beats that rose on the day: +0.16 / +0.74 / −0.12pp (n=286).
- With the MTUM−SPY B3 end date: −0.18 / −0.17 / −1.42pp (n=259).
- **Result: no evidence that sold beats rebound harder.** Pairs cluster within episodes, so the effective n is closer to 29 than 278.

## 5. Recommendation
Build the gauge as a **state monitor**, not a timing signal: episode on/off plus severity, keyed on MTUM−USMV, GVIP−SPY and the crowded-uncrowded spread. Show the GVIP−SPY A2 down-day check as an "early exhaustion" hint, labeled unvalidated. See `SPEC.md`.
