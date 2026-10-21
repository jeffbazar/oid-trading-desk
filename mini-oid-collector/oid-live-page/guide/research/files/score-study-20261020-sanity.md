# Sanity summary: direction-score data (pulled 2026-10-20 1:13 PM PT, after the 1:12 PM PT grade run)

## Live 2026-10-20 (mode=live, config v1-20261019): 1,610 rows, 61 tickers, 6:35 AM to 12:45 PM PT
| score | -3 | -2 | -1 | 0 | +1 | +2 | +3 | total |
|---|---|---|---|---|---|---|---|---|
| rows | 4 | 47 | 178 | 591 | 601 | 181 | 8 | 1,610 |
| anchor | 2 | 30 | 85 | 165 | 127 | 74 | 5 | 488 |
| grid | 2 | 14 | 91 | 425 | 469 | 94 | 3 | 1,098 |
| vol_surge | 0 | 3 | 2 | 1 | 5 | 13 | 0 | 24 |

Graded horizons, per bucket. Every bucket is fully graded at 15m/30m/60m/120m/close.
| h | graded | pending |
|---|---|---|
| 5m | 1,608 | 2 (one -1, one 0; bars missing, effectively final) |
| 15m, 30m, 60m (1h), 120m (2h), close | 1,610 each | 0 |
| next_open | 0 | 1,610 (fills after the 10/21 open, on the first grade run after 6:30 AM PT) |
Truncated at the close: 5m 19, 15m 17, 30m 77, 60m 199, 120m 442.

## Backfill 2026-10-19 (mode=backfill, replayed): 1,606 rows, 61 tickers
Buckets: -3: 1, -2: 30, -1: 410, 0: 767, +1: 351, +2: 47, +3: 0. All horizons graded, including next_open (5m: 1,601 of 1,606).

## Note from the mini's own grade report (reports/summary-20261020-live.json), not our study
On 10/20 the score was inversely related to forward returns. Hit rate on nonzero scores: 5m 34%, 60m 32%, close 27.5%. Correlation of raw score with the close return: -0.39. One session of 61 highly correlated tickers, so this is an anecdote and not evidence.
