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
  Tone color from the spike row net (green > +0.15, red < -0.15, else gray), or the last sample <= 60 min earlier (marked *).
- Prices: collector 1m SIP bars `~/oid-desk/desk/cache/bars/store/live/<SYM>-1m-<date>.jsonl`. Moves: +60 min (flag cut if
  the close comes first) and spike-to-close; also vs QQQ. Flat band +/-0.05%.
- Writes `corr-YYYYMMDD.md` + `.json` (spike table, preceded up/down, hit rates by color and 1.5-2x / 2-3x / 3x+ / z-only,
  rolling last 10 final days + today, emerging pattern with small-sample caveat). Before 13:05 PT the run is PRELIMINARY.
- Run by hand: `~/oid-desk/venv/bin/python ~/oid-desk/x-sentiment/corr_report.py [--date YYYYMMDD] [--partial] [--force]`.
- Holiday list in `HOLIDAYS` / `EARLY_CLOSE` covers 2026-2027; extend yearly.

## Change log
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
