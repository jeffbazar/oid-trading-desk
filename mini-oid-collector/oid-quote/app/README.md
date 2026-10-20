# OID quote collector (Phase 1 MVP)

One Alpaca market-data ingress on the Mac mini → in-memory latest-quote cache → small HTTP API for Rose, Hal and the other bots.

- **Stocks:** Alpaca v2 websocket, `sip` feed (Algo Trader Plus, consolidated). If the account isn't entitled to SIP (error 409), it falls back to `iex` automatically and retries SIP every 30 min. Subscribes **quotes + trades** for the core-20 in `stream-quote-allowlist.json`.
- **Overnight (v0.2.0):** 8 PM–4 AM ET, Sunday night through Friday morning, the *same single* stock connection is closed on `v2/sip` and reopened on `wss://stream.data.alpaca.markets/v1beta1/overnight` (Alpaca's derived overnight feed, BOATS-sourced, JSON, same `q`/`t` messages), then moves back to SIP at 4 AM ET. It never holds two stock sockets at once (Alpaca's per-endpoint connection limit is 1 on most plans). The schedule is checked every 10 s; `/v1/health → stock_schedule` shows the scheduled feed and `next_switch_at`. Rows carry `feed: alpaca-overnight`, `venue_scope: overnight`, `stream_feed` (`sip`/`overnight`) and per-channel `quote_feed` / `trade_feed`; `session` reads `overnight` in that window. Disable with `"stock_overnight_feed": null` in config.json or `--no-overnight`. No iex fallback overnight (a 409 just retries).
- **Options:** Alpaca v1beta1 `opra` websocket (msgpack only). Subscriptions are read from `~/oid-quote/options-subs.json`, a list of OCC symbols. The file can be empty, it's re-read every 5 s, and it's capped at 1000 contracts.
- **Options subs API + seeding (v0.3.0):** `PUT /v1/options/subs` (Bearer; body = list or `{"contracts": [...]}`) validates and atomically rewrites `options-subs.json` and applies it immediately; `GET /v1/options/subs` shows the list. The box declares its contracts this way (`quotes/option_marks.py push`). Subscribed contracts that have no quote yet (new subs, weekends, pre-open) are seeded once from Alpaca's data-only REST snapshot (`data.alpaca.markets/v1beta1/options/snapshots`, `feed=opra`): those rows carry `quote_feed`/`trade_feed` = `opra-snapshot` and their real exchange timestamps, so `source_age_s` shows how old they are. Retry for empty snapshots every 5 min. Disable with `"option_seed_enabled": false`.
- **Cache:** latest bid/ask/sizes plus last trade per symbol. It's written atomically to `~/oid-quote/cache/quotes.json` every 2 s.
- **API (port 8787):** `GET /v1/health` (no auth), `GET /v1/quotes?symbols=…`, `GET /v1/options?contracts=…` (both need `Authorization: Bearer <OID_QUOTE_TOKEN>`).
- **Placeholder mode:** with no Alpaca keys, the HTTP server still runs and health reports `status: "no_keys"`. Once you save keys, the feeds start within about 15 s, with no restart needed.
- **Data only.** The collector only connects to `stream.data.alpaca.markets` market-data streams. It makes no trading or brokerage calls of any kind, and it never logs or prints keys or the token.

## Layout on the mini

```
~/oid-quote/
  secrets/            (chmod 700) APCA_API_KEY_ID, APCA_API_SECRET_KEY, OID_QUOTE_TOKEN (chmod 600)
  app/                code (replaced on every install)
  venv/               Python 3.12 venv (aiohttp, msgpack, certifi)
  logs/               collector.log (rotates 5 MB x 5), launchd.err.log / launchd.out.log
  cache/quotes.json   snapshot every ~2 s
  config.json         your settings (created once, never overwritten)
  options-subs.json   OCC contracts to stream (created as [] once, never overwritten)
  stream-quote-allowlist.json   OPTIONAL override of the bundled core-20 list
~/Library/LaunchAgents/com.oid.quote-collector.plist   (RunAtLoad + KeepAlive)
```

## Install / upgrade (on the mini, as `jake`)

```bash
cd ~
tar xzf oid-quote-collector.tar.gz
cd oid-quote-collector
./install.sh
```

`install.sh` does the following:
- checks for `/opt/homebrew/bin/python3.12`
- creates `~/oid-quote/venv` and installs `requirements.txt`
- copies the code to `~/oid-quote/app`
- generates `secrets/OID_QUOTE_TOKEN` if it's missing (chmod 600, never printed)
- installs and loads the launchd agent
- curls `http://127.0.0.1:8787/v1/health`

Re-running it is safe. It upgrades the code and keeps your config, secrets and subscriptions.

## Save your keys (Jeffrey; type them yourself, never paste them in chat)

These commands work in both zsh (the macOS default) and bash. The key isn't echoed and doesn't go into shell history.

```bash
cd ~/oid-quote/secrets && umask 077
printf 'Alpaca API key ID: ';  read -rs K; echo; printf '%s\n' "$K" > APCA_API_KEY_ID;     unset K
printf 'Alpaca API secret: ';  read -rs S; echo; printf '%s\n' "$S" > APCA_API_SECRET_KEY; unset S
chmod 600 APCA_API_KEY_ID APCA_API_SECRET_KEY
ls -l   # expect -rw------- on all three files
```

The collector picks the keys up within about 15 s. To force it right away, run `launchctl kickstart -k gui/$(id -u)/com.oid.quote-collector`.

Use a **data-only key on the Algo Trader Plus account**. The collector never trades, but a key with no trading use limits the damage if it leaks. If you set the keys as env vars named `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` instead, the env vars take priority over the files.

To read the API token on the mini (for the box/bots' secrets), run `cat ~/oid-quote/secrets/OID_QUOTE_TOKEN`. Copy it into the box's agent secrets yourself.

## Smoke test

```bash
PY=~/oid-quote/venv/bin/python
# 1) health (no auth). Before keys: "status": "no_keys". After keys, during market hours: "ok"
curl -s http://127.0.0.1:8787/v1/health | $PY -m json.tool

# 2) stock quotes (auth)
TOKEN="$(cat ~/oid-quote/secrets/OID_QUOTE_TOKEN)"
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8787/v1/quotes?symbols=NVDA,SPY" | $PY -m json.tool

# 3) one option contract: add it to the subscription file (use a real listed OCC symbol)
echo '["NVDA261016C00190000"]' > ~/oid-quote/options-subs.json
sleep 8
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8787/v1/options?contracts=NVDA261016C00190000" | $PY -m json.tool

# 4) no token must be rejected (expect 401)
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:8787/v1/quotes?symbols=NVDA"

# 5) from another machine on the LAN / tailnet
curl -s http://Jakes-Mac-mini.local:8787/v1/health
```

Phase 1 "green" means: during RTH, NVDA and one option contract show `bid`/`ask` with `source_observed_at` timestamps, `feed` is `alpaca-sip` / `alpaca-opra`, and `feed_status` is `ok`.

Outside market hours the sockets still connect and authenticate (health shows `ok`), but few or no new quotes arrive, so the rows go `stale` after 120 s. That's expected.

## Options subscriptions

`~/oid-quote/options-subs.json` accepts any of these forms:
```json
["NVDA261016C00190000", "SPY261009P00650000"]
{"contracts": ["NVDA261016C00190000"]}
```
- Symbols are upper-cased, de-duplicated and validated (`ROOT YYMMDD C|P STRIKE×1000`, 8 digits). An `O:` prefix is stripped.
- Invalid entries are skipped and listed in `/v1/health → subscriptions.options.invalid`.
- The first 1000 contracts are kept and the rest are reported as `truncated`.
- Bad JSON keeps the previous list.
- Changes are applied live as subscribe/unsubscribe diffs (no reconnect). Wildcards are never sent.

## API

`GET /v1/health` (no auth) returns:
- `status`:
  - `ok`: both sockets authenticated
  - `partial`: only one is
  - `connecting`
  - `auth_failed`: bad keys, error 402
  - `no_keys`
  - `idle`
- `stocks` / `options`: `connected`, `feed`, `fallback_active`, `last_message_age_s`, `last_data_age_s`, `connects`, `reconnects`, `desired_count`, `subscribed_count`, `last_error`
- `subscriptions`: `count`, `invalid`, `truncated` and `error` for each file
- `cache`: row counts and counters, plus a lag histogram of `received_at − source_observed_at`
- `snapshot`: info about the last cache write

`GET /v1/quotes?symbols=NVDA,SPY` and `GET /v1/options?contracts=OCC1,OCC2` take a Bearer token. Leave the list off to get every cached row. Each row has:

| field | meaning |
| --- | --- |
| `instrument_id` / `contract_id` | symbol as Alpaca sends it |
| `bid`, `ask`, `bid_size`, `ask_size`, `bid_exchange`, `ask_exchange`, `quote_conditions` | quote channel |
| `last`, `last_size`, `last_exchange`, `trade_conditions` | trade channel |
| `source_observed_at` | newest exchange/stream timestamp (UTC, ns precision) |
| `quote_observed_at`, `trade_observed_at` | per-channel source timestamps |
| `received_at` | collector clock, PT ISO |
| `source_age_s`, `received_age_s` | ages at request time; gates should use **source** age |
| `session` | `RTH` / `extended` / `closed` (ET clock; holidays not modeled) |
| `delayed` | `false` for sip/iex/opra; `true` for indicative/delayed_sip |
| `feed` | `alpaca-sip` / `alpaca-iex` / `alpaca-opra` / … |
| `venue_scope` | `consolidated` / `iex` / `OPRA` |
| `feed_status` | `ok` / `stale` (no update for 120 s) / `disconnected` / `unsubscribed` |

## Config (`~/oid-quote/config.json`)

| key | default | notes |
| --- | --- | --- |
| `host` | `0.0.0.0` | Set to the mini's Tailscale `100.x` IP later to bind tailnet-only |
| `port` | `8787` | |
| `stock_feed` | `sip` | also `iex`, `delayed_sip` |
| `stock_feed_fallback` | `iex` | `null` to disable |
| `options_feed` | `opra` | `indicative` = delayed/derived, marked `delayed: true` |
| `option_cap` | `1000` | hard max 1000 |
| `enable_options` | `true` | |

Env overrides: `OID_QUOTE_HOST`, `OID_QUOTE_PORT`, `OID_QUOTE_STOCK_FEED`, `OID_QUOTE_OPTIONS_FEED`. Restart after editing.

## Operations

```bash
tail -f ~/oid-quote/logs/collector.log                          # connects, reconnects, sub changes, errors
launchctl kickstart -k gui/$(id -u)/com.oid.quote-collector      # restart
launchctl bootout gui/$(id -u)/com.oid.quote-collector           # stop (until next install/login)
launchctl print gui/$(id -u)/com.oid.quote-collector | head -30  # status
~/oid-quote/venv/bin/python -m oid_quote --root ~/oid-quote --check   # resolved config + which secrets exist (no values)
./uninstall.sh                                                   # remove agent; leaves ~/oid-quote
```

Foreground debug run (stop the agent first): `cd ~/oid-quote/app && ../venv/bin/python -m oid_quote --root ~/oid-quote`

Offline tests (fake Alpaca server, no keys or network needed): `cd ~/oid-quote/app && ../venv/bin/python -m unittest discover -s tests -t .`

## Notes / caveats

- **One connection per endpoint.** Alpaca allows one stocks and one options stream per account on most plans. If another app or bot uses the same keys, you'll see `406 connection limit exceeded` and the collector retries every 30 s. Only the mini should open these sockets.
- **LaunchAgent = runs while `jake` is logged in.** For unattended reboots, enable automatic login for `jake` (System Settings › Users & Groups), and stop the mini from sleeping (Energy › "Prevent automatic sleeping when the display is off").
- **macOS firewall.** If you turn the firewall back on, allow incoming connections for `~/oid-quote/venv/bin/python` (it's a symlink to Homebrew Python 3.12). Otherwise other machines can't reach port 8787.
- **Binding:** it currently binds `0.0.0.0` (LAN + tailnet). Health is open but holds no quotes; quotes and options need the token. Tailscale-only binding is a later step.
- **Not yet handled (MVP):** trade corrections and cancels, and exchange holidays in `session`. Phase 3 adds quote-quality checks and alarms.
