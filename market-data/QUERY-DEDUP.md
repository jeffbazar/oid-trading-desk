# Query dedup (V0)

As of 2026-10-05 (PT), after the production-root cutover. Research / paper only. Zero brokerage execution.

This is the short owner policy. `docs/QUERY-ARCHITECTURE.md` is the diagram and the longer fix list. It builds on this file and does not replace it.

Production root: `/workspace/oid-trading-desk`. `/workspace/options-intelligence-desk` is a symlink to that tree.

## Rule

Each vendor endpoint has one owner that writes `market-data/latest/{feed}.json`. Every other bot reads that file (`cache_io.read_fresh` or `cache_io.piggyback_rh_quotes`) and does not make the same call.

```bash
python3 market-data/cache_io.py get <feed>
```

Call the vendor only on a miss, and only if you are the owner. Write back with `write_feed(...)`, including error records (`error` set, never presented as fresh). Elevate / invalidate / liquidity gates need a live Robinhood quote ≤120s. They are never served from cache.

## rh-quotes

| Field | Value |
| --- | --- |
| File | `market-data/latest/rh-quotes.json` |
| Owner | `rose` |
| Writer | `refresh_marks.py` (`dashboard/refresh_marks.py`) |
| TTL | 120 seconds |
| Readers | Hal soft tape; `refresh_market_tape.py`; `refresh_support_map.py`; `live_refresh.py` (tape cache-first) |
| Must not | A second writer. `write_feed("rh-quotes")` from Hal, support-map, market-tape, or `oid-support-levels-watch` |

`cache_io.write_feed` rejects an `rh-quotes` write unless `writer` is `refresh_marks.py` and `owner` is `rose`.

## Duplicates

1. **Tech∪chip equity quotes — closed 2026-10-05.** Rose writes. Hal reads and Soft-A-annotates at `:05` / `:35` ET. No `get_equity_quotes` for that union while the file is fresh.
2. **support-map and market-tape — closed 2026-10-05.** Both call `piggyback_rh_quotes` first. Covered symbols are reused. A local `--equity-quotes-file` fills misses and does not override a fresh cache row. Neither builder writes `rh-quotes`.

## Owner sketch

| Feed | Owner writes | Everyone else |
| --- | --- | --- |
| `rh-quotes` | Rose `refresh_marks.py` | Read. Piggyback for tape and support-map |
| `market-tape` | `refresh_market_tape.py` / `live_refresh.py` | Read the strip. Do not re-quote SPY · QQQ · DIA · RSP · VTV · VUG when `rh-quotes` is fresh |
| `support-map` | Rose via `refresh_support_map.py` | Read put-wall distance. Do not write `rh-quotes` |
| `fa-levels` | Rose | Hal reads. One FlashAlpha Growth limit |
| `chart-daily` | Chart Bot | Post-close daily history only. Not the live quote file |
| `peanut-news` | Peanut | Wire / headline. No RH quote calls |
| `macro-morning` | Macro Bot | No FA / UW / RH quote calls |

No order tools. Alerts, research, and paper only.
