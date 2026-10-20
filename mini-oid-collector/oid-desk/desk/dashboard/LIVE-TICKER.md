# OID Live Book · Ticker refresh

**Site:** https://swift-dune-cs3e.here.now/ (bold-tulip frozen)  
**Mandate:** Research / paper only · Zero live execution  
**Updated:** 2026-09-19

## What “live” means

here.now is **static hosting**. Live = two layers:

1. **Browser** — `index.html` meta-refresh + JS reload every **60s** (shows latest published snapshot).
2. **Server-side (OID)** — pull Robinhood option marks → update `paper-trades/trades.json` → rebuild HTML → `publish.sh`.


## Production SPA auto-refresh (2026-10-07)

- Static host has **no** EventSource. Packaged `app.js` now **re-fetches** `data/snapshot.json` every **60s** (cache-busted query) while the tab is visible, and **Refresh snapshot** reloads on demand.
- CDN still advertises `max-age=3600` on JSON unless `_headers` is honored — cache-bust + `cache: no-store` mitigate browser/edge stickiness.
- Desk agents still must **publish** after `live_refresh.py` for marks to move; the SPA only shows the latest published snapshot.

## Cost basis & P&L (match scorecard)

- Cost basis: `entryAsk` (fallback `entryMark` / `entryBid`) via `outcome_helper.entry_ref`
- `%` = `(mark − entry) / entry × 100`
- `$` = `(mark − entry) × qtySuggested × 100`
- Marks update also refreshes MFE/MAE peak/trough via `apply_mark_update`

## Scripts

| Script | Role |
|--------|------|
| `dashboard/refresh_marks.py` | `--list-ids` or apply quotes from `--quotes-file` / `--quotes-stdin` |
| `dashboard/live_refresh.py` | Orchestrate apply → scorecard → rebuild → optional `--publish` |
| `dashboard/rebuild.py` | Dark ticker UI → `index.html` |
| `dashboard/publish.sh` | Publish slug `bold-tulip-nejq` |


## Session awareness (2026-09-19)

- Header + per open-row Ticker cell show **RTH | PRE | AH | CLOSED** (America/New_York; weekends/holidays CLOSED).
- Day% chip on Rose / Hal / Leopold underlyings: `(last or last_non_reg) vs adjusted_previous_close` from RH `get_equity_quotes`.
- When **CLOSED**: day% = last RTH close vs prior close; hover **"last RTH session"**.
- Fields on tickets: `lastUnderlying`, `underlyingPrevClose`, `underlyingDayPct`, `underlyingSession`, `lastNonRegUnderlying` (PRE/AH).
- Refresh: `live_refresh.py --emit-symbols` → MCP `get_equity_quotes` → `--equity-quotes-file …` (soft/paper only).

## Data sources tab

- Nav: **Blotter | Data sources** → `data-sources.html`.
- Catalog + TTLs: see `dashboard/DATA-SOURCES.md` (QUERY-DEDUP · HAL-CADENCE-V1 · HAL-X-ALLOWLIST).
- Status from `market-data/latest/*.json` (+ soft stamps). Weekend → most feeds STALE/NEVER is expected.

## Agent / executor flow (RTH)

```bash
# 1) List open instrument UUIDs
python3 /workspace/options-intelligence-desk/dashboard/refresh_marks.py --list-ids

# 2) MCP: user-robinhood-trading → get_option_quotes
#    args: { "instrument_ids": [ ... ] }   # quotes only — NEVER place orders
#    Save raw JSON to e.g. /workspace/options-intelligence-desk/tmp/oid-live-quotes.json

# 3) Apply + rebuild + publish
python3 /workspace/options-intelligence-desk/dashboard/live_refresh.py \
  --quotes-file /workspace/options-intelligence-desk/tmp/oid-live-quotes.json \
  --publish
```

Optional: also refresh underlyings with `get_equity_quotes` and set `lastUnderlying` / `underlyingNow` on open tickets (ticker column).

## Piggyback automations (primary keep-alive)

Do **not** rely on a fragile standalone routine API. After elevate / invalidate / close, or on walls-pulse notify when open seats exist, run the live refresh flow above.

Patched prompts:

- `automations/oid-5-min-qualifier/automation.json`
- `automations/oid-walls-pulse/automation.json`

Draft optional every-5-min RTH routine (disabled):  
`scripts/automation-prompts/oid-dashboard-live-refresh.md`  
`automations/oid-dashboard-live-refresh/automation.json` (enabled: false)

## Stale warning

Ticker shows a **stale** badge when `quoteDelayed` is true or `lastQuotedAt` is **> 2 minutes** old. Republish after a marks refresh to clear.

## Disclaimer

Research / paper tracking only. Zero Robinhood order placement from OID.

## Leopold / ZH watches

- Stored in `paper-trades/trades.json` → top-level `leopoldWatches` (status `leopold_watch`).
- **Do not** count toward `maxOpenTickets` / open seats n/8.
- Reference cost = Leopold bot print (`entryAsk` / `entryMark`) — labeled watch reference, **not** a paper fill.
- `refresh_marks.py --list-ids` includes Leopold `instrumentId`s; `apply_quotes` updates watches alongside open seats.
- Dashboard renders a distinct **Leopold / ZH watch** section; Agent column shows `Leopold`.

## Blotter columns (required — do not drop)

- **Agent** — Rose | Hal on paper seats; Leopold on ZH watches (`agent_label`).
- **MFE · time / MAE · time** — peak/trough % vs entry (tooltip has $); compact peak/trough PT stamp under the %. Shown on open seats, closed, and Leopold watches.

## Close triggers (soft alerts · V1)

- Spec: `/workspace/options-intelligence-desk/CLOSE-TRIGGERS-V1.md`
- Helper: `paper-trades/close_triggers.py` → `tmp/close-triggers-last.json`
- Hooked after marks in `dashboard/live_refresh.py` (before scorecard/rebuild)
- Live Book panel **Close triggers** on https://bold-tulip-nejq.here.now/ — per-seat Armed / Giveback / DTE≤1 / Thesis OK
- Alerts only: `INVALIDATE` (hard) · `CLOSE_TRIGGER_REVIEW` · `FORCE_REVIEW` — **never** auto-close or place RH orders
- MFE/exit starter: `journals/MFE-EXIT-DISTRIBUTION.md`
- Automations `oid-5-min-qualifier` + `oid-close-carry-pass`: after marks, run close-trigger check; WakeParent on review alerts (soft/hard list only)


## Market overview strip (2026-09-19)

- Top of Blotter: SPY · QQQ · DIA + Fidelity desert-island 3 proxies (RSP−SPY, FRED HY/IG OAS, VTV/VUG).
- Script: `dashboard/refresh_market_tape.py` · hooked from `live_refresh.py` when `--equity-quotes-file` present.
- Docs: `dashboard/MARKET-TAPE.md`. Soft/paper only.

## Shay · 2027 PE equity watch

- Store: `paper-trades/shay-semi-watch.json` (pointer `shayWatchesPath` on ledger).
- **Does not** consume open seats.
- Baseline = Fri RTH close before the weekend post (`baselineDate` / `baselinePrice` per symbol; SPY baseline for relative).
- On each marks / market-tape equity refresh: RH `get_equity_quotes` for all Shay symbols (+ SPY).
- Metrics: `last`, `dayPct`, `sincePostPct` = (last−baseline)/baseline, `vsSpySincePost`, session badge CLOSED/PRE/AH/RTH.
- Dashboard section **Shay · 2027 PE watch** below Leopold.
- Soft / paper only — zero RH orders.

## AH coverage gap (2026-09-22)

- `market_session.py` is correct: PRE 04:00–09:30 ET · RTH 09:30–16:00 · **AH 16:00–20:00 ET** · else CLOSED.
- Draft routine `oid-dashboard-live-refresh` was RTH-only (`*/5 6-12` PT = 09:00–15:55 ET). Extended draft schedule to `*/5 6-16` PT so AH 16:00–19:55 ET is covered — **still `enabled: false`**; piggyback Q5 + walls-pulse remain primary.
- After 20:00 ET the badge is **CLOSED**; RH may still return `last_non_reg` overnight — shown as `last AH` under CLOSED, not as live AFTER-HOURS.

## Peanut news marquee (2026-09-30 · updated 2026-10-05)

- Fixed bottom scroller on Blotter (`index.html`): ticker · ±1–5 score · gist · time · link.
- Store: `paper-trades/peanut-news.json` (copied to `dashboard/peanut-news.json` on rebuild). Full history kept; nothing deleted for the banner filter.
- **Banner filter:** only alerts with `asOfIso` **after** the prior completed RTH close (`market_session.prior_rth_close` — normally previous weekday 1:00 PM PT / 4:00 PM ET; early closes honored). On Monday morning that is Friday's close. Older alerts remain in the store and on **News Archive**.
- Marquee animation: `85s` linear loop (was `55s`; ~55% slower for readability). Hover still pauses.
- Helper: `dashboard/peanut_news.py` (`--ticker --score --gist [--link] [--id] [--read-through …]` · `--split` · `--render` then rebuild + `publish.sh`).
- Nav tab **News Archive** → `news-archive.html` (timestamps, tickers, scores, gists, links, banner vs archive badge).
- Owner: Peanut (News Alerts). Soft/research only — never elevates seats; never RH orders.
- Browser alert tone: click the Peanut banner Sound toggle to enable/disable the short Web Audio chime; preference and seen alert IDs persist locally.
