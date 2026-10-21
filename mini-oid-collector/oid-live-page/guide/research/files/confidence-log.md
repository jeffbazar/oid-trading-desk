# Confidence log + weekly calibration (DECISION-V1.1)

Approved by Jeffrey Sun 10/11/2026. **Scorekeeping only**: nothing here reads, changes or gates any trading
threshold, seat size, schedule or order. Paper ledger stays `paper-trades/trades.json`; zero RH execution.

- Journal (append-only, never edited): `journal/decisions/decisions.jsonl`
  (`kind=decision` rows + later `kind=resolution` rows; newest resolution wins).
- Helper: `paper-trades/decision_log.py` (alias `scripts/decision_log.py`, the R7 path in MINI-ARCHIVE-PLAN).
- Report: `paper-trades/calibration_report.py` -> `journal/calibration/YYYY-WW.md|.json` + `latest.json`
  (also lands in the blotter snapshot as `snapshot.calibration` / `data/calibration.json`, data only).
- Mini: Phase A archiver ingests this same file through `POST /v1/desk-state` append mode.

## What confidence means
`--confidence` is always **our stated probability that the setup works** (0-1), written at decision time.
- ELEVATE/OPEN: P(the seat wins). Default rule `PNL_SIGN` = seat realized P&L > 0 incl. scale-outs
  (same rule as SCORECARD). Optional `--rule HALF_TAKE_20` = reached the +20% half-take before stop/expiry.
- REJECT/NO_TRADE/WATCH: P(the skipped setup would have worked). Rule `UNDERLYING_TARGET`: underlying hits
  target before stop within the horizon (default target/stop = FA call/put wall for calls, reversed for puts;
  default horizon 3d). Resolved from 5-min bars, **flagged best effort**.
- `--basis` is required: one short line of why (e.g. "fresh CW + ask-heavy flow, put-led tide").
- Give an honest number; 0.5 means coin flip. Do not reuse the same number by habit.

## One-line commands for routines (paste into Rose/Hal routine prompts)
D=/workspace/oid-trading-desk/paper-trades

**Elevate/open a paper seat** (after the seat is appended to trades.json):
```
python3 $D/decision_log.py add --trader rose --action ELEVATE --seat <SEAT_ID> --confidence 0.65 --basis "<why>"
```
(Hal: `--trader hal`. Live Agentic order instead of a paper seat: `--action OPEN --symbol <SYM> --live-order <RH_ORDER_ID> --horizon 3d`.)

**Reject / no-trade a candidate** (once per evaluated candidate):
```
python3 $D/decision_log.py add --trader hal --action REJECT --symbol <SYM> --confidence 0.30 --basis "<why>" --reasons IV_RICH,WALL_TOO_CLOSE
```
(`--action NO_TRADE` for an explicit pass on the scan; add `--direction down` for put setups; override levels
with `--target <px> --stop <px>`; horizon with `--horizon 4h|eod|3d|YYYY-MM-DD`.)

**Close / invalidate / expire a seat** (after trades.json + refresh_scorecard.py are updated):
```
python3 $D/decision_log.py resolve --seat <SEAT_ID>
```
**Live Agentic order closed** (no box ledger for those yet):
```
python3 $D/decision_log.py resolve --id <CANDIDATE_ID> --outcome win|loss|scratch --pnl-pct <x>
```
**Weekly calibration** (e.g. Friday after the close; resolves pending calls first):
```
python3 $D/calibration_report.py --auto-resolve
```
Check: `python3 $D/decision_log.py list --open`

## Backfill
`decision_log.py backfill` logged the 61 parent seats that predate the log (scale-out children fold into their
parent) with `confidence=null`, `backfill=true`. They count toward win rate only, never Brier/ECE. A later real
entry for the same seat supersedes its backfill row in the report. Seat-level win rate (59%, 35W/24L/1 scratch,
1 open) differs from SCORECARD's per-row 61% because SCORECARD counts scale-out halves as separate rows.

## Report contents
By Rose, Hal and overall (each split taken vs passed): count, win rate, mean confidence, reliability buckets
(<0.5, 0.5-0.6 ... 0.9-1.0: predicted vs actual), Brier, ECE, overconfidence flags (gap > 10 pts; bucket n>=5),
and SMALL SAMPLE warnings (n<20 scored calls = not significant). Cumulative through the week end; binary
win=1, loss/expired=0, scratch/open excluded.

## Record fields (added to DECISION-V1)
`confidence`, `confidence_basis`, `outcome_rule`, `outcome_definition`, `horizon`, `horizon_end`, `seat_id`,
`live_order_ref`, `backfill`; resolution: `outcome` (win/loss/scratch/expired/open), `resolved_at`,
`realized_pnl_pct`, `realized_pnl_usd`, `resolution_method` (seat_ledger | bars_best_effort | manual), `best_effort`.
Any DECISION-V1 extras (inputs[], gates[], contract quote, mandate) can be passed with `--json '{...}'`.
Tests: `tests/test_decision_log.py`.
