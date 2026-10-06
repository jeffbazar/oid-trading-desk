# QUERY DEDUP — shared vendor cache policy (OID)

**V0 — 2026-09-17.** Research only; zero execution.  
Store: `/workspace/options-intelligence-desk/market-data/`  
Helpers: `cache_io.py` · schema: `schema/v0.md` · layout: `README.md`

## Goal

Every OID automation **reads shared cache first**, pulls FlashAlpha / Unusual Whales / Robinhood **only if stale or missing**, then **writes** results back. Stop parallel desks and overlapping OID routines from re-hitting the same endpoints within TTL.

## Critical rule (elevate / liquidity)

**Liquidity / PAPER_CANDIDATE quote-age ≤120s** still requires a **live** RH option + equity quote at elevate / invalidate time.

- Do **not** serve elevate gates from cache.
- Cache is OK for: walls tables, soft color (UW/FA exposure/OE/net-prem/Form-4/RVOL), Hal/OT2 sharing, non-gate scans, dashboard marks.
- `rh-quotes` cache (TTL 120s) may color scans; **elevate still re-pulls live RH**.

## RH quotes ownership (resolved 2026-10-05)

Jeffrey confirmed **Rose** owns shared `market-data/latest/rh-quotes.json` (sole writer; TTL 120s; path via `dashboard/refresh_marks.py` / live refresh). **Hal** reads + Soft A annotate at `:05/:35` ET. Elevate / invalidate still re-pulls **live RH ≤120s**. Do not change Hal automation schedules as part of this ownership note.

### Duplicates #2 — support-map / market-tape piggyback (closed 2026-10-05)

`dashboard/refresh_support_map.py` and `dashboard/refresh_market_tape.py` **must** call `cache_io.piggyback_rh_quotes(symbols)` (or `read_fresh("rh-quotes")` + payload extract) before any Robinhood `get_equity_quotes` for overlapping names.

| Builder | Behavior |
|---------|----------|
| `refresh_market_tape.py` | Default: reuse fresh cache for SPY·QQQ·DIA·RSP·VTV·VUG; `--equity-quotes-file` only for misses; `--check-piggyback` smoke. **Never writes** `rh-quotes`. |
| `refresh_support_map.py` | Default: reuse fresh cache for primary+extended support book; file fills misses; `--dry-run` / `--check-piggyback`. **Never writes** `rh-quotes`. |
| Rose on miss | `get_equity_quotes` for **missing only** → `refresh_marks.py --equity-quotes-file …` (sole writer) → re-run builder. |
| Hal | Reader only — no `rh-quotes` write. |


## Record shape

`latest/{feed}.json`:

```
as_of, as_of_pt, source, writer, feed, symbols, ttl_seconds, payload, error
```

- Missing file, expired age, or non-null `error` → treat as miss (`read_fresh` → `None`).
- On vendor failure: write with `error` set (e.g. `UW_DATA_INSUFFICIENT`); never present error records as fresh.

## Default TTLs (RTH unless noted)

| feed | TTL (s) | notes |
|------|--------:|-------|
| `fa-levels` | 600 | 10 min RTH; walls + flow levels |
| `fa-flow-levels` | 600 | alias / sibling of fa-levels when stored separately |
| `fa-soft` | 1800 | exposure_summary / DEX/VEX/CHEX etc. |
| `uw-flow-alerts` | 900 | near-wall soft catalyst |
| `uw-net-prem` | 900 | flow_per_strike + market_tide |
| `uw-oe` | 1800 | dark pool / off-exchange |
| `uw-form4` | 21600 | 6h; forced refresh premarket + midday owners |
| `rh-quotes` | 120 | scan color only; elevate needs live |
| `rh-rvol` | 1800 | session RVOL soft |
| `rh-option-marks` | 300 | open paper dashboard OK; elevate/invalidate need live |
| `paper-open` | 0 | write on change (not TTL-gated the same way) |
| `market-tape` | 300 | SPY·QQQ·DIA + helpers; piggybacks fresh `rh-quotes` (Duplicates #2); live_refresh |
| `fidelity-three` | 1800 | median-growth / credit / valuation proxies |
| `fred-hy-oas` / `fred-ig-oas` | 86400 | FRED public CSV siblings |

| `chart-daily` / `chart-daily-observations` | none (session) | Chart Bot sole post-close daily historicals; weekday 2:24 PM PT |
| `supply-chain-identity` | none | C&S identity snapshot; empty edges ≠ STALE; softOnly |
| `macro-morning` | 86400 | Macro weekday ~5:45 AM PT pack |
| `peanut-news` | none (alert stamp) | Peanut; quiet scans do not rewrite |
| `desk-catalysts` | 21600 | Hal soft calendar owner |
| `hal-x-scan` | 7200 | Hal 2h X scan |
| `hal-rh-watch` / `hal-rh-watch-pulse` | 120 | Hal :05/:35 Soft A annotate; **reads Rose `rh-quotes`** (resolved 2026-10-05) |
| `hal-intraday-marks` / `hal-marks` | 900 | Hal held marks every 15 min RTH |

Encoded as `DEFAULT_TTLS` in `cache_io.py`.

## Read-before-pull (all writers)

1. `rec = read_fresh(feed)` (or CLI `python3 cache_io.py get <feed>`).
2. If `rec` is not `None` → use `rec["payload"]`; **skip** vendor call for that feed.
3. If miss → only pull if this routine is an **allowed owner** for that feed (matrix below) under its trigger conditions.
4. After successful pull → `write_feed(feed, source=..., writer=..., symbols=..., payload=..., ttl_seconds=...)`.
5. After failed pull → optional `write_feed(..., payload={}, error="...")` so peers see the miss without stampeding.

Path for helpers (from workspace):

```bash
python3 /workspace/options-intelligence-desk/market-data/cache_io.py get fa-levels
python3 /workspace/options-intelligence-desk/market-data/cache_io.py age fa-levels
```

In-process: `from cache_io import read_fresh, write_feed` (cwd or sys.path includes `market-data/`).

## Owner matrix (who may pull on cache miss)

| feed | Primary writer | May pull on miss when… | Must not |
|------|----------------|------------------------|----------|
| `fa-levels` / `fa-flow-levels` | **walls-pulse** | walls-pulse: always refresh if miss/stale. **Q5**: only if miss **AND** (`:00/:15/:30/:45` **OR** near-wall **OR** ≥1% move). **opening / first-hour**: once if miss. **NVDA-driver**: read cache first; NVDA-only pull if miss. Afternoon/close: once if miss when walls table required. | Random re-pull within TTL; Hal |
| `fa-soft` | walls-pulse / Q5 / opening / FH when soft context needed | Same cadence as levels when miss; prefer piggyback after levels write | Hal |
| `uw-flow-alerts` | Q5 / opening / FH / walls-on-notify | Near-wall or soft-catalyst path **and** miss | Blanket every tick; Hal |
| `uw-net-prem` / market-tide | Q5 / opening / FH / walls-on-notify / afternoon wrap | Near-wall or session wrap **and** miss | Hal |
| `uw-oe` | walls-on-notify / Q5 near-wall | Near-wall notify **and** miss | Hal |
| `uw-form4` | **premarket** (universe sweep); **afternoon-validation** (midday refresh) | Premarket/afternoon owners; Q5/opening/FH **on-elevate / near-wall ticker only** if miss | Walls-pulse Form-4; Hal |
| `rh-rvol` | near-wall writers (walls notify, Q5, opening, FH) | Near-wall **and** miss | Elevate-from-cache; Hal as writer |
| `rh-quotes` | **Rose** (sole writer; live book pulse / `refresh_marks.py` / `live_refresh.py`) | Scan color if miss; **elevate always live**. support-map + market-tape **piggyback** when fresh (Duplicates #2) | Serving PAPER_CANDIDATE gate from cache; Hal / support-map / market-tape as second quote writer |
| `rh-option-marks` | dashboard / scorecard refresh | Dashboard TTL OK; elevate/invalidate **live** | Elevate marks from cache alone |
| `chart-daily` / `chart-daily-observations` | **Chart Bot** (`chart-daily-refresh`) | Weekdays 2:24 PM PT after cash close; sole `get_equity_historicals` daily pull | Anyone else re-pulling daily historicals; FA/UW/X; live quote pulse |
| `supply-chain-identity` | **Customer/Supplier Bot** | On-demand identity seed only | Inventing edges; second EDGAR/news/X/FA/UW; Benzinga/FactSet |
| `macro-morning` / `macro-econ-calendar` / `macro-x-tech` | **Macro Bot** | Morning pack ~5:45/5:50 AM PT; hourly X clear deltas 9:10–3:10 ET | FA/UW/RH quote calls |
| `peanut-news` | **Peanut** | Weekdays 5:30 AM PT + every 5 min 6:11 AM–1:56 PM PT on move-worthy alert | FA/UW/RH quotes; rewriting on quiet scans; double-counting X Summarizer lane |
| `desk-catalysts` | **Hal** | Soft calendar refresh / restamp; never elevates alone | Rose/others re-calling FA/RH earnings calendars when file fresh |
| `hal-x-scan` / `x-spend` | **Hal** | Every 2h, 11 accounts | Parallel same-handle searches in same window without reading peer files |
| `hal-rh-watch` / `hal-rh-watch-pulse` | **Hal** (Soft A annotate; **reads** Rose `rh-quotes`) | :05/:35 ET Tech∪chip; resolved 2026-10-05 | Re-quoting as parallel writer when `rh-quotes` fresh |
| `hal-intraday-marks` / `hal-marks` | **Hal** | Held seats every 15 min RTH; flat = idle | Elevate from marks cache alone |
| (all feeds) | — | **Hal / OT2: read only** | Hal must not re-pull FA/UW if `latest/` fresh |

## Per-routine summary

| Routine | Role |
|---------|------|
| `oid-walls-pulse` | Primary `fa-levels` writer; UW/RH soft on notify if miss |
| `oid-5-min-qualifier` | FA refresh only if miss + (:00/:15/:30/:45 \| near-wall \| ≥1% move); UW/RH near-wall if miss |
| `oid-opening-intelligence` / `oid-first-hour-pass` | FA once if miss; UW Form-4 on-elevate only; soft UW/RH if miss |
| `oid-afternoon-validation` | FA walls if miss; Form-4 midday forced refresh; net-prem wrap if miss |
| `oid-premarket-edgar-ping` | Form-4 universe owner (forced AM refresh) |
| `oid-close-carry-pass` | Prefer cache; pull only if walls/handoff miss |
| `oid-nvda-driver-watch` | Cache-first; NVDA-only FA if miss |
| `oid-x-core8-pulse` | X only — out of scope for FA/UW/RH cache |
| Hal / OT2 | **Read only** |

## Do not

- Change cron schedules as part of dedup work.
- Invent vendor payloads when cache miss + pull fails.
- Treat error-marked records as fresh.
- Bypass live RH quotes for PAPER_CANDIDATE / liquidity / invalidate.

## UW shared-cache stamp (added 2026-09-25 — Hal stale-page fix)

`uw-net-prem` and `uw-flow-alerts` are **shared** feeds Hal pages on. If FH / OPEN / Q5 / walls-pulse pulls UW (`get_market_tide`, `get_flow_per_strike`, `get_flow_alerts`) for near-wall or elevate color, that routine **must** `write_feed` both files it touched (at least `uw-net-prem` when tide/net-prem is used; `uw-flow-alerts` when alerts are pulled) via `market-data/cache_io.py` with a fresh `as_of`. Do **not** leave Thu/prior-session stamps while citing live UW in a journal. Soft/paper only — never RH execution.
