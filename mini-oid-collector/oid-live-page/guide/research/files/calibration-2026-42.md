# Calibration 2026-42 (Rose / Hal)

Week 2026-10-12 12:00 AM PT → 2026-10-19 12:00 AM PT · generated 2026-10-16 1:45 PM PT
Scorekeeping only. This report changes no trading rule, threshold or seat.
Calls logged this week: 230 (with confidence 230; Rose 33, Hal 197).

## Cumulative summary

| Group | Decided | Win rate | Scored | Mean conf | Hit rate (scored) | Brier | ECE | Backfill | Best-effort |
|---|---|---|---|---|---|---|---|---|---|
| overall | 178 | 43% | 118 | 36% | 34% | 0.2241 | 0.0228 | 60 | 103 |
| overall · taken | 70 | 59% | 10 | 49% | 50% | 0.2435 | 0.07 | 60 | 0 |
| overall · passed | 103 | 32% | 103 | 34% | 32% | 0.2215 | 0.0237 | 0 | 103 |
| Rose | 51 | 51% | 18 | 41% | 22% | 0.2081 | 0.1894 | 33 | 13 |
| Rose · taken | 37 | 65% | 4 | 45% | 50% | 0.2538 | 0.2 | 33 | 0 |
| Rose · passed | 13 | 15% | 13 | 42% | 15% | 0.2083 | 0.2662 | 0 | 13 |
| Hal | 127 | 39% | 100 | 35% | 36% | 0.227 | 0.0412 | 27 | 90 |
| Hal · taken | 33 | 52% | 6 | 52% | 50% | 0.2367 | 0.1833 | 27 | 0 |
| Hal · passed | 90 | 34% | 90 | 33% | 34% | 0.2235 | 0.0224 | 0 | 90 |

'passed' = rejects/no-trades/watches; their win rate means 'the skipped setup worked'.

## Reliability · overall

| Bucket | n | Predicted | Actual | Gap |
|---|---|---|---|---|
| <0.5 | 106 | 34% | 33% | +1% |
| 0.5-0.6 | 8 | 52% | 38% | +14% |
| 0.6-0.7 | 2 | 60% | 50% | +10% |
| 0.7-0.8 | 0 | — | — | — |
| 0.8-0.9 | 2 | 80% | 50% | +30% |
| 0.9-1.0 | 0 | — | — | — |

Flags: OVERCONFIDENT in 0.5-0.6: said 52%, hit 38% (n=8)

## Reliability · Rose

| Bucket | n | Predicted | Actual | Gap |
|---|---|---|---|---|
| <0.5 | 13 | 37% | 15% | +21% |
| 0.5-0.6 | 4 | 51% | 50% | +1% |
| 0.6-0.7 | 1 | 60% | 0% | +60% |
| 0.7-0.8 | 0 | — | — | — |
| 0.8-0.9 | 0 | — | — | — |
| 0.9-1.0 | 0 | — | — | — |

Flags: OVERCONFIDENT in <0.5: said 37%, hit 15% (n=13); OVERCONFIDENT overall: mean confidence 41% vs hit rate 22% (n=18); SMALL SAMPLE: n=18 scored calls < 20; not significant

## Reliability · Hal

| Bucket | n | Predicted | Actual | Gap |
|---|---|---|---|---|
| <0.5 | 93 | 33% | 35% | -2% |
| 0.5-0.6 | 4 | 52% | 25% | +28% |
| 0.6-0.7 | 1 | 60% | 100% | -40% |
| 0.7-0.8 | 0 | — | — | — |
| 0.8-0.9 | 2 | 80% | 50% | +30% |
| 0.9-1.0 | 0 | — | — | — |

Flags: none

## Definitions

- **confidence**: stated P(setup works); for REJECT/NO_TRADE/WATCH = P(the skipped setup would have worked)
- **binary**: win=1, loss=0, expired=0; scratch and open excluded
- **brier**: mean (confidence - outcome)^2; 0 perfect, 0.25 = always saying 50%
- **ece**: sum over buckets of n_b/N * |predicted - actual|
- **overconfident_flag**: predicted - actual > 10% (bucket needs n>=5)
- **significance**: n<20 scored calls = not significant
- **win_rate**: includes backfilled seats (confidence=null); calibration metrics use scored calls only
