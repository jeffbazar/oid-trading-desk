# OID private live page (Mac mini)

Second-by-second volume heatmap + table for every streamed desk ticker, held option contract volume, live trades with
marks, and vol_surge events. Separate launchd job `com.oid.desk.livepage`; stdlib python3; read-only.

- Soft put/call lean badges (private page only): reads local `~/oid-desk/desk/market-data/latest/uw-net-prem.json` + `uw-flow-alerts.json` (+ optional tide) every ~45 s. Day C/P volume ratio + 15m net call−put lean chip on heatmap tiles for core-20+focus; flow lean strip under surges. Soft color only; cites Unusual Whales; **zero new UW API calls** (daemon stays ~240 s).
- Server: `livepage.py` polls `http://127.0.0.1:8787/v1/live-volume?events=20` every 1 s (token read in-process from
  `~/oid-quote/secrets/OID_QUOTE_TOKEN`, never sent to the browser), option marks (`/v1/options`) every 5 s for open live
  trades, `~/oid-desk/desk/paper-trades/trades.json` every 30 s, and 1-min bars from the collector's files
  (`cache/bars/store/<SYM>-1m.json` last session, `store/live/<SYM>-1m-<date>.jsonl` today). Pushes over SSE (`/stream`).
- Binds 127.0.0.1:8791 only. Tailnet access: `./serve.sh on` (tailscale serve, HTTPS 443, tailnet-only). Never Funnel.
- Stop: `./serve.sh off` (unpublish from tailnet) and/or `./install.sh --uninstall` (stop the job). Logs: `logs/livepage.log`.
- Routes: `/` page · `/stream` SSE · `/state.json` · `/healthz` · `/sectors.json` (sector groups, edit + reload) · `/guide/` Field Guide (static: `guide/index.html` + vendored marked/mermaid + `guide/docs/` built by `./build_guide.sh` from `docs/live-page`) · `POST /ingest/ladder` (ladder dry-run snapshots from the box;
  Bearer token `secrets/LADDER_PUSH_TOKEN` chmod 600; JSON only, <=64 KB, 1-20 whitelisted rows, 120/h; stored in `data/ladder.jsonl`).
- Ladder feed off: `rm secrets/LADDER_PUSH_TOKEN` (all pushes then get 401) or `LADDER_PUSH=0` on the box.

## Private address (do not publish)
- After Serve is enabled for the tailnet and `./serve.sh on` has run: **https://oid-mini.tail3d8d4d.ts.net/** (HTTPS, tailnet-only).
- Until then (and also afterwards): **http://100.106.118.33:8791/**. The mini's tailscaled runs in userspace mode, which forwards
  tailnet connections to the mini's loopback ports, so this is reachable from tailnet devices only (WireGuard-encrypted), never the internet.
- Open on phone/laptop: Tailscale app connected to the same tailnet, then open the address in Safari/Chrome (Add to Home Screen works).

## Sectors and 5m lean (2026-10-19)
- `sectors.json`: groups + order for the heatmap sections, table Group column and sector strip. Unlisted tickers → Other. No restart needed.
- 5m UW lean: Δ of UW day net (call−put premium) between the newest `uw-net-prem.json` snapshot and one 3–10 min older (closest to 5); ±$25K FLAT; `—` if >10 min stale or no prior snapshot. History persisted in `data/uw-net-hist.json` (12 snapshots).

## Direction score badge (2026-10-19)
- Tile badge −3…+3 next to the symbol = composite direction score from `com.oid.desk.score` (~/oid-score), read from `~/oid-data/score/latest.json` into `row.score`. Hover = components (c·q·w), timestamp, config_version. Dashed/faded = not a fresh live reading. Research/log only. Field Guide page 24.

## Stock chart (2026-10-20)
Click a core tile, a Table row or a Sector watch row (or the header **Chart** button) to open a chart panel: candles + volume,
raw direction score lane (core; light + full for Sector watch), C/P 15s / 1m lane, call wall / put wall / flip history.
Files: `chart.js`, `chart.css`, `chart_backend.py` (child process, oid-desk venv duckdb, nice 10, exits after 15 idle min),
`vendor/lightweight-charts.standalone.production.js` (TradingView Lightweight Charts 5.0.9, Apache-2.0, LICENSE alongside).
Endpoint: `/chart.json?sym=&iv=15s|1m|5m|15m|1h|1d&range=1D|1W|1M|3M|YTD|1Y&ext=0|1&since=`. Wall history recorder writes
`~/oid-data/walls-history/walls-YYYYMMDD.jsonl`. Field Guide page 30. Backups: `*.bak-20261020-chart`.

## X sentiment panel (2026-10-27, SHADOW, display only)
- Jeffrey green light 10/27 ~7:28 AM PT. Section `#xsent` above News. `GET /xsent.json` (`xsent_payload()` in livepage.py) is a
  read-only compact copy of `~/oid-data/sentiment/x/latest.json` + `status.json` + newest scorecard name (written by
  `com.oid.desk.x-sentiment`). Page polls it every 60 s (`loadXS()` / `renderXS()`); hide/show remembered (`localStorage.lvXsMin`).
- Row: ticker (red dot = hot tier, updated <30 min) · tone bar + net −1..+1 (green > +0.15, red < −0.15, grey neutral / no sample) ·
  chatter vs normal pace (red = spike: z ≥ 2 or ≥ 2×; amber ≥ 1.5×). Spikes first, then hot tier, then chatter ratio. Rows older than 60 min fade.
- Never read by the score, alerts or orders. Patch: `patches/patch_xsent_20261027.py`; backups `*.bak-20261027-xsent`.
