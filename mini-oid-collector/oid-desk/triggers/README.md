# OID mini trigger engine
Plain-Python desk checks on the mini (launchd `com.oid.desk.triggers`, every 60 s, RTH weekdays 6:30 AM-1:05 PM PT).
Wakes Rose's routine "OID mini event wake" only when an event fires. Never trades; never calls RH/FA/UW (zero FA budget).
- Inputs (desk-relative, `~/oid-desk/desk`): paper-trades/paper-open.json, trades.json, paper-trades/hal-live/*.json,
  cache/mini-option-quotes.json (OPRA), cache/mini-quotes.json, cache/bars/*-5m.json, market-data/latest/fa-levels.json,
  cache/focus-watch-events.jsonl.
- Events: position_move (+10/+20/-10/-25 on OPRA mark; live seats carry verify_on_rh=true), scale_out_due, close5_cross
  (gamma flip / seat_exit_lines), wall_roll (fresh walls only, <=10 min), new_seat / seat_closed, feed_stale/dead/recovered,
  nvda_driver_move / nvda_driver_move15, focus_* (forwarded focus_watch 5-min events; wall events dropped if walls stale).
- Dedupe: ~/oid-desk/state/triggers/state.json (per PT day). Log: ~/oid-desk/state/triggers/events.jsonl.
- Seats (2026-10-16): reads trades.json AND paper-trades/trades.json (the desk-state push path); live:true / -LIVE- ids are book=live;
  live RH option positions in cache/rh-live-option-positions.json (both accounts) not covered by a seat become RH-<acct>-<occ> seats.
- Batching (2026-10-16): one POST per run (= per minute). One event keeps the flat body; several become event_type=batch with
  details.events[]. focus_wall_roll is dropped when the engine's own wall_roll for the same wall/price is in the batch.
  Wall-roll dedupe keys include the FA as_of so flip-flopping walls re-fire. NVDA peers: per_peer thresholds; prev_close
  falls back to market-data/latest/rh-quotes.json.
- Webhook: ~/.oid/webhook.env (chmod 600) with OID_WEBHOOK_URL / OID_WEBHOOK_KEY, filled by Jeffrey only.
  POST body {event_type, symbol, seat_id, details, data_stamp}; key sent as `Authorization: Bearer <key>` unless OID_WEBHOOK_KEY_HEADER set.
- Install (on mini): `./install.sh` (dry-run) -> `./install.sh --live` after parallel day. `./install.sh --uninstall` to remove.
- vol_surge (2026-10-18): separate fast loop, launchd `com.oid.desk.volsurge` (KeepAlive) runs `oid_triggers.py --vol-surge-loop`
  every `vol_surge.interval_s` (2 s) in RTH. Reads the collector's `GET /v1/live-volume` (token file ~/oid-quote/secrets/OID_QUOTE_TOKEN,
  read at runtime, never logged). Fires `vol_surge` when rolling 1-min SIP print volume >= 3x the same-minute 20-session norm, >= the
  share floor, and price crossed a level within 60 s (fresh FA walls/flip <= 30 min, seat_exit_lines, day high/low as of 5 min ago) by 2 bps.
  Skips first 2 min, half days, stream/print lag > 5 s, norms not built today. Once per symbol/level/PT day (volsurge-state.json).
  DRY-RUN unless config `vol_surge.live: true` AND global live (plist OID_TRIGGERS_MODE=live). Config hot-reloads (no restart).
  Status: ~/oid-desk/state/triggers/volsurge-status.json; events go to the same events.jsonl (engine=vol_surge).
  Test one tick: `python3 oid_triggers.py --vol-surge-once [--vol-surge-file saved.json]`. Unit tests: `python3 -m unittest discover -s tests`.


### vol_surge share floor (2026-10-18)
Per symbol: `per_symbol_min_shares_60s[sym]` if set, else the name's median 1-min norm (`norm_median_1m` from the collector) clamped to [`min_shares_floor_low` (2,000), `min_shares_60s` (20,000)]. Covers all 61 streamed symbols; thin names (KEYS, MH, ...) can fire on a genuine spike.

### vol_surge dry-run webhook notify (2026-10-18, v0.4.2, ladder dry run)
`vol_surge.notify_dry: true` POSTs DRY-RUN vol_surge events to the same wake webhook (~/.oid/webhook.env) so Rose pulls the
Robinhood price book read-only and runs `research/ladder-dryrun/ladder_dryrun.py ingest --event '<payload>'`. Trading behaviour is
unchanged: `live` stays false, events stay `dry_run: true`, and the live POST path is untouched.
- Payload: `{event_type:"vol_surge", symbol, seat_id, dry_run:true, test:false, tag:"ladder-dryrun", trade_action:"none",
  ticker, direction:"up|down", rvol, price, level, level_price, time_pt, data_stamp, details:{...original event...}}`.
- Caps (mini side): `notify_max_per_day` (20 per PT day), `notify_dedupe_min` (5 min per ticker), first event per ticker per tick.
  POST runs on a daemon thread (timeout `notify_timeout_s`, 8 s) so the 2 s loop never blocks. Counters live in volsurge-state.json.
- Log: `~/oid-desk/state/triggers/notify.jsonl` (ticker, direction, test, HTTP status; never URL/key); events.jsonl rows get `notify_status`
  (queued / dedupe / cap / same_tick / not_sent:<why>).
- **Off:** set `"notify_dry": false` in config.json (hot-reloaded within one loop tick, no restart).
- Self-test: `python3 oid_triggers.py --notify-test NVDA [--notify-test-dir down]` sends ONE payload with `test:true, tag:"ladder-dryrun-test"`.
- Rollback: `*.bak-20261018-v042` next to oid_triggers.py, config.json, tests/test_volsurge.py, then `launchctl kickstart -k gui/$(id -u)/com.oid.desk.volsurge`.
