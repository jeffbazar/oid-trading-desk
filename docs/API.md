# Local desk API

Default origin: `http://127.0.0.1:8768`. Start the service with `python3 server.py` from the project directory after importing a snapshot. Python 3.10 or newer is required; the server and importer use the standard library. This API exposes imported public-source data and local paper reviews. It does not expose brokerage execution or a live market-data connection.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/snapshot` | Return the current `data/snapshot.json` without mutating its source values |
| GET | `/api/health` | Local server/snapshot availability; not production collector health |
| GET | `/api/reviews` | Retrieve local SQLite review records |
| POST | `/api/reviews` | Append a paper review note/status to an imported evidence row; does not change source records |
| GET | `/api/events` | SSE notifications for local snapshot/review changes |
| POST | `/api/sync` | Manually fetch/import the eight allowlisted public resources |
| GET | `/api/export/trades.csv` | Export reported closed-trade source cells |
| GET | `/api/prompt/<bot>` | Read a copied operating prompt as JSON |
| GET | `/api/download/<basename>` | Download an allowed document/prompt attachment |
| GET | `/downloads/<basename>` | Attachment alias |
| GET | `/api/changes` | Read `docs/changes.json` |
| GET | `/api/registry` | Read the proposed `docs/source-registry.json` |

Prompt IDs are the configured five roles: `rose`, `hal`, `macro`, `chart`, `news`. The prompt endpoint returns `{ "bot": "…", "text": "…", "filename": "…" }`. Downloads are constrained to project documentation and prompt basenames; supplying a path does not authorize arbitrary file access. The registry is a recommendation artifact, not an assertion that its proposed feeds are connected.

## Snapshot and provenance

The snapshot endpoint serves the import JSON byte-for-byte. Its `ETag` represents disk content; `X-Snapshot-Revision` identifies the durable local snapshot revision; `X-Server-Time` gives a separate current server clock. `If-None-Match` can produce a 304 response for unchanged content. None of those headers changes a source observation date. Pages, sections, table headers, original cells/titles/details/links, positions, reported closed rows, macro, watches, news and validation findings remain available according to the importer contract.

Each import separates collection metadata from clocks visible in the source: page build, marks refresh, macro judgment, chart calculation/completed session and item dates. Missing observation times remain missing. Source text is evidence from the public publication, not private API verification. Original downloads remain in `data/raw/`; complete immutable bundles are archived in `data/reference-snapshots/<content-hash>/`. A successful fetch writes `data/raw/current.json` to select the current complete bundle. The importer does not rewrite the original download files.

Collection provenance includes its basis. A normal local import uses original file modification time, explicitly labeled `local_file_mtime_not_independent_network_receipt`, unless a known receipt time is supplied with `--collected-at`. A fetch records `network_response_received`. `imported_at` is normalization time, not a substitute for either source publication or market observation time.

The current public snapshot reports **zero open Rose/Hal positions** and 57 rows in its closed/all section. Closed/all includes expired and invalidated rows. Reported P&L must not become verified settlement proceeds or a fund NAV return. CSV exports original reported cells rather than recalculating them into new financial facts.

## Paper review write

Send JSON with these fields:

```json
{
  "client_request_id": "unique-client-request-id",
  "trade_id": "an-id-from-an-imported-evidence-row",
  "status": "needs-review",
  "note": "Check the reported exit timestamp and mark before grading this outcome.",
  "snapshot_id": "snapshot-id-that-was-inspected"
}
```

The four required keys are `client_request_id`, `trade_id`, `status`, and `note`. `snapshot_id` is the only optional field and is recommended to bind a review to the data inspected. Allowed status values are `reviewed`, `needs-review`, and `hold`. `client_request_id` accepts 8–128 letters, numbers, or `._:~-` characters; notes are limited to 4,000 characters; the bounded request body is limited to 32,768 bytes. `trade_id` must identify a row in the current imported tables, including Chart, Events and Sources, or the closed trades, watches and open positions. Unsupported status, unknown row ID or invalid fields return 422.

The server stores append-only records in `data/reviews.sqlite3`, independently of the imported snapshot. A newly accepted review returns 201 with `{review, revision, idempotent:false}`. Retrying the same request ID and identical payload returns 200 with `idempotent:true`; reusing an ID for a different payload returns 409 `request_id_conflict`. Review objects contain `id`, `client_request_id`, `trade_id`, `status`, `note`, `created_at`, and server-derived `snapshot_revision` and `snapshot_id`. A review is an annotation. It cannot open, close, edit, approve, or execute a financial position.

For a new review, a supplied `snapshot_id` unequal to the current import returns 409 `snapshot_changed` and writes no note. Reload the snapshot, inspect the row again, and use a new request ID for the revised request. Identical retries of an already completed write are checked first and return the original review even if the current snapshot changed; its recorded context is preserved.

`GET /api/reviews?cursor=0&limit=500` returns `{reviews, latest_by_trade, revision, next_cursor}`. Cursor is a nonnegative review ID; limit defaults to 500 and accepts 1–1,000. This permits reading the journal and each row's latest annotation separately.

POST requests require `Content-Type: application/json`, a bounded `Content-Length`, and an `Origin` exactly matching the local host/port. Cross-origin mutation returns 403; CORS preflight is not enabled. The server only permits loopback listening addresses. It is not an authenticated multiuser application; remote deployment requires a separate access-control and storage design.

## Manual public-source sync

`POST /api/sync` with `{}` invokes `scripts/import_snapshot.py --fetch` once. A lock prevents overlapping sync work; the operation has a 90-second timeout. The fetch allowlist contains the seven published HTML pages and `peanut-news.json`. The importer stages the complete collection/import before replacing the usable snapshot. Failure must retain the earlier valid snapshot; inspect the sync result and `/api/health` rather than assuming success from a button click.

Sync is user-triggered public-publication collection. There is no scheduled local vendor collector, API credential use, hidden production cache fetch, or brokerage refresh. A newly collected old page still contains old marks. Changing publication content can trigger SSE, but no changed publication means no new financial observation. An overlapping sync returns 409 `sync_in_progress`; missing importer returns 503; import failure returns 502; the 90-second timeout returns 504. Success returns `{ok, snapshot_id, imported_at, revision, output}`. A current import can have a new local server revision without new market observation dates.

```sh
curl -X POST http://127.0.0.1:8768/api/sync \
  -H 'Origin: http://127.0.0.1:8768' \
  -H 'Content-Type: application/json' \
  --data '{}'
```

## SSE

`GET /api/events` uses named `snapshot` and `reviews` events. The server checks local disk/review changes at approximately two-second intervals. It advertises a two-second reconnect delay and emits comment heartbeats approximately every 15 seconds. Event IDs are durable SQLite journal IDs. `Last-Event-ID` or a `cursor` query requests replay of later events; without either, the stream begins at the current journal head. A cursor beyond the journal head returns 400.

Snapshot payloads contain `revision`, `snapshot_id`, `imported_at`, and `etag`; review payloads contain `revision`, `review_id`, and `trade_id`. These events do not constitute a quote stream or bot push receiver. Clients should reload the latest snapshot/reviews after notifications; the durable API remains the source of truth.

```sh
curl -N http://127.0.0.1:8768/api/events
```

## Run and inspect

From `/Users/jb/Documents/Codex/oid-trading-desk`:

```sh
python3 scripts/import_snapshot.py
python3 server.py
```

The first command uses existing local raw files. To collect a fresh public publication explicitly:

```sh
python3 scripts/import_snapshot.py --fetch
```

Read endpoints can be inspected with:

```sh
curl http://127.0.0.1:8768/api/health
curl http://127.0.0.1:8768/api/snapshot
curl http://127.0.0.1:8768/api/export/trades.csv
curl http://127.0.0.1:8768/api/prompt/macro
```

Run the project checks with:

```sh
python3 -m unittest discover -s tests
```

Passing parser/server checks confirms tested local behavior; it does not verify all external claims, deploy vendor feeds, establish option forecasts, or publish this project to the original hosted site.

Errors return a JSON object `{error, message}`. A missing/invalid snapshot returns 503 from `/api/snapshot`; `/api/health` reports the server separately from snapshot availability. Its `ok:true` and current `server_time` do not establish a current financial-data feed. Unknown API paths return 404; unsupported mutations return 405. Read endpoints also support HEAD.
