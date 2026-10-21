# OID: Data-First Proposal for Scaling a Discretionary Options Desk into Supervised Bots

## 1. Diagnosis

**What the edge is today.** The edge is Jeffrey, reading one screen: a volume surge he recognizes, a direction he commits to in seconds, and an exit at +10–20% on the option within the session. Nothing in either repo expresses that style. The paper desk is long-calls-only (54/57 rows, zero outright puts, median Rose hold 24 h; map-desk-ops §f.10), and its entry family is "wall-press," which the desk's own wall-magnet study (#6: 46.9% vs 44.9% by chance, 82,190 ticker-minutes) says carries no information. The one thing the 10/20 studies found that is robust across every positive cell is **1-min rvol ≥ 3×** (study #6: 15-min breakout odds 8.7% → 26.7% away from walls; #2: light ±3 + surge held 5 min 67.5%, n=40; #3: core ±2 + surge held 2 min 61.5%, n=26). That is the same thing Jeffrey's eye is keyed on. So the desk's edge is a surge-recognition skill plus a fast-exit discipline, and the live page has been built to show it, not to record it.

**Where it is fragile.**

1. *The edge is unrecorded.* Jeffrey's live fills are in no repo (map-desk-ops §f.10). No decision row is written at decision time; `DATA_GAP_REPORT.md` row J: "no structured rejected/no-trade candidate records." Every surge he passes on, every one he takes, and every exit timing is lost the moment it happens. This is the single largest data loss on the desk and it costs $0 to stop.
2. *The ledger cannot support a claim.* 57 paper tickets Sep 10–Oct 4: 43 closes were batch administrative events on eight timestamps; all 26 Hal closes were batch; Rose's top 3 are 89% of her net (map-desk-ops §c, §g). Entry = ask, exit = mark, zero fees or slippage. Profit factor 7.7 on that basis is not a number a bot can be sized on.
3. *The scores are near coin-flip and chase.* Every "all nonzero" hit rate is below 50% (34%, 38%, 38.8%, 41.8%, 47.6%); the score is right most often in DECEL (46.7%) and worst in ACCEL (31.3%) (#5), i.e., it saturates after the move. Removing the live C/P input *improves* ±2 (50.3% → 55.8%, #12). Holding the score 30 s–5 min helps (#2, #3). These are one- and two-day samples of correlated names with 15 s snapshots counted as independent n (map-research §e).
4. *History is still mostly overwritten.* As of 10/10 only three feeds were append-only (`FEEDS_CURRENT.md` line 47); by 10/20 the data mini has 1-min bars, 1,045 wall snapshots, a 15 s `score_features` table, nightly `score_labels` and 5 s score-change logs, but none of it is in git, hashed into a manifest, or reachable by the research mini (map-research §c "Reconciliation"). OPRA quotes, UW lean, FA walls for sector names, news first-seen, momentum state and surge alerts still exist as "latest" only. Family C (options history) is ABSENT, so no study can label the thing Jeffrey actually trades: a +10–20% move on the option.
5. *No clocks.* `latency_model_ref` is `OWNER_DECISION_REQUIRED` in every study; the collector `LagHistogram` is not persisted (R15). The LLM decision path on the box is seconds-to-minutes while the target horizon is seconds-to-hours.
6. *The research mini is sealed off from the data.* Users, budget, isolation checks all pass; `archive.sqlite` holds zero datasets; the host at 192.168.5.191 silently drops traffic from 192.168.5.199 (`RESEARCH_MINI_BUILD_LOG.md`).

**Bottom line.** The desk has a plausible edge (surge + fast exit), a page that displays its precursors, and no archive that can prove or reproduce it. Everything below is ordered by "what is lost per day it is not captured."

## 2. Scaling strategy

Four stages. Each stage adds authority only after a gate measured on data captured during the previous stage. The gates are on *Jeffrey's own recorded decisions*, not on the paper ledger.

| Stage | What runs | Gate to enter | Measured how |
|---|---|---|---|
| **0. Discretionary + capture** (start now) | Jeffrey trades as today. Every decision, pass, and exit is written as a structured row (§5 `decisions` table). Archive on. Exits get a shadow bracket computed from the 5 s stream. | None; this is the baseline. | Count of decision rows (target ≥ 300 across ≥ 20 sessions), % with an outcome label, latency histogram persisted. |
| **1. Assisted** | A deterministic Candidate Ranker puts ≤ 5 names in a "Now" lane with the three study-backed conditioners. Jeffrey clicks Call / Put / Pass. Bracket exits are *proposed* with one-click accept. | 20 sessions of Stage-0 data; Ranker's top-5 precision ≥ Jeffrey's own take-rate baseline on the same sessions, with a session-block bootstrap CI not including 0. | Nightly scorecard: Brier skill vs B0 (same-window up fraction per name) and vs B1 (QQQ 5-min), on the option-leg label. |
| **2. Supervised auto** | Bot places paper orders on Alpaca paper (Level 3 automatic in paper, UNVERIFIED-S) with synthesized brackets; Jeffrey has a 10 s veto window on entries, none on exits. | Over 20 sessions of Stage 1: shadow-policy net expectancy per eligible opportunity ≥ Jeffrey's matched expectancy after §18 fills (buy ask, sell bid, registered latency), top-3 contributor ≤ 40% of net, max 3 correlated seats. | Both tracks logged side by side on identical `snapshot_id`s. |
| **3. Autonomous sleeve** | One live sleeve: 1 contract, $5,000 debit, 3 seats, daily loss limit = 2 × median winning ticket, hard halt. Jeffrey trades his own book separately. | 20 live-paper sessions of Stage 2 with no kill-switch firings caused by bot logic; risk kernel audited. | Live fills vs paper fills slippage ≤ modeled. |

**What gets automated first and why.** (1) *Capture*, because it is lossless and free. (2) *Exits*, because the ledger shows exits are where discretion dominates (43/57 administrative closes) and because a bracket (+12% on bid vs entry ask, −8% stop, 20-min time stop, flat at 12:55 PT) is deterministic, latency-tolerant, and easy to shadow against Jeffrey's actual exit. (3) *Ranking*, because it removes scanning cost without taking authority. (4) *Entry*, last, because it is the only step whose error is unbounded.

## 3. Bot architecture

Split the desk into a **data plane** (deterministic, on the data mini), a **decision plane** (mixed, on the box), and an **execution plane** (deterministic, single writer, nowhere near an LLM).

**Data plane (data mini, owner: Data Ops Bot).**
- `collector` (exists, :8787): Alpaca SIP + OPRA streams. Gains an append sink (R2).
- `archiver` (R5): every feed that overwrites `latest/` is also appended as a dated row with `received_at`. One process, one spool, hourly partition close with `MANIFEST.json` (sha256, rows, min/max clocks).
- `feature-service`: computes the 15 s `score_features` row set from the archive, not from the live cache, and exposes one function `features(symbol, as_of)` used by both the live scorer and the research loop. This is the feature store; same code path, same numbers.
- `labeler` (nightly): forward returns, option-leg bracket counterfactuals, B0/B1 baselines, written to `labels/` keyed by `snapshot_id`.
- `latency-probe` (R15): persists `LagHistogram`, per-feed `received_at − source_observed_at`, subscription count vs the ~1,000 cap (desk figure, UNVERIFIED-3P).

**Decision plane (box).**
- `scorer` (deterministic): the current core/light/direction scores, versioned by config hash. No LLM.
- `ranker` (deterministic): rank = f(rvol bucket, held-score seconds, momentum state, wall distance %, spread %, sector rvol). Output: `candidates` rows.
- **Rose / Hal become proposers and narrators.** They read the ranker output, attach a rationale and catalyst context, and write a `candidate_id`-keyed proposal (R7). They never write orders. Chart, Macro, Peanut, X Summarizer stay producers of soft color, archived first-seen.
- **Risk kernel** (deterministic, library imported by the gateway): seats (3 for the bot sleeve), $5,000 debit, chase gate (day% ≥ 3%), earnings gate, quote-age gate (equity and option quote ≤ 120 s, from the stream not the cache), spread gate (ask−bid ≤ 8% of mid, else WATCH), daily loss halt, correlated-exposure cap (≤ 2 seats in one sector group), FA quota floor.

**Execution plane (data mini or a dedicated small host).**
- `execution-gateway`: the only process with broker credentials. Accepts a signed `order_intent` (candidate_id, contract, side, limit, bracket), re-checks the risk kernel, places the entry limit at ask (or mid+1 tick), then runs the bracket itself: Alpaca has no native bracket/OCO for options (UNVERIFIED-S), so the gateway polls the OPRA stream and submits the exit limit/stop-limit. Writes every state change to `orders` append-only.
- **Kill switches**, in order of authority: (1) a file `HALT` on the data mini, checked before every order; (2) daily loss halt; (3) stream-age halt (no OPRA quote for ≥ 30 s on an open contract → close at market, pause entries); (4) quota halt (FA < 200 calls remaining → walls go STALE, entries that require walls pause); (5) drift halt (today's realized hit rate on ≥ 20 decisions below the 10-session 5th percentile → pause). Each firing is a logged event with a reason code.

**Broker choice.** Paper now: Alpaca paper (data and execution in one account; Level 3 automatic in paper, UNVERIFIED-S). Live Stage 3: Alpaca if options GTC/day limit orders and multi-leg are confirmed on the live account; fallback Tradier ($10/mo flat Pro plan, native OTOCO with option legs, UNVERIFIED-S) which would give real brackets. **Do not plan on Robinhood**: the Agentic MCP was stocks-only at launch (UNVERIFIED-3P) and desk policy already prohibits orders there; keep it as a quote source only. IBKR is the long-run answer if the desk ever needs multi-account or futures, not now.

## 4. Models

**What to model.** Not "direction." Model the thing the exit rule pays on.

- **Primary label (option leg)**: for a decision at `t0` on the nearest 0.50Δ, 7–21 DTE call/put listed at `t0`: `hit_12 ∈ {0,1}` = bid reaches ≥ 1.12 × entry ask before (bid ≤ 0.92 × entry ask) or (t0 + 20 min) or 12:55 PT, whichever first; plus `ret_policy` = signed net return under that fixed bracket with the §18 fill rule and the registered latency. Variants at +10/+15/+20% and 10/30/60-min time stops are registered up front, not searched.
- **Secondary label (underlying, cheap)**: 5-min and 15-min excess return vs QQQ, used only while the option archive is shallow, published as `UNDERLYING_ONLY` per `program.md` §17.
- **Baselines**: B0 = same-session, same-window base rate per name; B1 = QQQ 5-min sign; B2 = "surge-only rule" (rvol ≥ 3× at day_high/day_low, nothing else). Any model must beat B2, because B2 is what Jeffrey's eye already does.

**Features (all from the feature store, `feature_computed_at ≤ decision_at`).** rvol 1-min bucket (<1.5, 1.5–3, ≥3, ≥5), surge age in seconds, score value and `held_seconds`, momentum state with hysteresis, distance to call/put wall in % (diagnostic only), option spread % and size, day% (chase gate input), minutes since open, sector-group rvol and % change, QQQ/SMH 5-min return, UW 5-m lean with age, news first-seen within 15 min (binary + tone), C/P 1-m **with coverage %**, DTE and IV of the candidate contract. Keep it under 30 features; the sample will be hundreds of events, not millions.

**Model classes, in order.** (1) Stratified hit-rate tables with Wilson intervals (this is what the Research tab already does; make it the registered B2/B3). (2) L2 logistic regression (already the campaign-1 model, `config.draft.json`). (3) `HistGradientBoostingClassifier` with max_depth 3, min_samples_leaf 50, monotone constraint on rvol. Nothing deeper until there are ≥ 2,000 labeled events. Calibration: isotonic on the held-out inner fold, reported as a reliability table by score bucket (the page already shows core +2.0 → 58.0%; it needs n and CI). Walk-forward by **session** with purge by `label_end_at` and session-block bootstrap (`program.md` §13–14). Effective n is sessions × independent surges, not 15 s snapshots.

**Promotion ladder (steps 5–8 of study #1, not built).** `candidate → shadow (≥10 sessions) → challenger (scored beside champion on identical snapshot_ids) → promoted` only when Brier skill vs champion ≥ 0.01 with a 90% session-block CI excluding 0 **and** net expectancy per eligible opportunity ≥ champion's after costs. Promotion writes a new config hash; the scorer loads only hashed configs; the page shows the hash. Demotion is automatic on the drift halt.

**LLMs.** Should: turn text into features (news tone with Jeffrey's thumbs corrections as training signal, catalyst extraction from EDGAR first-seen, X claim normalization); write the human-readable rationale attached to a candidate; draft study specs and post-mortems; review code. Should not: emit a number that enters a score, decide an entry, run the bracket, or touch the sealed holdout. Pin model versions and temperature 0 for any routine whose output is archived as a feature, and store the prompt hash with the row.

## 5. Data collection and archive

**Principle.** Every byte that reaches the data mini is appended once, immutably, with its own clocks, before anything derives from it. Overwrite files stay for the page; they are views, not records.

**Capture from today (ordered by daily loss if absent).**

| # | Dataset | Source | Row | Est. size/day | Why now |
|---|---|---|---|---|---|
| 1 | `decisions` | UI click / Rose / Hal | one per Call/Put/Pass/Watch/Exit (schema below) | KB | Jeffrey's edge; unrecoverable |
| 2 | `opra_quotes` (R2) | collector stream | conflated to 1 s on change: contract, bp, bs, ap, as, exch `t`, `received_at` | ~23 M rows, 0.4–0.9 GB Parquet at 1,000 subs | option-leg labels |
| 3 | `opra_trades` | collector stream | every print with aggressor class | ~50–150 MB | C/P input provenance |
| 4 | `score_features_15s` + `score_changes_5s` | scorer | exists; add config hash and `feature_computed_at` | ~50 MB | feature store |
| 5 | `bars_1m` (R6) | SIP | 209 names + SPY/QQQ/SMH/SOXX/IWM/DIA | 85 k rows, < 5 MB | rvol norms |
| 6 | `surge_alerts`, `momentum_events`, `focus_events` | detectors | every emit, with detector version | KB–MB | precision labels |
| 7 | `walls` (R5) | FA + Alpaca OI | every snapshot incl. STALE_CARRY, with `source_observed_at` | small | already 1,045; keep going |
| 8 | `uw_lean`, `uw_flow`, `uw_tide` | UW | every pull with age | small | diagnostic |
| 9 | `news_firstseen` | Alpaca/Benzinga, X, EDGAR | `first_seen_at`, source ts, tickers, finbert, LLM tone, Jeffrey correction | MB | text features |
| 10 | `chain_snapshots` (R1) | Alpaca `/v1beta1/options/snapshots` | every 5 min RTH, 65 core, 7–45 DTE, ±15% | ~1–2 M rows, ~100 MB | contract selection, IV/skew |
| 11 | `open_interest_daily`, `security_master`, `universe_versions` (R3, R12) | Alpaca | daily | small | walls at $0; membership history |
| 12 | `latency` (R15) | collector, routines | 1-min histograms; `decision_at → order_ready_at` per routine | small | `latency_model_ref` |
| 13 | `macro_packs`, `catalysts`, `x_scans` (R8) | bots | as published | small | forward-only |

Total ≈ 0.6–1.2 GB/day, ~150–300 GB/yr compressed; the research mini's 3.6 TB holds 5+ years. Sizes marked "est." are mine; R1's own doc says do a one-day dry count first.

**Layout and PIT discipline.**
```
/Users/oidarch/archive/<dataset>/date=YYYY-MM-DD/hour=HH/part-<n>.parquet
/Users/oidarch/archive/<dataset>/date=YYYY-MM-DD/MANIFEST.json  # sha256, rows, min/max source_observed_at, received_at, writer, schema_version
```
Rules: (1) three clocks on every row: `source_observed_at` (vendor), `received_at` (mini), `feature_computed_at` or `decision_at` where relevant; (2) `availability_basis` = `OBSERVED_DESK_REPLAY` for live capture, `RECONSTRUCTED_PROVIDER_REPLAY` for backfills, never mixed in one partition; (3) a closed hour is `chmod a-w` and never rewritten; corrections are new rows with `supersedes`; (4) STALE and error records are archived too (a wall carried on quota 0 is a fact about the desk); (5) no derived table is written without the config hash of the code that made it. Store Parquet, query with DuckDB (already in the venv); JSONL only for the spool.

**Decision schema (the one new table that matters).**
```
decisions(decision_id, decision_at, actor ∈ {jeffrey,rose,hal,ranker,shadow:<hash>},
  symbol, action ∈ {CALL,PUT,PASS,WATCH,EXIT}, snapshot_id (score_features_15s row),
  score_cfg_hash, rvol_1m, held_seconds, momentum_state, wall_dist_call_pct, wall_dist_put_pct,
  cp_1m, cp_coverage_pct, lean_5m, lean_age_s, news_tone_15m, lane,
  reason_codes[] ∈ {surge,wall,flow,news,sector,gut}, confidence 1..3,
  contract (occ symbol), quote_at_decision {bp,bs,ap,as,t}, planned_bracket {tp_pct,sl_pct,time_stop_s},
  override_flag, override_reason, ticket_id, exit_tag (required at EXIT), note)
```
Pass and Watch rows are the negatives the desk has never had.

**Labeling pipeline (nightly, data mini, deterministic).** For every `decisions` row and every `score_changes_5s` row: join `opra_quotes` for the contract; compute `hit_10/12/15/20`, `ret_policy` for each registered bracket, `mfe/mae` as true stream maxima (not sampled), underlying 5/15-min excess return, B0/B1 for the same window. Write `labels/date=…` keyed by `snapshot_id`; `label_available_at` = run time. Labels never enter the feature store.

**Topology.** Data mini is the single writer (it already is since mid-October). Spool as `jake`, mover as `oidarch` (`RESEARCH_SETUP_ON_MINI_PLAN.md` Phase R-C). The research mini pulls closed partitions nightly over a read-only route. The missing network path is the blocker: install Tailscale on the research mini (the data mini already serves on it) or fix the LAN ACL; either is a one-evening job for Jeffrey. Sealed holdout = all dates ≥ D (owner picks D at archive start), copied by root into `/Users/oideval/sealed/`; `oidresearch` sees only dates < D. The box pulls a mirror of non-sealed partitions nightly for the live scorer's norms (113 GB free observed).

## 6. Additional data sources

Ranked by (hypothesis value ÷ cost), with PIT quality.

1. **Own OPRA quote/trade archive (R2)** — $0, PIT exact, starts the option-leg label clock. Hypothesis: the +10–20% exit is reachable net of spread on surge entries. Buy nothing until this has 20 sessions.
2. **Alpaca chain snapshots + daily OI (R1/R3)** — $0 (~300 calls/day for OI walls, adopted in study #8), PIT good (5-min grain). Hypotheses: contract-selection rules (spread, size, DTE) change expectancy; own OI walls match FA walls (they disagree: NVDA 230 vs 220).
3. **Latency probes (R15)** — $0. Not a source, but without it no study is executable.
4. **SEC EDGAR full-text and `acceptanceDateTime` first-seen** — $0, PIT excellent if archived at first sight (UNVERIFIED-3P endpoints). Hypothesis: 8-K/Form 4 first-seen within 5 min of a surge explains the surge and predicts continuation vs fade.
5. **FINRA short interest API + UW borrow** — $0 (already S5), PIT by publication date. Hypothesis: surge-to-upside continuation is stronger in high-SI names.
6. **Kalshi candlesticks for CPI/FOMC/NFP** — $0 (UNVERIFIED-3P). Hypothesis: pre-print odds drift conditions the first-15-minute reaction (S2 family D).
7. **FRED/ALFRED vintages, intraday macro ETF proxies (R9/R10)** — $0. Unblocks S2 arm C.
8. **Korea 10/20-day exports (data.go.kr)** — $0, ~36 events/yr. Hypothesis: semis gap direction next session; campaign 2.
9. **Databento OPRA, targeted historical pulls** — pay-as-you-go `cbbo-1m` ~$2/GB (UNVERIFIED-S), only around registered setup days once S3 is funded; `metadata.get_cost` first. Hypothesis: S3 duration/pricing filters on 2024–2026.
10. **ThetaData Standard ($80/mo, UNVERIFIED-S)** — the cheapest history-with-quotes if backtests need more than forward capture; defer until the archive shows the surge setups exist in the right number.

**Do not buy:** FlashAlpha Alpha ($1,499/mo) — the desk's own study says walls are not a signal, and the replay it sells is of a non-signal; Massive options (non-pro licensing is a trap for a desk that wants to automate); DRAMeXchange, Silicon Data Pro, Estimize, ORTEX — campaign-2 at best; more X credits — the add-one news study (#13) showed no lift and Peanut/X scores need corrections before they are features. Trim FA burn first (VIX 700 + oil 450 calls/day for two tiles; study #7's 1,300–1,500 free savings).

## 7. Strategy and edge techniques

**What "consistent arbitrage" means here.** Repeatable positive expectancy per eligible opportunity after spread, latency and the occasional −50%, with low enough dispersion that 1-contract sizing can be raised. The ledger's 9 tickets > +50% and 6 < −50% say the current paper book is a lottery; Jeffrey's live book is probably not, but nobody can show it. The number to beat is not win rate; it is `E[ret_policy]` with the top-3 removed.

**Setups to register (all testable on the archive; all suited to same-day +10–20% exits).**

- **S-A Surge continuation.** Trigger: 1-min rvol ≥ 3× **and** bar closes at a new 15-min high/low **and** momentum state ≠ ACCEL for ≥ 30 s **and** day% < 3%. Instrument: nearest 0.50Δ 7–21 DTE in the surge direction, spread ≤ 8%. Bracket: +12% / −8% / 20 min. Studies #2, #3, #6 are the prior.
- **S-B Surge fade (the mirror).** Same trigger but the score has already saturated (|S| = 3 for ≥ 2 min, ACCEL → DECEL flip). Study #3 shows ±3 at 34.8% → 22.2%: that is a fade signal if it survives registration. Puts on up-surges, calls on down-surges.
- **S-C News-first-seen reaction.** EDGAR/Benzinga first-seen ≤ 3 min before a surge → treat as S-A with a 60-min time stop; no first-seen → 20 min.
- **S-D Sector sympathy.** Leader surges (e.g., MU ≥ 3×) → second-mover in the same group with rvol 1.5–3× and no own news. The 16-group page already computes this; nobody scores it.
- **S-E Opening-range breakout at 9:45–10:15 ET** on rvol ≥ 2× (S1 variant on 1-min bars instead of 30m).
- **S-F Held-score rule** as registered in map-research §g.2: core ±2 held ≥ 30 s + surge; light ±3 held 5 min + surge.

**Avoid.** 0DTE (retail loses ~$350k/day aggregate, UNVERIFIED-S; the spec excludes it), wall-presses without volume, far-OTM substitution under the $5k cap (AMD 720C, MU 1600C), holding through prints, market orders on > 8% spreads (the ~12.6% effective retail spread figure, UNVERIFIED-S, would eat the whole target), and any strategy whose entry waits on an LLM round trip.

## 8. UI/UX changes

Ranked; the full critique is in map-ui §d, and these are the data-engineer's cut.

1. **Decision ticket with one-click capture (Call / Put / Pass / Watch)** on every tile and in the focus panel, writing the `decisions` schema above keyed to `snapshot_id`. Pass and Watch are mandatory for any name in the Now lane that Jeffrey dismisses. This is the single most valuable UI change because it turns the page into the labeler.
2. **Exit tag required at exit time**, seven existing tags plus an `admin` category, and a shadow-bracket chip showing "+12% would have hit at 10:41:07" so manual and policy exits are comparable from day one.
3. **Now lane** of ≤ 5 ranked candidates with the three conditioners as checkboxes (rvol ≥ 3×, held ≥ 30 s, not ACCEL), Ack / Ignore / Acted buttons; hysteresis ≥ 60 s on momentum flips; `test`/`shadow` lanes muted.
4. **One freshness grammar**: an age pill per datum against its own TTL; header goes amber when any gated feed is stale; fix the `()` template defect; unify Last-trade clocks.
5. **Tile hierarchy by evidence**: big glyph = rvol only when ≥ 1.5×, else % change; score chip small, with `+2 · 48s` held timer; closed-market tile mode.
6. **Execution cockpit** (Stage 1+): Row 0 status (session, stream ages, FA quota %, seats, open debit, day P&L vs halt, PAPER/LIVE, HALT button); Zone A Now lane + compact heatmap of names with rvol ≥ 1.5× or held score; Zone B focus panel (why-this-fired: each input × weight, C/P with coverage %, wall % distances, spread %, contract picker vs $5k) + ticket; Zone C positions with true-stream MFE/MAE and bracket state; Zone D news (time-sorted, thumbs on finbert), momentum tape, macro.
7. **Scorecard page** ahead of the studies table: today vs 10-session hit rate by |S| × horizon with n and CI, calibration by bucket, conditioner lifts, promotion ladder status, archive coverage (rows/day per dataset, gaps).
8. Color/shape separation (volume = amber→red ramp only; direction = diverging + ▲▼), 11 px minimum, drop italic-as-semantics.
9. Replay/scrub from the 15 s table overlaid with decisions (research use; later).
10. Mobile watch mode, ≤ 8 names.

## 9. Additional bots

| Bot | Purpose | Inputs → outputs | Cadence | Authority | Pays for itself by |
|---|---|---|---|---|---|
| **Archiver** (R5) | Append every feed before it overwrites | all feeds → Parquet partitions + manifests | continuous, hourly close | write archive only | Ending daily data loss; $0 |
| **Labeler** | Forward labels, bracket counterfactuals, B0/B1 | archive → `labels/` | nightly 5:30 PM PT | none | Makes every study and the scorecard possible |
| **Latency Probe** (R15) | Produce `latency_model_ref` | collector, routines → histograms | 1 min | none | Unblocks all §18 fills |
| **Execution Gateway** | Only order writer; synthesized brackets | signed `order_intent` → broker orders, `orders` log | event | paper now; live Stage 3 | Removes human exit latency |
| **Risk Kernel** | Gates + kill switches as a library and a watchdog | positions, streams, quotas → allow/deny, HALT | per order + 5 s watchdog | veto | Prevents the unbounded error |
| **Candidate Ranker** | Deterministic Now lane | feature store → ≤ 5 candidates | 5 s | propose | Replaces scanning 209 tiles |
| **Contract Selector** | Pick the leg | chain snapshots → contract, spread, size, debit vs $5k | per candidate | propose | Kills far-OTM substitution |
| **Shadow Scorecard** | Champion vs challengers on identical snapshots | labels + configs → scorecard, drift alerts | nightly + intraday 15 min | demote on drift | Promotion ladder steps 5–8 |
| **Quota Steward** | FA/X/UW budgets | call logs → per-bot caps, STALE policy | 1 min | throttle | Keeps walls under 2,500/day |
| **First-Seen Bot** | EDGAR/Benzinga/X first observation with timestamps | feeds → `news_firstseen` | continuous | none | Only PIT-clean text feature |
| **Post-Mortem Bot** (LLM) | Nightly narrative of every decision vs its label, lessons as proposed rules with evidence | decisions + labels → draft rule, never a live change | nightly | propose | Replaces the human changelog with a versioned one |
| **Data Ops Bot** (exists) | Extend: archive coverage, gap and manifest checks, subscription count vs cap | manifests → alerts | hourly | alert | Catches silent gaps before they become holdouts |

## 10. Risks and failure modes

- **Overfitting and consumed holdouts.** The 10/19–10/20 sessions are now development data (`program.md` §15). Every headline cell has n = 26–40 and overlapping 15 s snapshots; one up-day explains the ± asymmetry. Mitigation: register hypotheses before the archive matures, sealed dates ≥ D, session-block bootstrap, B2 surge-only baseline.
- **Concentration.** 89% of Rose's net in 3 tickets; correlated AI names move on one release. Mitigation: top-3-removed reporting, ≤ 2 seats per sector group, shared-shock report in the scorecard.
- **PDT / margin.** FINRA's intraday-margin regime took effect 2026-06-04 with a broker transition window to 2027-10-20 (UNVERIFIED-S); which regime Alpaca/Tradier apply today is unknown. Seconds-to-hours exits are day trades by definition. Owner must confirm the broker's current rule and account equity before Stage 3.
- **Latency.** Box LLM routines take seconds to minutes; the target is seconds. Mitigation: nothing in the order path is an LLM; the gateway and bracket run on the mini next to the stream; latency is measured before any study claims a fill.
- **Vendor quotas and caps.** FA 2,500/day (walls alone project 2,850), OPRA ~1,000 subs, X one pool, UW 50 EOD rows. Mitigation: Quota Steward; subscriptions chosen by the ranker (ATM ± 2 strikes for the 65 core = ~650 contracts), FA trimmed per study #7.
- **LLM nondeterminism.** A routine whose output is a feature must be pinned and hashed; otherwise replay is impossible. Rose/Hal rationales are archived as text, not as inputs.
- **Data-plane fragility.** One Mac mini is the single publisher, collector and (proposed) gateway. Mitigation: nightly export to the research mini and the box mirror; UPS; a `HALT` on stream gap.
- **Measurement.** Entry at ask / exit at mark with zero fees overstates every paper number; administrative closes mislabeled as wins. Mitigation: §18 fills, `admin` exit category, signed cashflow re-encoding of the 57.
- **Cost.** New recurring spend proposed: $0 beyond today's ~$400/mo (Alpaca $99, FA $299 Growth, UW, X). Disk: already owned. The only candidate adds (ThetaData $80, Databento metered) are gated on archive findings.
- **Key-person.** The edge is Jeffrey; capture makes it transferable, and only capture does.

## 11. First 30 days / first 90 days

**Days 1–7 (owner decisions in bold).**
1. **Jeffrey: pick the archive start date and the sealed boundary D; approve R5/R6/R2/R15 enable on the data mini.** Run the R1 one-day dry count.
2. Enable `archiver` (R5) and bars append (R6) as `jake`; add the OPRA append sink (R2) and latency persistence (R15). Verify manifests for one full session.
3. Ship the `decisions` table and the one-click Call/Put/Pass/Watch ticket plus required exit tag on the live page. **Jeffrey: commit to clicking on every name he acts on or dismisses from the Now lane, and to logging his live fills (entry ask, exit bid, timestamps) into the same table.**
4. **Jeffrey: open the network path (Tailscale on the research mini or the LAN ACL).** Nightly pull of closed partitions into `/Users/oidarch/archive`; register datasets in `archive.sqlite`.

**Days 8–30.**
5. Labeler nightly; scorecard page with n and CI; B0/B1/B2 baselines; true-stream MFE/MAE on paper positions.
6. Register, before looking, the six setups in §7 and the three hypotheses in map-research §g.2–4 as campaign-2 studies with option-leg labels; freeze thresholds.
7. Feature service refactor: live scorer and replay scripts call the same `features()`; config hashes shown on the page.
8. Re-encode the 57 paper closes with signed cashflows and `admin` separation; publish top-3-removed figures.
9. Trim FA burn (VIX/oil polling) per study #7; Alpaca OI walls for sector names.
10. **Jeffrey: confirm with Alpaca (a) options historical quotes exist or not, (b) GTC/limit behavior on options, (c) the PDT regime in force; confirm with Robinhood whether Agentic supports options (all UNVERIFIED).**

**Days 31–90.**
11. Candidate Ranker in shadow (Stage 1 gate measured over 20 sessions of decisions).
12. Execution Gateway against Alpaca paper with synthesized brackets; Risk Kernel as a library; HALT file; kill-switch drills logged.
13. Shadow Scorecard with champion/challenger on identical `snapshot_id`s; first promotion or demotion decision by the ladder, not by hand.
14. Research mini: real runner and evaluator for S1 (30m bars, no purchase) to prove the pipeline, then the surge-continuation study on the archive once ≥ 20 sessions exist.
15. Post-Mortem Bot nightly; rules proposed as versioned policy files with evidence links.
16. **Jeffrey at day 90: review Stage-2 gate evidence (bot shadow expectancy vs his own matched expectancy, net of §18 fills) and decide whether the supervised-auto paper sleeve starts.** No live order before that review, and none before the broker facts above are verified.