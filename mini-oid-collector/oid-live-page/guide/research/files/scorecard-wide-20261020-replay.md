# LIGHT direction score scorecard (Sector watch) — 2026-10-20

Source: **episodes (episodes-wide-20261020.jsonl)** (15090 holds). LIGHT score (profile light light-v1.0-20261021: trend + volume + market only, no flip/walls/options flow) for the Sector watch names. Price bars: 0 names on 5 s bars, 144 on 1-min fallback. C/P, wall-room and momentum rows read 'missing' by design. Not directly comparable with the core card.

Gain = start-to-stop move in the score's direction. Peak/trough = best/worst move in the score's direction during the hold. ±1/±2/±3 = score of that size in either direction, gains signed to the score. Score 0 has no direction, so its gain columns are blank. Times PT.

## Score alone

| score | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---:|---:|---:|---:|---:|---:|---:|
| -3 | 94 | 30.9 | -9.8 | -0.9 | 47.4 | -27.8 | 120 |
| -2 | 712 | 31 | -3.6 | -4.6 | 19.8 | -20 | 120 |
| -1 | 2565 | 33.5 | -2.7 | -2.3 | 14.5 | -14.9 | 120 |
| 0 | 4509 | – | – | – | – | – | 120 |
| 1 | 4305 | 41.4 | -1.1 | -0.8 | 14 | -14 | 120 |
| 2 | 2316 | 41 | -1.2 | 2 | 18.6 | -14 | 120 |
| 3 | 589 | 45 | 0 | 22.8 | 56.4 | -18.1 | 180 |
| all nonzero | 10581 | 38.8 | -1.8 | 0.5 | 18.2 | -14.9 | 120 |

## score x surge (rvol_1m >= 3)

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| no | all nonzero | 9716 | 38.6 | -1.8 | 0.4 | 17.4 | -14.4 | 120 |
| no | ±1 | 6400 | 38 | -1.9 | -1.5 | 13.7 | -13.9 | 120 |
| no | ±2 | 2740 | 38.6 | -1.8 | 0.4 | 18.1 | -14.8 | 120 |
| no | ±3 | 576 | 44.1 | -0.4 | 21.4 | 55.3 | -17.8 | 180 |
| yes | all nonzero | 865 | 41.6 | -1.9 | 1.7 | 27.3 | -21 | 120 |
| yes | ±1 | 470 | 44.3 | -1.3 | 0.3 | 21.4 | -19.4 | 120 |
| yes | ±2 | 288 | 38.9 | -1.6 | 1.1 | 26.9 | -20.9 | 120 |
| yes | ±3 | 107 | 37.4 | -3.5 | 9.4 | 54.5 | -27.8 | 180 |

## score x C/P agrees

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| missing | all nonzero | 10581 | 38.8 | -1.8 | 0.5 | 18.2 | -14.9 | 120 |
| missing | ±1 | 6870 | 38.4 | -1.9 | -1.4 | 14.2 | -14.3 | 120 |
| missing | ±2 | 3028 | 38.7 | -1.8 | 0.4 | 18.9 | -15.4 | 120 |
| missing | ±3 | 683 | 43 | -0.7 | 19.5 | 55.1 | -19.4 | 180 |

## score x wall room in score direction (ATR)

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| missing | all nonzero | 10581 | 38.8 | -1.8 | 0.5 | 18.2 | -14.9 | 120 |
| missing | ±1 | 6870 | 38.4 | -1.9 | -1.4 | 14.2 | -14.3 | 120 |
| missing | ±2 | 3028 | 38.7 | -1.8 | 0.4 | 18.9 | -15.4 | 120 |
| missing | ±3 | 683 | 43 | -0.7 | 19.5 | 55.1 | -19.4 | 180 |

## score x momentum state

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| missing | all nonzero | 10581 | 38.8 | -1.8 | 0.5 | 18.2 | -14.9 | 120 |
| missing | ±1 | 6870 | 38.4 | -1.9 | -1.4 | 14.2 | -14.3 | 120 |
| missing | ±2 | 3028 | 38.7 | -1.8 | 0.4 | 18.9 | -15.4 | 120 |
| missing | ±3 | 683 | 43 | -0.7 | 19.5 | 55.1 | -19.4 | 180 |

## score x surge x C/P agrees x room > 0.5 ATR

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| no / missing input | all nonzero | 10581 | 38.8 | -1.8 | 0.5 | 18.2 | -14.9 | 120 |
| no / missing input | ±1 | 6870 | 38.4 | -1.9 | -1.4 | 14.2 | -14.3 | 120 |
| no / missing input | ±2 | 3028 | 38.7 | -1.8 | 0.4 | 18.9 | -15.4 | 120 |
| no / missing input | ±3 | 683 | 43 | -0.7 | 19.5 | 55.1 | -19.4 | 180 |

## score x stock tape agrees (own 60 s return)

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| missing | all nonzero | 703 | 31.6 | -1.2 | -1.5 | 15.3 | -14.8 | 120 |
| missing | ±1 | 509 | 31.2 | -1.4 | -2 | 13.4 | -14.4 | 120 |
| missing | ±2 | 166 | 31.3 | -0.3 | -1.1 | 17.4 | -15.3 | 120 |
| missing | ±3 | 28 | 39.3 | -4.4 | 6.4 | 37.2 | -19 | 60 |
| no | all nonzero | 2966 | 49.8 | 0 | 1.3 | 17.1 | -14.8 | 120 |
| no | ±1 | 2218 | 48.7 | 0 | -0.3 | 14.4 | -14.3 | 120 |
| no | ±2 | 706 | 53.4 | 2.8 | 5 | 23.6 | -16.6 | 120 |
| no | ±3 | 42 | 42.9 | -0.9 | 25.8 | 51.4 | -13.3 | 180 |
| yes | all nonzero | 6912 | 34.8 | -2.9 | 0.4 | 19 | -15 | 120 |
| yes | ±1 | 4143 | 33.8 | -3 | -1.8 | 14.2 | -14.3 | 120 |
| yes | ±2 | 2156 | 34.4 | -2.9 | -0.9 | 17.5 | -15 | 120 |
| yes | ±3 | 613 | 43.2 | -0.7 | 19.7 | 56.2 | -19.9 | 180 |

## score x market agrees (SPY/QQQ 60 s return)

| bucket | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| no | all nonzero | 4251 | 38.2 | -2.1 | -1.7 | 15.9 | -15.9 | 120 |
| no | ±1 | 3012 | 38.3 | -2.1 | -2.4 | 13.5 | -15.2 | 120 |
| no | ±2 | 1095 | 37.4 | -2.1 | -1.2 | 18.9 | -17.2 | 120 |
| no | ±3 | 144 | 43.1 | -0.9 | 7.5 | 44.4 | -21.5 | 120 |
| yes | all nonzero | 6330 | 39.2 | -1.6 | 2 | 19.7 | -14.3 | 120 |
| yes | ±1 | 3858 | 38.5 | -1.7 | -0.6 | 14.7 | -13.6 | 120 |
| yes | ±2 | 1933 | 39.4 | -1.6 | 1.4 | 18.9 | -14.3 | 120 |
| yes | ±3 | 539 | 43 | -0.7 | 22.8 | 58 | -18.9 | 180 |

## Buffered vs raw (comparison only — the raw score above is primary)

Buffered shadow (band 0.15): 6608 nonzero holds vs raw 10581; % with score 38.6 vs 38.8; median gain -3.7 vs -1.8 bp; mean gain 1.2 vs 0.5 bp; median hold 240 vs 120 s.

## Secondary check: move 5 / 15 / 30 / 60 s after each change (nonzero scores, 5 s bar closes)

| after | changes | % with score | % flat | median gain bp | mean gain bp |
|---|---:|---:|---:|---:|---:|
| +5 s | 0 | – | – | – | – |
| +15 s | 0 | – | – | – | – |
| +30 s | 0 | – | – | – | – |
| +60 s | 10533 | 43.3 | 10.3 | 0 | 0 |
Per-change rows: `changes-wide-fwd-20261020-replay.jsonl`.

## score x held before acting (wait W s, enter only if the score is still unchanged)

Entry = price W s after the score started (close of the last 5 s bar at or before that moment, no lookahead), only for holds that lasted longer than W. Gain = entry to the end of the hold, in the score's direction. Peak/trough = best/worst move after entry. Remaining hold = seconds from entry to the score's next change. W = 0 is the same as 'Score alone'. Rows under 20 holds are marked small sample.

| scores | wait s | holds | % of W=0 holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median remaining hold s | note |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ±1 | 0 | 6870 | 100 | 38.4 | -1.9 | -1.4 | 14.2 | -14.3 | 120 |  |
| ±1 | 15 | 6828 | 99.4 | 38.7 | -1.9 | -1.4 | 12.1 | -12.2 | 105 |  |
| ±1 | 30 | 6828 | 99.4 | 38.7 | -1.9 | -1.4 | 12.1 | -12.2 | 90 |  |
| ±1 | 60 | 4473 | 65.1 | 39.3 | -1.9 | -1.4 | 14.2 | -14.6 | 180 |  |
| ±1 | 120 | 3233 | 47.1 | 40.2 | -1.8 | -1 | 14 | -13.7 | 180 |  |
| ±1 | 300 | 1376 | 20 | 42.2 | -0.9 | -0.1 | 13.2 | -11.8 | 180 |  |
| ±2 | 0 | 3028 | 100 | 38.7 | -1.8 | 0.4 | 18.9 | -15.4 | 120 |  |
| ±2 | 15 | 3004 | 99.2 | 39 | -1.9 | 0.4 | 16.5 | -12.6 | 105 |  |
| ±2 | 30 | 3004 | 99.2 | 39 | -1.9 | 0.4 | 16.5 | -12.6 | 90 |  |
| ±2 | 60 | 1875 | 61.9 | 39.4 | -2.1 | 0.3 | 19.4 | -16 | 180 |  |
| ±2 | 120 | 1318 | 43.5 | 39.5 | -1.9 | -0.5 | 18.8 | -16.9 | 180 |  |
| ±2 | 300 | 562 | 18.6 | 38.8 | -1.9 | 0.1 | 17.7 | -14.3 | 180 |  |
| ±3 | 0 | 683 | 100 | 43 | -0.7 | 19.5 | 55.1 | -19.4 | 180 |  |
| ±3 | 15 | 679 | 99.4 | 43.3 | -0.9 | 19.7 | 51.8 | -15.3 | 165 |  |
| ±3 | 30 | 679 | 99.4 | 43.3 | -0.9 | 19.7 | 51.8 | -15.3 | 150 |  |
| ±3 | 60 | 455 | 66.6 | 48.4 | 0 | 24.9 | 65.1 | -21.8 | 240 |  |
| ±3 | 120 | 362 | 53 | 49.4 | 0 | 27.4 | 69.3 | -24.5 | 360 |  |
| ±3 | 300 | 219 | 32.1 | 54.3 | 5.7 | 40.4 | 87.9 | -23.7 | 600 |  |
| all nonzero | 0 | 10581 | 100 | 38.8 | -1.8 | 0.5 | 18.2 | -14.9 | 120 |  |
| all nonzero | 15 | 10511 | 99.3 | 39.1 | -1.9 | 0.5 | 15.9 | -12.5 | 105 |  |
| all nonzero | 30 | 10511 | 99.3 | 39.1 | -1.9 | 0.5 | 15.9 | -12.5 | 90 |  |
| all nonzero | 60 | 6803 | 64.3 | 39.9 | -1.9 | 0.8 | 19 | -15.4 | 180 |  |
| all nonzero | 120 | 4913 | 46.4 | 40.7 | -1.6 | 1.2 | 19.4 | -15.4 | 180 |  |
| all nonzero | 300 | 2157 | 20.4 | 42.6 | -0.9 | 4.1 | 21.9 | -13.7 | 180 |  |
| ±2 + surge (rvol_1m >= 3) | 0 | 288 | 100 | 38.9 | -1.6 | 1.1 | 26.9 | -20.9 | 120 |  |
| ±2 + surge (rvol_1m >= 3) | 15 | 284 | 98.6 | 39.4 | -2 | 1.2 | 22.9 | -17.2 | 135 |  |
| ±2 + surge (rvol_1m >= 3) | 30 | 284 | 98.6 | 39.4 | -2 | 1.2 | 22.9 | -17.2 | 120 |  |
| ±2 + surge (rvol_1m >= 3) | 60 | 187 | 64.9 | 41.2 | -2.6 | 1.8 | 27.2 | -21.2 | 180 |  |
| ±2 + surge (rvol_1m >= 3) | 120 | 142 | 49.3 | 40.1 | -1.2 | 2.9 | 26.1 | -20.1 | 180 |  |
| ±2 + surge (rvol_1m >= 3) | 300 | 63 | 21.9 | 50.8 | 0.6 | 5.3 | 31.6 | -15.6 | 240 |  |
| ±3 + surge (rvol_1m >= 3) | 0 | 107 | 100 | 37.4 | -3.5 | 9.4 | 54.5 | -27.8 | 180 |  |
| ±3 + surge (rvol_1m >= 3) | 15 | 106 | 99.1 | 37.7 | -3.6 | 9.5 | 47.8 | -22.7 | 165 |  |
| ±3 + surge (rvol_1m >= 3) | 30 | 106 | 99.1 | 37.7 | -3.6 | 9.5 | 47.8 | -22.7 | 150 |  |
| ±3 + surge (rvol_1m >= 3) | 60 | 74 | 69.2 | 45.9 | -2.3 | 13.3 | 55.5 | -28.5 | 330 |  |
| ±3 + surge (rvol_1m >= 3) | 120 | 58 | 54.2 | 44.8 | -3.4 | 16.4 | 58.9 | -29.2 | 540 |  |
| ±3 + surge (rvol_1m >= 3) | 300 | 40 | 37.4 | 67.5 | 14.8 | 22.5 | 68.1 | -25.8 | 600 |  |
| ±2 + momentum resume/accelerate | 0 | 0 | – | – | – | – | – | – | – | small sample |
| ±2 + momentum resume/accelerate | 15 | 0 | – | – | – | – | – | – | – | small sample |
| ±2 + momentum resume/accelerate | 30 | 0 | – | – | – | – | – | – | – | small sample |
| ±2 + momentum resume/accelerate | 60 | 0 | – | – | – | – | – | – | – | small sample |
| ±2 + momentum resume/accelerate | 120 | 0 | – | – | – | – | – | – | – | small sample |
| ±2 + momentum resume/accelerate | 300 | 0 | – | – | – | – | – | – | – | small sample |
| ±3 + momentum resume/accelerate | 0 | 0 | – | – | – | – | – | – | – | small sample |
| ±3 + momentum resume/accelerate | 15 | 0 | – | – | – | – | – | – | – | small sample |
| ±3 + momentum resume/accelerate | 30 | 0 | – | – | – | – | – | – | – | small sample |
| ±3 + momentum resume/accelerate | 60 | 0 | – | – | – | – | – | – | – | small sample |
| ±3 + momentum resume/accelerate | 120 | 0 | – | – | – | – | – | – | – | small sample |
| ±3 + momentum resume/accelerate | 300 | 0 | – | – | – | – | – | – | – | small sample |

## score x sector (light score only)

| sector | scores | holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Autos/EV | all nonzero | 621 | 36.9 | -1.8 | 0.2 | 21.3 | -18.8 | 120 |
| Autos/EV | ±1 | 372 | 36.6 | -2.5 | -2.2 | 16.2 | -18.1 | 120 |
| Autos/EV | ±2 | 194 | 37.6 | -1.6 | 2.3 | 21.6 | -18.1 | 120 |
| Autos/EV | ±3 | 55 | 36.4 | -1.3 | 8.8 | 54 | -26.4 | 180 |
| Communication/Media | all nonzero | 724 | 37.2 | -2.3 | -0.7 | 15.8 | -14.1 | 120 |
| Communication/Media | ±1 | 478 | 35.6 | -2.5 | -2.3 | 12.4 | -13.6 | 120 |
| Communication/Media | ±2 | 200 | 40 | -2.2 | 0.4 | 17.3 | -14.3 | 120 |
| Communication/Media | ±3 | 46 | 41.3 | -1.1 | 11.1 | 44.8 | -17.6 | 207.5 |
| Consumer Discretionary/Retail | all nonzero | 758 | 41.7 | -1.6 | 0.7 | 13.1 | -10.8 | 120 |
| Consumer Discretionary/Retail | ±1 | 484 | 43.6 | -1 | 0.3 | 11.2 | -10.2 | 120 |
| Consumer Discretionary/Retail | ±2 | 230 | 37.8 | -1.8 | -1.4 | 12.9 | -11.9 | 120 |
| Consumer Discretionary/Retail | ±3 | 44 | 40.9 | -3.1 | 15.7 | 34.9 | -12.3 | 120 |
| Consumer Staples | all nonzero | 484 | 39.9 | -1.4 | -0.8 | 7.4 | -6.8 | 180 |
| Consumer Staples | ±1 | 340 | 39.7 | -1.5 | -0.6 | 7.1 | -6.3 | 180 |
| Consumer Staples | ±2 | 124 | 43.5 | -1 | 0.1 | 8.6 | -6.9 | 120 |
| Consumer Staples | ±3 | 20 | 20 | -7.7 | -9.8 | 5.8 | -13.1 | 60 |
| Crypto-linked (miners, treasuries, exchanges) | all nonzero | 665 | 35.6 | -7 | 0.9 | 31.9 | -24.3 | 120 |
| Crypto-linked (miners, treasuries, exchanges) | ±1 | 443 | 31.6 | -7.2 | -7.7 | 20.6 | -24.2 | 120 |
| Crypto-linked (miners, treasuries, exchanges) | ±2 | 178 | 43.3 | -4.7 | 1.6 | 31.9 | -23.1 | 120 |
| Crypto-linked (miners, treasuries, exchanges) | ±3 | 44 | 45.5 | -2.8 | 85.4 | 144.8 | -29.3 | 180 |
| Energy (oil & gas, LNG) | all nonzero | 734 | 39.9 | -1.6 | 0.9 | 17.1 | -13.7 | 120 |
| Energy (oil & gas, LNG) | ±1 | 485 | 42.3 | -0.4 | 1.6 | 15.5 | -12.3 | 120 |
| Energy (oil & gas, LNG) | ±2 | 215 | 32.6 | -2.4 | -1.7 | 16.8 | -15 | 120 |
| Energy (oil & gas, LNG) | ±3 | 34 | 52.9 | 1.3 | 6.7 | 42.2 | -24.2 | 120 |
| Financials: banks/brokers/fintech | all nonzero | 735 | 33.9 | -2.5 | 0.2 | 16.5 | -14 | 120 |
| Financials: banks/brokers/fintech | ±1 | 496 | 32.5 | -2.5 | -0.6 | 13.8 | -13.2 | 120 |
| Financials: banks/brokers/fintech | ±2 | 197 | 34 | -3.3 | -1.2 | 16.4 | -15.4 | 120 |
| Financials: banks/brokers/fintech | ±3 | 42 | 50 | 0.2 | 16.1 | 49 | -15.6 | 207.5 |
| Healthcare/Biotech/Pharma | all nonzero | 735 | 46.9 | 0 | 3.7 | 23.5 | -16.8 | 120 |
| Healthcare/Biotech/Pharma | ±1 | 408 | 48.5 | 0 | 0.9 | 17.4 | -17.1 | 120 |
| Healthcare/Biotech/Pharma | ±2 | 261 | 44.4 | 0 | 3.5 | 25.1 | -16.7 | 125 |
| Healthcare/Biotech/Pharma | ±3 | 66 | 47 | -0.5 | 21.9 | 55.5 | -15 | 207.5 |
| Industrials & Defense/Aerospace | all nonzero | 539 | 35.6 | -4.5 | -0.3 | 19.3 | -16.2 | 120 |
| Industrials & Defense/Aerospace | ±1 | 355 | 35.8 | -3.9 | -2.2 | 14.8 | -14.6 | 120 |
| Industrials & Defense/Aerospace | ±2 | 146 | 35.6 | -4.4 | -0.1 | 21.5 | -18.4 | 180 |
| Industrials & Defense/Aerospace | ±3 | 38 | 34.2 | -5.2 | 15.4 | 52.8 | -22.4 | 120 |
| Macro/commodity/intl ETFs | all nonzero | 663 | 40.4 | -0.6 | 1.1 | 7.8 | -5.1 | 120 |
| Macro/commodity/intl ETFs | ±1 | 461 | 40.3 | -0.7 | 0.6 | 6.1 | -4.8 | 120 |
| Macro/commodity/intl ETFs | ±2 | 177 | 39.5 | -1 | 0.6 | 8.8 | -6 | 120 |
| Macro/commodity/intl ETFs | ±3 | 25 | 48 | 0 | 14.1 | 31.6 | -5.4 | 180 |
| Materials/Metals & Mining (incl. gold, uranium) | all nonzero | 659 | 39.5 | -3.6 | 2.4 | 21.1 | -15.6 | 120 |
| Materials/Metals & Mining (incl. gold, uranium) | ±1 | 413 | 39.2 | -3.3 | 0.2 | 15.8 | -14.1 | 120 |
| Materials/Metals & Mining (incl. gold, uranium) | ±2 | 201 | 37.3 | -3.7 | -1.1 | 18.6 | -18.2 | 120 |
| Materials/Metals & Mining (incl. gold, uranium) | ±3 | 45 | 51.1 | 1.2 | 38.6 | 81.2 | -18.8 | 120 |
| Real Estate | all nonzero | 516 | 34.7 | -2.7 | -2.2 | 20.4 | -20.5 | 120 |
| Real Estate | ±1 | 344 | 33.4 | -2.8 | -2.9 | 18.4 | -20.8 | 120 |
| Real Estate | ±2 | 136 | 36 | -0.9 | -0.6 | 20.8 | -19 | 120 |
| Real Estate | ±3 | 36 | 41.7 | 0 | -1.9 | 38.1 | -23.6 | 210 |
| Sector & thematic ETFs | all nonzero | 724 | 40.5 | -1.3 | 0.9 | 8.5 | -6.4 | 120 |
| Sector & thematic ETFs | ±1 | 473 | 41.2 | -1.4 | -0.4 | 6.8 | -6.3 | 120 |
| Sector & thematic ETFs | ±2 | 203 | 39.9 | -1.3 | 0.7 | 7.9 | -6.7 | 120 |
| Sector & thematic ETFs | ±3 | 48 | 35.4 | -1.6 | 14.9 | 28.1 | -6.8 | 120 |
| Tech/software not in universe | all nonzero | 754 | 40.2 | -2.1 | -1.3 | 15.7 | -13.6 | 120 |
| Tech/software not in universe | ±1 | 485 | 40.6 | -2.7 | -3.1 | 12.7 | -13.9 | 120 |
| Tech/software not in universe | ±2 | 220 | 37.7 | -1.9 | -0.4 | 16.4 | -13.1 | 120 |
| Tech/software not in universe | ±3 | 49 | 46.9 | -1.9 | 12.2 | 42 | -12.7 | 180 |
| Transportation/Airlines | all nonzero | 595 | 39.8 | -1.5 | 2.6 | 28.2 | -21.9 | 120 |
| Transportation/Airlines | ±1 | 391 | 38.6 | -2.2 | 0.5 | 21.7 | -20.2 | 120 |
| Transportation/Airlines | ±2 | 158 | 43 | -0.7 | 1 | 31.2 | -24.3 | 120 |
| Transportation/Airlines | ±3 | 46 | 39.1 | -2.3 | 26.4 | 72.8 | -28.9 | 120 |
| Utilities/Power (incl. nuclear, AI power) | all nonzero | 675 | 36 | -2.9 | -1.1 | 24.3 | -22.1 | 120 |
| Utilities/Power (incl. nuclear, AI power) | ±1 | 442 | 34.4 | -3.8 | -4.2 | 19.1 | -21.9 | 180 |
| Utilities/Power (incl. nuclear, AI power) | ±2 | 188 | 36.7 | -1.8 | 2.7 | 27.1 | -20 | 120 |
| Utilities/Power (incl. nuclear, AI power) | ±3 | 45 | 48.9 | 0 | 13.9 | 63.9 | -32.9 | 240 |

## ±2 / ±3 holds by sector (counts, % with score)

| sector | ±2 holds | ±2 % with | ±3 holds | ±3 % with | names scored |
|---|---:|---:|---:|---:|---:|
| Autos/EV | 194 | 37.6 | 55 | 36.4 | 7 |
| Communication/Media | 200 | 40 | 46 | 41.3 | 10 |
| Consumer Discretionary/Retail | 230 | 37.8 | 44 | 40.9 | 10 |
| Consumer Staples | 124 | 43.5 | 20 | 20 | 7 |
| Crypto-linked (miners, treasuries, exchanges) | 178 | 43.3 | 44 | 45.5 | 10 |
| Energy (oil & gas, LNG) | 215 | 32.6 | 34 | 52.9 | 10 |
| Financials: banks/brokers/fintech | 197 | 34 | 42 | 50 | 10 |
| Healthcare/Biotech/Pharma | 261 | 44.4 | 66 | 47 | 10 |
| Industrials & Defense/Aerospace | 146 | 35.6 | 38 | 34.2 | 7 |
| Macro/commodity/intl ETFs | 177 | 39.5 | 25 | 48 | 10 |
| Materials/Metals & Mining (incl. gold, uranium) | 201 | 37.3 | 45 | 51.1 | 9 |
| Real Estate | 136 | 36 | 36 | 41.7 | 7 |
| Sector & thematic ETFs | 203 | 39.9 | 48 | 35.4 | 10 |
| Tech/software not in universe | 220 | 37.7 | 49 | 46.9 | 10 |
| Transportation/Airlines | 158 | 43 | 46 | 39.1 | 8 |
| Utilities/Power (incl. nuclear, AI power) | 188 | 36.7 | 45 | 48.9 | 9 |
| ALL SECTORS | 3028 | 38.7 | 683 | 43 | 144 |

Per-score (±1/±2/±3 separately) breakdowns are in the .json.
