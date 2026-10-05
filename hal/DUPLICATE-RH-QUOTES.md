# DUPLICATE — RH Tech ∪ chip quotes

**Status: open. Do not silently fork.**

## Overlap
| Writer today | Cadence | File / use |
|--------------|---------|------------|
| Rose live book pulse | Standing RTH pulse (both RH accounts + Tech/chip soft) | Rose path → should own shared `rh-quotes` |
| Hal `hal-rh-watch` | Weekday RTH `:05/:35` ET | `market-data/latest/hal-rh-watch-pulse.json` |

Both pull live Robinhood quotes for **Tech ∪ chip play** (~37 unique symbols).

## Target (one writer)
1. **One owner** writes `market-data/latest/rh-quotes.json` (TTL ~120s for scan color).
2. The other bot **reads** that file for soft tape / wall distance color.
3. Elevate / invalidate still re-pulls **live RH ≤120s** (never from cache).

## Until fixed
- Keep flagging this in handbook / query diagram.
- Hal continues `:05/:35` soft pulse for Soft A structure alerts, but treat quote overlap as known debt — no second parallel architecture.
- Prefer Rose as quote writer (live book + watchlists); Hal as reader + Soft A structure annotator on top of shared quotes + Rose `fa-levels`.

## Owner of fix
Rose (repo / handbook merge). Hal will switch to reader once `rh-quotes` exists and Rose confirms.
