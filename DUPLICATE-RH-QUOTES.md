# RESOLVED — RH Tech ∪ chip quotes (2026-10-05)

**Status: resolved.** Jeffrey locked ownership 2026-10-05. Do not re-open a second quote writer.  
**Duplicates #2 piggyback: closed 2026-10-05.**

## Owner
| Role | Who | Path |
|------|-----|------|
| **Writer** | Rose (live refresh / `refresh_marks.py`) | `market-data/latest/rh-quotes.json` |
| **Readers** | Hal Soft A / `hal-rh-watch`, Chart, Macro, Peanut as needed; **support-map** + **market-tape** builders | same file via `cache_io.piggyback_rh_quotes` |
| TTL | ~120s | `ttl_seconds` on the record |
| Universe | ~38 Tech ∪ chip + index symbols | see `symbols` array |

## Hal rules (locked)
1. For Tech∪chip soft tape / wall-distance color, **read** `rh-quotes.json` when fresh (`cache_io.read_fresh` / age ≤ TTL). Do **not** re-pull `get_equity_quotes` for that same union while within TTL.
2. `hal-rh-watch` `:05/:35` ET stays as **structure / Soft A annotation** on top of shared quotes + Rose `fa-levels` — not a second quote writer.
3. Elevate / invalidate still needs **live RH ≤120s** option + equity quotes. Never serve elevate gates from `rh-quotes` cache.
4. If `rh-quotes` is missing/stale/error, note `RH_QUOTES_STALE` and either wait for Rose’s next write or, only for Soft A structure alerts that must fire, pull a **minimal** live subset — never silently fork a parallel full-universe writer.

## Duplicates #2 (support-map + market-tape)
1. Builders call `piggyback_rh_quotes(symbols)` first.
2. Fresh + covered → reuse marks; **no** RH equity quote call for those symbols.
3. Miss/stale/partial → Rose pulls missing (or full) via `refresh_marks.py` / `live_refresh.py` (sole writer). `refresh_support_map.py` / `refresh_market_tape.py` **never** write `rh-quotes`.
4. Smoke: `python3 dashboard/refresh_market_tape.py --check-piggyback` · `python3 dashboard/refresh_support_map.py --check-piggyback`.

## GitHub
Keep this file under `hal/` as the resolution record. Live blotter remains https://bold-tulip-nejq.here.now/ — no collector cutover from this change alone.
