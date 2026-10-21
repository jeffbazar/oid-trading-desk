# Direction score scorecard — 2026-10-20

Source: **episodes (episodes-20261020.jsonl)** (13094 holds). Episodes from /Users/jake/oid-data/score/replay-20261020/episodes-20261020.jsonl.

Gain = start-to-stop move in the score's direction. Peak/trough = best/worst move in the score's direction during the hold. ±1/±2/±3 = score of that size in either direction, gains signed to the score. Score 0 has no direction, so its gain columns are blank. Times PT.

## Score alone

| score | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---:|---:|---:|---:|---:|---:|---:|
| -3 | 15 | 26.7 | -1.1 | -1.9 | 8.2 | -5.1 | 20 |
| -2 | 322 | 34.2 | -1.2 | -4.2 | 10.2 | -10.5 | 30 |
| -1 | 1883 | 35.8 | -1.4 | -1.7 | 8.5 | -7.7 | 30 |
| 0 | 4986 | – | – | – | – | – | 40 |
| 1 | 4627 | 39.3 | -1.1 | 0.1 | 8.7 | -7.2 | 45 |
| 2 | 1230 | 37.7 | -1.6 | 3.5 | 17.1 | -8 | 40 |
| 3 | 31 | 38.7 | -4.6 | -1.9 | 20.2 | -15.8 | 60 |
| all nonzero | 8108 | 38 | -1.3 | 0 | 10 | -7.6 | 40 |

## score x surge (rvol_1m >= 3)

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| no | all nonzero | 7823 | 38 | -1.3 | 0 | 9.9 | -7.5 | 35 |
| no | ±1 | 6323 | 38.3 | -1.2 | -0.5 | 8.5 | -7.3 | 40 |
| no | ±2 | 1471 | 36.7 | -1.6 | 1.9 | 15.6 | -8.3 | 35 |
| no | ±3 | 29 | 34.5 | -1.7 | -1.9 | 12 | -8.4 | 60 |
| yes | all nonzero | 285 | 40 | -1.1 | 1.5 | 14.1 | -9.6 | 50 |
| yes | ±1 | 187 | 39.6 | -1.2 | 1.5 | 11.7 | -8.1 | 50 |
| yes | ±2 | 81 | 42 | -0.7 | 2.3 | 17.7 | -11 | 45 |
| yes | ±3 | 17 | 35.3 | -2.3 | -1.8 | 23.6 | -18.9 | 45 |

## score x C/P agrees

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| missing | all nonzero | 3053 | 30.6 | -2.5 | -0.9 | 11.5 | -8.7 | 40 |
| missing | ±1 | 2703 | 30.6 | -2.3 | -1.2 | 10.2 | -8.6 | 40 |
| missing | ±2 | 349 | 30.9 | -3.8 | 1.4 | 22.2 | -9.7 | 40 |
| missing | ±3 | 1 | 0 | -14.3 | -14.3 | 12.9 | -20.9 | 90 |
| no | all nonzero | 845 | 46 | -0.4 | 1.5 | 9.8 | -7.2 | 45 |
| no | ±1 | 803 | 46.5 | -0.4 | 1.4 | 9.4 | -7.1 | 45 |
| no | ±2 | 42 | 38.1 | -0.9 | 2.9 | 16.5 | -9 | 45 |
| yes | all nonzero | 4210 | 41.8 | -0.7 | 0.4 | 9 | -6.8 | 35 |
| yes | ±1 | 3004 | 43.1 | -0.7 | -0.2 | 7 | -6.2 | 35 |
| yes | ±2 | 1161 | 38.8 | -1 | 2 | 13.7 | -8.1 | 30 |
| yes | ±3 | 45 | 35.6 | -1.7 | -1.6 | 16.4 | -12.1 | 60 |

## score x wall room in score direction (ATR)

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0.25-1 | all nonzero | 896 | 37.6 | -1.2 | -1.1 | 8 | -6.9 | 40 |
| 0.25-1 | ±1 | 769 | 38.4 | -1.1 | -0.6 | 7.3 | -6.2 | 40 |
| 0.25-1 | ±2 | 121 | 33.1 | -1.8 | -3.7 | 11.7 | -11.1 | 30 |
| 0.25-1 | ±3 | 6 | 33.3 | -6.7 | -5.8 | 20.9 | -12.9 | 52.5 |
| <0.25 | all nonzero | 955 | 42.5 | -0.6 | -0.1 | 6.4 | -5.1 | 35 |
| <0.25 | ±1 | 704 | 44 | -0.4 | -0.1 | 5.8 | -4.9 | 35 |
| <0.25 | ±2 | 245 | 38.4 | -0.8 | -0.1 | 7.9 | -5.6 | 30 |
| <0.25 | ±3 | 6 | 33.3 | -1.3 | -0.3 | 10 | -5.1 | 65 |
| >1 | all nonzero | 2673 | 39.1 | -1.2 | 0 | 9.6 | -7.9 | 40 |
| >1 | ±1 | 2084 | 39.3 | -1.3 | -0.9 | 7.9 | -7.6 | 40 |
| >1 | ±2 | 557 | 38.8 | -0.8 | 3.6 | 15.6 | -8.7 | 40 |
| >1 | ±3 | 32 | 34.4 | -1.7 | -1.2 | 17.3 | -13.7 | 45 |
| missing | all nonzero | 3584 | 36.1 | -1.6 | 0.3 | 11.8 | -8.2 | 40 |
| missing | ±1 | 2953 | 36.2 | -1.5 | -0.1 | 10.2 | -8 | 40 |
| missing | ±2 | 629 | 35.6 | -2.5 | 2.3 | 19.6 | -8.9 | 35 |
| missing | ±3 | 2 | 50 | -6.4 | -6.4 | 5.3 | -9.3 | 105 |

## score x momentum state

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| accelerate | all nonzero | 163 | 31.3 | -2.9 | -2.5 | 10.5 | -9.1 | 60 |
| accelerate | ±1 | 104 | 34.6 | -2.2 | -2.9 | 7.5 | -9.1 | 60 |
| accelerate | ±2 | 59 | 25.4 | -4.1 | -1.7 | 15.7 | -9.2 | 45 |
| decelerate | all nonzero | 2131 | 46.7 | -0.4 | 2.6 | 12.2 | -7.5 | 45 |
| decelerate | ±1 | 1453 | 49.3 | 0 | 1.2 | 9 | -6.9 | 45 |
| decelerate | ±2 | 659 | 41.1 | -1.1 | 5.7 | 19.1 | -8.5 | 45 |
| decelerate | ±3 | 19 | 36.8 | -5.2 | 0.7 | 19.4 | -14.8 | 60 |
| quiet | all nonzero | 5554 | 34.8 | -1.5 | -1 | 9 | -7.5 | 30 |
| quiet | ±1 | 4805 | 34.8 | -1.5 | -0.9 | 8.6 | -7.4 | 35 |
| quiet | ±2 | 734 | 35 | -1.4 | -1.4 | 11.6 | -8.2 | 30 |
| quiet | ±3 | 15 | 26.7 | -1.1 | -1.9 | 8.2 | -5.1 | 20 |
| resume | all nonzero | 260 | 39.6 | -1.2 | 1.9 | 14.4 | -8.6 | 60 |
| resume | ±1 | 148 | 45.3 | -0.5 | 1.5 | 7.7 | -6.7 | 60 |
| resume | ±2 | 100 | 31 | -2.4 | 3.4 | 23.5 | -10.5 | 50 |
| resume | ±3 | 12 | 41.7 | -1.3 | -6 | 21.5 | -17.5 | 62.5 |

## score x surge x C/P agrees x room > 0.5 ATR

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| no | all nonzero | 3542 | 41.8 | -0.7 | 0.3 | 8.5 | -6.8 | 40 |
| no | ±1 | 2710 | 43.2 | -0.7 | -0.1 | 7.2 | -6.4 | 40 |
| no | ±2 | 803 | 37.5 | -1 | 1.6 | 12.8 | -8 | 30 |
| no | ±3 | 29 | 31 | -1.7 | -1.9 | 11.6 | -8.2 | 60 |
| no / missing input | all nonzero | 4478 | 34.9 | -1.8 | -0.2 | 11.1 | -8.1 | 40 |
| no / missing input | ±1 | 3763 | 34.8 | -1.7 | -0.7 | 9.6 | -7.9 | 40 |
| no / missing input | ±2 | 712 | 35.5 | -2.5 | 2.2 | 18.9 | -8.9 | 37.5 |
| no / missing input | ±3 | 3 | 33.3 | -13.8 | -9 | 7.9 | -13.2 | 90 |
| yes (all three) | all nonzero | 88 | 44.3 | -1.6 | 2.2 | 17.3 | -12.9 | 45 |
| yes (all three) | ±1 | 37 | 35.1 | -2.7 | 2.2 | 13.1 | -10.8 | 45 |
| yes (all three) | ±2 | 37 | 54.1 | 0.7 | 3.3 | 17.6 | -12.2 | 45 |
| yes (all three) | ±3 | 14 | 42.9 | -1.5 | -0.3 | 27.8 | -20.7 | 45 |

## score x stock tape agrees (own 60 s return)

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| missing | all nonzero | 112 | 35.7 | -1.1 | -1.3 | 6.4 | -5.6 | 35 |
| missing | ±1 | 96 | 34.4 | -1.1 | -1.7 | 5.9 | -5.7 | 42.5 |
| missing | ±2 | 15 | 46.7 | -0.3 | 1.6 | 10.4 | -3.9 | 30 |
| missing | ±3 | 1 | 0 | -16.6 | -16.6 | 3.7 | -20.3 | 15 |
| no | all nonzero | 3016 | 42.5 | -0.7 | 0.5 | 9.4 | -7.5 | 30 |
| no | ±1 | 2564 | 43.1 | -0.7 | 0.2 | 8.6 | -7.5 | 30 |
| no | ±2 | 447 | 39.8 | -0.8 | 2.6 | 13.9 | -7.6 | 20 |
| no | ±3 | 5 | 0 | -7.4 | -8.3 | 21.6 | -10.7 | 30 |
| yes | all nonzero | 4980 | 35.4 | -1.6 | -0.3 | 10.5 | -7.6 | 45 |
| yes | ±1 | 3850 | 35.2 | -1.6 | -0.8 | 8.7 | -7.2 | 45 |
| yes | ±2 | 1090 | 35.7 | -1.8 | 1.6 | 16.5 | -8.9 | 45 |
| yes | ±3 | 40 | 40 | -1.1 | -0.7 | 16 | -12.3 | 60 |

## score x market agrees (SPY/QQQ 60 s return)

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| missing | all nonzero | 6 | 33.3 | -1.2 | -4 | 3.3 | -6.5 | 40 |
| missing | ±1 | 6 | 33.3 | -1.2 | -4 | 3.3 | -6.5 | 40 |
| no | all nonzero | 3348 | 37.6 | -1.3 | -0.6 | 8.9 | -7.8 | 30 |
| no | ±1 | 2841 | 37.6 | -1.3 | -0.8 | 8.1 | -7.7 | 30 |
| no | ±2 | 493 | 38.1 | -1.5 | 0.9 | 12.5 | -8 | 30 |
| no | ±3 | 14 | 21.4 | -5.5 | -0.2 | 27.1 | -17.1 | 67.5 |
| yes | all nonzero | 4754 | 38.3 | -1.2 | 0.4 | 10.8 | -7.4 | 45 |
| yes | ±1 | 3663 | 38.8 | -1.2 | -0.1 | 9 | -7.1 | 45 |
| yes | ±2 | 1059 | 36.4 | -1.5 | 2.4 | 17.2 | -8.7 | 45 |
| yes | ±3 | 32 | 40.6 | -1 | -2.6 | 11.6 | -10.2 | 45 |

## Buffered vs raw (comparison only — the raw score above is primary)

Buffered shadow (band 0.15): 3236 nonzero holds vs raw 8108; % with score 40.9 vs 38; median gain -1.5 vs -1.3 bp; mean gain 0.7 vs 0 bp; median hold 120 vs 40 s.

## Secondary check: move 5 / 15 / 30 / 60 s after each change (nonzero scores, 5 s bar closes)

| after | changes | % with score | % flat | median gain bp | mean gain bp |
|---|---:|---:|---:|---:|---:|
| +5 s | 7438 | 45.1 | 6.9 | 0 | -0.1 |
| +15 s | 7962 | 46.2 | 3.7 | 0 | -0.1 |
| +30 s | 8063 | 47.7 | 2.4 | 0 | -0.1 |
| +60 s | 8063 | 48.7 | 1.5 | 0 | 0.1 |
Per-change rows: `changes-fwd-20261020-replay5s.jsonl`.

## score x held before acting (wait W s, enter only if the score is still unchanged)

Entry = price W s after the score started (close of the last 5 s bar at or before that moment, no lookahead), only for holds that lasted longer than W. Gain = entry to the end of the hold, in the score's direction. Peak/trough = best/worst move after entry. Remaining hold = seconds from entry to the score's next change. W = 0 is the same as 'Score alone'. Rows under 20 holds are marked small sample.

| scores | wait s | holds | % of W=0 holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median remaining hold s | note |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ±1 | 0 | 6510 | 100 | 38.3 | -1.2 | -0.4 | 8.6 | -7.3 | 40 |  |
| ±1 | 15 | 4230 | 65 | 40.6 | -1.2 | -0.5 | 10.3 | -8.9 | 60 |  |
| ±1 | 30 | 3389 | 52.1 | 39.7 | -1.4 | -0.6 | 10.9 | -9.4 | 75 |  |
| ±1 | 60 | 2305 | 35.4 | 39 | -1.7 | -1 | 11.6 | -10.7 | 90 |  |
| ±1 | 120 | 1387 | 21.3 | 37.9 | -2.1 | -0.7 | 13 | -11.3 | 120 |  |
| ±1 | 300 | 477 | 7.3 | 36.7 | -3 | -1.5 | 15.3 | -13.2 | 215 |  |
| ±2 | 0 | 1552 | 100 | 37 | -1.5 | 1.9 | 15.7 | -8.5 | 35 |  |
| ±2 | 15 | 979 | 63.1 | 41.7 | -1.1 | 3.4 | 20.6 | -10.5 | 60 |  |
| ±2 | 30 | 782 | 50.4 | 43.2 | -0.9 | 3.8 | 22.6 | -11.5 | 75 |  |
| ±2 | 60 | 547 | 35.2 | 41.9 | -1.7 | 3.7 | 25.1 | -13.9 | 105 |  |
| ±2 | 120 | 340 | 21.9 | 45 | -1.3 | 4.1 | 30.2 | -16.3 | 137.5 |  |
| ±2 | 300 | 141 | 9.1 | 41.1 | -4.9 | 3.9 | 35 | -23.3 | 195 |  |
| ±3 | 0 | 46 | 100 | 34.8 | -1.7 | -1.9 | 16.3 | -12.3 | 60 |  |
| ±3 | 15 | 32 | 69.6 | 34.4 | -3.7 | -2.4 | 19.8 | -13.6 | 57.5 |  |
| ±3 | 30 | 27 | 58.7 | 22.2 | -4 | -6.4 | 16.9 | -18.3 | 60 |  |
| ±3 | 60 | 19 | 41.3 | 36.8 | -2.2 | -0.1 | 22.4 | -12.1 | 45 | small sample |
| ±3 | 120 | 8 | 17.4 | 12.5 | -4 | -13.9 | 24.5 | -20.6 | 80 | small sample |
| ±3 | 300 | 2 | 4.3 | 0 | -34.9 | -34.9 | 20.9 | -39.6 | 100 | small sample |
| all nonzero | 0 | 8108 | 100 | 38 | -1.3 | 0 | 10 | -7.6 | 40 |  |
| all nonzero | 15 | 5241 | 64.6 | 40.8 | -1.2 | 0.2 | 12.3 | -9.2 | 60 |  |
| all nonzero | 30 | 4198 | 51.8 | 40.2 | -1.3 | 0.2 | 13.1 | -9.8 | 75 |  |
| all nonzero | 60 | 2871 | 35.4 | 39.6 | -1.7 | -0.1 | 14.3 | -11.3 | 90 |  |
| all nonzero | 120 | 1735 | 21.4 | 39.1 | -2 | 0.2 | 16.4 | -12.4 | 120 |  |
| all nonzero | 300 | 620 | 7.6 | 37.6 | -3.2 | -0.4 | 19.8 | -15.6 | 207.5 |  |
| ±2 + surge (rvol_1m >= 3) | 0 | 81 | 100 | 42 | -0.7 | 2.3 | 17.7 | -11 | 45 |  |
| ±2 + surge (rvol_1m >= 3) | 15 | 57 | 70.4 | 45.6 | -0.8 | 2.9 | 20.2 | -13.1 | 90 |  |
| ±2 + surge (rvol_1m >= 3) | 30 | 46 | 56.8 | 45.7 | -0.6 | 5.4 | 24.6 | -12.5 | 112.5 |  |
| ±2 + surge (rvol_1m >= 3) | 60 | 34 | 42 | 44.1 | -1.8 | 2.4 | 24.5 | -18.8 | 120 |  |
| ±2 + surge (rvol_1m >= 3) | 120 | 26 | 32.1 | 61.5 | 3.5 | -1.2 | 20.7 | -18.8 | 187.5 |  |
| ±2 + surge (rvol_1m >= 3) | 300 | 13 | 16 | 61.5 | 3.9 | 8.3 | 26 | -11.1 | 300 | small sample |
| ±3 + surge (rvol_1m >= 3) | 0 | 17 | 100 | 35.3 | -2.3 | -1.8 | 23.6 | -18.9 | 45 | small sample |
| ±3 + surge (rvol_1m >= 3) | 15 | 14 | 82.4 | 35.7 | -2.1 | 1.7 | 30.1 | -14.9 | 50 | small sample |
| ±3 + surge (rvol_1m >= 3) | 30 | 11 | 64.7 | 36.4 | -3.4 | -0.9 | 31.3 | -18.9 | 45 | small sample |
| ±3 + surge (rvol_1m >= 3) | 60 | 7 | 41.2 | 57.1 | 6 | 9.2 | 47.4 | -12.7 | 45 | small sample |
| ±3 + surge (rvol_1m >= 3) | 120 | 3 | 17.6 | 33.3 | -18.3 | -24.6 | 53.6 | -37.7 | 125 | small sample |
| ±3 + surge (rvol_1m >= 3) | 300 | 1 | 5.9 | 0 | -68.1 | -68.1 | 41.9 | -77.2 | 185 | small sample |
| ±2 + momentum resume/accelerate | 0 | 159 | 100 | 28.9 | -2.9 | 1.5 | 20.6 | -10 | 50 |  |
| ±2 + momentum resume/accelerate | 15 | 113 | 71.1 | 34.5 | -2.5 | 3 | 25.9 | -11.5 | 60 |  |
| ±2 + momentum resume/accelerate | 30 | 92 | 57.9 | 38 | -1.9 | 2.9 | 29.1 | -13.7 | 92.5 |  |
| ±2 + momentum resume/accelerate | 60 | 61 | 38.4 | 45.9 | -2.1 | 0.6 | 35.6 | -19.4 | 180 |  |
| ±2 + momentum resume/accelerate | 120 | 46 | 28.9 | 37 | -2.9 | -6.2 | 35.4 | -24.9 | 240 |  |
| ±2 + momentum resume/accelerate | 300 | 27 | 17 | 37 | -21.5 | -8.1 | 28.9 | -31.2 | 228.3 |  |
| ±3 + momentum resume/accelerate | 0 | 12 | 100 | 41.7 | -1.3 | -6 | 21.5 | -17.5 | 62.5 | small sample |
| ±3 + momentum resume/accelerate | 15 | 11 | 91.7 | 36.4 | -1.1 | -5 | 22.4 | -15.8 | 50 | small sample |
| ±3 + momentum resume/accelerate | 30 | 9 | 75 | 33.3 | -3.4 | -8.5 | 21.9 | -18.2 | 45 | small sample |
| ±3 + momentum resume/accelerate | 60 | 6 | 50 | 16.7 | -4.3 | -3.3 | 23.5 | -13.8 | 67.5 | small sample |
| ±3 + momentum resume/accelerate | 120 | 3 | 25 | 0 | -6.3 | -8.2 | 31 | -13.3 | 60 | small sample |
| ±3 + momentum resume/accelerate | 300 | 1 | 8.3 | 0 | -68.1 | -68.1 | 41.9 | -77.2 | 185 | small sample |

Per-score (±1/±2/±3 separately) breakdowns are in the .json.
