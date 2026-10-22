# 38 · De-grossing gauge (is the hedge-fund selling still on?)
[← Index](README.md)

> Added **Thu 10/22/2026, 3:05 PM PT**. Shown as the **De-grossing gauge** section at the top of the `/credit` tab ([36](36-credit-betas.md)). Data endpoint: `/degross.json`. Built to Research Bot's 10/22 backtest and spec (copy in `~/oid-score/research/degross-study/`). Research only, not an order signal.

## Plain-English lessons: what these numbers mean

<!-- DGTUT 10/22 -->
*Base text by **Research Bot** and **Macro Bot** (their shared `TUTORIAL.md` on the box), merged with the desk outline and checked against the gauge's real rules in `degross.py`. The same lessons are in the **How to read this** panel under the gauge on `/credit`, where the numbers update every run. The worked numbers here are frozen at **2026-10-22** and are raw, not smoothed.*

**What "de-grossing" means.** Hedge funds borrow to hold more stock than they have cash for. When they get scared or lose money, they cut that borrowing fast by **selling everything at once**, starting with what they own the most of, no matter the news. That is why good earnings can still get sold. This gauge measures whether that is happening right now.

### The ETFs we use as thermometers
- **SPY** is the S&P 500, the whole market, and our baseline. On 2026-10-22: -1.18%.
- **QQQ** is the Nasdaq 100, the big tech names, so it usually gets hit harder than SPY in a tech unwind. -2.86%.
- **SMH** holds the chip stocks (NVDA, AVGO, MU and others), the center of the AI trade and of fund crowding. -5.99%.
- **MTUM** holds momentum stocks, last year's big winners (lots of AI and chips). Funds pile into these, so they get dumped hardest when funds sell. -3.67%.
- **USMV** holds low-volatility stocks: boring, steady names like utilities, staples and health care. Few funds are crowded into them, so in a fund selloff they hold up or even rise. +1.07%.
- **GVIP** is Goldman Sachs' list of the stocks hedge funds own most (the "VIP" basket), the closest public view of a typical fund's top holdings. -3.29%. It trades thinly, so one day can be noisy.

Moves on 2026-10-22, one day:
```
SPY (whole market)                             ████|                         -1.18%
QQQ (Nasdaq 100)                          █████████|                         -2.86%
SMH (chips)                      ██████████████████|                         -5.99%
GVIP (fund favorites)                    ██████████|                         -3.29%
MTUM (last year's winners)              ███████████|                         -3.67%
USMV (boring, steady)                              |███                      +1.07%
Crowded basket             ████████████████████████|                         -7.92%
Uncrowded basket                             ██████|                         -1.87%
```

### Why subtract one from another (a "spread")
If the whole market falls, everything falls together, and that is just a bad day. When funds de-gross, **their** stocks fall much more than everything else. Subtracting the market (or the boring stocks) takes out the "whole market" part and leaves only the "funds are dumping their favorites" part.

**Worked example.** MTUM -3.67% minus SPY -1.18% = **-2.49%** in one day, so the winners fell about 3.1× as much as the market. MTUM -3.67% minus USMV +1.07% = **-4.74%**: the crowded winners fell while the boring stocks *rose*. That gap is the fingerprint of funds selling one thing and not the other.

### The "10-day sum" and the "trigger line"
One day can be noise, so the gauge adds up the last 10 trading days of each spread (about two weeks). Each 10-day sum has a fixed **trigger line**: the worst 2.5% of days in the history before 2024. The lines were set once and are never re-fitted.

| 10-day sum | 2026-10-22 | Trigger line | Past the line? |
|---|---|---|---|
| MTUM − USMV (headline) | -12.77% | -4.68% | yes (about 2.7× the line; record -13.70%, July) |
| GVIP − SPY | -5.30% | -3.27% | yes |
| MTUM − SPY | -8.05% | -4.07% | yes |
| Crowded − uncrowded (context only) | -16.61% | −11.95% (display only) | does not switch the badge |

### Severity
Severity is the MTUM − USMV 10-day sum divided by the record (-13.70%). On 2026-10-22: -12.77% ÷ -13.70% = **0.93**, so this selloff was 93% as bad as the worst on record. It is not capped at 1: above 1 would be a new record. Near 0 is a normal day. Severity says how hard it is; it does not switch the badge on or off.
```
0%            ↓trigger 34%
█████████████████████████████████████░░░░░░░░░░░
                                    ↑today 93%   (record = 100% at 40 blocks)
```

### The badge, and the episode day count
**The badge turns on** on any day when **any one** of the three 10-day sums (MTUM − USMV, GVIP − SPY, MTUM − SPY) is past its trigger line. It then **stays on for 20 trading days** after the latest trigger day, so it does not flicker off on one green day. It caught 32 of 33 big unwinds since 2017; the miss was the one-day DeepSeek shock in January 2025.

On 2026-10-22: **DE-GROSSING**, triggered by mtum_usmv, mtum_spy, gvip_spy. **Episode day 6** means 6 trading days had passed since this round's first trigger on 2026-10-14, which counts as day 0.

> **Correction to the source text.** The draft said the badge "turns on below −4.68%" and that it turns on when "any reading reaches the worst 2.5% of history." The real rule: any one of **three** fixed lines (MTUM − USMV −4.68%, GVIP − SPY −3.27%, MTUM − SPY −4.07%). The lines are the worst 2.5% of days **before 2024** and are never re-fitted. Crowded − uncrowded is display only. The badge stays on for 20 sessions after the last trigger. Severity can go above 1.

### The down-day table
On each of the last 5 days when SPY fell, did GVIP (the hedge-fund favorites) fall less than SPY? ✗ means the fund favorites fell more, so funds were still selling into the weakness. On 2026-10-22 the table was **5 of 5 ✗**. Buyers stepping in would show up here first as ✓s.

| SPY-down day | SPY | GVIP | GVIP − SPY | GVIP beat SPY? |
|---|---|---|---|---|
| 2026-10-22 | -1.18% | -3.29% | -2.11% | ✗ |
| 2026-10-16 | -1.11% | -2.46% | -1.35% | ✗ |
| 2026-10-14 | -1.08% | -2.49% | -1.41% | ✗ |
| 2026-10-13 | -0.01% | -0.49% | -0.48% | ✗ |
| 2026-10-12 | -0.06% | -1.11% | -1.05% | ✗ |

### Crowded vs uncrowded, and crowded vs SMH
The **crowded basket** is the top 10% of our 74-stock tech and AI list ranked by last year's gain (12 months, skipping the latest month), reset at each month-end; on 2026-10-22: SNDK MU LITE WDC STX DELL AMD. The **uncrowded basket** is the bottom third by the same ranking. Each basket weights its stocks equally. Crowded -7.92% minus uncrowded -1.87% = **-6.06%** for the day and **-16.61%** over 10 days. It is shown for context only and does not switch the badge.

The desk's own AI basket minus SMH (-2.67%; 10 of 12 names worse than SMH) asks: are our crowded names falling more than chips overall? If so, it is fund selling, not just a chip-sector story.

### Supporting cards (context, not part of the badge)
- **VIX vs VIX3M.** VIX is the expected market swing over the next month, VIX3M over three months. Normally VIX is lower, giving a ratio below 1. Above 1 ("inverted") means panic about right now, which often comes near the end of a selloff. 19.03 vs 20.12, ratio 0.946: not inverted, so no panic yet.
- **Put skew.** How much more traders pay for crash insurance (puts) than for upside bets (calls), in volatility points. Higher means more fear. QQQ 5.51, SMH 4.11.
- **Short-volume ratio.** The share of trading in our crowded names marked "short" (this includes market makers, so it is noisy). Rising means more betting against them. 42.12% vs 45.34% average for the prior 20 days (FINRA 2026-10-22).
- **SOXL flow.** SOXL is a 3× leveraged chip ETF that retail traders love. New shares created (+) means people are buying the dip; redemptions (−) mean they are giving up. +3.45M shares (2026-10-21).
- **Borrow fee.** The yearly cost to borrow our crowded names to short them. A jump would mean shorts are crowding in. 0.312%.

### The "selling-ending hint" (UNTESTED)
The hint fires when, after the first trigger, **two SPY-down days in a row** show GVIP doing at least as well as SPY. It fires at most once per episode, and the badge then reads EXHAUSTION FLAG. On 2026-10-22: no flag (0 of 2).

**Why it's untested.** It looked good on old data but failed the out-of-sample check. In 2024–26 (8 cases), QQQ did no better than normal over the next 10 days, the crowded stocks did worse, and in 38–44% of past flags the selling came back within 20 days. Treat it as a hint, not a timer.

### Honest odds
Research Bot's rough read: about a **1-in-3 chance the selling is already done**. That is based on very few past cases, so it is soft. This episode is also **unusually severe** (93% of the record), so those few past cases may not fit it well.

### What would make it turn off
There are two ways:
1. **Fund favorites stop lagging on red days.** Two SPY-down days in a row with GVIP ≥ SPY switch the badge to EXHAUSTION FLAG (untested).
2. **Quiet for 20 trading days.** No 10-day sum past its line for 20 sessions turns it to CLEAR.

Because the 10-day sums were far past their lines, even flat days could take up to two weeks to pull them back inside. The 20-day count only starts from the last day any sum was past its line.

### How the desk trades it while the badge is on
- **No calls on earnings beats.** Good news gets sold when funds are de-grossing.
- **Puts on wall breaks, or stay flat.**
- **Smaller size.**
- **Calls come back only after price confirms**, such as SMH retaking 537.73 or QQQ holding 700, not just because the badge or the hint changes.

Research only, never a trade signal on its own.

---

**What it answers.** When funds cut their gross exposure, they sell their crowded winners and cover shorts in their losers, and indexes fall with them whatever the earnings say. The gauge reports whether that unwind is **on**, how hard it is (**severity**), and gives one **untested** hint about when it might be ending.

**The badge**

| Badge | Meaning |
|---|---|
| **DE-GROSSING** | A trigger fired in the last 20 sessions and no exhaustion flag is standing. A relapse after a flag sets it back to this. |
| **EXHAUSTION FLAG** | The episode's flag fired and no trigger has fired since. **UNTESTED**: see the caveat. |
| **CLEAR** | No trigger in the last 20 sessions. |

**Severity** = the MTUM − USMV 10-day sum divided by its record low (−13.70%, July 2026). 100% means the worst on record. The episode day count runs from the episode's first trigger.

**The three readings and their trigger lines.** Each reading is a 10-session sum of a daily spread. The lines are the pre-2024 2.5th percentiles. They are fixed and are never refit.

| Reading | Daily spread | Trigger line | Role |
|---|---|---|---|
| **MTUM − USMV** (headline) | momentum factor ETF minus min-vol ETF | ≤ −4.68% | best single detector: it alone caught the Apr 2025 tariff drop and Q4 2018 |
| GVIP − SPY | Goldman hedge-fund VIP basket minus SPY | ≤ −3.27% | trigger |
| MTUM − SPY | momentum ETF minus SPY | ≤ −4.07% | trigger (shown, not one of the three headline numbers) |
| Crowded − uncrowded | top momentum decile minus bottom tercile of a 74-name tech universe | −11.95% | **display only, not a trigger** |

A day is a **trigger** if any of MTUM − USMV, MTUM − SPY or GVIP − SPY is at or past its line. A new **episode** starts on a trigger more than 10 sessions after the previous trigger.

**Down-day check and the exhaustion flag (UNTESTED).** The table lists the last 5 SPY-down days and marks ✓ when GVIP beat SPY. The flag (rule "GVIP_SPY A2") fires once per episode, when the last two SPY-down days after the first trigger both have GVIP ≥ SPY. A **relapse** is a trigger within 20 sessions after the flag. The idea is that once funds stop dumping their own book, their names stop lagging on down days.

**Caveat (always shown on the tab).** *Exhaustion flag not validated out-of-sample. In 2024–26 (n=8) QQQ +10d was +0.1pp vs normal and the crowded basket was −4.1pp. In 38–44% of past flags the selling relapsed within 20 days. Use as context, not timing.*

**How well it was tested** (Research Bot, 2017-01 → 2026-10-22; train before 2024, holdout 2024 on)
- **Detection:** 33 episodes were found (23 train, 10 holdout), and the gauge caught 32 of 33 known unwinds. Examples are Q4 2018, Mar 2020, the Sep 2019 and Nov 2020 momentum crashes, 2022, the Jul–Aug 2024 yen carry, Apr 2025 tariffs, and 2026 Feb, Mar, Jul–Aug (18 trigger days, the biggest on record), late Aug and Oct. It **missed the one-day DeepSeek shock (2025-01-27)**, which a 10-day sum can't see.
- **Ending (the flag):** 24 rules were tested. In train they beat normal QQQ returns by about 2 pp over 10 days. **None held up in the holdout.** Selling relapsed after 33–65% of flags. Sold earnings beats did **not** rebound harder after an episode ended.
- **Survivorship bias:** all 74 tickers in the universe still trade in 2026. Delisted and acquired names (XLNX, JNPR, ANSS and others) are missing, which flatters the crowded-minus-uncrowded history. A name joins the momentum ranking only after 252 sessions (SNDK in 2026, NBIS from late 2025). PSTG and QRVO were dropped for missing data.
- "Crowded" in the spec basket means 12-1 price momentum, not measured ownership. On 9/30 CRWV ranked in the *uncrowded* tercile. Spec crowded members on 10/22 were SNDK, MU, LITE, WDC, STX, DELL and AMD. MTUM rebalances only twice a year, so its momentum tilt lags.

**Supporting readings (shown, not in the backtest, not used by the badge)**
- **Desk basket:** NVDA AVGO MU CRWV IREN NBIS COHR LITE CRDO MRVL AMD LRCX minus INTU NFLX MSFT XLP XLU XLV (equal weight). Also shows crowded − SMH and how many names lagged SMH.
- **VIX / VIX3M:** CBOE daily CSV and delayed quote, with FRED as fallback. A ratio ≥ 1 is flagged as inverted.
- **25-delta put skew for QQQ and SMH:** UW risk reversal (put IV − call IV, in vol points) on the first monthly expiry at least 20 days out.
- **Short-volume ratio** for the desk crowded names: UW/FINRA, about one session behind. It includes market-maker shorts, so read it as a trend, not as short interest.
- **SOXL creations/redemptions:** UW. Plus means inflow.
- **Mean borrow fee** from the UW borrow archive, which starts 10/13.

**Files and schedule.** Job `com.oid.desk.degross` runs Mon–Fri at **13:50 PT** and again at **17:45 PT**, which picks up late short-volume and SOXL data. The script is `~/oid-score/research/degross.py` and the log is `~/oid-score/logs/degross.log`. Output goes to `~/oid-data/degross/`:
- `degrossing_gauge.csv`: spec columns, append-only. Spreads are stored as decimals, and crowded/uncrowded members are space-separated.
- `degross-YYYYMMDD.json`: one file per session, holding the spec row plus the supporting readings.
- `latest.json`: the newest session, the down-day check, and 130 sessions of history.

The backfill starts 2025-07-01. Episode numbers count from the start of the mini's data window, not the study's.

**Data and differences from the study.** The study used Yahoo adjusted closes. The mini uses Alpaca SIP adjusted closes, which matched the study's 10/22 values to the basis point (MTUM−USMV −12.77%, GVIP−SPY −5.30%, MTUM−SPY −8.05%, crowded−uncrowded −16.61%). Nothing new was subscribed or paid for. FlashAlpha and X are not called. Prime-broker leverage has no feed (only secondhand reports on X), so it is not shown. Values are raw and never smoothed.
