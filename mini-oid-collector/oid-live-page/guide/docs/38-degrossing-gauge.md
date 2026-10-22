# 38 · De-grossing gauge (is the hedge-fund selling still on?)
[← Index](README.md)

> Added **Thu 10/22/2026, 3:05 PM PT**. Shown as the **De-grossing gauge** section at the top of the `/credit` tab ([36](36-credit-betas.md)). Data endpoint: `/degross.json`. Built to Research Bot's 10/22 backtest and spec (copy in `~/oid-score/research/degross-study/`). Research only, not an order signal.

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
