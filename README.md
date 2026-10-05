# OID Trading Desk

A separate local dashboard for Rose and Hal's paper trading desk, built from the actual published OID pages. It organizes the daily book, evidence, reported outcomes, bot operations and changes while keeping source provenance visible.

The imported October 4 publication reports **zero open positions**. Its page build is Oct 4, 5:26 PM PT; retained marks, macro judgment, chart bars and news have their own earlier clocks. This project provides snapshot imports and local application updates. Live brokerage feeds and collector deployment are unavailable here.

> **GitHub home:** https://github.com/jeffbazar/oid-trading-desk
>
> **Live blotter** remains https://bold-tulip-nejq.here.now/. **Local review server:** http://127.0.0.1:8768.
>
> This seed is docs, the review UI, and bot package stubs (`chart-bot/`, `hal/`, `macro/`, `peanut/`, `supply-chain/`). There is no live collector cutover. Live production stays on the separate box tree. Research/paper only. Zero brokerage orders.
>
> Read `docs/SETUP-VS-PRODUCTION.md`, `docs/API-INVENTORY.md`, `docs/QUERY-ARCHITECTURE.md`, `docs/HANDBOOK-ERRATA.md` and `data/live-bridge.md` before treating any feed as live.

## Start

Requires Python 3.10 or newer. The importer and server use the standard library; no API keys or package installation are needed for the public snapshot/local review workflow. From the repository root (originally `/Users/jb/Documents/Codex/oid-trading-desk`):

```sh
python3 scripts/import_snapshot.py
python3 server.py
```

Open [the local desk](http://127.0.0.1:8768). The importer reads the preserved `data/raw/` files and writes `data/snapshot.json`. The server defaults to loopback port 8768; `--port` selects another local port and `--host` only accepts loopback addresses.

For an explicit refresh of the eight allowlisted public resources:

```sh
python3 scripts/import_snapshot.py --fetch
```

The interface's manual sync uses the same public-source import path. It fetches static publication, not private collector caches or brokerage quotes. All eight resources are staged before the usable snapshot is replaced; preserve the earlier snapshot if refresh fails.

## Views

- **Daily Desk:** Reported book state, macro context and current evidence quality.
- **Evidence:** Existing production chart/MA observations, events, watches, news, claims and sources; search, ticker filters and provenance.
- **Trade journal:** Reported closed/invalidated/expired paper-ticket rows, review annotations and CSV export. Cumulative ticket debit is not account equity or fund NAV.
- **Bot Operations:** Actual production cadence and coverage alongside proposed five-role prompts and data-source recommendations.
- **Changes:** Reviewable before/after changes and production findings.

SQLite persists append-only local review notes. SSE notifies connected clients about changed local snapshots or reviews. Neither process executes trades, auto-closes positions, installs bot routines, or supplies new market quotes.

## Original sources

The importer preserves [Blotter](https://bold-tulip-nejq.here.now/index.html), [Data sources](https://bold-tulip-nejq.here.now/data-sources.html), [Events](https://bold-tulip-nejq.here.now/catalysts.html), [Trader intel](https://bold-tulip-nejq.here.now/trader-intel.html), [Soft Grader](https://bold-tulip-nejq.here.now/soft-grader.html), [Map](https://bold-tulip-nejq.here.now/map.html), [Chart](https://bold-tulip-nejq.here.now/chart.html), and [Peanut news JSON](https://bold-tulip-nejq.here.now/peanut-news.json). Internal JSON names mentioned by those pages are not treated as public endpoints.

Technical observations and an empty supplier identity map already exist in production. This project imports them rather than claiming to have collected new daily history or discovered relationships. News scores remain the source's judgment, and unvalidated forecasts remain unavailable.

## Files and checks

| Location | Purpose |
| --- | --- |
| `data/raw/` | Original public resources |
| `data/reference-snapshots/` | Complete immutable bundles with per-resource hashes and manifests |
| `data/snapshot.json` | Normalized imported evidence and provenance |
| `data/reviews.sqlite3` | Durable local review journal and API event revisions; preserve this database |
| `scripts/import_snapshot.py` | Local import / explicit public-source collection |
| `server.py` | Local API, review persistence, manual sync and SSE |
| `public/` | Dashboard interface |
| `prompts/` | Actual copied Rose, Hal, Macro, Chart and News operating prompts |
| `docs/source-registry.json` | Proposed source ownership, fields and cadence |
| `docs/record-field-catalog.json` | Proposed canonical-record field catalog |
| `docs/production-audit.md` | Evidence-backed production findings |
| `docs/CHANGES.md`, `docs/changes.json` | Human-readable and UI-readable change log |
| `docs/API.md` | Exact local endpoint contract and usage |

```sh
python3 -m unittest discover -s tests
```

## Verification

The combined importer/server suite passes **43 tests**. Desktop browser checks confirmed all five views render without errors, 37 actual chart symbol rows, ticker/topic filters, empty-result recovery, full record details and prompt reading. A reviewed note on the imported NVDA chart record was saved through the interface and persisted after reload with its source snapshot context. The reported Hal subset and both credit-spread rows retained their original figures.

All five views also passed checks at a narrow **325 CSS-pixel** viewport without document overflow or browser warnings/errors. Wide evidence tables scroll within their own containers, and the prompt dialog fits the viewport. Final layout checks also confirmed no document overflow at **390** and **1,280 CSS pixels**.

Manual public-source sync completed through the interface and archived a complete immutable bundle with actual network-receipt collection metadata. It retained the older source observation clocks. These checks verify this local import/review workflow; they do not activate live feeds or trader execution.

The service is a local review tool, not a secured multiuser deployment. Preserve data and SQLite review storage when restarting or upgrading. Deploying remotely, enabling paid feeds, distributing licensed raw data, or activating bot receiver schedules requires separate implementation. The original hosted site is unchanged by this local build.
