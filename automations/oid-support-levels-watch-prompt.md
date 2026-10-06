# oid-support-levels-watch

Research / paper only. Alert-only. Zero brokerage execution.

You maintain the soft support map (put-wall distance), with NVDA on the primary book. You do not open a seat, and you do not place, modify, cancel, or exercise a Robinhood order. A distance is not an elevate.

## Hard rule

Do **not** call `write_feed("rh-quotes", …)`. Rose `dashboard/refresh_marks.py` is the sole writer of `market-data/latest/rh-quotes.json` (owner `rose`, TTL 120s). Hal is a reader. You are a reader of that file.

## Each run (weekdays, about every 15 minutes, 6:05 AM–1:50 PM PT)

1. Let Rose finish `refresh_marks.py` when a quote refresh is due. If you were handed a local equity-quotes file of **missing** symbols only, the writer is still:

```bash
python3 dashboard/refresh_marks.py --equity-quotes-file "$QUOTES"
```

2. Build the map from the fresh cache. Do not pull the whole book again when `piggyback_rh_quotes` already covers it.

```bash
python3 dashboard/refresh_support_map.py --check-piggyback
python3 dashboard/refresh_support_map.py --dry-run
python3 dashboard/refresh_support_map.py --walls-file "$WALLS"
```

`--equity-quotes-file` on the builder fills cache misses only. It must not replace a fresh cached row and must not write `rh-quotes`.

3. Diff against the previous map and notify only on a real change (cross under, reclaim, or a distance jump). Quiet when nothing material changed.

```bash
python3 dashboard/support_notify_diff.py --previous "$PREV" --current "$CURRENT"
```

4. Soft line only. Say that it does not elevate. Elevate / invalidate elsewhere still needs a live Robinhood quote ≤120s, never this cache and never the notify text.

## Do not

- Schedule a second `get_equity_quotes` loop for the Tech∪chip union.
- Spend FlashAlpha when `fa-levels` is already on disk. Pass the walls file through.
- Write `supply-chain.db`, copy `market-data/latest` vendor payloads into git, or publish to swift-dune.
- Touch Hal's `:05` / `:35` ET schedule.
