# 29 · How data is saved (every archived file, its columns and a real row)

*Added **Tue 10/20/2026, 4:35 PM PT**. All times PT unless a field says UTC. Research and logging only: nothing here places orders.*

## In plain words

- Every number the desk shows during the day is saved to a file on the Mac mini with its own timestamp, so any second of the day can be replayed later.
- The **core tickers** (about 61 streamed names) and the **144 Sector watch names** now save the **same kinds of rows**: 5-second volume bars, 1-minute bars (live and the final REST copy), Parquet copies with 5-min / 15-min / 1-hour rollups, 15-second C/P history, and a row for every direction-score change and every finished score hold.
- Two things the Sector watch still does **not** have, by design: the momentum engine (ACCEL / DECEL / RESUME), and the old 15-minute score grid (`scores-*.jsonl`). The change and hold files replace the grid.
- The Sector watch **C/P is measured differently** (see "Why the Sector watch C/P is a tick test" below), and its walls come only from on-surge FlashAlpha pulls.
- Raw stock and option prints are **not** saved one by one, for the core or the Sector watch. They are rolled up in memory into the 5-second buckets, 1-minute bars and 15 s / 60 s C/P windows, and those roll-ups are what's saved.

## Core vs Sector watch, file by file

Sizes are bytes on disk for one full trading day (measured 10/19–10/20; Sector watch sizes are estimates until its first full session on Wed 10/21).

| What | Core file | Sector watch file | Written | Timestamp fields | Kept | Size / day |
|---|---|---|---|---|---|---|
| Raw stock trades / quotes | not saved (rolled up in memory) | not saved | — | — | — | — |
| Raw option trades / quotes | not saved (last 50 prints per name viewable at `127.0.0.1:8792/v1/recent?sym=`) | not saved | — | — | — | — |
| 5-second volume bars | `~/oid-data/archive/volume_5s/date=YYYY-MM-DD/part-oid-quote-N.jsonl` | `~/oid-data/archive-wide/volume_5s/date=YYYY-MM-DD/part-oid-quote-wide-N.jsonl` | every 5 s, 3 s after the bucket closes; regular hours = one row per name per bucket (zero volume allowed), pre/post = only names that traded | `bucket_start_ns` / `bucket_end_ns` (UTC epoch nanoseconds), `bucket_start_iso` (UTC, `Z`), `event_ts_*`, `ingest_ts_*` | JSONL 90 days (deleted only once Parquet holds every row), Parquet forever | core ≈ 265–290 MB JSONL + 18 MB Parquet; wide ≈ 400–450 MB JSONL + ≈ 40 MB Parquet (est.) |
| 1-minute bars, live | `~/oid-data/archive/bars_1m/date=…/part-oid-quote-N.jsonl` | `~/oid-data/archive-wide/bars_1m/date=…/part-oid-quote-wide-N.jsonl` | each minute from Alpaca's websocket bars (`final: false`) | `bar_start_ns`, `bar_end_ns`, `bar_start_iso`, `event_ts_*`, `ingest_ts_*` (UTC) | as above | core ≈ 24 MB, wide ≈ 2–8 MB |
| 1-minute bars, final (REST) | `…/archive/bars_1m/date=…/part-bars-reconcile-N.jsonl` | `…/archive-wide/bars_1m/date=…/part-bars-reconcile-N.jsonl` (**new 10/20**) | 2:00 PM (core) / 2:10 PM (wide) for pre + regular hours, 5:15 PM / 5:25 PM for after hours | same as above, `final: true`, `writer: bars-reconcile` | as above | core ≈ 20 MB, wide ≈ 40 MB |
| Parquet + 5m / 15m / 1h bars, daily bar | `~/oid-data/archive/parquet/<table>/date=…/<table>-D-main.parquet` (+ `-post`) | `~/oid-data/archive-wide/parquet/…` (**new 10/20**) | same jobs as the REST copy | same columns as the JSONL | forever | core ≈ 20 MB, wide ≈ 45 MB |
| C/P history (15 s) | `~/oid-optflow/data/cp-history/YYYY-MM-DD.jsonl` | `~/oid-optflow/data/cp-history-wide/YYYY-MM-DD.jsonl` (**new 10/20**) | every 15 s in regular hours | `t` (epoch seconds of the slot start), `pt` (PT clock `HH:MM:SS`), `sel` (when the contract set was picked, PT ISO) | 365 days (gzipped the next day) | core 6.8 MB, wide ≈ 15–17 MB (est.) |
| Live options flow snapshot | `~/oid-optflow/data/optflow.json` | `~/oid-optflow/data/optflow-wide.json` (**new**) | rewritten every 1 s | `computed_at` (PT ISO), `computed_epoch`, `last_trade_t`, `last_recv` | overwritten (the 15 s history above is the archive) | ≈ 30 KB / 80 KB file |
| Options contract set | `~/oid-optflow/data/optflow-subs.json` | `~/oid-optflow/data/optflow-wide-subs.json` (**new**) | every 15 min | `selected_at` (PT ISO) | overwritten | 32 KB / 96 KB |
| Momentum events | `~/oid-desk/state/momentum/events-YYYYMMDD.jsonl`, `ticks-YYYYMMDD.jsonl` | not produced (momentum engine is core only) | on each event / bar | `time_pt` (`YYYY-MM-DD hh:mm:ss AM PT`) | kept | 2.5 + 1.7 MB |
| Score grid (15 min + volume-surge rows) | `~/oid-data/score/scores-YYYYMMDD.jsonl` | not produced | 15-min grid + anchors + surge events | `t` (epoch s), `t_pt` | kept | 2.2 MB |
| Score changes | `~/oid-data/score/changes-YYYYMMDD.jsonl` | light: `changes-wide-YYYYMMDD.jsonl`; full: `changes-widefull-YYYYMMDD.jsonl` (**new**) | checked every 5 s, one row only when the whole-number score changes (and the first score each day) | `t` (epoch s), `t_utc` (UTC, ms, `Z`), `t_pt`, plus `prev_start_*` | kept | ≈ 35–40 MB each |
| Score holds | `episodes-YYYYMMDD.jsonl` | `episodes-wide-…`, `episodes-widefull-…` | one row when a score ends | `start_t`/`stop_t`/`peak_t`/`trough_t` (epoch s) with `_utc` and `_pt` twins | kept | ≈ 40 MB each |
| Buffered shadow holds | `episodes-buffered-YYYYMMDD.jsonl` | `episodes-wide-buffered-…`, `episodes-widefull-buffered-…` | one row when the shadow score ends | same as holds | kept | 17–27 MB |
| Open holds (restart file) | `changes-state.json` | `changes-wide-state.json`, `changes-widefull-state.json` | every 30 s | `saved_t` | overwritten | small |
| Seconds check (+5/15/30/60 s) | `changes-fwd-YYYYMMDD.jsonl` | `changes-wide-fwd-…`, `changes-widefull-fwd-…` | after the session, by the 1:10 PM scorecard job | `t`, `t_pt`, `base_bar_end_t`, `fwd.<h>.bar_end_t` | kept | 5–7 MB |
| Score badge | `latest.json` (every 60 s) | `latest-wide.json`, `latest-widefull.json` (every 5 s) | overwritten | `as_of` (epoch s), `as_of_pt` | overwritten (changes files are the archive) | < 100 KB |
| Old fixed-window grading | `outcomes-YYYYMMDD.jsonl` | not produced | every 15 min | `t` | kept | 3.9 MB |
| Daily scorecard | `scorecard-YYYYMMDD.json/.md` | `scorecard-wide-YYYYMMDD.json/.md`, `scorecard-widefull-YYYYMMDD.json/.md` (**new**) | 1:10 PM PT weekdays | `generated_pt` | kept | < 200 KB |
| Live page state | not saved (in memory, `127.0.0.1:8791/state.json`) | not saved | — | — | — | — |

**Retention change (10/20):** the Sector watch archive used to delete its raw files after **21 days**. It now follows the core rule: raw JSONL is kept 90 days and deleted only after the Saturday check (`com.oid.archive.wide-weekly`, 10:15 AM) confirms the Parquet copy holds every row; Parquet is kept. At ≈ 0.5 GB a day for the Sector watch and 411 GB free, the disk has room for years.

**New jobs (10/20):** `com.oid.archive.wide-main` (2:10 PM), `com.oid.archive.wide-post` (5:25 PM), `com.oid.archive.wide-weekly` (Sat 10:15 AM), `com.oid.desk.score-widefull` (always on, 5 s in regular hours). `com.oid.desk.optflow` 0.4.0 now also streams the Sector watch option trades.

## Why the Sector watch C/P is a tick test

- The core C/P decides buy or sell by comparing each option print with that contract's live bid and ask (print at the ask = a buyer).
- Alpaca lets one connection watch **1,000 option quotes** at most, and this account allows **2 options connections**. Both are in use (the C/P stream uses 900 quotes, the collector keeps one for position marks), and a third connection was refused with "connection limit exceeded" when tested on 10/20.
- Option **trades** have no such cap (tested up to 2,400 plus the all-symbols feed). So the Sector watch rides the same connection as **trades only**: 2,972 contracts across 140 of the 144 names (4 had no options within 21 days and ±12% of price).
- Without a bid and ask, each print is judged by the **tick test**: above that contract's previous print = buy, below = sell, same price = same side as last time, first print of the day = neutral. It is less exact than the quote test, so every Sector watch C/P row carries `cls: "tick"`, and the full Sector watch score gives this input half weight (`q_tick` 0.5).

## Column tables

### changes-*.jsonl (core) and changes-wide / changes-widefull (Sector watch)

One row = the whole-number direction score of one ticker just changed (or was seen for the first time that day).

| Column | Unit | Meaning | How it's calculated (code) |
|---|---|---|---|
| `kind` | text | always `score_change` | `score_changes.Tracker.observe` |
| `sym`, `date` | text | ticker, PT trading date | |
| `score`, `prev_score` | −3…+3 | new score, the score that just ended (null on the first row of the day) | `score_lib.combine`: raw rounded half away from zero |
| `raw`, `prev_raw` | −3…+3 | unrounded score | `clamp(3 × 1.5 × s, −3, 3)`, `s = Σ(weight × quality × input) ÷ Σ(weight of enabled inputs)` |
| `t` | epoch seconds | moment of the change (fast pass clock) | `time.time()` of the 5 s pass |
| `t_utc`, `t_pt` | text | same moment in UTC (ms, `Z`) and PT | `utc_str(t)`, `pt_str(t)` |
| `px` | $ | price used for the pass | live last trade from the live page (Sector watch: live last, else last 5 s close) |
| `atr` | $ | 14-day average true range from 1-min history | `score_lib.daily_atr` |
| `coverage` | 0–1 | share of the score's weight that had good data | `Σ(weight × quality) ÷ Σ(weight)` |
| `stale`, `missing` | list | inputs that were stale or missing | from each input's flags |
| `settings_version`, `config_version` | text | config used (core `v1.1-20261020`, light `light-v1.0-20261021`, full `widefull-v1.0-20261021`) | |
| `mode`, `trigger` | text | `live` / `replay` / `test`; always `fast` | |
| `prev_start_t/_utc/_pt` | epoch s / text | when the score that just ended had started | |
| `prev_duration_s` | seconds | how long that score held | `t − prev_start_t` |
| `prev_start_px`, `prev_ret_bp` | $, basis points | price when it started, move since (1 bp = 0.01%) | `(px ÷ prev_start_px − 1) × 10,000` |
| `start_reason` | text | `score_change`, `first_seen`, `resume_after_gap` | |
| `agree.cp` | yes/no/null | C/P on the score's side | 1-min C/P (else 15 s, else UW lean) > 1.10 = call side, < 0.91 = put side |
| `agree.stock_tape_60/120` | yes/no/null | the stock's own 60 s / 120 s move matches the score's direction | from 5 s bars |
| `agree.market_60/120` | yes/no/null | average SPY/QQQ 60 s / 120 s move matches | from 5 s bars |
| `agree.room_dir_atr` | ATR | room to the call wall (score > 0) or put wall (score < 0) | `(call wall − px) ÷ ATR` or `(px − put wall) ÷ ATR` |
| `agree.surge` | yes/no | 1-min rvol ≥ 3 | |
| `agree.mom_state` | text | momentum engine state (core only) | |
| `comps.<input>.x` | mixed | raw measures for each input (below) | `score_lib.build_components` |
| `comps.<input>.f` | flags | source, age, stale / missing, `cls: tick` for Sector watch flow | |
| `comps.<input>.c` | −1…+1 | the input's reading | `score_lib.c_from_x` |
| `comps.<input>.q` | 0–1 | quality (1 = fresh; 0.5 stale, UW or tick-test flow; 0 = missing) | `score_lib.q_from_f` |
| `comps.<input>.w` | weight | flip 1.00, trend 1.00, volume 0.75, walls 0.75, market 0.75, flow 0.50 | config |
| `ctx.flow.cp_15s`, `cp_60s` | ratio | aggressor C/P = call-buy premium ÷ put-buy premium over the last 15 s / 60 s (99 = puts zero) | `optflow._summ` → live page `af15` / `af60` |
| `ctx.flow.thin_15s/60s` | yes/no | fewer than 5 prints in the window | |
| `ctx.flow.net_k_15s/60s` | $K | (call buy − call sell) − (put buy − put sell) premium | |
| `ctx.flow.n_15s/60s` | prints | classified + neutral prints in the window | |
| `ctx.flow.age_s`, `stale` | seconds, yes/no | time since the last option print; stale = over 30 s in regular hours | |
| `ctx.flow.uw_cp`, `lean5`, `lean15`, `ask_lean` | | Unusual Whales C/P and leans (core only) | |
| `ctx.flow.lean`, `cls`, `contracts` | | Sector watch only: CALL / PUT / FLAT from the C/P, `tick`, contracts streamed | |
| `ctx.flow_dir` | +1 / 0 / −1 | call side / flat / put side | `cp_side`: C/P > 1.10, < 1/1.10 |
| `ctx.rvol_1m`, `surge` | ×, yes/no | last 60 s volume ÷ normal for those minutes; surge = ≥ 3 | collector `rvol_1m` |
| `ctx.walls.cw/pw/gf` | $ | call wall, put wall, gamma flip | FlashAlpha (core: every 10 min; Sector watch: on surge only) |
| `ctx.walls.age_s`, `stale`, `src`, `as_of_pt` | | age of the levels, stale = over 20 min | |
| `ctx.room_call_atr`, `room_put_atr` | ATR | distance to the call / put wall | |
| `ctx.mom` | | momentum engine state, raw event, since, age (core only) | |
| `ctx.tape.60/120.ret_bp` | bp | the stock's move over the last 60 / 120 s | close of the last 5 s bar vs close 60 / 120 s earlier |
| `ctx.tape.*.hh/hl/lh/ll` | count | higher highs, higher lows, lower highs, lower lows between 5 s bars | |
| `ctx.tape.*.speed_bp_10s` | bp per 10 s | `ret_bp ÷ (window ÷ 10)` | |
| `ctx.tape.*.vol_rising`, `vol_1st`, `vol_2nd` | yes/no, shares | volume in the second half of the window vs the first half | |
| `ctx.tape.*.n`, `covered_s`, `lag_s` | | bars used, seconds covered, seconds since the last bar | |
| `ctx.mkt.SPY/QQQ.60/120` | bp | SPY / QQQ moves | |
| `ctx.mkt.avg_60/120`, `agrees_stock_60/120` | bp, yes/no | their average, and whether it matches the stock's own move | |
| `ctx.day_rvol`, `chg_pct` | ×, % | day volume vs normal so far, % change vs prior close | |
| `ctx.vdir` | | **new 10/20**: volume direction: last 15 s rate vs the prior 60 s (`a`: up ≥ 1.3×, dn ≤ 0.7×, flat, thin under 500 shares; `x` ratio; `v15`, `p60` shares) | live page `vol_dir` |
| `ctx.cpdir` | | **new 10/20**: C/P direction for `15s` and `1m`: now (`to`) vs ~60 s ago (`from`), `d` change, `a` up/dn/flat (±0.10)/thin/wait, `strong` (doubled, halved or moved > 0.5) | live page `CpDir` |
| `ctx.px_src` | text | Sector watch: `live_last` or `5s_close` | |
| `buffered_score`, `buffered_band` | −3…+3, 0.15 | shadow score that moves only when raw clears the cutoff by 0.15 | `score_changes.buffered` |
| `score_profile`, `profile_version`, `sector_id`, `sector` | text | Sector watch rows only | |

Input raw measures (`comps.<input>.x`):

| Input | Fields | Reading `c` |
|---|---|---|
| flip | `gf` flip price, `d_atr = (px − gf) ÷ ATR` | `tanh(d_atr ÷ 0.3)` |
| walls | `cw`, `pw`, `up_atr = (cw − px) ÷ ATR`, `dn_atr = (px − pw) ÷ ATR` | `(up − dn) ÷ (up + dn)`; past a wall ±0.3 |
| volume | `updn` = (up-bar volume − down-bar volume) ÷ total over 15 closed 1-min bars, `rvol15` | `updn × (0.4 + 0.6 × g)`, `g = clamp((rvol15 − 0.8) ÷ 1.2, 0, 1)` |
| flow | `cp` 1-min C/P, `thin`, `net_k`, `cov` (or UW lean) | `clamp(ln(cp) ÷ ln 3)`; UW lean ±0.5 |
| trend | `vwap`, `vwap_atr = (px − VWAP) ÷ ATR`, `ret_atr` = 15-min move ÷ ATR | mean of `tanh(vwap_atr ÷ 0.15)` and `tanh(ret_atr ÷ 0.10)` |
| market | `idx.SPY/QQQ` trend measures, `vix`, `vix_chg_pct`, `tide_delta` | mean of tape, `−tanh(vix_chg_pct ÷ 5)`, `tanh(tide_delta ÷ $50M)` |

### episodes-*.jsonl (core), episodes-wide / episodes-widefull (Sector watch)

One row = one score hold that just ended (start to stop of one whole-number score).

| Column | Unit | Meaning |
|---|---|---|
| `kind` | text | `score_episode` (`score_episode_buffered_shadow` in the buffered files) |
| `score`, `dir`, `raw_start` | | the score held, its sign, raw value at the start |
| `start_t/_utc/_pt`, `stop_t/_utc/_pt` | epoch s / text | start and end of the hold |
| `duration_s` | seconds | `stop_t − start_t` |
| `start_px`, `stop_px` | $ | prices at start and stop |
| `ret_bp` | bp | `(stop_px ÷ start_px − 1) × 10,000` |
| `gain_bp` | bp | `ret_bp × dir` (positive = the stock went the score's way) |
| `peak_px/_t/_pt/_bp`, `trough_px/_t/_pt/_bp` | $, time, bp | highest and lowest price during the hold (5 s bar highs/lows plus each pass's last price) vs `start_px` |
| `mfe_bp`, `mae_bp` | bp | best and worst move in the score's direction (score > 0: peak / trough; score < 0: −trough / −peak) |
| `next_score`, `start_reason`, `stop_reason` | | what came next; `score_change`, `session_end`, `daemon_gap`, `date_roll` |
| `n_obs`, `n_5s_bars` | count | fast passes and 5 s bars seen during the hold |
| `price_src`, `settings_version`, `mode` | text | |
| `comps_start` | `[c, q, w]` per input | inputs at the start |
| `agree_start`, `ctx_start`, `ctx_stop` | | same blocks as the change row, at the start and at the stop |
| `shadow`, `buffered_band`, `note` | | buffered files only |

### scores-*.jsonl (core 15-minute grid) and latest*.json (badge)

`scores-*` rows have `id` (`SYM-epoch-trigger`), `sym`, `t`, `t_pt`, `date`, `slot` (`HH:MM` PT), `mode`, `trigger` (`anchor`, `grid`, `vol_surge`), `config_version`, `px`, `atr`, `score`, `raw`, `coverage`, `stale`, `missing`, `comps` (same as the change row), `rvol_1m`, `day_rvol`, `chg_pct`, and `event` on surge rows.

`latest.json`: `as_of` (epoch s), `as_of_pt`, `config_version`, `kind`, `market` (the market input's raw measures) and `by_sym.<SYM>`: `s` score, `raw`, `cov`, `t`, `t_pt`, `trigger`, `cfg`, `stale`, `missing`, `comps` (`[c, q, w]`), `why` (reason an input is missing).
`latest-wide.json` / `latest-widefull.json`: `as_of`, `as_of_pt`, `kind` (`light_live` / `wide_full_live`), `score_profile`, `config_version`, `inputs`, `refresh_s` (5), `raw_unsmoothed`, `n`, and `by_sym.<SYM>`: `s`, `raw`, `cov`, `since_t` (when this score started), `comps`, `missing`, `sector_id`.

### cp-history (core) and cp-history-wide (Sector watch)

The first line of each day is a header: `hdr`, `version`, `tuple` (the order of the six numbers below), `deadband`, `hist_n`, `sample_s`; the Sector watch header adds `tier: wide`, `cls: tick`.
Each later line is one 15 s slot:

| Column | Unit | Meaning |
|---|---|---|
| `t` | epoch seconds | slot start (multiple of 15 s) |
| `pt` | `HH:MM:SS` PT | same moment |
| `sel` | PT ISO | when the contract set in use was picked |
| `tier`, `cls` | text | Sector watch only: `wide`, `tick` |
| `u.<SYM>.15` / `u.<SYM>.60` | list of 6 | `[cp, L, cb, pb, n, why]` for the 15 s and 60 s windows |
| `cp` | ratio | call-buy ÷ put-buy premium (null when `why` is set) |
| `L` | log ratio | `ln((cb + k) ÷ (pb + k))`, `k = max($2,000, 5% of cb + pb)`, clamped to ±ln 10; the C/P momentum arrow is the slope of the last 4 slots |
| `cb`, `pb` | $ | call-buy and put-buy premium in the window |
| `n` | prints | prints in the window |
| `why` | text | null when usable, else `closed`, `warmup`, `ws`, `stale`, `thin`, `nobuy`, `missed` |

### optflow.json / optflow-wide.json (live snapshot, every 1 s)

Top level: `service`, `version`, `tier` (wide only), `source`, `computed_at`, `computed_epoch`, `ws` (connection state), `subs`, `selected_at`, `exch_to_recv_lag_5m` (core), `counts` (prints by how they were classified; Sector watch counts start with `wide_`), `method`, `momentum`, `thin_prints`.
`underlyings.<SYM>.15s` / `60s` / `day`:

| Column | Unit | Meaning |
|---|---|---|
| `cb`, `cs`, `pb`, `ps` | $ | call buy, call sell, put buy, put sell premium (price × size × 100) |
| `cbn`, `csn`, `pbn`, `psn` | contracts | same, in contracts |
| `cp_buy` | ratio | `cb ÷ pb` (99 if puts are zero), the C/P on the page |
| `cp_buy_strict` | ratio | the same using only prints at or through the bid/ask (core only; null for the tick test) |
| `net` | $ | `(cb − cs) − (pb − ps)` |
| `neutral`, `unclassified`, `complex` | $ | premium that couldn't be given a side, had no usable quote, or was multi-leg / tied to stock |
| `n`, `coverage`, `thin` | | prints, share of premium given a side, under 5 prints |
| `cls` | text | Sector watch: `tick` |

Plus `last_trade_t`, `last_recv` (PT ISO), `contracts`, `mom.15s/60s` (`d` arrow, `s` slope per minute, `nv` valid slots, `h` last 6 C/P readings, `rr` contracts re-picked).

### volume_5s (core and Sector watch, same columns)

| Column | Unit | Meaning |
|---|---|---|
| `symbol` | text | |
| `bucket_start_ns`, `bucket_end_ns` | UTC epoch ns | the 5 s bucket `[start, start + 5 s)` |
| `bucket_start_iso` | UTC text | |
| `session` | text | `pre`, `rth`, `post` |
| `volume`, `trade_count` | shares, prints | SIP prints in the bucket (official open/close re-reports Q, M, 9 excluded) |
| `open`, `high`, `low`, `close`, `vwap` | $ | prices of the bucket's prints (odd-lot / average-price / out-of-sequence prints excluded from price); null with no prints |
| `rvol_1m_at_end` | × | regular hours only: last 60 s volume ÷ normal volume for those minutes (normal = average of the prior full sessions) |
| `pace_rvol_10s_at_end` | × | last 10 s volume × 6 ÷ normal for the current minute |
| `stream_feed`, `stream_ok` | text, yes/no | feed used; false if the feed lagged > 5 s or was down |
| `late_prints` | count | prints that arrived after the previous bucket was written |
| `schema_version`, `writer` | text | `v1`, `oid-quote@<version>` |
| `event_ts_ns/_iso`, `ingest_ts_ns/_iso` | UTC | bucket time, and when the row was written |

### bars_1m (core and Sector watch, same columns)

`symbol`, `timeframe` (`1m`), `bar_start_ns`, `bar_start_iso`, `bar_end_ns` (UTC), `session`, `open`, `high`, `low`, `close`, `volume`, `vwap`, `trade_count`, `src` (`alpaca-ws` live or `alpaca-rest` final), `feed` (`sip`), `adjustment` (`raw`), `final` (true for the REST copy), `revised_ts_ns`, `schema_version`, `event_ts_*`, `ingest_ts_*`, `writer` (`oid-quote@…` or `bars-reconcile`).

### scorecard-*.json

| Key | Meaning |
|---|---|
| `date`, `source`, `n_holds`, `generated_pt` | day, where the holds came from (`episodes (…)` or `scores fallback (…)` for the 15-min grid), count, when written |
| `score_alone.<score>` / `all nonzero` | stats for each score |
| `combos.<combo>.<bucket>.<group>` | stats split by surge, C/P agrees, wall room, momentum, the three-together stack, stock tape and market |
| `held_before_acting` | the same stats if you waited 0 / 15 / 30 / 60 / 120 / 300 s before acting |
| `secondary_fwd` | the +5 / 15 / 30 / 60 s seconds check |
| `buffered_vs_raw` | shadow vs raw |
| `by_sector`, `big_counts_by_sector` | Sector watch cards only |
| `score_profile`, `config_version`, `inputs`, `price_bars` | Sector watch cards only |
| `definitions` | plain-text definitions used |

Each stats block: `holds` (count), `pct_with` (% of holds whose `gain_bp` > 0, the "went with the score" rate), `median_gain_bp`, `mean_gain_bp`, `mean_peak_bp` (average `mfe_bp`), `mean_trough_bp` (average `mae_bp`), `median_hold_s`.

## Real example rows (copied from the mini, 10/20/2026)

Today's change and hold files are the **5-second replay** of the session (`~/oid-data/score/replay-20261020/`, `mode: "replay"`), because the live fast pass was switched on after the close; the live files start at Wednesday's open with the same columns.

### changes-20261020.jsonl (core, NVDA +1 → +2 at 7:00:01 AM)
```json
{
 "kind": "score_change",
 "sym": "NVDA",
 "date": "2026-10-20",
 "score": 2,
 "prev_score": 1,
 "raw": 1.878,
 "prev_raw": 0.541,
 "t": 1792504801.7,
 "t_utc": "2026-10-20T14:00:01.700Z",
 "t_pt": "2026-10-20 07:00:01 AM PT",
 "px": 214.41,
 "atr": 5.7271,
 "coverage": 1.0,
 "stale": [],
 "missing": [],
 "settings_version": "v1.1-20261020",
 "config_version": "v1.1-20261020",
 "mode": "replay",
 "trigger": "fast",
 "prev_start_t": 1792504651.7,
 "prev_start_utc": "2026-10-20T13:57:31.700Z",
 "prev_start_pt": "2026-10-20 06:57:31 AM PT",
 "prev_duration_s": 150.0,
 "prev_start_px": 214.0,
 "prev_ret_bp": 19.16,
 "start_reason": "score_change",
 "agree": {
  "cp": true,
  "stock_tape_60": false,
  "stock_tape_120": true,
  "market_60": true,
  "market_120": true,
  "room_dir_atr": 0.9761,
  "surge": false,
  "mom_state": "decelerate"
 },
 "comps": {
  "flip": {
   "x": {
    "gf": 213.0,
    "d_atr": 0.2462
   },
   "f": {
    "gf_ok": true,
    "stale": false,
    "age_s": 888,
    "src": "fa-focus-levels",
    "as_of": "Tue 10/20 6:45 AM PT",
    "gf_status": "available"
   },
   "c": 0.6754,
   "q": 1.0,
   "w": 1.0
  },
  "walls": {
   "x": {
    "cw": 220.0,
    "pw": 200.0,
    "up_atr": 0.9761,
    "dn_atr": 2.5161
   },
   "f": {
    "stale": false,
    "age_s": 888,
    "src": "fa-focus-levels",
    "as_of": "Tue 10/20 6:45 AM PT"
   },
   "c": -0.441,
   "q": 1.0,
   "w": 0.75
  },
  "volume": {
   "x": {
    "updn": 0.279,
    "rvol15": 0.9372
   },
   "f": {
    "stale": false,
    "bar_age_s": 2,
    "n_bars": 30
   },
   "c": 0.1307,
   "q": 1.0,
   "w": 0.75
  },
  "flow": {
   "x": {
    "cp": 6.05,
    "thin": false,
    "net_k": null,
    "cov": null
   },
   "f": {
    "src": "alpaca-opra-aggressor-1m",
    "age_s": 2,
    "stale": false
   },
   "c": 1.0,
   "q": 1.0,
   "w": 0.5
  },
  "trend": {
   "x": {
    "vwap": 214.1828,
    "vwap_atr": 0.0397,
    "ret_atr": 0.234
   },
   "f": {
    "stale": false
   },
   "c": 0.62,
   "q": 1.0,
   "w": 1.0
  },
  "market": {
   "x": {
    "idx": {
     "SPY": {
      "vwap_atr": 0.2965,
      "ret_atr": 0.4892
     },
     "QQQ": {
      "vwap_atr": 0.2579,
      "ret_atr": 0.4968
     }
    },
    "vix": 18.14,
    "vix_ref": 18.44,
    "vix_ref_kind": "prev_close",
    "vix_chg_pct": -1.6269,
    "vix_age_s": 8,
    "vix_stale": false,
    "tide_delta": 20519390.5,
    "tide_age_s": 2,
    "tide_stale": false
   },
   "f": {
    "n_parts": 3,
    "parts": {
     "tape": 0.975,
     "vix": 0.314,
     "tide": 0.389
    }
   },
   "c": 0.5594,
   "q": 1.0,
   "w": 0.75
  }
 },
 "ctx": {
  "flow": {
   "cp_15s": 2.25,
   "thin_15s": false,
   "why_15s": null,
   "cp_60s": 6.05,
   "thin_60s": false,
   "why_60s": null,
   "n_15s": 307,
   "n_60s": 1218,
   "age_s": 2,
   "src": "cp-history",
   "uw_cp": null,
   "lean5": null,
   "lean15": null,
   "ask_lean": null
  },
  "flow_dir": 1,
  "rvol_1m": 1.029,
  "surge": false,
  "walls": {
   "cw": 220.0,
   "pw": 200.0,
   "gf": 213.0,
   "age_s": 888,
   "stale": false,
   "src": "fa-focus-levels",
   "as_of_pt": "Tue 10/20 6:45 AM PT"
  },
  "room_call_atr": 0.9761,
  "room_put_atr": 2.5161,
  "mom": {
   "state": "decelerate",
   "raw": "decelerate",
   "since_t": 1792504800.0,
   "since_pt": "2026-10-20 07:00:00 AM PT",
   "age_s": 2
  },
  "tape": {
   "60": {
    "ret_bp": -1.4,
    "hh": 7,
    "hl": 6,
    "lh": 4,
    "ll": 3,
    "speed_bp_10s": -0.23,
    "vol_rising": true,
    "vol_1st": 154303,
    "vol_2nd": 164187,
    "n": 12,
    "covered_s": 60,
    "lag_s": 1.7
   },
   "120": {
    "ret_bp": 14.95,
    "hh": 16,
    "hl": 14,
    "lh": 7,
    "ll": 7,
    "speed_bp_10s": 1.25,
    "vol_rising": true,
    "vol_1st": 290036,
    "vol_2nd": 318490,
    "n": 24,
    "covered_s": 120,
    "lag_s": 1.7
   }
  },
  "mkt": {
   "SPY": {
    "60": 3.91,
    "120": 9.19
   },
   "QQQ": {
    "60": 4.05,
    "120": 17.0
   },
   "avg_60": 3.98,
   "agrees_stock_60": false,
   "avg_120": 13.09,
   "agrees_stock_120": true
  }
 },
 "buffered_score": 2,
 "buffered_band": 0.15
}
```

### episodes-20261020.jsonl (core, DIA +2 hold, 40 s)
```json
{
 "kind": "score_episode",
 "sym": "DIA",
 "date": "2026-10-20",
 "score": 2,
 "dir": 1,
 "raw_start": 1.537,
 "start_t": 1792504231.7,
 "start_utc": "2026-10-20T13:50:31.700Z",
 "start_pt": "2026-10-20 06:50:31 AM PT",
 "stop_t": 1792504271.7,
 "stop_utc": "2026-10-20T13:51:11.700Z",
 "stop_pt": "2026-10-20 06:51:11 AM PT",
 "duration_s": 40.0,
 "start_px": 522.64,
 "stop_px": 522.37,
 "ret_bp": -5.17,
 "gain_bp": -5.17,
 "peak_px": 522.85,
 "peak_t": 1792504245.0,
 "peak_pt": "2026-10-20 06:50:45 AM PT",
 "peak_bp": 4.02,
 "trough_px": 522.37,
 "trough_t": 1792504270.0,
 "trough_pt": "2026-10-20 06:51:10 AM PT",
 "trough_bp": -5.17,
 "mfe_bp": 4.02,
 "mae_bp": -5.17,
 "next_score": 1,
 "start_reason": "score_change",
 "stop_reason": "score_change",
 "n_obs": 9,
 "n_5s_bars": 7,
 "price_src": "5s SIP bars (high/low) + score-pass last price",
 "settings_version": "v1.1-20261020",
 "mode": "replay",
 "comps_start": {
  "flip": [
   0.0,
   0.0,
   1.0
  ],
  "walls": [
   0.0,
   0.0,
   0.75
  ],
  "volume": [
   0.3799,
   1.0,
   0.75
  ],
  "flow": [
   1.0,
   1.0,
   0.5
  ],
  "trend": [
   0.9966,
   1.0,
   1.0
  ],
  "market": [
   -0.2127,
   1.0,
   0.75
  ]
 },
 "agree_start": {
  "cp": true,
  "stock_tape_60": true,
  "stock_tape_120": true,
  "market_60": true,
  "market_120": true,
  "room_dir_atr": null,
  "surge": false,
  "mom_state": "decelerate"
 },
 "ctx_start": {
  "flow": {
   "cp_15s": null,
   "thin_15s": true,
   "why_15s": "thin",
   "cp_60s": 13.77,
   "thin_60s": false,
   "why_60s": null,
   "n_15s": 2,
   "n_60s": 6,
   "age_s": 2,
   "src": "cp-history",
   "uw_cp": null,
   "lean5": null,
   "lean15": null,
   "ask_lean": null
  },
  "flow_dir": 1,
  "rvol_1m": 1.661,
  "surge": false,
  "walls": {
   "cw": null,
   "pw": null,
   "gf": null,
   "age_s": null,
   "stale": null,
   "src": null,
   "as_of_pt": null
  },
  "room_call_atr": null,
  "room_put_atr": null,
  "mom": {
   "state": "decelerate",
   "raw": "decelerate",
   "since_t": 1792504080.0,
   "since_pt": "2026-10-20 06:48:00 AM PT",
   "age_s": 152
  },
  "tape": {
   "60": {
    "ret_bp": 11.49,
    "hh": 7,
    "hl": 6,
    "lh": 2,
    "ll": 3,
    "speed_bp_10s": 1.92,
    "vol_rising": true,
    "vol_1st": 3527,
    "vol_2nd": 10135,
    "n": 10,
    "covered_s": 60,
    "lag_s": 1.7
   },
   "120": {
    "ret_bp": 15.33,
    "hh": 13,
    "hl": 11,
    "lh": 7,
    "ll": 9,
    "speed_bp_10s": 1.28,
    "vol_rising": false,
    "vol_1st": 15465,
    "vol_2nd": 13662,
    "n": 21,
    "covered_s": 120,
    "lag_s": 1.7
   }
  },
  "mkt": {
   "SPY": {
    "60": 3.66,
    "120": 10.58
   },
   "QQQ": {
    "60": -0.15,
    "120": 13.9
   },
   "avg_60": 1.76,
   "agrees_stock_60": true,
   "avg_120": 12.24,
   "agrees_stock_120": true
  }
 },
 "ctx_stop": {
  "flow": {
   "cp_15s": null,
   "thin_15s": true,
   "why_15s": "thin",
   "cp_60s": 99.0,
   "thin_60s": false,
   "why_60s": null,
   "n_15s": 2,
   "n_60s": 9,
   "age_s": 12,
   "src": "cp-history",
   "uw_cp": null,
   "lean5": null,
   "lean15": null,
   "ask_lean": null
  },
  "flow_dir": 1,
  "rvol_1m": 3.275,
  "surge": true,
  "walls": {
   "cw": null,
   "pw": null,
   "gf": null,
   "age_s": null,
   "stale": null,
   "src": null,
   "as_of_pt": null
  },
  "room_call_atr": null,
  "room_put_atr": null,
  "mom": {
   "state": "resume",
   "raw": "resume",
   "since_t": 1792504260.0,
   "since_pt": "2026-10-20 06:51:00 AM PT",
   "age_s": 12
  },
  "tape": {
   "60": {
    "ret_bp": 4.02,
    "hh": 7,
    "hl": 7,
    "lh": 4,
    "ll": 4,
    "speed_bp_10s": 0.67,
    "vol_rising": false,
    "vol_1st": 21754,
    "vol_2nd": 11983,
    "n": 12,
    "covered_s": 60,
    "lag_s": 1.7
   },
   "120": {
    "ret_bp": 12.07,
    "hh": 14,
    "hl": 13,
    "lh": 6,
    "ll": 7,
    "speed_bp_10s": 1.01,
    "vol_rising": true,
    "vol_1st": 16399,
    "vol_2nd": 33737,
    "n": 21,
    "covered_s": 120,
    "lag_s": 1.7
   }
  },
  "mkt": {
   "SPY": {
    "60": -1.44,
    "120": 3.85
   },
   "QQQ": {
    "60": -6.31,
    "120": -3.09
   },
   "avg_60": -3.88,
   "agrees_stock_60": false,
   "avg_120": 0.38,
   "agrees_stock_120": true
  }
 }
}
```

### changes-wide-20261020.jsonl (Sector watch light score, PFE +2 → +3)
From the 1-minute replay (`replay-20261020-wide/`), written before the C/P was streamed for these names, so `ctx.flow` is empty. From 10/21 the same block carries `cp_15s`, `cp_60s`, `lean` and `cls: "tick"`, as in the test row below.
```json
{
 "kind": "score_change",
 "sym": "PFE",
 "date": "2026-10-20",
 "score": 3,
 "prev_score": 2,
 "raw": 2.655,
 "prev_raw": 1.544,
 "t": 1792503180.0,
 "t_utc": "2026-10-20T13:33:00.000Z",
 "t_pt": "2026-10-20 06:33:00 AM PT",
 "px": 29.945,
 "atr": 0.5689,
 "coverage": 0.9,
 "stale": [],
 "missing": [],
 "settings_version": "light-v1.0-20261021",
 "config_version": "light-v1.0-20261021",
 "mode": "replay",
 "trigger": "fast",
 "prev_start_t": 1792503060.0,
 "prev_start_utc": "2026-10-20T13:31:00.000Z",
 "prev_start_pt": "2026-10-20 06:31:00 AM PT",
 "prev_duration_s": 120.0,
 "prev_start_px": 29.745,
 "prev_ret_bp": 67.24,
 "start_reason": "score_change",
 "agree": {
  "cp": null,
  "stock_tape_60": true,
  "stock_tape_120": true,
  "market_60": true,
  "market_120": false,
  "room_dir_atr": null,
  "surge": true,
  "mom_state": null
 },
 "comps": {
  "volume": {
   "x": {
    "updn": 1.0,
    "rvol15": 1.961
   },
   "f": {
    "stale": false,
    "bar_age_s": 0,
    "n_bars": 3
   },
   "c": 0.9805,
   "q": 1.0,
   "w": 0.75
  },
  "trend": {
   "x": {
    "vwap": 29.8034,
    "vwap_atr": 0.2489,
    "ret_atr": 0.4834
   },
   "f": {
    "stale": false
   },
   "c": 0.965,
   "q": 1.0,
   "w": 1.0
  },
  "market": {
   "x": {
    "idx": {
     "SPY": {
      "vwap_atr": -0.0145,
      "ret_atr": -0.068
     },
     "QQQ": {
      "vwap_atr": -0.0836,
      "ret_atr": -0.1358
     }
    },
    "tide_delta": -20257096.0,
    "tide_age_s": 180,
    "tide_stale": false
   },
   "f": {
    "n_parts": 2,
    "parts": {
     "tape": -0.517,
     "tide": -0.384
    }
   },
   "c": -0.4509,
   "q": 0.667,
   "w": 0.75
  }
 },
 "ctx": {
  "flow": {},
  "flow_dir": null,
  "rvol_1m": 4.395,
  "surge": true,
  "walls": {
   "cw": null,
   "pw": null,
   "gf": null,
   "age_s": null,
   "stale": null,
   "src": null,
   "as_of_pt": null
  },
  "room_call_atr": null,
  "room_put_atr": null,
  "mom": {
   "state": null,
   "note": "momentum not tracked for wide names"
  },
  "tape": {
   "60": {
    "ret_bp": 16.73,
    "hh": 0,
    "hl": 0,
    "lh": 0,
    "ll": 0,
    "speed_bp_10s": 2.79,
    "vol_rising": false,
    "vol_1st": 477101,
    "vol_2nd": 0,
    "n": 1,
    "covered_s": 60,
    "lag_s": 0.0
   },
   "120": {
    "ret_bp": 67.24,
    "hh": 1,
    "hl": 1,
    "lh": 0,
    "ll": 0,
    "speed_bp_10s": 5.6,
    "vol_rising": false,
    "vol_1st": 716675,
    "vol_2nd": 477101,
    "n": 2,
    "covered_s": 120,
    "lag_s": 0.0
   }
  },
  "mkt": {
   "SPY": {
    "60": 0.78,
    "120": -1.83
   },
   "QQQ": {
    "60": -0.14,
    "120": -13.01
   },
   "avg_60": 0.32,
   "agrees_stock_60": true,
   "avg_120": -7.42,
   "agrees_stock_120": false
  },
  "px_src": "1m_close"
 },
 "buffered_score": 3,
 "buffered_band": 0.15,
 "score_profile": "light",
 "profile_version": "light-v1.0-20261021",
 "sector_id": "w-healthcare-biotech-pharm",
 "sector": "Healthcare/Biotech/Pharma"
}
```

### episodes-wide-20261020.jsonl (Sector watch light score, HTZ +3 hold)
```json
{
 "kind": "score_episode",
 "sym": "HTZ",
 "date": "2026-10-20",
 "score": 3,
 "dir": 1,
 "raw_start": 2.727,
 "start_t": 1792503060.0,
 "start_utc": "2026-10-20T13:31:00.000Z",
 "start_pt": "2026-10-20 06:31:00 AM PT",
 "stop_t": 1792503120.0,
 "stop_utc": "2026-10-20T13:32:00.000Z",
 "stop_pt": "2026-10-20 06:32:00 AM PT",
 "duration_s": 60.0,
 "start_px": 2.1278,
 "stop_px": 2.1109,
 "ret_bp": -79.42,
 "gain_bp": -79.42,
 "peak_px": 2.18,
 "peak_t": 1792503120.0,
 "peak_pt": "2026-10-20 06:32:00 AM PT",
 "peak_bp": 245.32,
 "trough_px": 2.09,
 "trough_t": 1792503120.0,
 "trough_pt": "2026-10-20 06:32:00 AM PT",
 "trough_bp": -177.65,
 "mfe_bp": 245.32,
 "mae_bp": -177.65,
 "next_score": 0,
 "start_reason": "first_seen",
 "stop_reason": "score_change",
 "n_obs": 13,
 "n_5s_bars": 1,
 "price_src": "5s SIP bars (high/low) + score-pass last price",
 "settings_version": "light-v1.0-20261021",
 "mode": "replay",
 "comps_start": {
  "volume": [
   1.0,
   1.0,
   0.75
  ],
  "trend": [
   0.9295,
   1.0,
   1.0
  ],
  "market": [
   -0.329,
   0.667,
   0.75
  ]
 },
 "agree_start": {
  "cp": null,
  "stock_tape_60": true,
  "stock_tape_120": true,
  "market_60": false,
  "market_120": false,
  "room_dir_atr": null,
  "surge": true,
  "mom_state": null
 },
 "ctx_start": {
  "flow": {},
  "flow_dir": null,
  "rvol_1m": 5.132,
  "surge": true,
  "walls": {
   "cw": null,
   "pw": null,
   "gf": null,
   "age_s": null,
   "stale": null,
   "src": null,
   "as_of_pt": null
  },
  "room_call_atr": null,
  "room_put_atr": null,
  "mom": {
   "state": null,
   "note": "momentum not tracked for wide names"
  },
  "tape": {
   "60": {
    "ret_bp": 132.38,
    "hh": 0,
    "hl": 0,
    "lh": 0,
    "ll": 0,
    "speed_bp_10s": 22.06,
    "vol_rising": false,
    "vol_1st": 1111655,
    "vol_2nd": 0,
    "n": 1,
    "covered_s": 60,
    "lag_s": 0.0
   },
   "120": {
    "ret_bp": 132.38,
    "hh": 0,
    "hl": 0,
    "lh": 0,
    "ll": 0,
    "speed_bp_10s": 11.03,
    "vol_rising": true,
    "vol_1st": 0,
    "vol_2nd": 1111655,
    "n": 1,
    "covered_s": 60,
    "lag_s": 0.0
   }
  },
  "mkt": {
   "SPY": {
    "60": -4.31,
    "120": -4.31
   },
   "QQQ": {
    "60": -7.13,
    "120": -7.13
   },
   "avg_60": -5.72,
   "agrees_stock_60": false,
   "avg_120": -5.72,
   "agrees_stock_120": false
  },
  "px_src": "1m_close"
 },
 "ctx_stop": {
  "flow": {},
  "flow_dir": null,
  "rvol_1m": 18.901,
  "surge": true,
  "walls": {
   "cw": null,
   "pw": null,
   "gf": null,
   "age_s": null,
   "stale": null,
   "src": null,
   "as_of_pt": null
  },
  "room_call_atr": null,
  "room_put_atr": null,
  "mom": {
   "state": null,
   "note": "momentum not tracked for wide names"
  },
  "tape": {
   "60": {
    "ret_bp": -79.42,
    "hh": 0,
    "hl": 0,
    "lh": 0,
    "ll": 0,
    "speed_bp_10s": -13.24,
    "vol_rising": false,
    "vol_1st": 1336984,
    "vol_2nd": 0,
    "n": 1,
    "covered_s": 60,
    "lag_s": 0.0
   },
   "120": {
    "ret_bp": 51.9,
    "hh": 1,
    "hl": 1,
    "lh": 0,
    "ll": 0,
    "speed_bp_10s": 4.33,
    "vol_rising": true,
    "vol_1st": 1111655,
    "vol_2nd": 1336984,
    "n": 2,
    "covered_s": 120,
    "lag_s": 0.0
   }
  },
  "mkt": {
   "SPY": {
    "60": -2.61,
    "120": -6.92
   },
   "QQQ": {
    "60": -12.87,
    "120": -19.99
   },
   "avg_60": -7.74,
   "agrees_stock_60": true,
   "avg_120": -13.45,
   "agrees_stock_120": false
  },
  "px_src": "1m_close"
 },
 "score_profile": "light",
 "profile_version": "light-v1.0-20261021",
 "sector_id": "w-transportation-airlines",
 "sector": "Transportation/Airlines"
}
```

### changes-widefull (Sector watch full score) — TEST row
There is no live row yet (first session is 10/21). This row was written by the real code at 4:25 PM PT into a scratch folder (`/tmp/swtest`, `mode: "test"`), with a test clock of 1:00 PM. The XOM price bars and SPY/QQQ inputs are real, while the C/P and wall levels were typed in to exercise the code. Note `comps.flow.q` = 0.5 (tick test) and `ctx.flow.cls` = `tick`.
```json
{
 "kind": "score_change",
 "sym": "XOM",
 "date": "2026-10-20",
 "score": 2,
 "prev_score": null,
 "raw": 1.545,
 "prev_raw": null,
 "t": 1792526400.0,
 "t_utc": "2026-10-20T20:00:00.000Z",
 "t_pt": "2026-10-20 01:00:00 PM PT",
 "px": 177.89,
 "atr": 3.4277,
 "coverage": 0.842,
 "stale": [],
 "missing": [],
 "settings_version": "widefull-v1.0-20261021",
 "config_version": "widefull-v1.0-20261021",
 "mode": "test",
 "trigger": "fast",
 "prev_start_t": null,
 "prev_start_utc": null,
 "prev_start_pt": null,
 "prev_duration_s": null,
 "prev_start_px": null,
 "prev_ret_bp": null,
 "start_reason": "first_seen",
 "agree": {
  "cp": true,
  "stock_tape_60": null,
  "stock_tape_120": null,
  "market_60": null,
  "market_120": null,
  "room_dir_atr": 1.0386,
  "surge": false,
  "mom_state": null
 },
 "comps": {
  "flip": {
   "x": {
    "gf": 176.11,
    "d_atr": 0.5193
   },
   "f": {
    "gf_ok": true,
    "stale": false,
    "age_s": 600,
    "src": "fa-walls-wide",
    "as_of": "12:50 PM PT",
    "gf_status": "available"
   },
   "c": 0.9392,
   "q": 1.0,
   "w": 1.0
  },
  "walls": {
   "x": {
    "cw": 181.45,
    "pw": 172.55,
    "up_atr": 1.0386,
    "dn_atr": 1.5579
   },
   "f": {
    "stale": false,
    "age_s": 600,
    "src": "fa-walls-wide",
    "as_of": "12:50 PM PT"
   },
   "c": -0.2,
   "q": 1.0,
   "w": 0.75
  },
  "volume": {
   "x": {
    "updn": -0.1144,
    "rvol15": 0.7901
   },
   "f": {
    "stale": false,
    "bar_age_s": 0,
    "n_bars": 390
   },
   "c": -0.0458,
   "q": 1.0,
   "w": 0.75
  },
  "flow": {
   "x": {
    "cp": 1.45,
    "thin": false,
    "net_k": 30.2,
    "cov": 0.88
   },
   "f": {
    "src": "alpaca-opra-tick-1m",
    "age_s": 2.1,
    "stale": false,
    "cls": "tick"
   },
   "c": 0.3382,
   "q": 0.5,
   "w": 0.5
  },
  "trend": {
   "x": {
    "vwap": 177.0125,
    "vwap_atr": 0.256,
    "ret_atr": 0.07
   },
   "f": {
    "stale": false
   },
   "c": 0.7704,
   "q": 1.0,
   "w": 1.0
  },
  "market": {
   "x": {
    "idx": {
     "SPY": {
      "vwap_atr": 0.0004,
      "ret_atr": 0.0779
     },
     "QQQ": {
      "vwap_atr": -0.0397,
      "ret_atr": -0.0056
     }
    }
   },
   "f": {
    "n_parts": 1,
    "parts": {
     "tape": 0.085
    }
   },
   "c": 0.0851,
   "q": 0.333,
   "w": 0.75
  }
 },
 "ctx": {
  "flow": {
   "cp_15s": 1.8,
   "thin_15s": false,
   "net_k_15s": 12.4,
   "n_15s": 9,
   "cp_60s": 1.45,
   "thin_60s": false,
   "net_k_60s": 30.2,
   "n_60s": 31,
   "age_s": 2.1,
   "stale": false,
   "uw_cp": null,
   "lean5": null,
   "lean15": null,
   "ask_lean": null,
   "lean": "CALL",
   "cls": "tick",
   "contracts": 40,
   "src": "live_page_wide"
  },
  "flow_dir": 1,
  "rvol_1m": 1.2,
  "surge": false,
  "walls": {
   "cw": 181.45,
   "pw": 172.55,
   "gf": 176.11,
   "age_s": 600,
   "stale": false,
   "src": "fa-walls-wide",
   "as_of_pt": "12:50 PM PT"
  },
  "room_call_atr": 1.0386,
  "room_put_atr": 1.5579,
  "mom": {
   "state": null,
   "note": "momentum not tracked for wide names"
  },
  "tape": {},
  "mkt": {},
  "px_src": "test"
 },
 "buffered_score": 2,
 "buffered_band": 0.15,
 "score_profile": "wide_full",
 "profile_version": "widefull-v1.0-20261021"
}
```

### changes-fwd-20261020-replay5s.jsonl (seconds check)
```json
{
 "kind": "score_change_fwd",
 "sym": "NFLX",
 "date": "2026-10-20",
 "t": 1792504201.7,
 "t_pt": "2026-10-20 06:50:01 AM PT",
 "score": 2,
 "prev_score": 1,
 "change_px": 70.365,
 "base_px": 70.365,
 "base_bar_end_t": 1792504200.0,
 "price_src": "5s SIP bar closes",
 "fwd": {
  "5": {
   "px": 70.38,
   "bar_end_t": 1792504205.0,
   "ret_bp": 2.13,
   "gain_bp": 2.13
  },
  "15": {
   "px": 70.4,
   "bar_end_t": 1792504215.0,
   "ret_bp": 4.97,
   "gain_bp": 4.97
  },
  "30": {
   "px": 70.42,
   "bar_end_t": 1792504230.0,
   "ret_bp": 7.82,
   "gain_bp": 7.82
  },
  "60": {
   "px": 70.45,
   "bar_end_t": 1792504260.0,
   "ret_bp": 12.08,
   "gain_bp": 12.08
  }
 }
}
```

### scores-20261020.jsonl (core 15-minute grid, NVDA 6:35 AM anchor)
```json
{
 "id": "NVDA-1792503301-anchor",
 "sym": "NVDA",
 "t": 1792503301.7,
 "t_pt": "2026-10-20 06:35:01 AM PT",
 "date": "2026-10-20",
 "slot": "06:35",
 "mode": "live",
 "trigger": "anchor",
 "config_version": "v1-20261019",
 "px": 214.315,
 "atr": 5.7271,
 "score": -3,
 "raw": -2.596,
 "coverage": 1.0,
 "stale": [],
 "missing": [],
 "comps": {
  "flip": {
   "x": {
    "gf": 215.72,
    "d_atr": -0.2453
   },
   "f": {
    "gf_ok": true,
    "stale": false,
    "age_s": 275,
    "src": "fa-focus-levels",
    "as_of": "Tue 10/20 6:30 AM PT",
    "gf_status": "available"
   },
   "c": -0.6738,
   "q": 1.0,
   "w": 1.0
  },
  "walls": {
   "x": {
    "cw": 220.0,
    "pw": 200.0,
    "up_atr": 0.9927,
    "dn_atr": 2.4995
   },
   "f": {
    "stale": false,
    "age_s": 275,
    "src": "fa-focus-levels",
    "as_of": "Tue 10/20 6:30 AM PT"
   },
   "c": -0.4315,
   "q": 1.0,
   "w": 0.75
  },
  "volume": {
   "x": {
    "updn": -1.0,
    "rvol15": 0.6686
   },
   "f": {
    "stale": false,
    "bar_age_s": 62,
    "n_bars": 4
   },
   "c": -0.4,
   "q": 1.0,
   "w": 0.75
  },
  "flow": {
   "x": {
    "cp": 0.56,
    "thin": false,
    "net_k": -78.5,
    "cov": 0.975
   },
   "f": {
    "src": "alpaca-opra-aggressor-1m",
    "age_s": 0.8,
    "stale": false
   },
   "c": -0.5278,
   "q": 1.0,
   "w": 0.5
  },
  "trend": {
   "x": {
    "vwap": 215.2462,
    "vwap_atr": -0.1626,
    "ret_atr": -0.2872
   },
   "f": {
    "stale": false
   },
   "c": -0.8941,
   "q": 1.0,
   "w": 1.0
  },
  "market": {
   "x": {
    "idx": {
     "SPY": {
      "vwap_atr": -0.0104,
      "ret_atr": -0.0651
     },
     "QQQ": {
      "vwap_atr": -0.111,
      "ret_atr": -0.1842
     }
    },
    "vix": 18.63,
    "vix_ref": 18.44,
    "vix_ref_kind": "prev_close",
    "vix_chg_pct": 1.0304,
    "vix_age_s": 79,
    "vix_stale": false,
    "tide_delta": -20112782.0,
    "tide_age_s": 302,
    "tide_stale": false
   },
   "f": {
    "n_parts": 3,
    "parts": {
     "tape": -0.555,
     "vix": -0.203,
     "tide": -0.382
    }
   },
   "c": -0.3802,
   "q": 1.0,
   "w": 0.75
  }
 },
 "rvol_1m": 0.68,
 "day_rvol": 0.66,
 "chg_pct": -1.28
}
```

### latest.json (core badge, NVDA only; last write 12:59 PM)
```json
{
 "as_of": 1792526378.5,
 "as_of_pt": "2026-10-20 12:59:38 PM PT",
 "config_version": "v1-20261019",
 "kind": "live_badge",
 "market": {
  "idx": {
   "SPY": {
    "vwap_atr": -0.0748,
    "ret_atr": 0.034
   },
   "QQQ": {
    "vwap_atr": -0.0879,
    "ret_atr": -0.0316
   }
  },
  "vix": 17.51,
  "vix_ref": 18.44,
  "vix_ref_kind": "prev_close",
  "vix_chg_pct": -5.043383947939262,
  "vix_age_s": 93,
  "vix_stale": false,
  "tide_delta": 11041249.0,
  "tide_age_s": 278,
  "tide_stale": false
 },
 "by_sym": {
  "NVDA": {
   "s": 0,
   "raw": -0.029,
   "cov": 1.0,
   "t": 1792526378.5,
   "t_pt": "2026-10-20 12:59:38 PM PT",
   "trigger": "badge",
   "cfg": "v1-20261019",
   "stale": [],
   "missing": [],
   "comps": {
    "flip": [
     0.2615,
     1.0,
     1.0
    ],
    "walls": [
     -0.632,
     1.0,
     0.75
    ],
    "volume": [
     -0.0895,
     1.0,
     0.75
    ],
    "flow": [
     0.363,
     1.0,
     0.5
    ],
    "trend": [
     -0.1179,
     1.0,
     1.0
    ],
    "market": [
     0.247,
     1.0,
     0.75
    ]
   },
   "why": {}
  }
 }
}
```

### cp-history/2026-10-20.jsonl (header + one 15 s slot, NVDA only)
```json
{"hdr": 1, "version": "0.3.0", "tuple": ["cp", "L", "cb", "pb", "n", "why"], "deadband": {"15s": [0.35, 0.2], "60s": [0.2, 0.1]}, "hist_n": 6, "sample_s": 15}
{
 "t": 1792514685,
 "pt": "09:44:45",
 "sel": "2026-10-20T09:43:44.679-07:00",
 "u": {
  "NVDA": {
   "15": [
    0.54,
    -0.5558,
    16688,
    30859,
    78,
    null
   ],
   "60": [
    0.94,
    -0.0601,
    54540,
    58270,
    282,
    null
   ]
  }
 }
}
```

### optflow.json (after hours, NVDA only) and optflow-wide.json (after hours, no prints yet)
```json
{
 "service": "oid-optflow",
 "version": "0.4.0",
 "source": "alpaca-opra-ws",
 "computed_at": "2026-10-20T16:28:52.212-07:00",
 "computed_epoch": 1792538932.212,
 "ws": {
  "state": "subscribed_ready",
  "connected_at": "2026-10-20T16:18:34.434-07:00",
  "last_msg_age_s": 498.16
 },
 "subs": 900,
 "selected_at": "2026-10-20T16:19:13.359-07:00",
 "exch_to_recv_lag_5m": null,
 "counts": {},
 "method": "quote rule vs prior OPRA NBBO: >=ask buy, <=bid sell, inside spread nearest side, exact mid tick test; unclassified if no quote / crossed-locked / quote >2s older than trade / spread >50% of mid; multi-leg + stock-tied (complex), cancel/late excluded; momentum (mom): 15 s slots of L=ln((cb+k)/(pb+k)), k=max(2000,5% of cb+pb), clamped +-ln10; OLS slope of last 4 slots per min; >=3 valid incl latest; deadband w/ hysteresis",
 "momentum": {
  "enabled": true,
  "hist_n": 6,
  "sample_s": 15,
  "deadband": {
   "15s": [
    0.35,
    0.2
   ],
   "60s": [
    0.2,
    0.1
   ]
  }
 },
 "quote_max_age_s": 2.0,
 "thin_prints": 5,
 "underlyings": {}
}
```
```json
{
 "service": "oid-optflow",
 "version": "0.4.0",
 "tier": "wide",
 "source": "alpaca-opra-ws (trades only)",
 "computed_at": "2026-10-20T16:30:23.386-07:00",
 "computed_epoch": 1792539023.387,
 "ws": {
  "state": "subscribed_ready",
  "connected_at": "2026-10-20T16:18:34.434-07:00",
  "last_msg_age_s": 589.34
 },
 "subs": 2972,
 "selected_at": "2026-10-20T16:20:33.300-07:00",
 "counts": {},
 "method": "TICK TEST ONLY (no OPRA quotes for wide contracts: Alpaca 1,000-quote cap per connection is used by the core): print above the contract's previous print = buy, below = sell, equal = previous side, first print of the day = neutral; multi-leg + stock-tied (complex), cancel/late excluded. Same 15 s / 60 s windows, C/P, net and momentum as the core.",
 "momentum": {
  "enabled": true,
  "hist_n": 6,
  "sample_s": 15,
  "deadband": {
   "15s": [
    0.35,
    0.2
   ],
   "60s": [
    0.2,
    0.1
   ]
  }
 },
 "thin_prints": 5,
 "underlyings": {}
}
```

### volume_5s (core NVDA first regular-hours bucket; Sector watch after-hours bucket)
```json
{
 "symbol": "NVDA",
 "bucket_start_ns": 1792503000000000000,
 "bucket_start_iso": "2026-10-20T13:30:00.000000000Z",
 "bucket_end_ns": 1792503005000000000,
 "session": "rth",
 "volume": 841055,
 "trade_count": 8364,
 "open": 215.98,
 "high": 216.46,
 "low": 215.97,
 "close": 216.1,
 "vwap": 216.02422545493263,
 "rvol_1m_at_end": 0.322,
 "pace_rvol_10s_at_end": 1.923,
 "stream_feed": "sip",
 "stream_ok": true,
 "late_prints": 0,
 "schema_version": "v1",
 "event_ts_ns": 1792503000000000000,
 "event_ts_iso": "2026-10-20T13:30:00.000000000Z",
 "ingest_ts_ns": 1792503008257054000,
 "ingest_ts_iso": "2026-10-20T13:30:08.257054000Z",
 "writer": "oid-quote@0.5.0"
}
```
```json
{
 "symbol": "AGNC",
 "bucket_start_ns": 1792534440000000000,
 "bucket_start_iso": "2026-10-20T22:14:00.000000000Z",
 "bucket_end_ns": 1792534445000000000,
 "session": "post",
 "volume": 1,
 "trade_count": 1,
 "open": null,
 "high": null,
 "low": null,
 "close": null,
 "vwap": 8.8293,
 "rvol_1m_at_end": null,
 "pace_rvol_10s_at_end": null,
 "stream_feed": "sip",
 "stream_ok": true,
 "late_prints": 0,
 "schema_version": "v1",
 "event_ts_ns": 1792534440000000000,
 "event_ts_iso": "2026-10-20T22:14:00.000000000Z",
 "ingest_ts_ns": 1792534448146505000,
 "ingest_ts_iso": "2026-10-20T22:14:08.146505000Z",
 "writer": "oid-quote@0.5.1"
}
```

### bars_1m (core NVDA live and final copies; Sector watch XOM final copy written by the new 2:10 PM job, run once by hand at 4:25 PM PT on 10/20)
```json
{
 "symbol": "NVDA",
 "timeframe": "1m",
 "bar_start_ns": 1792503000000000000,
 "bar_start_iso": "2026-10-20T13:30:00.000000000Z",
 "bar_end_ns": 1792503060000000000,
 "session": "rth",
 "open": 215.96,
 "high": 216.46,
 "low": 215.52,
 "close": 215.65,
 "volume": 1415742,
 "vwap": 215.983511,
 "trade_count": 22052,
 "src": "alpaca-ws",
 "feed": "sip",
 "adjustment": "raw",
 "final": false,
 "revised_ts_ns": null,
 "schema_version": "v1",
 "event_ts_ns": 1792503000000000000,
 "event_ts_iso": "2026-10-20T13:30:00.000000000Z",
 "ingest_ts_ns": 1792503060640650000,
 "ingest_ts_iso": "2026-10-20T13:31:00.640650000Z",
 "writer": "oid-quote@0.5.0"
}
```
```json
{
 "symbol": "NVDA",
 "timeframe": "1m",
 "bar_start_ns": 1792503000000000000,
 "bar_start_iso": "2026-10-20T13:30:00.000000000Z",
 "bar_end_ns": 1792503060000000000,
 "session": "rth",
 "open": 215.96,
 "high": 216.46,
 "low": 215.52,
 "close": 215.65,
 "volume": 1415742,
 "vwap": 215.983511,
 "trade_count": 22052,
 "src": "alpaca-rest",
 "feed": "sip",
 "adjustment": "raw",
 "final": true,
 "revised_ts_ns": null,
 "schema_version": "v1",
 "event_ts_ns": 1792503000000000000,
 "event_ts_iso": "2026-10-20T13:30:00.000000000Z",
 "ingest_ts_ns": 1792530004165241000,
 "ingest_ts_iso": "2026-10-20T21:00:04.165241000Z",
 "writer": "bars-reconcile"
}
```
```json
{
 "symbol": "XOM",
 "timeframe": "1m",
 "bar_start_ns": 1792503000000000000,
 "bar_start_iso": "2026-10-20T13:30:00.000000000Z",
 "bar_end_ns": 1792503060000000000,
 "session": "rth",
 "open": 179.9,
 "high": 180.12,
 "low": 179.654,
 "close": 179.94,
 "volume": 21517,
 "vwap": 179.957019,
 "trade_count": 354,
 "src": "alpaca-rest",
 "feed": "sip",
 "adjustment": "raw",
 "final": true,
 "revised_ts_ns": null,
 "schema_version": "v1",
 "event_ts_ns": 1792503000000000000,
 "event_ts_iso": "2026-10-20T13:30:00.000000000Z",
 "ingest_ts_ns": 1792538736971137000,
 "ingest_ts_iso": "2026-10-20T23:25:36.971137000Z",
 "writer": "bars-reconcile"
}
```

### scorecard-20261020.json (excerpt: `+2` alone, all nonzero, and one combo)
```json
{
 "date": "2026-10-20",
 "source": "scores fallback (scores-20261020.jsonl)",
 "n_holds": 991,
 "generated_pt": "2026-10-20 03:08:25 PM PT",
 "score_alone": {
  "2": {
   "holds": 110,
   "pct_with": 44.5,
   "median_gain_bp": -7.2,
   "mean_gain_bp": 36.1,
   "mean_peak_bp": 88.5,
   "mean_trough_bp": -42.9,
   "median_hold_s": 900.8
  },
  "all nonzero": {
   "holds": 664,
   "pct_with": 35.2,
   "median_gain_bp": -11.0,
   "mean_gain_bp": -7.6,
   "mean_peak_bp": 43.4,
   "mean_trough_bp": -52.8,
   "median_hold_s": 900.8
  }
 },
 "combos": {
  "score x surge (rvol_1m >= 3)": {
   "yes": {
    "all nonzero": {
     "holds": 31,
     "pct_with": 45.2,
     "median_gain_bp": -2.3,
     "mean_gain_bp": 9.8,
     "mean_peak_bp": 66.7,
     "mean_trough_bp": -50.3,
     "median_hold_s": 900.8
    }
   }
  }
 },
 "_other_top_level_keys": [
  "buffered_vs_raw",
  "definitions"
 ]
}
```


## Host health log (added 10/20)

Files: `~/oid-data/host/host-YYYYMMDD.jsonl` (one line per sample, appended; dated in PT) and `~/oid-desk/desk/cache/host-health.json` (latest sample only, rewritten each time, plus `written_by` and `file`). Written by `oid_desk/host_monitor.py`. Summary: `python -m oid_desk.host_monitor summary YYYYMMDD`.

| Column | Meaning |
|---|---|
| `ts` | Sample time, ISO 8601 with offset |
| `ts_pt` | Same time in plain PT |
| `interval_s` | 15 in the weekday 6:00 AM–1:30 PM PT window, 300 otherwise |
| `load1` / `load5` / `load15` | Load averages (1, 5, 15 min) |
| `cpu_pct` | Total CPU busy % across all cores since the previous sample |
| `mem_free_pct` | Memory free % from `memory_pressure` |
| `swap_used_mb` | Swap in use, MB |
| `disk_free_gb` | Free space on the data volume, GB |
| `net_in_Bps` / `net_out_Bps` | Network bytes per second in / out since the previous sample (physical interfaces) |
| `top` | Top 8 processes by CPU: `pid`, `cpu` (% of one core, ps), `rss_mb`, `cmd` (short name; Python shows `python:<script or module>`) |

Real row (10/20/2026, top list cut to 3 here):

```json
{
 "ts": "2026-10-20T17:09:05-07:00",
 "ts_pt": "2026-10-20 05:09:05 PM PT",
 "interval_s": 300,
 "load1": 1.55,
 "load5": 1.74,
 "load15": 1.78,
 "cpu_pct": 10.2,
 "mem_free_pct": 84,
 "swap_used_mb": 0.0,
 "disk_free_gb": 441.0,
 "net_in_Bps": 232419,
 "net_out_Bps": 331869,
 "top": [
  {
   "pid": 14539,
   "cpu": 15.8,
   "rss_mb": 12.5,
   "cmd": "contactsd"
  },
  {
   "pid": 154,
   "cpu": 12.0,
   "rss_mb": 135.4,
   "cmd": "WindowServer"
  },
  {
   "pid": 136,
   "cpu": 11.8,
   "rss_mb": 26.6,
   "cmd": "dasd"
  },
  {
   "…": "5 more"
  }
 ]
}
```
