# Overnight hold: 12:55 PM → next open (core 61, 60 nights, 10/21)

Research only. Nothing here changes a trade, score or alert. **In-sample, one 60-session regime (entries 7/28–10/20, exits through 10/21).**

**Question:** the overnight/intraday split showed most of the gains came overnight. Does buying at 12:55 PM PT and selling at the next 6:30 open (or at 6:45) beat buy-and-hold and intraday, as shares or as 45-DTE calls, after costs?

## Method
- **Bars:** Alpaca SIP 5-minute and daily bars, split-adjusted, 61 core tickers (SPY and QQQ included). Entry = close of the 12:50 PM PT 5-min bar (the 12:55 price; never fell back to the close). Exit = official open (6:30) or close of the 6:40 bar (the 6:45 price). Event nights from Unusual Whales earnings history (43 ticker-nights: post-market report → that day's entry; pre-market → the prior day's entry).
- **Share costs (assumption):** 4 bp round trip for the open exit, 3 bp for the 6:45 exit. Gross shown too.
- **45-DTE calls (modelled, no quote history on the mini):** Black-Scholes repricing, r = 4%, ATM strike or the 0.35-delta strike, T = 45 days minus the actual clock time held. IV = each ticker's real 10/21 Alpaca OPRA ~45-DTE call IV (mostly the 11/27 expiry), **held constant** (no vega P&L, no earnings IV crush). Entry at the modelled ask, exit at the bid, using the snapshot's real bid-ask % of mid; the exit spread is 2× (6:30 open) or 1.25× (6:45) the close spread (assumption: opening quotes are wider). P&L in % of the premium paid.
- **Stats:** basket = equal weight across the names each night. Total = compounded (shares) or summed % of premium (options). Sharpe = mean ÷ stdev × √252. Top-5 share = sum of the 5 best nights ÷ total P&L.

## Equal-weight basket, all 61 core names

| Strategy | Total | Mean / night | Win | Sharpe | Max DD | Worst night | Top-5 share |
|---|---|---|---|---|---|---|---|
| Shares 12:55 → 6:30, net | **+8.39%** | +0.152% | 51.7% | 1.29 | −10.8% | −4.45% | 210% |
| Shares 12:55 → 6:30, gross | +11.02% | +0.192% | 51.7% | 1.62 | −10.5% | −4.41% | 168% |
| Shares 12:55 → 6:45, net | +6.40% | +0.121% | 60.0% | 1.01 | −12.5% | −4.00% | 257% |
| Shares → 6:30, ex-earnings | +8.24% | +0.149% | 51.7% | 1.29 | −10.8% | −4.45% | 202% |
| Buy-and-hold (EW, close → close) | +8.28% | +0.163% | 56.7% | 1.05 | −15.3% | −4.79% | 264% |
| Intraday (EW, open → close) | −3.20% | −0.041% | 48.3% | −0.40 | −7.3% | −4.36% | — |
| ATM 45-DTE call → 6:30 | −19.1% of premium / night | | 3.3% | −33 | | −40.8% | |
| ATM 45-DTE call → 6:45 (gap-follow) | −14.0% / night | | 6.7% | −23 | | −35.2% | |
| 0.35Δ 45-DTE call → 6:30 / → 6:45 | −29.5% / −21.9% per night | | 1.7% / 3.3% | | | | |
| ATM call, mid to mid (no spread) → 6:30 | +0.58% / night | | 50.0% | 0.83 | | −25.8% | 339% |

Mean single-ticker buy-and-hold: +6.53%. The all-name option rows are dominated by wide-spread names: the median ATM 45-DTE spread is 10.9% of mid (0.35Δ: 16.0%).

## Liquid 9 (ATM 45-DTE spread ≤ 3% of mid: IREN, MRVL, NFLX, NVDA, ORCL, PLTR, QQQ, SPCX, SPY)

| Strategy | Total | Mean / night | Win | Sharpe | Max DD | Top-5 share |
|---|---|---|---|---|---|---|
| Shares → 6:30, net | +9.50% | +0.161% | 55.0% | 1.85 | −6.3% | 141% |
| Shares → 6:45, net | +14.27% | +0.235% | 56.7% | 2.39 | −8.7% | 116% |
| Buy-and-hold (EW) | +16.70% | +0.282% | 53.3% | 2.01 | −11.7% | 154% |
| Intraday (EW) | +4.93% | +0.092% | 51.7% | 0.94 | −7.3% | 323% |
| ATM call → 6:30 / → 6:45 | −2.07% / −0.83% of premium per night | | 36.7% / 40.0% | −3.6 / −1.2 | | |
| 0.35Δ call → 6:30 / → 6:45 | −6.39% / −3.79% per night | | 28.3% / 35.0% | | | |
| ATM call mid to mid → 6:30 / → 6:45 | +0.62% / +1.20% per night | | 51.7% / 53.3% | 1.05 / 1.76 | | |

## Filters (pooled ticker-nights; shares → 6:30 net unless noted)

| Filter | n | Mean / night | Win | Note |
|---|---|---|---|---|
| All | 3,660 | +0.152% | 52.0% | |
| Closed in top 25% of the day's range at 12:55 | 955 | +0.307% | 52.1% | but the basket of those names: +1.32% total, Sharpe 0.34 (worse: crowded strong days gave back) |
| Not top 25% | 2,705 | +0.097% | 51.9% | |
| Core score > 0 at 12:55 | 33 | +1.86% | 81.8% | only 2 nights archived (10/19, 10/20): anecdote |
| Aggressor C/P > 1.10 at 12:55 | 60 | +0.45% | 46.7% | only 2 nights archived |
| Ex-earnings nights | 3,617 | +0.138% | 52.1% | |
| Earnings nights only | 43 | +1.31% (→ 6:45: +1.47%) | 46.5% | ATM call → 6:30 −6.9%; 0.35Δ → 6:45 +2.8% of premium, **overstated (no IV crush)** |
| Options with filters | | ATM → 6:30: top 25% −19.6%, score > 0 −11.3% (33), C/P > 1.10 −13.0% (60) | | |

## Per ticker (shares → 6:30 net)

| Ticker | Total | Sharpe | Max DD | Worst | Top-5 share | Ex-earnings | → 6:45 | Buy-hold | Intraday | ATM → 6:30 (% prem / night) |
|---|---|---|---|---|---|---|---|---|---|---|
| BE | +41.4% | 2.49 | −20.0% | −6.9% | 122% | +31.6% | +54.6% | +43.0% | −9.1% | −9.8% |
| LITE | +40.2% | 2.78 | −12.8% | −7.6% | 112% | +28.3% | +11.7% | +30.5% | −9.4% | −14.9% |
| COHR | +37.0% | 2.36 | −15.3% | −7.6% | 137% | +40.5% | +9.7% | −2.4% | −28.3% | −14.0% |
| LRCX | +32.5% | 2.11 | −16.3% | −7.9% | 132% | +6.5% | +5.1% | −3.3% | −27.6% | −13.7% |
| ANET | +32.4% | 3.42 | −10.3% | −4.8% | 84% | +21.0% | +19.8% | +8.6% | −18.4% | −13.7% |
| MRVL | +29.7% | 2.06 | −17.4% | −8.6% | 145% | +39.0% | +40.1% | +40.3% | +5.7% | +0.5% |
| NVDA | +25.8% | 4.25 | −5.9% | −3.5% | 64% | +18.4% | +21.0% | +12.7% | −15.0% | −0.2% |
| SPY | +2.3% | 1.57 | −2.1% | −0.8% | 171% | +2.3% | +2.3% | +4.4% | −1.3% | −0.6% |
| QQQ | +2.0% | 0.75 | −4.3% | −1.7% | 317% | +2.0% | +2.9% | +7.4% | +1.7% | −1.4% |
| PLTR | +11.1% | 1.36 | −11.2% | −2.2% | 212% | −3.9% | +36.1% | +63.3% | +38.6% | −1.2% |
| MSFT | +6.4% | 1.08 | −12.1% | −2.2% | 257% | −4.8% | +24.9% | +35.5% | +19.3% | −6.3% |
| AAPL | −10.1% | −2.02 | −12.4% | −8.5% | — | −1.7% | −12.3% | +1.2% | +8.0% | −7.3% |
| NFLX | −13.8% | −2.48 | −16.2% | −6.2% | — | −8.1% | −11.1% | −10.2% | +2.6% | −5.4% |
| WDC | −17.7% | −0.93 | −36.6% | −17.8% | — | −17.2% | −25.7% | −18.3% | −1.6% | −26.7% |
| CBRS | −37.6% | −3.39 | −42.8% | −16.2% | — | −25.5% | −34.2% | −38.8% | −2.2% | −45.4% |

47 of 61 names were positive overnight after costs; full table in `~/oid-data/patterns/onhold-20261021.json`.

## Verdict
- **Shares:** for the 61-name basket, the overnight hold roughly tied buy-and-hold on return (+8.4% vs +8.3%) while holding ~18 h a night. Drawdown was smaller (−10.8% vs −15.3%) and Sharpe higher (1.29 vs 1.05). It beat intraday by about 11.6 points (+8.4% vs −3.2%). In the liquid 9 it lagged buy-and-hold (+9.5% vs +16.7%); selling at 6:45 instead closed most of the gap (+14.3%).
- **Concentrated:** the 5 best of 60 nights produced 210% of the basket's P&L. Without them the strategy loses money. Excluding earnings nights barely changes it (+8.2%).
- **45-DTE calls:** negative after spread in every variant. All names: −14% to −30% of premium per night. Liquid 9: −0.8% (ATM, 6:45) to −6.4% (0.35Δ, open) per night. Gross (mid to mid) it would be +0.6% to +1.2% per night, so the bid-ask spread, wider at the open, eats it. Selling at 6:45 is less bad mainly because of the assumed narrower 6:45 spread.
- **Caveats:** in-sample, one 60-day regime with a strong semis/AI overnight drift; the option IV is held constant (no vega, no IV crush); the share costs and open-spread multiplier are assumptions; the score and C/P filters have 2 nights of data.

Files: `~/oid-score/research/onhold_fetch.py`, `onhold.py`; data `~/oid-data/patterns/onhold-*.json`, `earnings-core-20261021.json` (not synced).
