# oid-score — composite direction score (−3…+3) + outcome tracker (Mac mini)

Research/log only. Never places orders. Zero extra FlashAlpha/UW/paid calls. It reads files and the local live page state.

- `score_daemon.py` (launchd `com.oid.desk.score`, KeepAlive): during market hours it logs rows at the anchor, grid and vol_surge times to `~/oid-data/score/scores-YYYYMMDD.jsonl`, and writes the ~60 s badge feed `latest.json`.
- `score_outcomes.py` + `score_report.py` (launchd `com.oid.desk.score-grade`, every 15 min via `score_grade.sh`): fill forward returns, MFE/MAE and wall/flip touches for +5m…close and next open; write reports to `~/oid-data/score/reports/`.
- `score_backfill.py <date>`: replays a past session from logged bars (`mode=backfill`, with lookahead flags).
- `score_report.py --config alt.json` re-scores history with another config. `--ablate` drops one input at a time.
- Config: `~/oid-data/config/score-config.json` (`config_version` is stamped on every row; the daemon hot-reloads it).
- Install/uninstall: `./install.sh` / `./install.sh --uninstall`. Logs: `logs/`.
- Full spec: Field Guide page 24 (`docs/24-direction-score.md`, served at `/guide/#24-direction-score.md`).

## v1.2-20261022 — Rule 5 negative-gamma / de-grossing walls clamp + Rule 4d downtrend volume clamp
- `score_lib.py` (`_apply_clamps`, active in `build_components()` and `rescore()`):
  - **Negative-gamma / de-grossing regime (`Rule 5`):** holds when `px < gf` (`below_gf`), OR `degross_armed()` (`~/oid-data/degross/latest.json` badge is `DE-GROSSING`, cached by `mtime` with a 5 s `stat()` TTL and safe `False` fallback) with `market_c < 0` (`degross_mkt_neg`), OR `gf is None and trend_c < 0 and market_c < 0` (`no_gf_downtrend`).
  - **Walls clamp (`Rule 5`, `components.walls.clamp_rule5: true`):** in that regime, clamps `walls_c = min(walls_c, 0.0)` (preserving `-0.3` below the put wall while preventing `+0.01..+1.0` bullish wall-headroom votes when pressed against the put wall).
  - **Volume clamp (`Rule 4d`, `components.volume.clamp_downtrend: true`):** when in that regime AND `trend_c < 0`, clamps `volume_c = min(volume_c, 0.0)` so 1-minute short-covering volume surges during an intraday downtrend cannot vote `+1.0` bullish at bounce tops.
  - Records `regime_clamp`, `clamped`, `clamp_reason`, and `raw_c` in `comps["walls"]["f"]` and `comps["volume"]["f"]`.

## v1.1-20261020 — score change + episode logging (logging only; score math unchanged)
- `score_daemon.py` now also runs a fast pass every `cadence_pt.change_refresh_s` (5 s) that re-scores every ticker on the live price, 1-min bars and options flow (walls/VIX refresh at their own pace) and, via `score_changes.py`, appends:
  - `~/oid-data/score/changes-YYYYMMDD.jsonl`: one row whenever a ticker's integer score changes (plus its first score of the session): new/previous score, ts (UTC + PT), price, every component, settings version, start + duration of the score that ended, and context (aggressor C/P 15 s + 1 m, UW C/P and lean, rvol_1m, room to call/put wall in ATR, wall age, momentum state + age, the stock's 60/120 s tape from 5 s bars, SPY/QQQ 60/120 s tape, agreement flags).
  - `~/oid-data/score/episodes-YYYYMMDD.jsonl`: one row when a score ends: start/stop ts + price, peak/trough (5 s SIP bars + live last), MFE/MAE in the score's direction, context at start and stop. Open holds close at 1:00 PM PT (`session_end`); `changes-state.json` lets a restart resume them.
- Buffered score: COMPARISON-ONLY shadow (hysteresis band `changes.buffer_band`, 0.15). Logged as `buffered_score` on change rows and as `episodes-buffered-YYYYMMDD.jsonl`; the raw score stays primary everywhere (changes/episodes, latest.json, live page, scorecard).
- `scores-*.jsonl` slots, `latest.json` badge (60 s) and the outcomes grader are unchanged.
- `score_replay_changes.py <date>` replays a session from 5 s bars into `~/oid-data/score/replay-YYYYMMDD/` (test/measurement).
- `daily_scorecard.py [date]` (launchd `com.oid.desk.score-scorecard`, weekdays 1:10 PM PT) writes `scorecard-YYYYMMDD.json/.md` from episodes (falls back to holds rebuilt from `scores-*.jsonl`).

## light-v1.0-20261021 — LIGHT direction score for the 144 Sector watch names (separate from the core)
- `score_wide.py` (launchd `com.oid.desk.score-wide`, KeepAlive, Nice 10): every 5 s in market hours scores each wide name with the **light** profile (`score-config.json` → `profiles.light`): the core's trend (1.00), volume (0.75) and market (0.75) inputs with the same calculations and weights; flip, walls and options flow are switched off, and `score_lib.combine()` divides by the enabled weights (2.50), so the score keeps the −3…+3 range. Raw and unsmoothed.
- Writes only its own files: `changes-wide-YYYYMMDD.jsonl`, `episodes-wide-YYYYMMDD.jsonl`, `episodes-wide-buffered-YYYYMMDD.jsonl` (comparison-only shadow), `changes-wide-state.json`, `latest-wide.json` (live page). Every row has `score_profile: "light"`, `profile_version`, `sector_id`, `sector`.
- Data: wide bar store `~/oid-quote/cache/bars-wide/store` (1-min bars, ATR history, `live-norms-1m.json`), wide 5 s bars `~/oid-data/archive-wide/volume_5s`, SPY/QQQ from the core store/archive, price from the live page's wide rows. WDC/STX/SNDK excluded.
- `daily_scorecard.py` (same 1:10 PM PT job) also writes `scorecard-wide-YYYYMMDD.json/.md` (every core section + score × sector + ±2/±3 counts by sector + held before acting) and `changes-wide-fwd-YYYYMMDD.jsonl`. `--profile core|light|all`.
- `score_replay_wide.py <date>` replays a session into `~/oid-data/score/replay-YYYYMMDD-wide/` (uses 1-min bars when no wide 5 s RTH bars exist).
- Live page: Sector watch rows show a small `L±n` chip (light, raw, unsmoothed). Field Guide page 24 §"Light score" and page 27.
