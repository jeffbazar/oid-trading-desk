# x-sentiment: per-ticker X sentiment feed (SHADOW)

Jeffrey go 2026-10-26 ("yes, that would be great"), shadow mode. Runs on the Mac mini only. Nothing in the live
direction score, orders, or alerts reads it.

## What it does (per ticker, per pass)
- `GET /2/tweets/counts/recent` (minute buckets, last 15 min): chatter count. $0.005 per request.
- Once a day per ticker, `counts/recent` hourly over 7 days: trailing RTH pace -> `chatter_ratio`, `chatter_z`.
- `GET /2/tweets/search/recent` `$SYM -is:retweet -is:nullcast lang:en`, max 10 newest posts since the last seen id: tone sample. $0.005 per post.
- Drops spam (cashtag stuffing, spam terms, x-on-surge blocklist, follow-farm / low-activity authors when the author is
  already in the x-on-surge user cache; no paid user lookups). Scores each post with TypeSafe Jev (`jev.py`, since
  v0.4): one Choice question per post {bullish, bearish, neutral, not_about_ticker} -> probabilities; post score
  s = P(bull) - P(bear); not_about_ticker posts are dropped. If Jev errors, times out, has no key, or hits its cost cap,
  that post falls back to the local finance lexicon (`lexicon.py`). Weights by author followers (cached authors) x
  engagement, rolls up to `net` (-1..+1, weighted mean of s) and `net_ewma`. Every row logs `post_scores` (engine,
  p_bull/p_bear/p_neu/p_off, confidence, weight, text up to 280 chars) plus `engines` and `jev_error`.

## Files
- Feed: `~/oid-data/sentiment/x/YYYYMMDD.jsonl` (one row per ticker per pass), `latest.json`, `status.json`
- Scorecard: `~/oid-data/sentiment/x/scorecard-YYYYMMDD.{md,json}` (lead vs lag at 5/15/30 min, chatter spikes)
- Config: `~/oid-data/config/x-sentiment-config.json` (hot-reloaded). Ledger: `~/oid-data/state/x/sentiment_budget.json`

## Schedule (launchd)
- `com.oid.desk.x-sentiment`: every 300 s; no-op outside 06:30-13:00 PT weekdays or while `fetch_enabled=false`.
  Full universe (61 core names) when minute % 15 < 5, else the hot tier (position-trigger seats + top 6 movers, max 12).
- `com.oid.desk.x-sentiment-scorecard`: weekdays 13:45 PT.
- `com.oid.desk.x-sentiment-corr`: weekdays 13:10 PT (`corr_report.py`; skips NYSE holidays, 10:00 PT close on early-close days).

## Budget
Every request is prechecked at worst case against the sentiment caps and the desk's combined X caps
($5/day, $100/month across x-on-surge + name-credit + this). Kill: `touch ~/oid-data/state/x/SENTIMENT_STOP`
(or the shared `STOP`), or set `fetch_enabled=false`.

## Jev scorer (TypeSafe)
- API: `POST https://api.typesafe.ai/v1/systemone`, model pinned `jev-1.14.0` (config `scorer.model`). Stdlib HTTP, no SDK.
- Key: `~/oid-data/secrets/TYPESAFE_API_KEY` (chmod 600), read at runtime, never logged.
- Cost guard: own ledger `~/oid-data/state/x/jev_budget.json`; caps $0.50/day, $10/month, 3,000 posts/day (config
  `scorer.*`). Billed on input tokens only, $0.042 per million; measured ~660 tokens/post = ~$0.00003/post.
- Off switch: set `scorer.engine` to `"lexicon"` in the live config (hot-reloaded).
- Replay saved posts with no X reads: `~/oid-desk/venv/bin/python ~/oid-desk/x-sentiment/jev_replay.py --n 14 --per-sym 2`
  (reads the newest x-on-surge `archive/posts_raw` file).

## Commands
```
~/oid-desk/venv/bin/python ~/oid-desk/x-sentiment/oid_x_sentiment.py pull --test --force-session --symbols NVDA,MU,AVGO --keep-posts
~/oid-desk/venv/bin/python ~/oid-desk/x-sentiment/oid_x_sentiment.py pull --dry-run --force-session --test
~/oid-desk/venv/bin/python ~/oid-desk/x-sentiment/oid_x_sentiment.py scorecard --date 20261027
```

## Spike vs price correlation report (2026-10-27, Jeffrey ask on voice ~7:39 AM PT; display only)
- `corr_report.py` rebuilds chatter spikes from the dated snapshots (no separate intraday logger): spike = z >= 2 or >= 2x
  (red), watch = >= 1.5x (amber); first snapshot per ticker per episode (episode ends on a non-spike snapshot or >35 min gap).
  Tone color (green > +0.15, red < -0.15, else gray) from the spike-time sample (<= 5 min after, fresh), else the last sample <= 60 min earlier (stale, marked *).
- Prices: collector 1m SIP bars `~/oid-desk/desk/cache/bars/store/live/<SYM>-1m-<date>.jsonl`. Moves: +60 min (flag cut if
  the close comes first) and spike-to-close; also vs QQQ. Flat band +/-0.05%.
- Writes `corr-YYYYMMDD.md` + `.json` (spike table, preceded up/down, hit rates by color and 1.5-2x / 2-3x / 3x+ / z-only,
  rolling last 10 final days + today, emerging pattern with small-sample caveat). Before 13:05 PT the run is PRELIMINARY.
- Run by hand: `~/oid-desk/venv/bin/python ~/oid-desk/x-sentiment/corr_report.py [--date YYYYMMDD] [--partial] [--force]`.
- Holiday list in `HOLIDAYS` / `EARLY_CLOSE` covers 2026-2027; extend yearly.

## Event-driven tone (v0.5, 2026-10-27, Jeffrey voice 7:45 AM PT; display only)
- Live cadence stays as it was: hot tier (max 10 names) chatter counts every 15 min, full tier off (preset `hot-10`;
  the doc's "full 15 / hot 5" spec was never affordable). Unchanged by v0.5.
- Trigger: in the same pass, right after the chatter count, a red spike (z >= 2 or >= 2x) pulls and scores a tone sample
  (`event_decide` / `event_mark`, Jev + lexicon fallback). Amber 1.5-2x alone does NOT trigger (cost/noise); an amber
  name that climbs to red triggers then.
- Cooldown per ticker per episode: one pull when the spike fires; re-pull only on escalation (ratio +1x or z +2 since
  the last pull) or after 30 min still at red. Episode closes on a non-red snapshot. Max 6 event pulls per pass.
- Hourly sample dropped: `cadence.hot_sample_every_min` 60 -> 390 = one opening sample on the first hot pass (baseline tone
  for every hot name). Revert: set 60.
- Cost: event pulls have their own cap `event_sample.daily_usd_cap` $2.75/day on top of `Budget.precheck` (sentiment
  $5.25/day, desk $10/day). Expected ~$3.3/day for the feed, worst case ~$4.65 (old hot-10 worst $4.85).
- Rows: `sample_reason` (`scheduled` | `event:spike` | `event:escalation` | `event:cooldown_rescore`), `tone_t`,
  `event_skip` (cooldown / event_day_cap / event_pass_cap / budget reason). `latest.json` carries `tone_t` + `sample_reason`;
  `status.json` has `event_pulls`, `event_day_usd`, `event_day_n`. Off switch: `event_sample.enabled=false`.
- 400 fix: X rejects `since_id` together with `start_time`/`end_time`. Search now sends `since_id` alone when that post
  is inside the window, else a plain start/end window (`snowflake_t`). This was the 07:34 400 on BE / WDC / WULF.
- Panel: tone age per name (minutes; blue ⚡ = pulled at the spike, grey italic = older than 20 min).
- `corr_report.py` v2: tone = sample at the spike or <= 5 min after it (fresh), else the prior reading <= 60 min old
  (stale, *), else none; the report prints fresh / stale / none counts and a fresh-only 1h tone-right rate.

## Change log
- 2026-10-27 v0.5: event-driven tone pulls on red chatter spikes + per-ticker cooldown; hourly sample -> opening only; since_id 400 fix; panel tone age; corr_report v2 spike-time tone.
- 2026-10-26 v0.4 (Jeffrey approved): post scorer = TypeSafe Jev with lexicon fallback per post, per-post probabilities
  always logged (with text), not_about_ticker drop, Jev cost guard. `--keep-posts` is now a no-op. Added jev.py, jev_replay.py.
- 2026-10-26 v0.3 (Jeffrey approved): ENABLED, preset hot-10 (10 names = position-trigger seats then top movers; chatter
  every 15 min, tone sample hourly; ~$4.85/day worst case). Caps: this job $5.25/day, $110/month; desk combined X
  $10/day, $220/month. Slot dedupe so each 15-min block runs once regardless of launchd drift.
  Companion changes (backups *.bak-20261026-xsent on the mini):
  - x-on-surge config (live ~/oid-data/config + lib copy): x_daily_usd_cap 5->10, x_monthly_usd_cap 100->220,
    reserve_other_usd 0.30->5.05 (keeps x-on-surge's own allowance at $4.45/day).
  - x-on-surge lib/budget_guard.py: _ext_month() now counts name-credit + x-sentiment month spend in its pacing.
  - x-on-surge oid_x_on_surge.py: --selftest cap asserts 5/100 -> 10/220.
  - oid-score/research/name_credit.py: X_MONTH_CAP_TOTAL 95 -> 209 (95% of $220).
