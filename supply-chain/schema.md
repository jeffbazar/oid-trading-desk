# Supply-chain paper store

Path: `supply-chain.db` (SQLite, WAL). Research and paper alerts only. No orders, no outbound messages.

Open with Python `sqlite3` and run `PRAGMA foreign_keys = ON` on every connection. Foreign keys are not persisted as a database default. `PRAGMA journal_mode` is WAL.

Stable text ids. Variable payloads are JSON text (`alert_outbox.payload_json` must be valid JSON).

## Tables

- `entities` — legal identity. `listing_status` is `public`, `private`, or `unknown`. `cik`, `lei`, `country` stay null when not known.
- `entity_aliases` — `legal`, `brand`, `ticker_label`, or `other`. Unique per entity, alias, and type.
- `instruments` — one row per listed line. Unique `(ticker, exchange, share_class)`. `adr_ratio` and `effective_to` nullable.
- `sources` — provider registry, including gaps (`not_entitled`).
- `claims` — a row needs `source_id` or a non-empty `excerpt` (seed-unverified placeholder). `evidence_status`: `PRIMARY_DOCUMENT`, `PRIMARY_STATEMENT`, `REPORTED`, `DISCOVERY_ONLY`, `INFERRED`, `DISPUTED`, `RETRACTED`.
- `relationships` — directed edge. `edge_type`: `SUPPLIES`, `BUYS_FROM`, `COMPETES_WITH`, `PARTNERS_WITH`, `INVESTS_IN`, `LENDS_TO`, `LEASES_FROM`, `HOSTS_COMPUTE_FOR`, `BUILDS_PROJECT_FOR`, `PROVIDES_POWER_TO`. Certainty: `confirmed`, `reported`, `inferred`, `unknown`. Do not insert a row without evidence. Bootstrap leaves this table empty.
- `economic_events` — `public_at` nullable. `received_at` required.
- `impact_assessments` — per event and entity. Direction: `POSITIVE`, `NEGATIVE`, `MIXED`, `UNCERTAIN`.
- `alert_outbox` — `idempotency_key` unique. `status`: `pending`, `suppressed`, `delivered_paper`. `event_id` nullable.
- `source_checkpoints` — primary key `(source_id, checkpoint_key)`.

Identity seed rows are not claims. No collector or cron is attached.

## Bootstrap (2026-10-04 PT)

37 entities and 37 instruments from the Robinhood watchlist inventory: 33 company tickers (one entity each) and 4 fund tickers (`SPY`, `QQQ`, `SMH`, `EWY`). Fund entities use the ticker as `legal_name` and are marked as funds, not operating companies. Issuers are not modeled.

`GOOG` is Alphabet Inc., share class `Class C`. There is no `GOOGL` instrument and no second Alphabet entity.

`SKHY` and `MH` are ticker-only (`legal_name` = ticker; note `ticker-only identity; legal name not verified this pass`). No CIKs or LEIs. `instrument.effective_from` is the inventory date `2026-10-04`, not a verified listing date. Exchange `UNVERIFIED` means the venue was not confirmed (`SNDK`, `SPCX`, `SKHY`, `MH`).

Sources: `robinhood-watchlists` (`connected`, `last_success_at` `2026-10-04`); `robinhood-sec-filing-index` (`connected`, Robinhood tool, not direct EDGAR, no backfill); `flashalpha`, `unusual-whales`, `x` (`connected_not_called`); `benzinga`, `factset`, `eia` (`not_entitled`, url null).

One paper alert, `idempotency_key` `hypothetical-capex-example-v1`, status `suppressed`, recipient `desk-paper`. Payload has `hypothetical: true`, capex `$10B` to `$12B` (+20% vs own prior guidance), `consensus_surprise` `UNKNOWN`, supplier impact inferred, allocation unknown, not an order and not a trade. The linked event summary starts with `HYPOTHETICAL` and names no real company. No impact-assessment row.

Rebuild with `bootstrap_store.py` (replaces the db file).
