# Customer/Supplier Bot — supply-chain/

Folder drop for https://github.com/jeffbazar/oid-trading-desk

## Contents
- `supply-chain.db` — **not committed** (Rose seed policy: no sqlite in this repo). Lives on the box at `/workspace/options-intelligence-desk/supply-chain/supply-chain.db`; rebuild with `bootstrap_store.py`.
- `schema.md` — table contract
- `bootstrap_store.py` — rebuild script (replaces the db)
- `supply-chain-identity.json` — published identity snapshot (also mirrored under `market-data/latest/`)

## Rules
- Google: one Alphabet entity, **GOOG Class C only** (no GOOGL instrument)
- Relationships / claims: currently **0**. Empty edges are intentional unknown exposure, not a failed fetch
- Soft / empty map never elevates a trade
- No weekday collector. On-demand identity seed from Robinhood Tech ∪ chip play watchlists
- Shared Robinhood `get_sec_filing_index` when filing evidence is needed — not a second EDGAR client
- Do **not** call FlashAlpha, Unusual Whales, X, Benzinga, FactSet, or EIA from this bot for the map

## Counts (as of snapshot)
37 entities, 37 instruments, 0 relationships, 0 claims. Writer: Customer/Supplier Bot.
