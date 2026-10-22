# De-grossing gauge — spec for Rose's Mac mini (/credit tab)
Research Bot, 2026-10-22. Free daily data only (Yahoo/yfinance adjusted closes). No keys, no paid feeds. Run once after the close (~1:30 PM PT).

## Inputs
- ETFs: SPY, QQQ, SMH, GVIP, MTUM, USMV (adjusted close).
- Universe: the 74 tickers in `basket_members.csv` / README (tech, semis, AI infra).

## Formulas (daily, r = close-to-close return)
| Field | Formula |
|---|---|
| `gvip_spy` | r(GVIP) − r(SPY) |
| `mtum_spy` | r(MTUM) − r(SPY) |
| `mtum_usmv` | r(MTUM) − r(USMV) |
| `cvu` | EW r(crowded) − EW r(uncrowded). Rebalanced at each month-end close: 12-1 momentum = P[t−21]/P[t−252]−1 over names with 252 days of history; crowded = top decile (min 5 names), uncrowded = bottom tercile |
| `*_10d` | rolling 10-day sum of each spread |
| `*_ds5` | rolling 5-day sum of the spread on SPY-down days only (0 on SPY-up days) |
| `trigger` | true if any of: mtum_spy_10d ≤ −4.07%, gvip_spy_10d ≤ −3.27%, mtum_usmv_10d ≤ −4.68% (pre-2024 2.5th percentiles; keep fixed, don't refit) |
| `episode_id` | a new episode starts on a trigger day >10 trading days after the last trigger day |
| `armed` | trigger on any of the last 20 trading days |
| `exhaust_flag` | (while armed) the last 2 SPY-down days since the episode's first trigger both had gvip_spy ≥ 0 (rule "GVIP_SPY A2"). Fires once per episode |
| `relapse` | a trigger day within 20 trading days after exhaust_flag fired |
| `severity` | mtum_usmv_10d ÷ its record low (−13.70%, 2026-07) |

## Output: `degrossing_gauge.csv`, one row per day, append-only
`date, spy_ret, qqq_ret, smh_ret, gvip_spy, mtum_spy, mtum_usmv, cvu, gvip_spy_10d, mtum_spy_10d, mtum_usmv_10d, cvu_10d, gvip_spy_ds5, mtum_spy_ds5, mtum_usmv_ds5, cvu_ds5, spy_down, trigger, armed, episode_id, days_since_first_trigger, downdays_gvip_nonneg_streak, exhaust_flag, relapse, severity, crowded_members, uncrowded_members`
Store spreads as decimals. Keep `crowded_members` and `uncrowded_members` as space-separated tickers so the basket can be audited.

## /credit tab
1. **State badge:** DE-GROSSING (armed, no flag) / EXHAUSTION FLAG (flag fired, no relapse yet) / CLEAR (not armed). Add the episode day count.
2. **Three numbers:** mtum_usmv_10d, gvip_spy_10d and cvu_10d, each next to its trigger line, plus severity.
3. **Down-day check:** on each of the last 5 SPY-down days, did GVIP beat SPY? Show ✓/✗.
4. **Chart:** 6 months of the three 10d sums with episode shading.
5. **Caveat line, always shown:** "Exhaustion flag not validated out-of-sample. In 2024–26 (n=8) QQQ +10d was +0.1pp vs normal and the crowded basket was −4.1pp. In 38–44% of past flags the selling relapsed within 20 days. Use as context, not timing."

## Not in v1
Prime-broker leverage (only secondhand via X), borrow fees and short interest (no free history), and SOXL flows (yfinance has no shares-outstanding history).
