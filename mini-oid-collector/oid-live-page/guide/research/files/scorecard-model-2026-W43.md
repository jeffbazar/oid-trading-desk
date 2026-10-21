# Score model scorecard 2026-W43

Generated 2026-10-20 07:55:20 PM PT. Days with labels: 2026-10-19, 2026-10-20.

Hit = the score's direction was right at that horizon (score 0 excluded). Moves in bp from 5 s closes (1-min on sector names without 5 s bars).

## core (replay)

| |S| | n (5m) | hit 1m | hit 5m | hit 15m | mean dmove 5m bp | mean MFE 5m | mean MAE 5m |
|---|---|---|---|---|---|---|---|
| 1 | 91074 | 47.8% | 47.9% | 44.8% | -0.9 | 17.6 | -18.7 |
| 2 | 14703 | 50.7% | 53.5% | 55.7% | 4.6 | 27.3 | -22.3 |
| 3 | 249 | 38.6% | 45.8% | 59.0% | 4.4 | 39.3 | -35.8 |
| any | 106026 | 48.2% | 48.7% | 46.3% | -0.1 | 19.0 | -19.2 |

## light (replay)

| |S| | n (5m) | hit 1m | hit 5m | hit 15m | mean dmove 5m bp | mean MFE 5m | mean MAE 5m |
|---|---|---|---|---|---|---|---|
| 1 | 212537 | 42.9% | 45.9% | 47.3% | -0.5 | 15.7 | -16.5 |
| 2 | 85301 | 43.9% | 45.4% | 44.8% | -0.1 | 22.0 | -22.2 |
| 3 | 20130 | 50.5% | 59.2% | 64.8% | 13.6 | 42.5 | -27.8 |
| any | 317968 | 43.7% | 46.6% | 47.7% | 0.5 | 19.1 | -18.8 |

## Calibration (5-min hit rate by raw score, half-point bins, n>=30)

| profile | raw | n | hit 5m |
|---|---|---|---|
| core | -2.5 | 288 | 33.0% |
| core | -2.0 | 1288 | 43.9% |
| core | -1.5 | 4197 | 40.6% |
| core | -1.0 | 17634 | 46.7% |
| core | -0.5 | 14779 | 48.9% |
| core | +0.5 | 19831 | 46.7% |
| core | +1.0 | 28000 | 48.8% |
| core | +1.5 | 13933 | 52.7% |
| core | +2.0 | 4983 | 58.0% |
| core | +2.5 | 1055 | 56.5% |
| light | -3.0 | 817 | 49.7% |
| light | -2.5 | 4887 | 40.8% |
| light | -2.0 | 18989 | 43.9% |
| light | -1.5 | 36451 | 44.2% |
| light | -1.0 | 53465 | 46.3% |
| light | -0.5 | 31248 | 48.1% |
| light | +0.5 | 30695 | 45.2% |
| light | +1.0 | 54008 | 45.6% |
| light | +1.5 | 40237 | 44.7% |
| light | +2.0 | 22595 | 47.6% |
| light | +2.5 | 12029 | 55.3% |
| light | +3.0 | 12547 | 61.2% |

## Data

| profile | bars | snapshots |
|---|---|---|
| core | 5s | 187941 |
| light | 1m | 448416 |

No model is trained or promoted by this file: it measures the live scores (step 6 of the plan adds challengers).
