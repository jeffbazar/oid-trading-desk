# hal-exit-watch: rules file contract

Hal writes `paper-trades/hal-live/active-exit-rules.json` on the box (`/workspace/oid-trading-desk/...`) at every entry
and exit (whole file, atomic). `quotes/mirror_poller.py` on the box pushes it to the mini over POST `/v1/desk-state`
(it's on the `desk_state` allow-list in `config/mirror-feeds.json`, box and mini; `push_every_s` is 15 in `config/mirror.json`).
Latency: ≤ about 15 s in RTH (poller cycle 15 s), ≤ 60 s otherwise. The mini job `com.oid.desk.hal-exit-watch`
(`oid_desk/hal_exit_watch.py`) re-reads it every 3 s check. `quotes/option_marks.desired_contracts` adds every seat's
OCC to the OPRA subscription (`ref hal-exit:<seat_id>`).

- `active-exit-rules.schema.json`: JSON Schema (draft 2020-12). Hal's seed `{owner, account, updated_at, seats: []}` validates.
- `active-exit-rules.example.json`: a live single-leg call and a paper put debit spread.
- Field Guide page: `~/oid-live-page/guide/docs/28-hal-exit-watch.md` (timers: page 27, "Exit watch").

Webhook payload (POST JSON, `Authorization: Bearer <HAL_EXIT_WEBHOOK_KEY>`):

```json
{"source":"mini:hal-exit-watch","event":"exit_rule_tripped","status":"trigger","mode":"live",
 "seat_id":"...","account":"8444","underlying":"AMD","occ_symbol":"AMD261023C00540000","side":"long_call","qty":2,
 "rule":"option_stop","leg":"option",
 "observed":{"option_mid":7.0,"option_bid":6.9,"option_ask":7.1,"option_age_s":0.8,"stock_last":536.2,"stock_bid":536.1,
             "stock_ask":536.3,"stock_age_s":0.4,"level":7.05,"bid_below_stop":true,"stock_stop":533.5,
             "stock_stop_also_hit":false,"cause":"option mark only (stock still inside its stop: decay / IV / spread)"},
 "quote_age_s":0.8,"fire_n":1,"max_fires":3,"refire_s":120,"first_tripped_at":"2026-10-21T16:02:01Z",
 "ts":"2026-10-21T16:02:04Z","ts_pt":"2026-10-21 9:02:04 AM PT","rules_updated_at":"...","watcher_version":"1.0.0-20261020",
 "detail":"... plain text ...","never_trades":true,"note":"Exit alert only. ..."}
```

Rules: option_stop, stock_stop, target_option, target_stock, take_half, structure_break, time_stop, preclose_dte, quotes_stale.
De-dupe: price rules need 2 consecutive checks; each (seat, rule) fires once, re-fires every 120 s while still tripped, max 3/day.
Mode: live when both `~/oid-quote/secrets/HAL_EXIT_WEBHOOK_URL` and `HAL_EXIT_WEBHOOK_KEY` exist (hot-loaded), else dry run.
Enter them on the mini: `~/oid-desk/bin/hal-exit-keys.sh` (hidden input, 600). Force dry: `touch ~/oid-desk/flags/hal-exit-watch.dry`.
