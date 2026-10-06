# DUPLICATE — RH Tech ∪ chip quotes

**Status: resolved 2026-10-05** (Jeffrey confirmed Rose owner).  
**Duplicates #2 (piggyback): closed 2026-10-05** — support-map + market-tape reuse fresh `rh-quotes`.

## Resolved ownership
| Role | Cadence | File / use |
|------|---------|------------|
| **Rose** (sole writer) | Live book pulse + `refresh_marks.py` / `live_refresh.py` path | `market-data/latest/rh-quotes.json` (TTL 120s; writer=`refresh_marks.py`) |
| **Hal** (reader + Soft A annotate) | Weekday RTH `:05/:35` ET | Reads shared `rh-quotes`; Soft A structure on `hal-rh-watch-pulse.json` — no second quote writer |
| **support-map / market-tape** (readers) | When building strip / put-wall map | `cache_io.piggyback_rh_quotes` — reuse if fresh; never write `rh-quotes` |

## Target (met)
1. **Rose** is sole writer of `market-data/latest/rh-quotes.json` (TTL ~120s for scan color).
2. **Hal** reads that file for soft tape / wall distance color and annotates Soft A on top (plus Rose `fa-levels`).
3. Elevate / invalidate still re-pulls **live RH ≤120s** (never from cache).
4. **Duplicates #2:** `dashboard/refresh_support_map.py` and `dashboard/refresh_market_tape.py` read `rh-quotes` first via `piggyback_rh_quotes`. Covered symbols skip `get_equity_quotes`. Misses: Rose may pull missing only and write through `refresh_marks.py`.

## Piggyback helpers
```bash
python3 -c "from cache_io import piggyback_rh_quotes; ..."   # market-data/ on path
python3 dashboard/refresh_market_tape.py --check-piggyback
python3 dashboard/refresh_support_map.py --check-piggyback
python3 dashboard/refresh_support_map.py --dry-run   # reuse cache; no rh-quotes write
```

## Notes
- Live feed already present: Tech ∪ chip (+ tape helpers when Rose last pulled them), ttl=120.
- Do **not** change Hal automation schedules / Vercel / cutover as part of this ownership note.
- Hal `:05/:35` soft pulse may continue for Soft A structure alerts; it must not be a parallel RH quote architecture once Rose `rh-quotes` is fresh (`read_fresh(ttl=120)`).
- `oid-support-levels-watch` must **not** `write_feed("rh-quotes", …)` — call `refresh_support_map.py` after Rose marks refresh.
