# Wall-magnet study (2026-10-20)

**Question.** Jeffrey's observation was: "If price is above the call floor it gets pulled into the call floor. Right above a put wall it gets pulled into the put wall. If neither, it lives in limbo unless volume picks up."

**Short answer, from 82,190 ticker-minutes over 325 ticker-days (9/25 to 10/20):**
- **The pull is weak.** After price sits just above a wall, it drops to that wall about as often as it would drop the same distance at any random minute.
  - Above the call wall, it touches the wall about 3 points more often than chance over 5 and 15 minutes. That edge is gone by 30 minutes.
  - Above the put wall, the touch rate is at chance or slightly below it.
- **"Limbo" is not specific to the middle.** Price is not more range-bound when it is away from the walls. If anything, the opposite holds: price sitting just above a wall is a bit more range-bound (54–56% vs 48%), which looks like mild pinning.
- **Volume is the real switch, and it works in all three states.** A 1-minute rvol of 3× or more roughly triples the odds of a breakout everywhere. Away from the walls, 15-minute breakouts go from 8.7% to 26.7%.

## Definitions
- **Walls.** These are FlashAlpha `call_wall` / `put_wall` values (from `/v1/flow/levels`). They were harvested from every stored snapshot that has an as-of time: the desk repo `tmp/fa-walls-*`, `market-data/latest/bak`, `cache/mini-fa-walls-pulse.json`, the chart-bot raw files, and the mini 10/20 replay's per-change wall context. The result is `walls_history.csv`: 1,045 snapshots, about 20 core names a day from 10/1 to 10/19 and 59 names on 10/20.
  - For each minute, the study uses the **latest snapshot taken earlier the same day**, so it never looks ahead.
  - The field `wage` is the wall age.
- **"Call floor".** No desk file uses this term. Here it means the **call wall when price is above it**, so the call wall acts as a floor under price.
- **Price and ATR.**
  - Price comes from 1-minute SIP regular-session bars, from the mini store `~/oid-desk/desk/cache/bars/store`.
  - ATR is the 14-day daily ATR from the days before, the same as the score engine.
- **rvol_1m.** This is the minute's volume divided by the median volume of the same minute over the previous 10 sessions.
- **States, for each ticker-minute and each X in {0.25, 0.5, 1.0} ATR:**
  - `CALL_ABOVE`: price is at or above the call wall and within X ATR of it.
  - `PUT_ABOVE`: price is at or above the put wall and within X ATR of it, and the minute is not already CALL_ABOVE.
  - `NEITHER`: everything else.
  - Reference states, which also count inside NEITHER: `CALL_BELOW` and `PUT_BELOW`, meaning price is just under a wall, within X ATR.
- **Outcomes over the next 5, 15 and 30 minutes.** A minute only counts if the full window fits before the close.
  - `touch`: the minute low comes within 0.02 ATR of the wall. For the BELOW states, the minute high does.
  - `chance_touch`: how often the same ticker travels that same distance downward in the same window from *any* minute. This is the no-magnet baseline.
  - `mirror_up_same_dist`: how often price travelled the same distance *up* instead.
  - `closer`: price ends the window nearer the wall than it started.
  - `through`: the window closes more than 0.05 ATR past the wall.
  - `range`: the window's high-to-low span is below that ticker's median span for that window length. About 50% of all minutes qualify by construction.
  - `breakout`: price moves at least 0.10 / 0.18 / 0.25 ATR (5 / 15 / 30 min) from the start, in either direction.
- **Two samples.**
  - "all minutes" counts every minute. Neighbouring minutes overlap heavily, so the real independent sample is closer to the number of ticker-days and visits.
  - "first minute of each visit" counts each entry into a state once.

## Headline numbers (X = 0.5 ATR, all minutes)
| State | Window | Minutes | Ticker-days | Touch wall | Chance | Ends closer | Range | Breakout | Breakout, rvol<2 | Breakout, rvol≥2 | Breakout, rvol≥3 (n) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Just above call wall | 5m | 1,843 | 56 | 46.9% | 44.9% | 50.6% | 50.6% | 12.7% | 10.2% | 22.8% | 34.7% (150) |
| | 15m | 1,693 | 54 | 58.6% | 55.7% | 52.0% | 54.0% | 9.6% | 8.0% | 16.1% | 18.8% (144) |
| | 30m | 1,457 | 50 | 61.4% | 63.0% | 49.5% | 56.5% | 9.3% | 7.8% | 14.9% | 14.3% (126) |
| Just above put wall | 5m | 28,272 | 190 | 9.2% | 9.9% | 50.5% | 54.2% | 8.7% | 7.4% | 16.9% | 19.0% (1,702) |
| | 15m | 27,119 | 187 | 14.5% | 15.3% | 51.4% | 54.1% | 7.4% | 6.4% | 13.9% | 15.3% (1,667) |
| | 30m | 25,413 | 187 | 19.7% | 20.4% | 52.5% | 54.1% | 7.6% | 6.4% | 14.8% | 16.7% (1,584) |
| Neither | 5m | 50,450 | 277 | – | – | – | 47.8% | 12.2% | 9.5% | 25.0% | 30.6% (3,973) |
| | 15m | 48,503 | 276 | – | – | – | 47.9% | 11.0% | 8.7% | 21.7% | 26.7% (3,903) |
| | 30m | 45,583 | 274 | – | – | – | 48.0% | 11.2% | 8.8% | 21.6% | 27.2% (3,745) |

Other X values (0.25 and 1.0 ATR) tell the same story. Full tables are in `results.csv` and `results.json`.

**With a surge, the touch rate rises but so does chance.** At rvol≥3, above the call wall at X = 0.5, the touch rates were:
- 15 minutes: 66.0% vs 63.7% chance;
- 30 minutes: 64.3% vs 68.6% chance.

## Caveats
- **Small sample above the call wall.** There are only about 150 visits on 54 ticker-days, because price rarely trades above its call wall. A 3-point edge is well within noise at that size.
- **10/20 alone is tiny:** 24 minutes on 3 ticker-days above the call wall. It can't be judged by itself.
- **Wall freshness.** Before 10/20, walls came from routine snapshots, about 4–6 a day. A wall may have shifted between snapshots, although on 10/20, 48 of 59 names never changed walls all day.
- **Coverage.** The study uses 1-minute bars only. The 5-second archive covers just 10/19–10/20, and its extra detail matters little at 5–30 minute horizons.
- **No sector names.** They had no FlashAlpha walls.

## Files
- `harvest_walls.py` builds `walls_history.csv` from the desk repo and `raw/wm-ctx-walls.jsonl`, which holds the mini replay wall context for 10/20.
- `wall_magnet_study.py` produces `results.csv` and `results.json`.
- `raw/` holds the copies from the mini: the 1-minute store (`store/*-1m.json`), `live-norms-1m.json` and the replay wall context.
