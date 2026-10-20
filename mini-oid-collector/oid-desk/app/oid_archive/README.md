# oid_archive 0.1.0 (schema v1)

Mini-side archive for volume-news-score Phases 1–2. Source of truth: `research-bot/designs/volume-news-score/SCHEMAS.md`.

Layout: `~/oid-data/archive/<table>/date=YYYY-MM-DD/part-<writer>-<seq>.jsonl` (live JSONL), `~/oid-data/archive/parquet/<table>/date=D/<table>-D-<pass>.parquet`
(+ `_manifest.json`). Tables: `volume_5s`, `bars_1m` (volume of record), `bars_5m/15m/1h` (derived from 1m, session-bounded, 1h anchored 9:30 ET), `bars_1d`
(Alpaca raw + `split_factor`), `surges`, `fetch_log`.

Writers: collector (`oid_quote/volume5s.py`: volume_5s + live bars_1m), trigger engine (`oid_surges.py`: surges), this package (compaction/backfill).
All writers are inert unless `~/oid-data` exists.

Modules / CLIs (run with `PYTHONPATH=$HOME/oid-desk/app $HOME/oid-desk/venv/bin/python -m …`):
- `oid_archive.compact --pass main|post [--date D] [--no-rest]`: launchd 2:00 PM / 5:15 PM PT Mon–Fri.
- `oid_archive.backfill --depth-test SYM | --full [--symbols …] [--force] [--max-per-min N]`: resumable via `state/backfill-status.json`.
- `oid_archive.integrity [--delete]`: launchd Sat 10:00 AM PT; deletes JSONL > 90 days only when Parquet covers it.
- `oid_archive.api_routes`: `/v1/archive/{tables,schema,rows,bars}` on the data-api (:8788), bearer = `~/oid-data/secrets/OID_ARCHIVE_READ_TOKEN`
  (503 until Jeffrey runs `~/oid-desk/bin/enter-keys.sh --archive --generate-read-token`).

Data quality (flag, never rewrite): `~/oid-data/archive/quality/exclusions.json`
(`{"schema_version":"v1","updated_iso":…,"exclusions":[{id, symbol, tables, before, [after], reason, added_iso, added_by, schema_version}]}`).
A row matches when the symbol and table match and its ET date is before `before` (exclusive) and on/after `after` if set.
- `GET /v1/archive/quality[?table=&symbol=&date=]` lists exclusions. `/v1/archive/tables` reports the exclusion count.
- `/v1/archive/bars` always returns the matching exclusions in `quality`. Rows are dropped only with `apply_exclusions=1`, on both `/bars` and `/rows`.
- Parquet/JSONL readers (duckdb etc.) should anti-join against this file themselves.
- CLI: `python -m oid_archive.quality --list` and `--add SYM --before D [--after D] [--tables bars_1m,bars_5m,bars_15m,bars_1h] --reason TEXT`.
- Current entry: `SPCX-pre-20260612`: SPCX bars_1m/5m/15m/1h before 2026-06-12 (ticker likely reused; daily bars start 2026-06-12).

Tests: `python -m pytest -q tests` (box venv `/workspace/venvs/oid-archive`). Deploy: `docs/VNS-DEPLOY-RUNBOOK-20261018.md`.
