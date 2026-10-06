# NVDA support watch

As of 2026-10-05. Research / paper only. Soft color. Never elevates alone. Zero brokerage execution.

## What it watches

`support-map` is Rose's put-wall distance file (data-sources: weekdays every 15 minutes, 6:05 AM–1:50 PM PT, TTL 300s). NVDA sits on the **primary** book with SPY, QQQ, TSLA, AMD, MU, AVGO, META, GOOG, and SMH. The **extended** book is the rest of the Tech∪chip union (37 names together).

Distance is `(last - put_wall) / put_wall` when both numbers exist. Positive means the last is above the put wall. The walls come from a local `--walls-file` (Rose `fa-levels` already on disk). This watch does not call FlashAlpha.

The 2026-10-05 Hal pulse sample recorded NVDA call wall 240 / put wall 230 as structure color. That sample is not a live level and is not a quote permission. The watch reads `support-map` distance. It does not re-quote.

## Piggyback

`dashboard/refresh_support_map.py` calls `cache_io.piggyback_rh_quotes` for the primary + extended book.

- Fresh cache rows are reused.
- `--equity-quotes-file` fills misses only.
- `--dry-run` and `--check-piggyback` do not write.
- The builder never writes `rh-quotes`.

`dashboard/support_notify_diff.py` compares the previous map to the new one. A cross under the put wall, a reclaim, or a distance jump of at least 0.5% becomes a soft line. Empty previous input is a baseline, not a burst of adds. The notify text says soft only, no elevate, zero RH execution.

## Automation

`oid-support-levels-watch` must not `write_feed("rh-quotes", …)`. After Rose `refresh_marks.py`, run `refresh_support_map.py`, then the diff. Prompt: `automations/oid-support-levels-watch-prompt.md`.

Walls may be STALE_CARRY when the FlashAlpha quota is 0. Carry is not a failed fetch and is not an elevate.
