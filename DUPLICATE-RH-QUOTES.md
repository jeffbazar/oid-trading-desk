# DUPLICATE — RH Tech ∪ chip quotes

**Status: resolved 2026-10-05 (Jeffrey + Rose).** Rose is the sole writer. Hal reads. Duplicates #2 (support-map / market-tape piggyback) closed the same day.

Research / paper only. Zero brokerage execution.

## Resolved ownership

| Role | Cadence | File / use |
| --- | --- | --- |
| Rose (sole writer) | Live book pulse, then `dashboard/refresh_marks.py` | `market-data/latest/rh-quotes.json` (TTL 120s; writer `refresh_marks.py`; owner `rose`) |
| Hal (reader + Soft A annotate) | Weekday RTH `:05` / `:35` ET | Reads shared `rh-quotes`. Soft A structure on `hal-rh-watch-pulse.json`. Not a second quote writer |
| support-map / market-tape (readers) | When building the strip or the put-wall map | `cache_io.piggyback_rh_quotes`. Reuse when fresh. Never write `rh-quotes` |

## Target (met)

1. Rose is the sole writer of `market-data/latest/rh-quotes.json` (TTL 120s for scan color and soft tape). Symbols: Tech∪chip union plus indexes (38 on the live file).
2. Hal reads that file (`read_fresh`, TTL 120s) for soft tape and wall-distance color and annotates Soft A on top (plus Rose `fa-levels`). When the file is fresh, Hal does not call `get_equity_quotes` for the Tech∪chip union.
3. Miss, stale, or `error`: prefer the next Rose refresh. A one-shot quote is only for symbols missing from an otherwise fresh file.
4. Elevate / invalidate still re-pulls live Robinhood ≤120s. Never from `rh-quotes`, the Hal pulse, or FlashAlpha cache.
5. Duplicates #2: `dashboard/refresh_support_map.py` and `dashboard/refresh_market_tape.py` read `rh-quotes` first via `piggyback_rh_quotes`. Covered symbols skip a new equity pull. Misses: Rose may pull the missing names only and write them through `refresh_marks.py --equity-quotes-file`, then the builder reruns. `--equity-quotes-file` on a builder fills misses and does not override fresh cache rows.

## Piggyback helpers

```bash
python3 -c "from cache_io import piggyback_rh_quotes"
python3 dashboard/refresh_market_tape.py --check-piggyback
python3 dashboard/refresh_support_map.py --check-piggyback
python3 dashboard/refresh_support_map.py --dry-run
```

`market-data/` has to be on `PYTHONPATH` for the one-liner (`python3` from that directory, or the dashboard scripts, which load it themselves).

| Builder | Behavior |
| --- | --- |
| `refresh_market_tape.py` | Default: reuse a fresh cache for SPY · QQQ · DIA · RSP · VTV · VUG. `--equity-quotes-file` only for misses. `--check-piggyback` smoke. Never writes `rh-quotes`. |
| `refresh_support_map.py` | Default: reuse a fresh cache for the primary + extended support book. A file fills misses. `--dry-run` / `--check-piggyback`. Never writes `rh-quotes`. |
| Rose on a miss | `get_equity_quotes` for the missing names only, then `refresh_marks.py --equity-quotes-file …` (sole writer), then rerun the builder. |
| Hal | Reader only. No `rh-quotes` write. |
| `oid-support-levels-watch` | Must not `write_feed("rh-quotes", …)`. Call `refresh_support_map.py` after Rose's marks refresh. See `automations/oid-support-levels-watch-prompt.md`. |

## Notes

- `live_refresh.py` is tape cache-first: the piggyback runs before any other refresh step and does not write `rh-quotes`.
- Do not change Hal automation schedules as part of this ownership note. The `:05` / `:35` ET pulse may keep Soft A structure alerts. It must not be a parallel quote architecture while `rh-quotes` is fresh.
- Hal package detail: `hal/DUPLICATE-RH-QUOTES.md` and `hal/RH-QUOTES-READER.md`.
- The checked-in `market-data/latest/hal-rh-watch-pulse.json` sample is pre-resolution evidence of the old union pull. It is not permission to keep a second writer.
