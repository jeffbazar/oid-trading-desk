# momentum (SHADOW) — accelerate / decelerate / resume / market-recede

launchd `com.oid.desk.momentum` (KeepAlive loop, 15 s ticks, 6:31 AM–1:00 PM PT weekdays) runs
`momentum.py --loop`. Config: `~/oid-desk/triggers/momentum.json` (read every tick, `"live": false`).
Events: `~/oid-desk/state/momentum/events-YYYYMMDD.jsonl`; 15 s last-trade samples: `ticks-YYYYMMDD.jsonl`;
`status.json`; log `~/oid-desk/logs/momentum.log`. **No sender exists in the code: nothing reaches chat.**
Universe = live-page sectors.json minus WDC/STX/SNDK (+ VIX/WTI/BRENT, non-SIP).
Events caught up after a (re)start carry backfill=true.

## Rules (calibrated 10/20 on Jeffrey's CRWV 60C/65C + NVDA 215C fills, 1m SIP bars)
- z = 1m close change / median |1m change| of prior 30 bars.
- accelerate: z >= 1.25 and close > prior 15-min high.
- decelerate (while up): 1m change <= 35% of the best 1m change of the prior 3 bars and z <= 0.5.
- resume (after decel): z >= 1.25 and close > held level (high of the prior impulse).
- market-recede: breadth hit = non-ETF name making a new 15-min high on >=2x same-minute rvol; b5 = hits over 5 bars;
  warn when b5 <= 35% of its 45-min peak (peak >= 25), confirm after 10 straight minutes; market-resume at >= 60%.
- Every event carries distance to next $0.25/$0.50/$1 level and nearest FA wall (with age/stale flag).
- intrabar (basis=intrabar, provisional): same decel/resume test on the forming bar >=30 s in, from the collector's
  last SIP trade. Uncalibrated: no sub-minute history existed before 10/20; ticks-*.jsonl is building it.

## 10/20 replay scorecard
13/14 fills matched within -90/+75 s; exits median lag ~ +10 s (range -36..+51), entries ~ +17 s (-24..+73);
missed: CRWV 6:44 buy (bounce, not a 15-min-high break). ~14 extra flags in his windows, about half 1-2 min
pause->resume pairs he held through. market-recede warn 7:36, confirm 7:45 (he stopped 7:46:00); SPY/QQQ/SMH
last decels 7:30-7:32 with no resume after.

    python3 momentum.py --replay --date 2026-10-20 --symbols CRWV,NVDA --from 06:30 --to 08:30
