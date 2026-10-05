# Live bridge: how this project archives production data for backtesting

Status 2026-10-04 (PT): **documented bridge, no scheduled job.** Nothing in this project writes to the live desk, calls a vendor, or publishes to here.now. Research/paper only.

## Two inputs, kept separate

| Input | Location | What it is | Rights |
| --- | --- | --- | --- |
| A. Public publication | the eight here.now resources below | What the desk published (HTML + Peanut JSON) | Public pages. OK to archive locally |
| B. Live shared cache | `/workspace/options-intelligence-desk/market-data/latest/*.json` | One overwrite-in-place JSON per feed (`as_of, as_of_pt, source, writer, feed, symbols, ttl_seconds, payload, error`). Written only by the feed owners (see `docs/QUERY-ARCHITECTURE.md`) | Contains vendor payloads (Robinhood, FlashAlpha, Unusual Whales, X). **Box-local research use only. Do not redistribute, publish or commit to a public repo** |

### A. The eight public resources (implemented: `scripts/import_snapshot.py --fetch`)
1. https://bold-tulip-nejq.here.now/index.html (Blotter)
2. https://bold-tulip-nejq.here.now/data-sources.html
3. https://bold-tulip-nejq.here.now/catalysts.html (Events)
4. https://bold-tulip-nejq.here.now/trader-intel.html
5. https://bold-tulip-nejq.here.now/soft-grader.html
6. https://bold-tulip-nejq.here.now/map.html
7. https://bold-tulip-nejq.here.now/chart.html
8. https://bold-tulip-nejq.here.now/peanut-news.json

Each successful fetch stages all eight and then writes an immutable bundle `data/reference-snapshots/<sha256>/` with `manifest.json` (per-file sha256, `collected_at`, `collected_at_basis`). `data/raw/current.json` points to the current bundle. The shipped bundle `72b155a6…ca2a` was collected on Jeffrey's Mac (its manifest paths say `/Users/jb/...`). Those paths are historical provenance and are left unedited.

The site republishes often (the 9:46 PM PT 10/04 build already shows Chart as "Weekdays 2:24 PM PT"). Run `make sync` when you want a new bundle. It reads public pages only and never touches the live desk.

### B. Live cache → immutable bundles (proposed, not built)
Intended layout (read-only copy, never edits `latest/`):

```
/workspace/options-intelligence-desk/market-data/snapshots/YYYY-MM-DD/<HHMMSS>-<sha12>/
    <feed>.json ...        # byte copies of latest/*.json that changed since the previous bundle
    manifest.json          # file, sha256, feed, writer, as_of, as_of_pt, captured_at_pt, error
```

Rules for whoever implements it (Rose to approve):
- **Read-only** against `latest/`. Copy bytes; don't re-serialize. Skip `*.bak*` and `_tmp-*` files.
- **No vendor calls.** The archiver only copies what owners already wrote, so it adds zero quota.
- **Write once.** Never modify a bundle; corrections are new bundles. Keep `as_of` (observation) separate from `captured_at` (archive time).
- **Cadence:** piggyback after `live_refresh.py` finishes, or a weekday post-close sweep after Chart's ~2:24 PM PT write. **Not** a second publisher loop.
- Error records (`error` non-null) are archived as-is and are never treated as data.
- Licensed payloads stay on the box. Backtests may publish derived aggregates only, never raw vendor rows.

Manual one-off equivalent (not scheduled; run only when Rose wants a capture):

```sh
SRC=/workspace/options-intelligence-desk/market-data/latest
DST=/workspace/options-intelligence-desk/market-data/snapshots/$(date +%F)/$(date +%H%M%S)
mkdir -p "$DST" && find "$SRC" -maxdepth 1 -name '*.json' ! -name '_tmp-*' -exec cp -p {} "$DST"/ \; \
  && (cd "$DST" && sha256sum *.json > SHA256SUMS) && chmod -R a-w "$DST"
```

No symlink into `latest/` is placed in this project on purpose. It keeps licensed payloads out of `data/` (and out of any future GitHub repo) and keeps the importer's public-only allowlist intact.
