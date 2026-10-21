# OID Execution & Risk Proposal: From Discretionary to Bot-Placed Orders

## 1. Diagnosis

**What the edge is today.** Jeffrey's live edge is a human pattern-matcher reading one input the studies actually validate (1-min rvol ≥3x, study 6: breakout odds 8.7% → 26.7% away from walls) plus flow/news context, and exiting fast at +10-20% on the option. Nothing in either repo encodes that style: the paper desk is long-calls-only (54/57 rows, zero outright puts, MAP 1 §f.10), median Rose hold is 24 h, and the only path to a real order is "a human sentence" (MAP 1 §f.11). The bots trade a different strategy (wall-press, Soft A) than the owner does.

**What the ledger says.** +$14,888 on 57 paper tickets is not evidence of a scalable process: 43/57 closes were batch administrative events on eight timestamps (MAP 1 §c); Rose's top 3 winners are 89% of her net (MAP 1 §g); entry = ask, exit = mark, zero fees or slippage; MFE is a 5-15 min sampled max, so the +50% trail arm has never been tested against executable peaks; sign errors exist on the credit spreads. Profit factor 7.7 is a function of three correlated wall-presses closed together on 9/21. Hal's PF 1.75 with median +0.4% is noise.

**What the 10/20 studies say.** Every "all nonzero" hit rate is below 50% (34%, 38%, 38.8%, 41.8%, 47.6%; MAP 2 §e). The cells above 50% with n ≥1,000 are "±2 held ≥30 s to 5 m" and "drop the C/P flow input" (50.3% → 55.8%, study 12). The 67.5% and 61.5% headlines are n=40 and n=26 on one up-day. Corr(raw direction score, close return) = -0.39 on 10/20 (study 10) is one effective observation of market direction, not a signal. The score saturates after the move (±3 is worst; ACCEL state is worst, DECEL best, study 5): the scorer chases.

**Where it is fragile (execution lens).**
1. **No options history** (family C ABSENT, `DATA_GAP_REPORT.md`): no study can label "+10% on the option," so nothing has been measured in the unit Jeffrey trades.
2. **Latency is unmeasured** (`latency_model_ref` = OWNER_DECISION_REQUIRED everywhere; R15 not built). The LLM agent path on the box is seconds-to-minutes; the target hold is seconds-to-hours. A bot that takes 40 s to decide on a 40 s median hold (study 3) is trading a different instrument.
3. **No execution layer exists.** Robinhood MCP order tools are policy-prohibited and, per press (MAP 4 §2, UNVERIFIED-3P), the Agentic account was stocks-only at launch. Alpaca has no native option bracket (`simple`/`mleg` only, UNVERIFIED-S). Nothing reconciles positions to a broker because there are no positions.
4. **The exit is the weakest link.** The close-trigger engine has never closed anything (0 review alerts). AMZN 260C bled to -61% awaiting a book harvest. For a +10-20% target the exit *is* the strategy.
5. **Fill quality is unmodeled.** Single-name weeklies in the sector universe routinely carry 3-10% bid-ask as a fraction of mid. A +10% target with 5% round-trip spread is a 2:1 handicap on every ticket. The paper ledger assumes zero.

The honest summary: the desk has a discretionary trader with a plausible edge, a scorer that is not yet one, a research spec with no runner, and no execution layer. The order of work is therefore execution/risk plumbing and option-leg labeling first, model promotion second, autonomy last.

## 2. Scaling strategy

Four stages. Each gate is measured by code the owner does not edit, on data that post-dates the rule.

**Stage 0: Discretionary with capture (start now, weeks 1-4).** Jeffrey keeps trading by hand. Every decision (Call/Put/Pass/Watch) is written at decision time with `snapshot_id` from the 15 s `score_features` table (MAP 3 §e). His live fills are exported daily from the broker and joined. Gate to Stage 1: ≥15 sessions and ≥150 decision rows (including Pass/Watch) with option-leg labels; R2 streamed BBO archive live for the core ATM set; R15 latency histogram persisted.

**Stage 1: Assisted (weeks 4-10).** A deterministic Candidate Engine on the data mini proposes a ticket (contract, debit, bracket). Jeffrey clicks Send. The OMS sends to **Alpaca paper** and runs the bracket. Gate: ≥20 sessions, ≥100 OMS tickets; slippage-adjusted net expectancy per ticket >0 with a session-block bootstrap 90% CI excluding 0; top-3 share of net <40%; zero unreconciled fills; kill switch exercised weekly with evidence; bracket exits dominate (administrative closes <10%).

**Stage 2: Supervised auto (weeks 10-20).** The Candidate Engine sends paper orders itself; Jeffrey has a 15 s veto window on entries and none on exits. After 20 clean paper sessions, flip to live with hard caps: 1 contract, $500 debit per ticket, 2 open seats, $750 daily loss stop. Gate: live expectancy after real fills and fees not statistically worse than paper (paired by session); realized slippage ≤ modeled; no risk-limit breach; reconciliation mismatch count = 0.

**Stage 3: Autonomous within limits (month 6+).** Caps raised stepwise (one notch per 20 clean sessions): $500 → $1,500 → $5,000 debit; 2 → 4 → 8 seats. Jeffrey retains the kill switch and a daily review. The desk never gets "fully autonomous" in the sense of unlimited; it gets autonomous inside a config file the owner signs.

**What gets automated first and why: exits, then risk, then entries.** Jeffrey's edge is entry judgment; his documented failures are exits held for a ping. A bracket manager (+10%/+20% ladder, stop, time stop) is deterministic, testable in paper tomorrow, and immediately improves the discretionary book. Entries are automated last because they depend on the option-leg labels that do not exist yet.

## 3. Bot architecture

**Deterministic vs LLM, as a hard rule.** Anything inside the order path (signal evaluation, contract selection, sizing, order send, bracket, reconciliation, kill switch) is deterministic Python on the data mini, no LLM calls, p99 decision→order-ready ≤500 ms. LLMs (Rose, Hal, Macro, Peanut, X Summarizer) run on the box at minute cadence and may only (a) set gates that *reduce* exposure (earnings gate, news-shock gate, macro -2 scaling), (b) annotate, (c) review after the fact. An LLM may never raise a cap, name a wall that "governs," or send an order. "Named gate governs" (MAP 1 §f.2) becomes a signed config change, not a chat sentence.

**Components (one owner each, per the existing one-writer rule).**

| Component | Host | Deterministic? | Owns |
|---|---|---|---|
| Collector (exists) | data mini :8787 | yes | SIP + OPRA streams, `score_features`, R2 BBO archive |
| Candidate Engine | data mini | yes | `candidates` table: setup id, snapshot_id, proposed contract, bracket |
| Contract Selector | data mini | yes | picks 0.45-0.55Δ, 5-21 DTE, spread ≤ threshold, OI ≥500, size ≤ ask size |
| Risk Sentinel | data mini (separate process) | yes | pre-trade checks, caps, daily loss, kill flag; sole writer of `risk_state` |
| OMS / Bracket Manager | data mini | yes | order intents, idempotent sends, fills, bracket ladders, time stops; sole broker-API writer |
| Reconciler | data mini | yes | broker positions/orders vs OMS every 10 s; halts on mismatch |
| Shadow Scorer | data mini | yes | challenger scores logged beside champion (steps 5-8 of study 1) |
| Rose / Hal / Macro / Peanut | box | LLM | gates-down signals, context, review; read-only on OMS |
| Research Bot | research mini | code + LLM (editable/ only) | campaigns; never touches production |
| Data Ops | box | LLM + scripts | feed health, quota, archive integrity |

**Execution/risk layer schema (SQLite WAL on the data mini, mirrored to parquet nightly).**

`order_intent {intent_id (uuid, idempotency key), ts_decision, snapshot_id, setup_id, actor ∈ {jeffrey, engine}, symbol, occ_symbol, side ∈ {buy_to_open}, qty, limit_px, max_debit, bracket {tp1_pct=10, tp1_frac=0.5, tp2_pct=20, stop_pct, time_stop_s}, risk_check_id, status}`
`risk_check {risk_check_id, intent_id, ts, checks[] {name, value, limit, pass}, verdict ∈ {PASS, REJECT, HALT}}`
`fill {fill_id, intent_id, broker_order_id, ts_broker, px, qty, fee, slippage_vs_mid_at_decision}`
`position {occ_symbol, qty, avg_px, peak_mark, bracket_state ∈ {OPEN, TP1_DONE, TRAILING, CLOSING}, time_stop_at}`
`recon_event {ts, broker_qty, oms_qty, delta, action}`

**Pre-trade checks the Sentinel must pass, in order (any fail = REJECT; two fails in a row on different intents = HALT):** kill flag absent; mode ∈ {PAPER, LIVE} matches intent target; quote age ≤5 s for both underlying and contract (the 120 s gate is for Hal's cadence, not a seconds-horizon trader); spread/mid ≤5% (core) or ≤8% (sector, with half size); debit ≤ cap; open debit + new debit ≤ book cap; seats < cap; per-name 1 seat, per-sector 3; no earnings within the hold window (deterministic from the catalyst file, not an LLM); day P&L > -daily loss limit; order rate ≤6/min desk-wide; duplicate intent_id rejected; underlying day% < chase gate (3%, keep the existing rule until study 5-style evidence says otherwise); session clock inside 6:35-12:50 PT (no first 5 min, no last 10 min for new entries).

**Bracket mechanics without native brackets.** Alpaca options support `simple` and `mleg` order classes only, no bracket/OCO (MAP 4 §1, UNVERIFIED-S). So the OMS runs synthetic brackets: on fill, post a GTC limit sell at +10% for half the quantity (or the whole single contract on a 1-lot) and manage the second half with a trailing rule from the stream; stop is a software stop that cancels the resting take-profit then sends a marketable limit at bid-1 tick, re-pricing every 2 s up to 5 times, then market as last resort. Time stop: flat at `time_stop_at` (default 90 min for the surge setup, 3:50 PM PT hard for everything). Stream disconnect >10 s with open positions → flatten-at-limit sequence, then HALT.

**Kill switches (three, independent).** (1) File flag `/opt/oid/KILL` checked by the Sentinel before every send and every 1 s by the Bracket Manager (cancel all, flatten, refuse new). (2) Broker-side: Alpaca account-level "block new orders" via API key rotation script (revoke trading key, keep data key). (3) Human: a physical button on the cockpit page that writes the file and posts to chat. Weekly drill: flip, verify cancel-all latency <2 s and zero residual orders, log it.

**Broker choice.** Stage 1-2 paper: **Alpaca paper** (same vendor as the collector, Level 3 automatic in paper, alpaca-py `OptionDataStream` already in use). Live Stage 2+: Alpaca first because the data, the clock and the symbology are already there; apply for Level 2 (long calls/puts). Keep **Tradier** as the evaluated alternative: native `otoco` with option legs and $10/mo flat options pricing (UNVERIFIED-S) would replace the synthetic bracket, but its sandbox is 15-min delayed with no streaming, so it cannot be paper-tested at seconds scale. IBKR (TWS API, native bracket via `parentId`/`ocaGroup`, ib_async) is the institutional fallback if per-contract fees matter at scale. **Robinhood is out of the order path**: no options on the Agentic MCP as of the last verified report (UNVERIFIED-3P), terms questions on bots, and no bracket. Owner decision needed: confirm Robinhood MCP options status in writing before anyone plans around it.

## 4. Models

**The target.** Not "direction right at 5 m." The label is the executable one from MAP 2 §g.1: for a decision at `t0` on the selected contract, `y = 1` if the contract **bid** reaches entry **ask** × 1.10 before the stop (ask × 0.80) and before `time_stop`, else 0; secondary continuous label = realized net P&L of the bracket policy with §18 fills (buy at ask after decision + measured latency, sell at bid). Both need R2 streamed BBO (or R1 5-min snapshots as a coarse fallback) and R15 latency. Until that archive exists, nothing is promotable, and studies stay `UNDERLYING_ONLY`.

**Features (all with `feature_available_at ≤ decision_at`).** 1-min rvol and 10 s pace; surge flag and side (day_high/day_low); seconds since score last changed (the "held" conditioner); momentum state with hysteresis; score value and version; drop-C/P variant of the score; distance to day high/low in ATR; QQQ/SMH 5-min return (market/sector baseline B1); time-of-day bucket; contract spread/mid; contract IV vs 20-day; OI; wall distance % (keep as a feature, expect zero weight per study 6); news tone age; macro score. Explicitly excluded: anything from UW 15 m lean with unknown age, raw C/P at <20% classified coverage.

**Model classes, in order.** Hand weights (today) → L2 logistic with Platt calibration (already in `config.draft.json`) → small gradient-boosted trees (depth ≤3, ≤200 trees, monotone constraints on rvol and spread) → nothing bigger. Walk-forward by session with purge by `label_end_at`; session-block bootstrap for CIs; report Brier skill vs B0 (same-window base rate) and B1, not hit rate. PBO/deflated-Sharpe style check once >5 configs are compared.

**Calibration matters more than accuracy** because sizing and the veto window key off probability: a model that says 0.62 must hit about 62%. Reliability plot by decile is the first chart on the Research tab (MAP 3 §d.9).

**Promotion ladder (builds steps 5-8 of study 1).** Challenger runs in shadow on the data mini, logging a score per snapshot beside the champion. Promotion requires: ≥10 sessions of live (not replay) shadow; Brier skill over champion ≥0.01 with 90% CI excluding 0; expectancy on the option-leg label ≥ champion; no single session >30% of the lift; evaluator run as `oideval` on the research mini on dates the researcher never saw. Promotion flips a config version string (`core v1.2`), logged in the experiments table. Demotion is automatic if a promoted model trails the previous champion by the same margin over 10 sessions.

**Research → live handoff is a config, not code.** The live Candidate Engine loads `model_<version>.json` (weights/trees serialized) and a `features_<version>.py` hash-pinned from the research mini's FROZEN artifact. No LLM-written code reaches the data mini without a human diff review.

**LLMs: what they should and should not do.** Should: classify news/filings into gate categories (earnings, guidance, halt, M&A) with a confidence and a quote; write the post-trade review from structured rows; propose hypotheses as registered study drafts; write and review code offline. Should not: be in the decision loop at seconds scale; produce probabilities; choose sizes; interpret walls as "governing"; edit `program.md` or the risk config; be trusted to re-run an experiment identically (nondeterminism makes them unfit as evaluators).

## 5. Data collection and archive

**Capture from today (ordered by irreversibility).** R5 dated append-only copies of every `latest/` write (cheapest, highest value); R6 1-min SIP bars + same-minute norms for the 209 names + QQQ/SPY/SMH/SOXX (already partly on the data mini per the 10/20 page; put it in git-tracked schema); **R2 streamed OPRA BBO for a fixed ATM set**: for each of the 65 core names, the nearest 0.50Δ call and put in the two nearest weekly expiries = 260 contracts, re-pinned daily at 6:20 AM PT, well under the ~1,000 cap (desk figure, UNVERIFIED), every quote with `bp/bs/ap/as/t` to parquet partitioned by date/symbol; R1 5-min chain snapshots for the sector 144 (±30% strikes, 5-45 DTE), dry-count calls first; R7 the structured decision log (Section 8) including Pass/Watch; R15 `LagHistogram` persisted per feed plus `decision_at → order_ready_at → broker_ack_at → fill_at` once the OMS exists; the OMS tables themselves; Jeffrey's live broker fills (daily CSV export, hashed, joined to decisions).

**PIT discipline.** Every row carries the twelve `program.md` §6 clocks that apply (minimum: `source_observed_at`, `received_at`, `feature_computed_at`, `available_at`). Features are computed by the same code path live and in replay (`score_features` already is 15 s; keep it). Labels are computed only by the nightly job and stored in a table the engine cannot read. FRED/ALFRED vintages (R10) for macro features so S2 arm C stops being blocked.

**Labeling pipeline.** Nightly on the data mini: join decisions and candidate rows to the R2 BBO archive; compute option-leg outcomes at +10/+20/stop/time-stop; underlying 5/15/30-min returns and B0/B1 baselines; write `labels_<date>.parquet`. Weekly: a hashed export (`exports(target=dev)`) to the research mini; the final 20% of dates are written only to `sealed/` by root.

**Storage.** Parquet + DuckDB on the data mini (~1 GB/month for R2 at 260 contracts; R6 ~70 MB/yr); SQLite WAL for OMS/decisions; nightly rsync to the research mini's `oidarch` and to an off-site encrypted copy (the data mini is a single point of loss).

**Data mini / research mini split.** Data mini = the only writer of production feeds, the OMS, and the champion scorer. Research mini = archive, challengers, evaluator, sealed holdout. The **network path does not exist** (MAP 2 §b): install Tailscale on the research mini (the live site is already on tailnet), expose only :8788 archive-pull, pull-only from the research side, no route from research to the OMS. This is a week-1 item; every day without it is unrecoverable research time.

## 6. Additional data sources

Ranked by value per dollar for the +10-20% same-day style. PIT quality noted.

1. **Own decisions + own live fills** ($0, PIT perfect). Hypothesis: Jeffrey's discretionary hit rate on the option-leg label exceeds the scorer's; which of his reason chips carry the lift.
2. **R2 OPRA BBO archive from the existing Alpaca plan** ($0, PIT perfect, forward-only). Hypothesis: the +10% label is reachable within 90 min after a ≥3x surge at a rate that beats spread costs.
3. **Databento OPRA targeted pulls** (`cbbo-1m` $2/GB, `definition` $5/GB, pay-as-you-go; est. $50-300 for ~60 surge-days across core names; UNVERIFIED-S). Hypothesis: backfill the option-leg label onto the existing 82,190 ticker-minutes of surge events (9/25-10/20) so study 5 can be run in the right units before R2 accumulates months. Run `metadata.get_cost` first.
4. **FINRA short interest API** ($0, bi-monthly, published-date PIT). S5 as registered; expect weak lift on mega-caps.
5. **Kalshi candlesticks** ($0, PIT good). Nests in S2 (macro event odds as a gate for first-hour trades on CPI/FOMC days).
6. **Korea 10/20-day exports via data.go.kr** ($0, PIT = release at 17:00 PT prior day). Hal catalyst study only; no intraday use.
7. **UW analyst-rating changes** (already paid). Pre-open gap setups; feature inside S1.
8. **Alpaca OI-derived walls** ($0, OI 2 days old). Keep as the wall feature so the study-6 null can be re-tested on 144 names without FlashAlpha spend.

**Do not buy:** FlashAlpha Alpha ($1,499/mo) — study 6 found walls add ~2 pts over chance; historical replay of a non-signal is not worth 18k/yr. DRAMeXchange ($5k/yr) and Silicon Data Pro ($998/mo) — monthly/daily series cannot help a same-day exit. Massive options plan — "non-pros only" licensing is a live question once a bot trades. ORTEX — defer until S5 shows anything. More X credits — add-one news showed no lift (study 13). Any second GEX vendor — resolving NVDA 230 vs 220 (study 8) is resolving a null.

## 7. Strategy/edge techniques

"Consistent arbitrage" for this desk means: many small, independent, cost-aware bets with positive expectancy after spread, exited by rule, with turnover high enough that the law of large numbers works within weeks rather than quarters. It does not mean riskless. Concretely:

**Setup A: Surge continuation (the only study-backed one).** Trigger: 1-min rvol ≥3x printed at `day_high` (calls) or `day_low` (puts), underlying day% <3%, momentum state not ACCEL for >2 min already (study 5), QQQ 5-min return same sign or flat. Contract: 0.50Δ, 5-14 DTE, spread ≤5% of mid, OI ≥500. Entry: limit at mid + 25% of spread, cancel if unfilled in 10 s (no chase). Bracket: TP +10% on half, trail the rest with 50%-of-MFE giveback after +20%, stop -20%, time stop 90 min. Testable today on the underlying (study 5 design), on the option after item 3 of Section 6.

**Setup B: Held-score confirmation.** Core score ±2 held ≥60 s (not ±3) with rvol ≥2x, drop-C/P variant (studies 3, 12). Same bracket. This is the setup that tests whether the scorer adds anything to Setup A; registered as a challenger, not a trade source, until it beats A's base rate.

**Setup C: Opening-range break with time filter.** 6:35-7:15 PT only, first 5-min range break on ≥2x volume, sector ETF (SMH/QQQ) confirming. S1 is the 30-min cousin; this is its intraday registration.

**Setup D: Pre-open catalyst gap (Hal lane).** Analyst change or 8-K first-seen pre-open; trade the first pullback, not the open print. Minutes-hours; LLM classification allowed because the clock is slow.

**Cost arithmetic that must hold before any setup goes live.** Expected gross per ticket ≥ 2 × (round-trip spread + fees). With a $2.00 option at 5% spread, round-trip cost ≈ $0.10 + $1.30 fees/contract = ~5.6%; a +10% target then nets ~4.4% on wins. At a 55% win rate and -20% stops that is a losing policy; it needs either ≥62% wins or a 2:1 TP:stop ratio. The Candidate Engine computes this per ticket and rejects when the break-even win rate exceeds the model's calibrated probability.

**Avoid:** 0DTE on single names (retail 0DTE evidence is uniformly negative, MAP 4 §9, UNVERIFIED-S); far-OTM substitution to fit the cap (MAP 1 §b.4, now prohibited; keep it prohibited); wall-press without volume; FOMC/CPI first-hour entries without the Kalshi/Macro gate; stacking the same sector move in three names and counting three wins; ACCEL-state chasing; any entry with contract quote age >5 s.

## 8. UI/UX changes

Ranked, building on MAP 3 §d.

1. **Decision ticket with capture (Stage 0 prerequisite).** Click a tile → drawer pre-filled with contract, debit vs cap, bracket, break-even win rate, spread %, coverage %; buttons Call / Put / Pass / Watch write the R7 row keyed to `snapshot_id` with reason chips (surge, held, flow, news, gut, sector) and confidence 1-3. Pass/Watch are the negatives nobody has.
2. **Row-0 risk and freshness bar.** Mode PAPER/LIVE; kill switch button (red, two-step); day P&L vs loss limit; open debit vs book cap; seats; Alpaca stream age; FlashAlpha quota %; UW age. One age-pill grammar everywhere (MAP 3 §d.2); amber header when any gated feed is past TTL.
3. **Positions zone with bracket state.** Mark, MFE/MAE from the stream (not sampled), `bracket_state`, resting TP order id, time-stop countdown, slippage at entry. Replaces the here.now blotter for intraday.
4. **Now lane.** ≤5 ranked candidates (rvol × held-seconds × spread fitness), hysteresis ≥60 s on momentum flips, `test`/`shadow` collapsed. Ack / Ignore / Acted writes labels.
5. **Re-rank tiles**: big glyph = rvol only when ≥1.5x, else % change; score chip small with held timer (`+2 · 48s`); `0.0×` removed after close.
6. **Why-this-fired panel** from the stored score inputs; C/P shows coverage %.
7. **Scorecard-first Research tab**: calibration by decile with n, conditioner lifts with CIs, promotion ladder status, latency histogram.
8. **Color/shape fixes** (volume ramp vs direction palette, ▲▼ glyphs, 11 px minimum).
9. **Closed-market mode** and the `()` template fix.
10. **Mobile watch mode** for the ≤8 open seats with a flatten-all button that hits the kill file.

## 9. Additional bots

- **Bracket Manager (OMS)** — deterministic; inputs: fills, stream; outputs: TP/stop/time-stop orders; cadence: event-driven, 1 s heartbeat; authority: close positions, never open; pays for itself by removing the "await a ping" exits (AMZN -61%, FORCE_REVIEW 30-min delays).
- **Risk Sentinel** — deterministic; inputs: intents, positions, P&L, feed ages; outputs: PASS/REJECT/HALT, kill file; cadence: per intent + 1 s; authority: block everything; it is the condition for ever flipping LIVE.
- **Reconciler** — deterministic; inputs: broker positions/orders, OMS tables; outputs: `recon_event`, HALT on delta; cadence: 10 s; the only defense against duplicate sends and ghost fills.
- **Contract Selector / Liquidity Bot** — deterministic; inputs: chain snapshot, spread, OI, Δ; outputs: `occ_symbol`, break-even win rate; cadence: on candidate; stops the OTM-substitution pattern and quantifies the spread tax per ticket.
- **Shadow Scorer** — deterministic; runs challengers beside the champion; cadence 15 s; authority none; it is how a model ever gets promoted.
- **Latency Monitor** — deterministic; persists `LagHistogram` and OMS clock deltas; outputs the `latency_model_ref` every study is waiting on; cadence continuous.
- **Event Gate Bot** — deterministic from `desk-catalysts.json` + calendar + Kalshi; outputs per-name `no_new_entries_until`; cadence 5 min; encodes the earnings/FOMC gates so no LLM has to remember them.
- **Post-Trade Reviewer** — LLM, nightly; inputs: labeled decisions and fills; outputs: a structured review (entry quality, exit quality, process adherence 1-3) and candidate never_again rules as *registered study drafts*, not policy; this replaces the human changelog with a versioned proposal queue.
- **Data Ops** (exists) gains: archive hash checks, parquet row counts vs expected, Tailscale path health, off-site backup verification.
- **Retire or demote:** Customer/Supplier Bot (0 edges), Soft Grader (0 graded elevates; its gates move into the Sentinel as code).

## 10. Risks and failure modes

- **Overfitting / selection.** 10/19-10/20 are consumed dates; headline cells are n=26-40; campaign 1 has zero headroom. Mitigation: sealed = future dates on the research mini; Brier vs B0; session-block bootstrap; promotion only on live shadow sessions.
- **Concentration.** 89% of Rose's net in 3 tickets; sector moves counted as many wins. Mitigation: per-sector seat cap 3, top-3 share gate <40%, shared-shock report in the scorecard.
- **PDT / margin.** FINRA replaced the PDT designation effective 2026-06-04 with a broker transition to 2027-10-20 (UNVERIFIED-S); each broker may still apply legacy 4-in-5/$25k rules. Same-day option round trips are day trades under the legacy rule. Mitigation: ask Alpaca (and any alternative) in writing which regime applies to the account; until answered, assume legacy and keep live account equity >$25k or cap round trips at 3 per rolling 5 sessions in the Sentinel.
- **Latency.** Unmeasured; LLM path is seconds-to-minutes. Mitigation: deterministic order path on the data mini; p99 budget 500 ms decision→order-ready, 2 s to broker ack; trades rejected when the measured lag exceeds budget.
- **Fill quality.** Paper at mid flatters. Mitigation: paper OMS marks entries at ask + 1 tick and exits at bid; live slippage reconciled against the model weekly; spread cap in the Sentinel.
- **Vendor quotas.** FlashAlpha 2,500/day already over on a full wall day; Alpaca ~1,000 subs; X pool near empty. Mitigation: walls demoted to a feature; R2 set fixed at 260 contracts; the Sentinel HALTs new entries when any gated feed is STALE.
- **LLM nondeterminism and prompt drift.** Mitigation: LLMs outside the order path; every gate they set is a signed row with a reason; weekly replay of the same inputs to detect drift.
- **Single points of failure.** Data mini hosts collector, OMS and site; no off-site archive. Mitigation: nightly off-site copy; broker-side flatten script runnable from a phone; stream-loss flatten rule.
- **Cost creep.** Current run rate ≈ $99 Alpaca + $299 FA + UW + X + LLM tokens. This plan adds ≈$0-300 one-time (Databento pulls) and $10/mo if Tradier is evaluated. It explicitly does not add FA Alpha.
- **Terms of service.** Robinhood bot prohibition (UNVERIFIED-3P) and Massive non-pro licensing. Mitigation: trade only through brokers whose API terms allow automation (Alpaca, Tradier, IBKR, tastytrade).

## 11. First 30 days / first 90 days

**Days 1-7.** Owner decisions: (a) confirm Alpaca paper as the execution target and apply for live Level 2; (b) confirm in writing Robinhood MCP options status and Alpaca's PDT regime; (c) sign the risk config v0 (caps above); (d) approve Tailscale on the research mini. Build: R5/R6 append writers in git with schema; R2 260-contract BBO archive; R15 histogram persisted; decision ticket with Pass/Watch (UI items 1-2); daily export of Jeffrey's live fills into `fills_owner`.
**Days 8-14.** OMS tables and the Bracket Manager against Alpaca paper with synthetic brackets; Risk Sentinel with the full check list; Reconciler; kill file + weekly drill; Latency Monitor wired to OMS clocks. Research mini: archive-pull working over Tailscale; S1 run end-to-end to prove runner/evaluator.
**Days 15-30.** Stage 0 capture running every session; nightly option-leg labeling from R2; Databento cost query and, if <$300, the surge-day backfill; register (before looking) the surge-conditioned hold study and drop-C/P as confirmatory with sealed = dates ≥ day 31; Post-Trade Reviewer nightly; retire Soft Grader into Sentinel code. Gate review at day 30: ≥15 sessions captured, OMS paper tickets ≥50 with zero recon deltas.

**Days 31-60.** Stage 1 assisted: Candidate Engine for Setup A proposing tickets; Jeffrey clicks Send; bracket fully automated; Now lane and positions zone live; Shadow Scorer running the drop-C/P challenger and the first logistic model; scorecard tab. Owner decisions: Tradier evaluation yes/no; sector seat caps; time-stop defaults.
**Days 61-90.** If the Stage 1 gate passes (≥100 tickets, positive slippage-adjusted expectancy with CI, top-3 <40%, clean recon), Stage 2 paper with the engine sending; then live at 1 contract / $500 / 2 seats / $750 daily stop with the 15 s veto. First promotion review for a challenger on ≥10 live shadow sessions. If the gate fails, the desk has lost nothing but has, for the first time, the archive, the labels, the latency model and the execution layer that any future edge will need.

Unverified items this plan leans on (confirm before acting): Alpaca option order classes/TIF and paper Level 3; Alpaca websocket contract cap; Robinhood MCP options status; Tradier OTOCO with option legs and pricing; Databento per-GB pricing; the FINRA 4210 transition timeline and each broker's current regime.