# Market tape

As of 2026-10-05. Research / paper only. Soft color. Zero brokerage execution.

## What it is

Feed `market-tape`. TTL 300s on the data-sources row. The blotter strip is **SPY · QQQ · DIA** (last and day%). Helpers **RSP · VTV · VUG** feed the breadth and valuation proxies (RSP−SPY, VTV/VUG) on the fidelity-three panel. They are not a second quote architecture.

Writer string on a tape file produced here: `refresh_market_tape.py`. Owner of the underlying equity quotes remains Rose.

## Cache first

`dashboard/refresh_market_tape.py` calls `cache_io.piggyback_rh_quotes` for those six symbols before anything else.

- Fresh `rh-quotes` (TTL 120s, `error` unset): reuse the cached last and day% for every symbol the file actually contains.
- `--equity-quotes-file` fills **misses only**. A fresh SPY row is kept even if the file has a different SPY price.
- Stale, missing, or `error` on `rh-quotes`: nothing from that file is reused. The quotes file may fill the gap. What is still missing stays `missing`. This module does not call `get_equity_quotes`.
- `--check-piggyback` prints coverage and writes nothing.
- `--dry-run` prints the strip and writes nothing.
- The builder never writes `rh-quotes`. `cache_io.write_feed` would reject it anyway.

`dashboard/live_refresh.py` runs this tape step first (`market-tape-piggyback`) and records `quote_pulls: []` in this package. FRED OAS (`fred-hy-oas`, `fred-ig-oas`) stays a separate public-CSV step on the box. This module does not fetch FRED or Yahoo.

## Not an elevate

Tape day% is session color. Elevate / invalidate still need a live Robinhood quote ≤120s.
