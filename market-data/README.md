# Shared market-data store (OID ↔ Hal/OT2)

**V0 — 2026-09-17.** Research only; zero execution.

## Ownership
- **OID (Rose)** = primary writer for FlashAlpha + Unusual Whales soft snapshots (+ RH session RVOL when computed).
- **Hal / OT2** = reader; may write RH option marks for OT2 paper tickets only; should **not** re-pull FA levels/UW if `latest/` is fresh (&lt; soft TTL below).
- **Chart Bot** = sole writer of post-close daily equity historicals (`chart-daily`). Does not share Rose/Hal live quote pulse.
- **Macro / Peanut / C&S** = producer writers for their own feeds only (see QUERY-ARCHITECTURE).
- Optional later: dedicated collector bot — not required for V0.

## Query dedup (mandatory)
See **[QUERY-DEDUP.md](QUERY-DEDUP.md)** for owner writers, TTLs, read-before-pull rules, and the elevate live-quote exception.

Helpers: **`cache_io.py`**
- `read_fresh(feed, ttl_seconds=None) -> dict|None`
- `write_feed(feed, *, source, writer, symbols, payload, ttl_seconds, error=None)`
- CLI: `python3 cache_io.py get fa-levels` · `python3 cache_io.py age fa-levels`

**Rule:** every OID automation reads cache first → pull FA/UW/RH only if stale/missing → write back.  
**Exception:** PAPER_CANDIDATE / liquidity quote-age ≤120s still needs **live** RH option+equity quotes at elevate — never from cache.

## Layout
```
market-data/
  README.md
  QUERY-DEDUP.md
  cache_io.py
  schema/v0.md
  latest/           # one JSON per feed key (overwrite)
  snapshots/YYYY-MM-DD/  # optional dated copies
```

## Feed keys (latest/{key}.json)
| key | source | writer | TTL (default) |
|-----|--------|--------|---------------|
| `fa-levels` | FlashAlpha get_levels / get_flow_levels | OID (walls-pulse primary) | 600s |
| `fa-flow-levels` | FlashAlpha get_flow_levels | OID | 600s |
| `fa-soft` | exposure_summary etc. | OID | 1800s |
| `uw-flow-alerts` | get_flow_alerts | OID | 900s |
| `uw-net-prem` | flow_per_strike + market_tide | OID | 900s |
| `uw-oe` | dark_pool trades / price group | OID | 1800s |
| `uw-form4` | insider transactions | OID (premarket + afternoon) | 21600s |
| `rh-rvol` | equity historicals RVOL soft | OID (near-wall) | 1800s |
| `rh-quotes` | equity quotes (scan color) | **Rose** (sole writer; Jeffrey confirmed 2026-10-05). support-map + market-tape **piggyback** when fresh (Duplicates #2) | 120s (elevate = live) |
| `rh-option-marks` | option marks for open paper | either | 300s (elevate = live) |
| `paper-open` | pointer/summary of open seats | either | on change |
| `chart-daily` / `chart-daily-observations` | RH `get_equity_historicals` daily bars | **Chart Bot only** (sole post-close daily historicals) | session (weekday 2:24 PM PT) |
| `supply-chain-identity` | desk SQLite identity snapshot | Customer/Supplier Bot | none (empty ≠ STALE) |
| `macro-morning` | Macro soft-color morning pack | Macro Bot | ~86400s |
| `peanut-news` | move-worthy news alerts | Peanut | alert stamp (quiet scans no rewrite) |
| `desk-catalysts` | soft event calendar | Hal | 21600s |
| `hal-x-scan` | Hal X allowlist scan | Hal | 7200s |
| `hal-rh-watch-pulse` | Tech∪chip soft tape :05/:35 | Hal (**reads** Rose `rh-quotes` + Soft A annotate; resolved 2026-10-05) | 120s |
| `hal-marks` | held option marks 15 min | Hal | 900s |

## Record shape
See `schema/v0.md`. Every file: `{ "as_of", "as_of_pt", "source", "writer", "feed", "symbols", "ttl_seconds", "payload", "error" }`.

## Rules
- Never invent vendor data. On failure write `{ "as_of", "error": "UW_DATA_INSUFFICIENT"|... }` rather than stale-as-fresh.
- Cite source in downstream briefs (FA / UW / RH).
- FA Growth quota: prefer reading `latest/fa-levels.json` via `read_fresh` before a new pull if within TTL.
