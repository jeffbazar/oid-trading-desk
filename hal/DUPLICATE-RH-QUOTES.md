# RH Tech ∪ chip quotes — duplicate resolved

**Status: resolved 2026-10-05.** Jeffrey + Rose agreed. Rose owns shared Robinhood equity quotes. Hal is the reader.

This file used to flag an open overlap. It now records the closed rule so the debt is not reopened. Collector cutover is **not** in this repo: live routines still run from `options-intelligence-desk` on the bot box. The packaged desk enforces the reader contract in `hal/RH-QUOTES-READER.md`.

## What overlapped

| Path | Cadence | File / use |
| --- | --- | --- |
| Rose live book pulse, then `dashboard/refresh_marks.py` | Standing RTH write of the shared quote file | **Sole writer** of `market-data/latest/rh-quotes.json` |
| Hal `hal-rh-watch` | Weekday RTH `:05` / `:35` ET | `market-data/latest/hal-rh-watch-pulse.json` |

Both had been pulling live Robinhood `get_equity_quotes` for **Tech ∪ chip** (Hal: 37-symbol union, two batches). That second pull is closed.

## Rule now

1. **Rose** is the sole writer of `market-data/latest/rh-quotes.json`. Writer string: `refresh_marks.py`. `ttl_seconds`: **120**. Symbols: Tech∪chip union plus indexes (38 on the live file). Contract owner: `rose`.
2. **Hal reads** that file (`read_fresh`, TTL 120s) for soft tape and wall-distance color. When the file is fresh, Hal **must not** call `get_equity_quotes` for the Tech∪chip union.
3. Miss, stale, or `error`: prefer the next Rose refresh. Optional one-shot quotes only for symbols missing from a fresh file. No second parallel quote architecture.
4. Hal may keep Soft A structure annotation and pulse logic in `hal-rh-watch-pulse.json`. That file is not a quote writer.
5. Elevate / invalidate still re-pulls **live Robinhood ≤120s**. Never serve those gates from `rh-quotes` or the Hal pulse.
6. **Duplicates #2 closed 2026-10-05.** `support-map` and `market-tape` call `cache_io.piggyback_rh_quotes` and never write `rh-quotes`. Hal is not that writer either. Desk note: `DUPLICATE-RH-QUOTES.md` (repo root). Watch prompt: `automations/oid-support-levels-watch-prompt.md`.

The checked-in `market-data/latest/hal-rh-watch-pulse.json` is a pre-resolution sample (it records a live union pull). It is evidence of the old overlap, not permission to keep quoting.

## Where the rule lives

- `hal/RH-QUOTES-READER.md` — path, TTL, owner, read_fresh, Soft A annotate-only
- `hal/registry.json` — `rh-quotes` reader; `hal-rh-watch` no longer a duplicate writer
- `docs/QUERY-ARCHITECTURE.md` — Duplicates #1 and #2 closed
- `DUPLICATE-RH-QUOTES.md` (repo root) — tape and support-map piggyback
- `market-data/QUERY-DEDUP.md` — owner line for `rh-quotes`
