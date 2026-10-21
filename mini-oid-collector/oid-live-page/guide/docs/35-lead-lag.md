# 35 · Lead-lag: leader → follower (shadow)

**Status: shadow only.** It logs predictions and grades them each night. It never feeds a live score, sends an alert or places a trade. Added 2026-10-21 (`ll-v1-20261021`). It extends the chart-pattern detector (page 34).

## The idea

On 10/21, MU was rejected at the open (the pattern detector logged a 5m gap-up fill at 6:40 AM PT). Memory and semi names (DRAM, SKHY, SOXX, SMH, EWY, AMD) faded right after. The question is whether we can see that coming for a name's *followers*.

When a **leader** fires a directional pattern event, the detector logs the expected move of each of its mapped **followers**:

- the predicted direction
- the expected lag
- the horizon
- a probability with its sample size n

Leader events are the pattern detector's *triggered* records for these patterns:

- breakout
- breakdown
- failed_breakout (a rejection)
- failed_breakdown
- gap fill (gap_up −1, gap_down +1)
- vwap_loss
- vwap_reclaim

## Who follows whom: the map (`~/oid-data/patterns/leadlag-map.json`)

The map is built from 1-min regular-hours bars for all 205 tracked tickers over 26 sessions (9/15 to 10/20). IBIT stands in for BTC; it trades regular hours only.

- **c5**: the 5-minute return correlation. This is the relationship itself.
- **c_lags[k]**: corr(leader return at t, follower return at t+k) for k = 1–10 min. **lag_min** is the k with the strongest same-sign value.
- **lead_t**: the sum of c(1..10) divided by its null standard error. **asym_t** is leader→follower minus follower→leader.
- **beta5**, **n_1m**, **n_5m**, and whether the pair is in the same live-page sector.
- **Followers of A**: |c5| ≥ 0.30 and lead_t > −2, ranked by |c5| + 0.05·lead_t + 0.03 if same sector. Top 12 are kept, and the live detector uses the top 8. Every ticker also lists its **leaders** (the reverse index) and its top 25 **pairs**.

**Honest read:** the lagged 1-minute correlations are tiny (about 0.02–0.05). Followers mostly move *with* the leader inside the same minute or two, not 5–10 minutes later. Only about 13% of mapped pairs (258 of 2,003) have lead_t > 3. Read lag_min as "roughly how long," not as a timer.

Examples from the 10/21 build:

- **MU → followers:** DRAM 0.89, SNDK 0.75, SOXX 0.71, SKHY 0.70, SMH 0.69, EWY 0.69, XLK 0.62, TQQQ 0.61, QQQ 0.61, AMD 0.57, WDC 0.55, KLAC 0.44. KLAC is the only one with a real lag (lead_t 3.2).
- **WULF ← leaders:** IREN 0.77, CLSK 0.80, CIFR 0.80, APLD 0.79, CORZ 0.73, RIOT 0.75, MARA 0.75, NBIS 0.60, CRWV 0.56, HOOD 0.40, CBRS 0.38, COIN 0.39. MU is not a WULF leader. IBIT (BTC) is 0.36 with lead_t 2.5, so it sits in WULF's pairs but just outside its top 12. BE is not in WULF's top 25.

## Probability (`~/oid-data/patterns/leadlag-rates.json`)

A follower **hit** means it moved the predicted way (log return > 0 bp) from the close of the leader's event bar to the end of the horizon:

- 15 min for 1m events
- 30 min for 5m events
- 60 min for 30m events

The predicted direction is the leader's direction × sign(c5). Rates are keyed by `pattern|interval|leader direction|bucket`:

- **c50**: |c5| ≥ 0.5
- **c30**: |c5| 0.30–0.50
- **neg**: an inverse relationship

**backtest = out of sample.** The map is rebuilt from sessions before 10/6 only, then graded on leader events from 10/6 to 10/20 (38,539 events, 268,077 follower predictions). An in-sample run is kept beside it as `backtest_insample`, and per-pair in-sample rates are kept as `backtest_pairs`. **The live hit rate takes over once live n ≥ 20.** Both rates are kept. Rates are raw, not calibrated, and a coin flip is 50%. n overstates independence because many tickers fire in the same minute.

What the out-of-sample backtest says:

- **Overall: 49.5%** (n = 268,077), which is a coin flip. Most events tell you nothing about the followers.
- **Gap fills carry over:** a leader's gap-up fill (5m, −1) → followers fade **63.0%** (c50, n = 934; mean +25 bp) and **59.6%** (c30, n = 832). A gap-down fill → followers bounce 55.0% (c50, n = 1,419).
- **Rejections on longer bars:** failed_breakout 5m → followers down 54.3% (c50, n = 3,769). On 30m it is 60.6% (c50, n = 695).
- **Weaker than a coin flip:** 1m vwap_reclaim (44.1%, c50, n = 16,591), failed_breakdown 5m and 30m (43–46%), and breakout 30m (42.3%).
- The follower rate tracks whether the *leader itself* follows through (the `leader_follow_through` column). This is co-movement, not a hidden lag.

## Live (`com.oid.desk.leadlag`, `leadlag.py daemon`)

The daemon runs at each 1-min bar close + 25 s in regular hours. It reads new triggered records from today's pattern archive (`part-patterns-live-*.jsonl`), so it adds nothing to the pattern daemon or any score pass. For each record it writes one prediction per follower to `~/oid-data/archive/leadlag/date=D/part-leadlag-live-<n>.jsonl`.

Each prediction includes:

- pred_id, leader, follower, pattern, interval, direction, f_dir
- c5, lag_min, lead_t, horizon, the follower's price at the event bar close
- prob_est, its source and n, plus the in-sample pair rate and n
- a wall tag: `call_wall_rejection`, `call_wall_breakout`, `put_wall_bounce` or `put_wall_breakdown`. This tag uses the *current* FlashAlpha walls file and is context only, not part of any rate.

The daemon also rewrites `~/oid-data/patterns/leadlag-live.json` with active predictions per follower and the latest 30 leader events. Restarts are safe because pred_ids already in today's archive are skipped. On startup it catches up on the day's events, using prices from the event time and setting `catchup: true`. Kill switch: `touch ~/oid-data/patterns/leadlag-disabled`.

**Live page:** the **Lead-lag** column, right after Patterns, shows ▲/▼, the leader and the raw prob. Hover for the pattern, wall tag, n, lag and window. It reads `/leadlag.json` (live once the page server restarts after hours), and otherwise the read-only copy at `/guide/ll/leadlag-live.json`.

**Feature registry / score_features (shadow):** `leadlag_active`, `leadlag_signal`, `leadlag_prob`, `leadlag_prob_n`, `leadlag_prob_src`, `leadlag_leader`, `leadlag_lag_min`, `age_ll`. Rows start carrying these at the score daemons' next restart, which is after hours and never during the session.

## Nightly

- **1:50 PM PT, `com.oid.desk.pattern-grade`:** `pattern_learn.py grade` also runs `leadlag.grade`. It labels every live prediction into `archive/leadlag_labels/date=D/`, refreshes the `live` rates, writes `leadlag-scorecard-D.{md,json}`, and appends one row to `experiments.jsonl`.
- **2:10 PM PT weekdays, `com.oid.desk.leadlag-build`:** rebuilds the map and the backtest. It uses `~/oid-score/venv-leadlag` (numpy) and takes about 1 minute.
