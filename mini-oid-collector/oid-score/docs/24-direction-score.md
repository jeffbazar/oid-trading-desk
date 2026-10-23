# 24 · Direction score (−3…+3): inputs, timers and grading

> **Research and logging only.** The score never places or suggests orders. It is a timestamped guess at which way a stock has the least resistance *right now*, and we grade it afterwards. Built 10/19/2026, config `v1-20261019`. **Page updated Thu 10/22/2026, 9:55 PM PT** (config `v1.2-20261022`: Rule 5 negative-gamma / de-grossing `walls` clamp + Rule 4d downtrend `volume` clamp). Earlier: Tue 10/20/2026, 6:55 PM PT (section 0: the three scores and their on-screen names) and 4:15 PM PT (section 9, light score).

## 0. The three scores and their names (added Tue 10/20/2026, 6:55 PM PT)

The page shows three direction scores. Each is named the same way everywhere (table header, chart lane, chart tooltip, header chips and the badge hover): **name (profile settings-version)**. The short version drops the date; the full settings ID is in the header hover and in `~/oid-data/config/score-config.json`. The live page reads the active IDs from that file (state field `score_versions`) and shows them, so a new settings version renames the column by itself.

| Name on screen | Profile | Settings version (full ID) | Tickers | Inputs | Where it shows |
|---|---|---|---|---|---|
| **Direction (core v1.2)** | core | `v1.2-20261022` | 61 core names | All six (flip, wall room with Rule 5 clamp, volume with Rule 4d downtrend clamp, options flow with the quote-rule C/P, trend, market) | Tile badge, table column 2, chart lane "Direction", chart header chip |
| **Full (sector widefull-v1.0)** | `wide_full` | `widefull-v1.0-20261021` | 144 sector names | Same six and same weights; options flow = 1-min **tick-test** C/P with its quality × 0.5; flip/walls only from on-surge FlashAlpha pulls | Table column 3 (chip F±n), chart lane "Full" |
| **Light (light-v1.0)** | `light` | `light-v1.0-20261021` | 144 sector names | Trend, volume, market only (section 9) | Table column 4 (chip L±n), chart lane "Light" |

**Which settings produced a value.** Every saved row carries the version that made it (`config_version` / `settings_version`). If it differs from the active version, the badge hover says so: on 10/22 `v1.2-20261022` became active (adding the Rule 5 negative-gamma / de-grossing `walls` clamp and the Rule 4d downtrend `volume` clamp; earlier `v1.1-20261020` added the 5 s change log on top of `v1-20261019`). **Momentum** is not a score (it has no −3…+3 scale or weights); it sits just to the right of the score block in the table.

## 1. What the badge means

The **badge next to each ticker** (for example <span style="background:#4ac26b;color:#fff;padding:0 4px;border-radius:3px;font-weight:800">+2</span>) is the latest score.

- **+3:** the path of least resistance is up. **−3:** it is down. **0:** mixed, or not enough evidence.
- **Colors:** green is positive, red is negative, grey is 0.
- **Dashed or faded badge:** not a fresh live reading. The market is closed, the score is a backfill or the last logged row, or it is more than 5 minutes old.
- **Hover:** every input with its value, quality and weight, plus the timestamp and config version.

## 2. The inputs, in plain words

Each input gives three numbers: a **direction** from −1 (down) to +1 (up), a **quality** from 0 to 1 (0 when the data is missing, lower when it is old or low-confidence), and a **weight** from the config file `~/oid-data/config/score-config.json`.

Distances are measured in **ATR** (the stock's normal daily range, 14 sessions, built from the mini's own 1-minute history), so a $30 stock and a $1,600 stock are comparable.

| Input | What it asks | How it is calculated | Weight | Data source | Update timer | Counts less when |
|---|---|---|---|---|---|---|
| **Volume** | Is volume coming in on up-ticks or down-ticks, and is it heavier than normal? | Over the last 15 one-minute bars: the share of volume on up bars minus down bars, scaled up when 15-minute relative volume is above normal (no boost at 0.8× or below, full boost at 2.0× and above). **Rule 4d (`v1.2-20261022`):** clamped to `≤ 0.0` (`min(volume, 0.0)`) when in the Rule 5 regime and `trend < 0`. | **0.75** | 1-minute Alpaca SIP bars on the mini, plus same-minute volume norms (`live-norms-1m.json`) | Every minute (each closed 1-minute bar) | Newest bar older than 3 min: half weight. No closed bar yet: ignored. Positive votes clamped to 0 in negative-gamma / de-grossing downtrends. |
| **Options flow** | Are option buyers paying up for calls or for puts? | Live call-buy ÷ put-buy premium over the last 60 s (the 1m C/P chip). C/P of 3 or more counts as fully bullish, 1/3 or less as fully bearish. If that is thin or stale, it falls back to the Unusual Whales 5-minute (else 15-minute) lean: CALL = +0.5, PUT = −0.5. | **0.50** | Alpaca OPRA option prints (`~/oid-optflow`), fallback UW net premium | C/P recomputed every 1 s; UW lean refreshed every 240 s | C/P older than 60 s: half weight. UW fallback always counts half, and half again when the 5-minute value is missing. |
| **Wall room** | Is there more room up to the call wall or down to the put wall? | Room up = (call wall − price) ÷ ATR; room down = (price − put wall) ÷ ATR. Direction = (up − down) ÷ (up + down). Already above the call wall = +0.3; below the put wall = −0.3. **Rule 5 (`v1.2-20261022`):** clamped to `≤ 0.0` (`min(walls, 0.0)`) below gamma flip or in a de-grossing / missing-flip downtrend. | **0.75** | FlashAlpha walls on the mini (newest of the walls caches the live page uses) | Core names every 10 min, other names every 40 min (rotated) | Walls older than 20 min in market hours: half weight. Either wall missing: ignored. Positive votes clamped to 0 in negative-gamma / de-grossing regimes (keeping −0.3 below put wall). |
| **Gamma flip** | Is price above or below the gamma flip? | Distance from the flip in ATR, squashed so about 0.3 ATR above the flip already reads strongly positive (below is negative). | **1.00** | FlashAlpha walls (same files) | Same as wall room | FlashAlpha marks the flip low-confidence (hollow dot): half weight. Walls older than 20 min: half again. No flip: ignored. |
| **Trend** | Is the stock above VWAP and up over the last 15 minutes? | Half from price vs session VWAP (in ATR), half from the 15-minute price change (in ATR). | **1.00** | 1-minute SIP bars | Every minute | Bars older than 3 min: half weight. |
| **Market** | Is the whole market leaning the same way? | Average of up to three parts: **tape** (the same trend measure on SPY and QQQ), **VIX** (VIX up = bearish, scaled on a 5% move vs prior close), **UW market tide** (change in market-wide call minus put premium over 30 min, scaled on $50M). | **0.75** | SPY/QQQ 1-minute bars; VIX from FlashAlpha (`vix-live.json`); UW market tide | Tape every minute; VIX every 120 s; tide every 240 s | Quality = parts available ÷ 3. VIX older than 15 min or tide older than 20 min is dropped. |
| **News** | Is the last hour of headlines positive or negative? | Net 60-minute headline sentiment (headlines −2…+2, X posts at half weight) ÷ 4. | 0.50 if turned on | Mini news feed (Alpaca/Benzinga, FinBERT) | Headlines arrive in seconds | **OFF.** Not in the live score. Only to be turned on with Jeffrey's OK. |

Macro is color only and never enters the score.

### Regime clamps in `v1.2-20261022` (Rule 5 wall room + Rule 4d volume)

In a normal positive-gamma tape, being just above the put wall with plenty of room up to the call wall is constructive (`walls` approaches `+1.0`). In a negative-gamma selloff or de-grossing tape, however, price pressing down toward the put wall is dealer-accelerated downside — not a mean-reversion buy setup — and 1-minute short-covering spikes (`rvol ≥ 3`) inside an intraday downtrend frequently mark local bounce tops.

Starting in `v1.2-20261022`, `score_lib.py` checks whether a ticker is in a **negative-gamma / de-grossing selloff regime**:
1. **`below_gf`:** `px < gf` (`flip` `d_atr < 0` when gamma flip `gf` is present), **OR**
2. **`degross_mkt_neg`:** the daily de-grossing gauge badge (`~/oid-data/degross/latest.json`, cached in memory with a 5 s `stat()` TTL and safe fallback) is **`DE-GROSSING`** (`degross_armed`) **and** the intraday `market` component is `< 0`, **OR**
3. **`no_gf_downtrend`:** `gf` is `None` (the ~14 symbols without a FlashAlpha gamma flip) **and** `trend < 0` **and** `market < 0`.

When any of the three conditions holds:
- **Rule 5 (`walls` clamp, `clamp_rule5: true`):** `walls_c = min(walls_c, 0.0)`. Positive wall-headroom votes (`+0.01…+1.0`) are clamped to `0.0`, while `−0.3` (price already below the put wall) is preserved.
- **Rule 4d (`volume` clamp, `clamp_downtrend: true`):** When **also** `trend_c < 0`, `volume_c = min(volume_c, 0.0)`. Positive volume-pressure votes during an active downtrend are clamped to `0.0` so short-covering bounce spikes cannot push the composite score bullish, while negative selling-volume votes remain untouched.
- **Breakdown metadata:** When clamped, the component's `f` dict records `regime_clamp`, `clamped: true`, `clamp_reason` (`below_gf`, `degross_mkt_neg`, `no_gf_downtrend`, or `<reason>+trend_neg`), and the pre-clamp `raw_c`.

## 3. From inputs to −3…+3

1. Multiply each input's direction × quality × weight, add them up, and divide by the total weight (4.75). Missing or old inputs pull the result toward 0.
2. Multiply by 3 × 1.5 (the "gain") and cap at ±3.
3. Round to the nearest whole number (halves round away from 0).

So **±3 needs most inputs present, fresh and agreeing.** A ticker without walls (about 40 of the 61) tops out around ±2. Coverage (how much of the evidence was actually there) is saved with every row.

**Worked example, NVDA Mon 10/19 10:00 AM PT (backfill row):** flip +0.10, walls −0.60, volume −0.10, flow 0 (missing), trend +0.07, market −0.37. Sum −0.91 ÷ 4.75 = −0.19; × 4.5 = −0.86, so the badge is **−1**, coverage 74%.

## 4. When the score is computed (current cadence, as of 10/20)

| What | When | Saved? |
|---|---|---|
| **Live badge** | Recomputed about every **60 s** in market hours (the score job checks every 5 s) | **No.** It only updates the tile badge. |
| **Anchor rows** | 6:35, 6:45, 7:00, 7:30, 8:30, 10:00, 11:30, 12:30 PT | Yes, all tickers |
| **Grid rows** | Every **15 min**, 6:45 AM–12:45 PM PT | Yes, all tickers |
| **vol_surge rows** | Whenever the trigger engine logs a volume surge | Yes, that ticker only |
| **Change log (v1.1, from 10/21)** | Score recomputed about every **5 s** in market hours on live price, 1-min bars and options flow (walls and VIX refresh at their own pace) | **Yes:** every change goes to `changes-YYYYMMDD.jsonl`, every ended hold to `episodes-YYYYMMDD.jsonl` |

About 1,600 saved rows a day (all live-page tickers except VIX, WTI and BRENT). Because the live badge is not saved, a score change between two 15-minute rows has no exact saved start or stop time today. That is what the new grading fixes: from 10/21 the 5 s change log saves every change with exact start and stop times. The score math is unchanged (settings `v1.1-20261020` is a logging-only change). On a replay of 10/20 the score changed about **33 times per ticker per hour**, and the median hold was about **40 s**.

## 5. How the score is graded

### New grading: score holds, start to stop (live from 10/21)

- **Every score change is saved the moment it happens**, with its start time. The next change for that ticker closes it with a stop time. That stretch is one **hold**.
- **Each hold is graded from its start to its stop:**
  - **Move:** price at the stop vs price at the start.
  - **Peak:** the best price during the hold, in the score's direction.
  - **Trough:** the worst price during the hold, against the score.
  - **Duration:** how long the score held, in seconds.
  - A hold counts as **right** when the stock moved the way the score said.
- **Secondary check:** the move **5, 15, 30 and 60 seconds** after each change, whether or not the score still holds. It is worked out after the session by the daily scorecard (about 1:10 PM PT), never live, so nothing looks ahead. Base = close of the last 5-second bar at or before the change; each check = close of the last 5-second bar at or before change + 5/15/30/60 s (so +5 s means the next 5-second bar). Saved per change as `changes-fwd-YYYYMMDD.jsonl` and shown as its own table in the scorecard.
- **Hours and the close are no longer used.** The score is about the next move while it holds, so fixed windows like +1h, +2h, the close and the next open are dropped from grading.
- Prices come from the mini's 5-second bars for all 61 tickers.

### Context saved with every score change (live from 10/21)

- **Live C/P ratio:** call-buy ÷ put-buy premium over the last **15 s** and **1 min**.
- **Volume surge:** 1-minute relative volume (rvol_1m), with **3× normal or more** flagged as a surge.
- **Wall room:** distance to the call wall and to the put wall in ATR, plus how old the wall reading is.
- **Momentum state:** speeding up, slowing down, resuming or quiet (from the momentum detector, page 25).
- **Stock tape:** the stock's own move over the last **60 and 120 s**.
- **Market tape:** whether SPY and QQQ are moving the same way at that moment.

### Buffered score: comparison-only shadow

The **raw score is the score**, everywhere: the change log, episodes, the badge (`latest.json`), the live page and the scorecard. Flipping back and forth is expected and fine.

For comparison only, the change log also keeps a **buffered** version of the score. It only moves when the raw value clears the rounding cutoff by an extra **0.15** (for example +1 → +2 needs raw above 1.65, and +1 → 0 needs raw below 0.35). It is saved as `buffered_score` on each change row and as its own holds in `episodes-buffered-YYYYMMDD.jsonl`. The scorecard shows one "buffered vs raw" line. The buffered score is never shown on the badge or used to grade the score.

### Daily scorecard (live from 10/21)

Runs on the mini at about **1:10 PM PT** each weekday. Results go to Jeffrey in chat at about **1:20 PM PT**, best combo first, compared with earlier days.

For each combo: how often the stock moved the score's way during the hold, the typical move, the best move inside the hold, and how many cases.

| Combo | What it tests |
|---|---|
| Score alone | The baseline every other row is compared to |
| Score × volume surge | Score fired with 1-minute volume at 3× normal or more |
| Score × C/P agrees | Live C/P leans the same way as the score |
| Score × wall room | Plenty of room before the wall the score points at, vs already pressed against it |
| Score × momentum | Score fired during a speed-up or resume, vs during a slowdown |
| Score × stock tape agrees | The stock's last 60/120 s already moving the score's way |
| Score × market agrees | SPY/QQQ moving the score's way |
| Surge + C/P agrees + wall room | All three together: the setup closest to Jeffrey's own trades |
| Score × held before acting | Wait 0, 15, 30, 60, 120 or 300 s after the score starts, then enter only if it has not changed yet |

**Score × held before acting** (added 10/20). This asks: if you wait for the score to hold before you act, does it do better?
- For each wait (0, 15, 30, 60, 120 and 300 seconds), only holds that lasted **longer** than the wait count. A hold that changed before or exactly at the wait is skipped, because you would never have entered it.
- Pretend entry is the price at start + wait: the close of the last 5-second bar at or before that moment. Nothing after that moment is used to pick the entry.
- The move is measured from that entry to the end of the hold (the next score change, or the 1:00 PM PT close), in the score's direction.
- Each row shows: holds, the share of the wait-0 holds still alive at that wait, % that went with the score, median and mean gain (bp), mean best and mean worst move after entry (bp, from 5-second bar highs and lows), and the median time left in the hold after entry.
- Wait 0 is the plain hold from its start, the same numbers as "Score alone".
- Rows: ±1, ±2, ±3, all nonzero, then ±2 and ±3 with a volume surge (1-minute volume at 3× normal or more at the start), and ±2 and ±3 that started during a momentum resume or speed-up.
- Any row with fewer than 20 holds is marked **small sample**.

### Old grading (through 10/20, retired as the main measure)

The `score-grade` job (every 15 min) graded each saved 15-minute row at fixed windows: +5m, +15m, +30m, +1h, +2h, the close and the next open. That mixed the score's call with whatever happened hours later, so it no longer judges the score.

**First read, 10/20 (Research Bot):** on the 15-minute rows, nonzero scores went the score's way in only **36% of 624 holds**, median −0.10%. Holds fired during a volume surge did better (45% vs 35%), but that is only 31 cases. This is one day, timed only to 15-minute rows, so it is a lead to keep checking, not evidence.

## 6. Testing a change to the score

All weights, scales and staleness limits live in `~/oid-data/config/score-config.json`. The score job reloads it automatically, and every row is stamped with its `config_version`.

- **Try a variant:** copy the config to `score-config.<name>.json`, change it, give it a new version, then run `python3 score_report.py --mode all --config <that file>`. It re-scores all saved history from the stored raw measures, without touching live.
- **Drop one input at a time:** `python3 score_report.py --mode all --ablate`.
- **Promote a winner:** edit the live config and bump the version.

## 7. Files and jobs

| What | Where |
|---|---|
| Code | `~/oid-score/` |
| Config | `~/oid-data/config/score-config.json` |
| Saved rows | `~/oid-data/score/scores-YYYYMMDD.jsonl` |
| Grades | `~/oid-data/score/outcomes-YYYYMMDD.jsonl`; reports in `~/oid-data/score/reports/` |
| Badge feed | `~/oid-data/score/latest.json` (read by the live page) |
| Change log (v1.1) | `~/oid-data/score/changes-YYYYMMDD.jsonl` (one row per score change) and `episodes-YYYYMMDD.jsonl` (one row per hold); code `score_changes.py` |
| Buffered shadow | `~/oid-data/score/episodes-buffered-YYYYMMDD.jsonl` (comparison only) |
| Scorecard | `~/oid-data/score/scorecard-YYYYMMDD.json` / `.md` (`daily_scorecard.py`) |
| Replay | `score_replay_changes.py <date>` → `~/oid-data/score/replay-YYYYMMDD/` |
| Jobs | `com.oid.desk.score` (always on, idle outside market hours), `com.oid.desk.score-grade` (every 15 min) and `com.oid.desk.score-scorecard` (weekdays 1:10 PM PT) |
| Light score (Sector watch, section 9) | `score_wide.py` (job `com.oid.desk.score-wide`, always on); `changes-wide-*`, `episodes-wide-*`, `episodes-wide-buffered-*`, `changes-wide-fwd-*`, `latest-wide.json`, `scorecard-wide-YYYYMMDD.json/.md`; replay `score_replay_wide.py <date>` → `replay-YYYYMMDD-wide/` |

The score makes **no** paid data calls of its own. It only reads files that other mini jobs already write. Every timer is listed on page 27, Timers.

## 8. Direction arrows next to the live numbers (added 10/20, live from 10/21)

Two small arrows sit next to numbers that are already on every core tile. They never hide, replace or smooth any number. They only show which way that number is heading right now.

**Volume direction** (next to the tile's "1m" volume, and in the Table's 1-min vol column)
- Compares the share rate of the **last 15 seconds** with the rate of the **60 seconds before that** (15–75 s ago), from the mini's per-second SIP trade prints (the same prints that build the 5-second bars).
- **▲** gaining: the 15 s rate is at least **1.3×** the prior-60 s rate. **▼** losing: **0.7×** or less. **–** in between. The small number is the ratio.
- **·** thin: fewer than **500 shares** across the whole 75 s, so no direction is shown.

**C/P direction** (right after the 15s and 1m C/P chips)
- Compares each live aggressor C/P (call-buy ÷ put-buy premium, page 21) with its own reading **about 60 seconds ago** (any reading 45–75 s old, closest to 60 s).
- **▲** toward calls: C/P rose by **0.10** or more. **▼** toward puts: fell by **0.10** or more. **–** otherwise.
- **STRONG** (solid green or red, with the from→to values in small text): C/P **at least doubled or halved**, or moved **more than 0.5**, within that 60 s.
- Floor, so thin prints never trigger it: both readings (now and 60 s ago) need at least **8 prints and $15K** of call+put-buy premium for 15s, or **20 prints and $40K** for 1m. Below the floor the arrow shows **·**. Ratios above 20 (or ∞) are treated as 20.
- Hover or tap the arrow for from → to, the change, and the prints and premium behind it.

Both are research only. They run in market hours only, are computed every **1 s** on the mini, and the page redraws them at least every **5 s**. The thresholds sit in one config block (`DIR_CFG` in `livepage.py`) and are also sent to the page as `dir_cfg`.

## 9. Light score for the Sector watch names (added 10/20, live from 10/21)

A second, separate direction score for the **144 Sector watch names** (healthcare, crypto, energy, airlines and the rest), so we can see whether non-tech names give more ±2/±3 setups. It is called the **light score** (profile `light`, settings `light-v1.0-20261021`) because it uses only the inputs those names actually have. It never mixes with the core score: own job, own files, own scorecard.

**Inputs (same calculations and weights as the core, section 2):**

| Input | Weight | Data for the wide names |
|---|---|---|
| **Trend** (price vs VWAP + 15-min change, in ATR) | **1.00** | 1-minute SIP bars from the wide collector tier (`~/oid-quote/cache/bars-wide/store/live/`), ATR(14) from the wide 1-minute history |
| **Volume** (up vs down volume over 15 bars, boosted by 15-min rvol) | **0.75** | Same bars + the wide same-minute norms (`~/oid-quote/cache/bars-wide/live-norms-1m.json`) |
| **Market** (SPY/QQQ tape, VIX, UW market tide) | **0.75** | Exactly the core's market input (same SPY/QQQ bars, VIX and tide files) |
| Gamma flip, wall room, options flow, news | off | The wide names have no live walls or options flow, so these are switched off, not set to zero |

**From inputs to −3…+3:** the same three steps as section 3, but the total weight is the three inputs that are on, **2.50** instead of 4.75. That is what keeps the range at −3…+3 (it is renormalized, not squeezed):
- light value = (1.00 × trend + 0.75 × volume + 0.75 × market, each × its quality) ÷ 2.50
- raw = light value × 3 × 1.5, capped at ±3; score = raw rounded (halves away from 0)
- So ±2 needs the weighted inputs to average at least 0.33 in one direction, and ±3 at least 0.56. With fewer inputs each one counts for more (trend 40%, volume 30%, market 30%), so the light score reaches ±2/±3 more easily than the core. **Light and core numbers are not directly comparable.**

**Timer:** re-scored every **5 s** in market hours (Nice 10), on the collector's live last price (or the last 5-second bar close), closed 1-minute bars (re-read every 20 s) and the market input. Raw and unsmoothed. Holds still open at 1:00 PM PT close then.

**What is saved (separate files, `~/oid-data/score/`):**
- `changes-wide-YYYYMMDD.jsonl`: one row per light-score change (same fields as the core change log).
- `episodes-wide-YYYYMMDD.jsonl`: one row per ended hold: start/stop time and price, peak and trough from the wide 5-second bars, context at start and stop.
- `episodes-wide-buffered-YYYYMMDD.jsonl`: the comparison-only buffered shadow (band 0.15), same rule as the core.
- `changes-wide-fwd-YYYYMMDD.jsonl`: the +5/15/30/60 s check, written after the session by the scorecard.
- `latest-wide.json`: the live page feed, rewritten every pass. `changes-wide-state.json` lets a restart resume open holds.
- Every row is tagged `score_profile: "light"`, `profile_version`, `sector_id` and `sector`.
- Context per change: rvol_1m and surge (3× or more), the stock's 60/120 s tape, SPY/QQQ 60/120 s tape and agree flags. C/P, wall room and momentum are logged as missing, because the wide names have none.

**Daily scorecard:** the same weekday **1:10 PM PT** job writes a separate `scorecard-wide-YYYYMMDD.json/.md` with every core section (score alone, × surge, × C/P, × wall room, × momentum, × stock tape, × market, surge + C/P + room, buffered vs raw, the 5/15/30/60 s check, held before acting) plus **score × sector** and a **±2/±3 count by sector** table. The C/P, wall-room and momentum sections read "missing" by design; they are kept so the two cards line up. Prices for grading come from the wide 5-second bars, or the 1-minute bars where 5-second bars are missing (coarser).

**On the live page:** each Sector watch row has a small dashed **L±n** chip in the "Light" column (green up, red down, grey 0, faded if the feed is over 30 s old, hidden after 15 min). Hover shows the raw value and how long the score has held. The Sector watch sort menu has "Light score (strongest first)". Nothing existing was removed.

**First replay, 10/20 (1-minute resolution only, because the wide 5-second stream started after the close, at 3:08 PM PT):** 144 names, about 16 changes per name per hour, median hold 120 s. ±2 showed up in 3,028 holds and went the score's way 38.7% of the time; ±3 in 683 holds, 43.0%. Healthcare had the most ±2/±3 (261 and 66). ±3 holds that lasted 5 minutes before acting went the right way 54% of the time (219 holds). One day at coarse resolution: a lead, not evidence. Tomorrow's live log is the first real seconds-level test.

**Changing it:** `~/oid-data/config/score-config.json` → `profiles.light`. Add or drop inputs in `components_enabled` (optional per-input `weights`), bump `config_version`; the job reloads it automatically. WDC, STX and SNDK are excluded. Code: `score_wide.py` (live), `score_replay_wide.py <date>` (replay), job `com.oid.desk.score-wide`.
