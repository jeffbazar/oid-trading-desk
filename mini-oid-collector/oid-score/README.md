# oid-score — composite direction score (−3…+3) + outcome tracker (Mac mini)

Research/log only. Never places orders. Zero extra FlashAlpha/UW/paid calls. It reads files and the local live page state.

- `score_daemon.py` (launchd `com.oid.desk.score`, KeepAlive): during market hours it logs rows at the anchor, grid and vol_surge times to `~/oid-data/score/scores-YYYYMMDD.jsonl`, and writes the ~60 s badge feed `latest.json`.
- `score_outcomes.py` + `score_report.py` (launchd `com.oid.desk.score-grade`, every 15 min via `score_grade.sh`): fill forward returns, MFE/MAE and wall/flip touches for +5m…close and next open; write reports to `~/oid-data/score/reports/`.
- `score_backfill.py <date>`: replays a past session from logged bars (`mode=backfill`, with lookahead flags).
- `score_report.py --config alt.json` re-scores history with another config. `--ablate` drops one input at a time.
- Config: `~/oid-data/config/score-config.json` (`config_version` is stamped on every row; the daemon hot-reloads it).
- Install/uninstall: `./install.sh` / `./install.sh --uninstall`. Logs: `logs/`.
- Full spec: Field Guide page 24 (`docs/24-direction-score.md`, served at `/guide/#24-direction-score.md`).

## v1.1-20261020 — score change + episode logging (logging only; score math unchanged)
- `score_daemon.py` now also runs a fast pass every `cadence_pt.change_refresh_s` (5 s) that re-scores every ticker on the live price, 1-min bars and options flow (walls/VIX refresh at their own pace) and, via `score_changes.py`, appends:
  - `~/oid-data/score/changes-YYYYMMDD.jsonl`: one row whenever a ticker's integer score changes (plus its first score of the session): new/previous score, ts (UTC + PT), price, every component, settings version, start + duration of the score that ended, and context (aggressor C/P 15 s + 1 m, UW C/P and lean, rvol_1m, room to call/put wall in ATR, wall age, momentum state + age, the stock's 60/120 s tape from 5 s bars, SPY/QQQ 60/120 s tape, agreement flags).
  - `~/oid-data/score/episodes-YYYYMMDD.jsonl`: one row when a score ends: start/stop ts + price, peak/trough (5 s SIP bars + live last), MFE/MAE in the score's direction, context at start and stop. Open holds close at 1:00 PM PT (`session_end`); `changes-state.json` lets a restart resume them.
- Buffered score: COMPARISON-ONLY shadow (hysteresis band `changes.buffer_band`, 0.15). Logged as `buffered_score` on change rows and as `episodes-buffered-YYYYMMDD.jsonl`; the raw score stays primary everywhere (changes/episodes, latest.json, live page, scorecard).
- `scores-*.jsonl` slots, `latest.json` badge (60 s) and the outcomes grader are unchanged.
- `score_replay_changes.py <date>` replays a session from 5 s bars into `~/oid-data/score/replay-YYYYMMDD/` (test/measurement).
- `daily_scorecard.py [date]` (launchd `com.oid.desk.score-scorecard`, weekdays 1:10 PM PT) writes `scorecard-YYYYMMDD.json/.md` from episodes (falls back to holds rebuilt from `scores-*.jsonl`).
