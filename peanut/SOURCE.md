# Peanut — source registry (folder drop)

**Repo:** https://github.com/jeffbazar/oid-trading-desk  
**Paths:** `peanut/` · `market-data/latest/peanut-news.json`

## Feed
- **Id:** `peanut-news`
- **Owner:** Peanut - News Alerts
- **Universe:** Robinhood Tech ∪ chip play (~37 names)
- **Cadence:** weekdays every 5 min ~6:11a–1:56p PT + 5:30a PT premarket
- **Sources:** X news search + public web (shared X credit pool). No FlashAlpha, Unusual Whales, or Robinhood quote calls from Peanut.
- **Outputs:** chat alerts to Jeffrey; forward to Rose and Hal for call/put analysis; Live Book marquee + News Archive
- **Banner rule:** marquee shows only alerts after the prior RTH close; full history stays in the JSON store and on News Archive
- **Stamp note:** file `as_of` is last **alert**, not last quiet scan

## Not built / N/A
SEC collector, issuer IR, Form 4, policy feed, Benzinga websocket, immutable revisions, read API.

## Lane split (2026-10-05)
Peanut owns wire/headline. X Summarizer owns X-edge tape (overreaction / early valuation accounts, grade ≥3 → Rose/Hal). Do not re-forward the same X-edge stories as Peanut wire hits.
