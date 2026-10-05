# Hal reader: Rose `rh-quotes`

As of 2026-10-05. Research / paper only. Jeffrey + Rose agreed: **Rose is the sole writer** of shared Robinhood equity quotes for the Tech∪chip union. Hal reads that file. This note is the Hal package rule. It does not install a collector, reschedule the live desk, or cut production off `options-intelligence-desk`.

## Contract

| Field | Value |
| --- | --- |
| Path | `market-data/latest/rh-quotes.json` |
| Feed | `rh-quotes` |
| Owner | `rose` |
| Writer | `refresh_marks.py` (Rose path `dashboard/refresh_marks.py`) |
| TTL | `ttl_seconds` = **120** (scan color and soft tape / wall-distance color) |
| Symbols | Tech∪chip union **plus indexes** (38 on the live file) |
| Hal role | Reader. Soft A structure annotation only. |
| Elevate / invalidate | **Live Robinhood ≤120s.** Never from this cache. |

Live envelope (do not add a second file shape):

```json
{
  "as_of": "<ISO-8601>",
  "as_of_pt": "<PT display>",
  "source": "<live source string>",
  "writer": "refresh_marks.py",
  "feed": "rh-quotes",
  "symbols": ["<38 Tech∪chip + indexes>"],
  "ttl_seconds": 120,
  "payload": { "quotes": {} },
  "error": null
}
```

`owner: rose` is the desk contract. The live writer string stays `refresh_marks.py`. `error` set means the record is not fresh.

## Read rule (prefer `read_fresh`)

On the weekday RTH `:05` / `:35` ET watch:

1. `read_fresh` `rh-quotes` with TTL **120s**.
2. **Fresh:** use `payload.quotes` for Tech∪chip soft tape and wall-distance color. **Do not call** Robinhood `get_equity_quotes` for that union.
3. **Miss, stale, or `error` set:** prefer waiting for the next Rose refresh. A one-shot `get_equity_quotes` is allowed only for symbols missing from an otherwise fresh file. Do not re-pull the union and do not stand up a second quote loop.
4. Keep Soft A **annotation** in `hal-rh-watch-pulse.json` (walls distance, thru/under, avoid list, pulse logic). The pulse file is not a quote cache and is not a second writer of `rh-quotes.json`.
5. Soft color never elevates alone.

## Elevate / invalidate

Paper elevate and invalidate still require a **live Robinhood** equity and option quote **≤120s**. Do not serve those gates from `rh-quotes`, from `hal-rh-watch-pulse.json`, or from FlashAlpha cache.

## Not this package

Live collectors remain on the bot box under `options-intelligence-desk`. No cron change, no Vercel cutover, and no brokerage order path lives here.
