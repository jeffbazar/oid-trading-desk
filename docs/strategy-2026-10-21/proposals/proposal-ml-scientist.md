# OID: From Discretionary Desk to Supervised Automation — a Microstructure Quant's Proposal

## 1. Diagnosis

**What the edge actually is today.** Jeffrey's live edge is a human pattern-matcher reading one robust signal (abnormal 1-minute volume at a day extreme) plus context (sector sympathy, news, walls), buying the ATM option, and exiting fast at +10–20%. Nothing in either repo encodes that. The paper desk (map 1, §b–c) runs a different strategy: long-call wall-presses with 24 h median holds, closed in administrative batches (43/57 closes on eight timestamps; the close-trigger engine has never auto-closed anything). The live page (map 3) scores a third thing: a Direction/Light/Full score whose own Research tab rates it near coin-flip. So there are three uncoordinated systems, and the one that reportedly makes money (Jeffrey's hand) has no data trail: his live fills are in neither repo (map 1, §f.10).

**What the 10/20 studies say, read as a statistician.** Every "all nonzero" cell is below 50% (34%, 38%, 38.8%, 41.8%, 47.6%; studies 2, 3, 4, 10, 12). The positive cells share one conditioner: 1-min rvol ≥ 3×. Study 6 is the cleanest result on the page: wall proximity adds ~2 pts over chance (46.9% vs 44.9%) while rvol ≥ 3× triples 15-min breakout odds away from walls (8.7% → 26.7%) on 82,190 ticker-minutes. Study 5 (DECEL 46.7% vs ACCEL 31.3%) and study 3 (±3 worse than ±2; ±3 degrades to 22.2% after 30 s) say the score saturates after the move, i.e., it chases. Study 12 says the 15 s/1 m C/P input is churn (removing it: 50.3% → 55.8% on n 1,034). Study 11's +/− asymmetry (core +2.0 → 58%, −2.5 → 33%) is an up-day base rate, not skill; no B0 is reported anywhere (map 2, §e).

The headline numbers are not evidence yet. 67.5% (n=40) has a binomial 95% CI of ~51–81%; 61.5% (n=26) is ~41–80%. 15 s snapshots labeled at 5 m overlap ~20×, so n=14,703 is closer to n≈700 effective, and those are correlated names on one or two sessions. By `program.md` §13–16 this is hypothesis generation; 10/19–10/20 are consumed development dates for any study of these cells (§15).

**What the ledger says.** Net +$14,888 is paper, at ask-in/mark-out with zero fees or slippage, and Rose's top 3 tickets are 89% of her net (map 1, §g). Seven 9/18 wall-presses closed together on 9/21 are one market move counted seven times. Hal is PF 1.75 with median +0.4%. The desk's own audit is right: this sample supports no return target. It also cannot be a baseline for Jeffrey's style because it is long-calls-only (54/57), multi-day, and batch-exited.

**Where it is fragile.** (1) Edge lives in one head and is unmeasured; (2) the one robust conditioner is encoded on the page as the weakest visual (map 3, §b); (3) no PIT archive existed before mid-October and what exists is page-local, unhashed, unreachable by the research sandbox (map 2, §f.3); (4) no option-leg labels: no study can say whether "+10% on the option" was available (map 2, §f.2); (5) decision latency is unmeasured for a seconds-to-hours strategy (map 2, §f.5); (6) the research mini has no network path and stub features/model/evaluator (map 2, §b).

## 2. Scaling strategy

Four stages. Each gate is measured on a pre-registered, append-only record; no gate is passed on hit rate alone.

**Stage 0 — Discretionary with capture (now → ~day 30).** Jeffrey keeps trading by hand. Every decision (Call/Put/Pass/Watch) is captured as a structured row keyed to the 15 s `score_features` snapshot id (map 3, §e); his live fills are imported daily (broker CSV or screenshots → `owner_fills` table). The Exit Manager (§3) runs in paper shadow against his entries. Gate to Stage 1: ≥ 20 sessions, ≥ 300 decision rows including ≥ 150 Pass/Watch negatives, ≥ 60 live fills with timestamps, R15 latency histogram persisted, drop-C/P confirmatory study (§4) complete.

**Stage 1 — Assisted (~day 30–75).** The page shows a ranked "Now" lane (§8), a pre-filled decision ticket with bracket, and the deterministic Exit Manager takes over paper exits for Jeffrey-entered paper positions (he still exits live by hand). A frozen Shadow Trader emits entries on the same snapshots. Gate to Stage 2: 30 sessions; shadow-vs-Jeffrey comparison on identical snapshots; paper ledger with modeled fees and spread; shadow policy net expectancy per opportunity > 0 with session-block bootstrap 90% CI excluding 0 on ≥ 150 tickets; no single session > 30% of net; top-3 tickets < 40% of net.

**Stage 2 — Supervised auto (~day 75–150).** Bot sends entry proposals to a one-tap approve (10 s timeout = Pass); exits fully automatic; live size tiny (1 contract, ≤ $500 debit, 3 seats, $750 daily loss stop). Gate to Stage 3: 40 live sessions; realized slippage within the registered latency/fill model (median realized entry ≤ modeled ask + 1 tick); rolling 20-session profit factor ≥ 1.3 after commissions; max drawdown ≤ 2.5× average daily gross; calibration ECE ≤ 0.05 on live labels; every kill switch exercised at least once in a drill.

**Stage 3 — Autonomous inside an envelope.** Entries and exits auto within per-name, per-sector, and daily caps; Jeffrey supervises. Any gate metric that fails on a rolling 20-session window demotes to Stage 2 automatically.

**What gets automated first and why: exits.** Exits are deterministic, latency-sensitive, and demonstrably the weakest link (43/57 administrative closes; AMZN 260C bled to −61% waiting for a harvest; GOOGL 340C MFE +164% exited +17.8%). Entries are where the human edge is; automating them last preserves the asset while the data accumulates. Second: the surge detector (already built as `vol_surge` dry-run) becomes the single gate for everything else. Third: contract selection (liquidity, spread, DTE) is pure code and should never be an LLM judgment again (the AMD 720C / MU 1600C OTM substitutions in map 1 §b.4 are what happens when it is).

## 3. Bot architecture

Split into two planes. The **decision plane** is deterministic Python on the data mini (it already holds the Alpaca stream and the 15 s feature table). The **reasoning plane** is the LLM agents on the box, which produce slow features and reviews, never orders.

| Bot | Plane | Owns | Authority |
|---|---|---|---|
| Surge Engine (exists as `vol_surge`) | det. | `surge_events` append log: ticker, ts, rvol, type day_high/day_low, 5-min rvol, sector rvol, hysteresis state | gate only |
| Feature Builder | det. | 15 s `score_features` (exists) + held-score timer, momentum state, ATM option quote/spread/IV | none |
| Shadow Trader (frozen model, §4) | det. | `signals` log with p, config hash, snapshot id | paper entries (Stage 1), proposals (Stage 2) |
| Exit Manager | det. | bracket state machine per position; `exit_events` | paper exits Stage 1; live exits Stage 2+ |
| Risk/Execution Gateway | det. | one process, one broker key; seat/debit/day-loss/quota/latency checks; order log | the only writer of orders |
| Label Bot (nightly `score_labels`, exists) | det. | forward returns, option-leg first-passage labels, bracket counterfactuals | none |
| Scorecard/Promotion Bot | det. | daily champion vs challenger scorecard; promotion ladder status | none |
| Data Ops (exists) | det.+LLM | feed health, archive integrity, quota | kill switch on feed failure |
| Rose / Hal | LLM | rationale, catalyst context, structured candidate/REJECT log (R7) | propose only |
| Macro / X Summarizer / News | LLM | slow features: event gates, tone, earnings/FOMC flags | gate inputs |
| Research Bot (program.md loop) | LLM + det. | experiments in sandbox; evidence packages | none |

**Risk/Execution Gateway rules (code, not prompt):** quote age ≤ 5 s for entries (the 120 s gate is for a 24 h strategy; it is useless at this horizon); ATM option spread ≤ 5% of mid and ≥ 500 OI or skip (S3's own filter); 1 contract; debit ≤ cap; no entry within earnings window (Hal's `desk-catalysts.json`), within 2 min of a scheduled macro print (Macro Bot calendar), or in the last 20 min of RTH; per-name max 1 open, per-sector max 2 (the 9/18 cohort problem); daily loss stop; FA/UW quota floor (if FA < 300 calls remaining, walls → diagnostic only, no block).

**Kill switches (all deterministic, all logged):** (1) daily loss ≥ limit → flatten + halt; (2) Alpaca stream gap > 10 s or SIP/OPRA lag > 2 s → no new entries, exits continue on broker-side brackets; (3) model p-distribution drift (KS test vs last 10 sessions) → shadow only; (4) three consecutive fills worse than modeled by > 1 tick → halt entries; (5) manual red button on the page and a `HALT` file the gateway polls every second; (6) broker-side brackets exist for every live position so a dead mini cannot strand a trade.

**Broker choice.** Keep Robinhood for Jeffrey's hand. For the bot: **Alpaca paper now** (paper accounts get Level 3 automatically; options order types are market/limit/stop/stop-limit only; no native bracket/OCO for options; GTC status conflicts across docs — all UNVERIFIED-S, map 4 §1). That means the Exit Manager must synthesize the bracket (resting limit at target + software stop) in Stage 1 — acceptable on paper. For **live Stage 2, evaluate Tradier first**: OTOCO with option legs is a native +target/−stop bracket for $10/mo flat (UNVERIFIED-S); tastytrade OTOCO is the alternative; IBKR is heavier but has full bracket support. **Do not plan execution around the Robinhood Agentic MCP**: press reports stocks-only at the May 2026 launch with options "coming soon" (UNVERIFIED-3P) and the customer agreement reportedly prohibits bots on equities/options (UNVERIFIED-3P). Owner action: confirm with Robinhood, Alpaca, and Tradier in writing.

## 4. Models

**What to model.** Not "direction." The tradeable object is: given a decision snapshot, does the ATM 7–21 DTE option's bid reach +X% over the entry ask before it reaches −Y% or a time stop? That is a triple-barrier first-passage label and it is the only label that matches the exit style.

**Labels (registered, all computed by Label Bot on the data mini, never by agents):**
- `L_opt(X,Y,T)` ∈ {target, stop, timeout}: X ∈ {10%, 15%, 20%}, Y ∈ {−15%, −25%}, T ∈ {15 m, 45 m, close}. Requires the option BBO path (R2) or Alpaca option 1-min bars as a lower-fidelity proxy.
- `L_und(h)`: sign and magnitude of underlying return at h ∈ {1, 5, 15, 60 min}, minus QQQ (B1) — the existing `score_labels`, extended.
- `L_exc`: 15-min maximum favorable excursion in ATR-scaled units (needed for exit-policy counterfactuals).
- Every label row carries `label_end_at`; purge/embargo uses it (`program.md` §13).

**Baselines, always reported:** B0 same-name, same-session, same-time-of-day up-fraction; B1 QQQ h-minute return sign; B2 "naive surge rule" (enter on every rvol ≥ 3× at day_high/day_low, no score). The score must beat B2, not chance.

**Features (snapshot-time only; `feature_available_at ≤ decision_at` enforced in code).** Tier 1 (the ones with any evidence): 1-min rvol vs same-minute norm, 5-min rvol, surge type, minutes since surge, held-score duration (30 s / 2 m / 5 m), momentum state (DECEL/Quiet/RESUME/ACCEL), distance to day high/low in ATR, sector rvol and sector avg % change, QQQ/SMH 5-min return. Tier 2 (option microstructure, new): ATM spread % of mid, ATM option volume rvol, IV change over 15 min, 15-min C/P premium with coverage % (as a feature with coverage, not a score input). Tier 3 (diagnostic): wall distance %, UW lean, news tone, VIX 15-min change, time-of-day bucket. Drop the 15 s/1 m C/P from the score pending the confirmatory test.

**Model classes, in order; each must earn its place against the previous on OOF Brier skill:**
1. B0/B1/B2 rules.
2. L2 logistic on Tier 1 (what `config.draft.json` already specifies; numpy/sklearn on the mini).
3. `HistGradientBoostingClassifier` (sklearn 1.9 is installed) with monotone constraints on rvol and held-duration, max_depth 3, ≤ 200 trees. Trees earn complexity only if Brier skill improves ≥ 0.01 over logistic with the CI excluding 0.
4. No neural nets, no sequence models: the independent-event count is in the hundreds, not millions.

**Calibration.** Isotonic (or Platt when n < 2,000) fitted on the last 20% of each outer training window; report reliability diagrams by decile and ECE; a trading threshold is set on calibrated p and expected net $ per opportunity under §18 fills, not on hit rate.

**Sample sizes, stated plainly.** Detecting 50% → 55% (two-sided α 0.05, power 0.8) needs ~785 independent events. The page's 15 s overlap and cross-name correlation imply a design effect of roughly 3–5×, so budget 2,500–4,000 snapshots, or ~800 non-overlapping decision events. The "±2 held 30 s" cell produces ~780 holds/day → about 10–15 sessions. The "±2 + surge held 2 min" cell produces ~26/day → 30–60 sessions before it can be called anything. For the option-leg label at p≈0.40 vs 0.46, ~520 independent trades: at 5–10/day that is 50–100 sessions. Promotion rules must respect these numbers, which is why the page's "beat the current score on 10+ days" plan (study 1, steps 5–8) needs a floor on events, not just days.

**Registered experiments to run now (campaign 2 items, dates ≥ 10/21 only):**
- E1 *Drop-C/P confirmatory*: H: removing the 15 s/1 m C/P raises ±2 5-min hit rate ≥ 3 pts; 10 sessions; falsified if the session-block bootstrap 90% CI includes 0. `score_replay_changes.py --drop flow` daily. If supported, change core v1.1 → v1.2.
- E2 *Surge-conditioned hold*: core ±2 held ≥ 30 s AND rvol ≥ 3×; light ±3 held 5 m AND surge; vs B2; 15 sessions min and ≥ 400 events.
- E3 *Momentum gate*: act-on-DECEL-only vs all vs never-on-ACCEL; register ACCEL as the fragility flag.
- E4 *Surge event study with option leg*: after rvol ≥ 3× at day_high/day_low, distribution of `L_opt(10/15/20, −20, 45 m)` by rvol bucket, time-of-day, sector rvol. Needs R2.
- E5 *Bracket grid*: counterfactual net $ per opportunity for X×Y×T on E4 events. This is the Exit Manager's config, chosen offline, not by a bandit (below).

**Exit policy: bandit later, grid first.** A contextual bandit over bracket arms is the right end state (reward = realized net $; context = rvol bucket, momentum state, minutes since surge, spread), but with < 500 trades a Thompson-sampling bandit will mostly explore. Stage 1–2: fixed bracket from E5; log the full option path so every arm is counterfactually scorable. Stage 3: Thompson sampling over K ≤ 6 discrete arms per regime with doubly-robust off-policy evaluation on the logged paths before any arm goes live. Jeffrey's +50% MFE trail stays as an overlay (it has never fired in automation; keep it for the tail).

**Promotion ladder (steps 5–8 the page says are not built):** champion = frozen config hash serving live; challenger = frozen config emitting shadow signals on the same snapshots. Promote iff, over ≥ 15 sessions and ≥ 800 events, challenger beats champion on Brier skill AND net $ per opportunity with CI excluding 0, wins ≥ 11 of 15 sessions, and keeps calibration ECE ≤ 0.05. Demote on the mirror test over a rolling 20 sessions. Every promotion writes a row to `model_registry` with hashes, dates, and the evidence package.

**LLMs: what they should and should not do.** Should: classify news/events into gate flags (earnings, guidance, halt, macro print) with a logged confidence; produce the structured REJECT/NO_TRADE log for Rose/Hal (R7); write and review study code and evidence packages inside the sandbox; summarize anomalies for Jeffrey. Should not: sit in the sub-minute decision path (seconds-to-minutes latency, map 2 §f.5); set thresholds; choose strikes; touch the holdout; read sealed dates. Every LLM output used as a feature is versioned by prompt hash, run at temperature 0, logged, and scored like any other feature (the finbert mis-scores visible on the page are a reminder).

## 5. Data collection and archive

**Capture from today (R5 first, then R6, R2/R1, R7, R15; `RESEARCH_FEED_ADDITIONS.md`).** Every feed that overwrites `latest/` gets a dated append-only copy (R5) — cheapest, highest value, and every day without it is unrecoverable. The data mini already has 1-min SIP bars, 1,045 wall snapshots, 15 s `score_features`, and nightly `score_labels` (map 2 §c reconciliation); formalize those as registered datasets with manifest hashes.

**R2 is the key new stream.** Subscribe OPRA BBO for a fixed ATM set per core name (2 calls + 2 puts nearest spot, 7–21 DTE, re-centered at the open and after any 1% move): 65 core × 4 = 260 subscriptions, well under the ~1,000 cap (UNVERIFIED-3P). Store `{ts, contract, bid, bid_sz, ask, ask_sz}` at every change, parquet partitioned by date/underlying. This is what makes `L_opt` labelable and is the $0 path noted in map 2 §f.2. R1 chain snapshots every 5 min for the 144 sector names complement it (and feed the Alpaca-OI walls already adopted in study 8).

**Decision capture (R7 + the UI, §8).** Table `decisions`: `{decision_id, ts, actor ∈ {jeffrey, rose, hal, shadow:<hash>}, ticker, action ∈ {CALL, PUT, PASS, WATCH}, snapshot_id, score_cfg_hash, rvol_1m, rvol_5m, surge_id, held_s, momentum_state, cp_15s, cp_coverage, wall_dist_pct, lean, news_tone, lane, reason_chips[], confidence 1–3, planned_bracket, contract, quote_at_decision {bid, ask, sizes, age_ms}}`. Table `owner_fills`: `{fill_ts, contract, side, qty, price, decision_id?}`. Table `exits`: `{position_id, ts, reason ∈ {target, stop, time, trail, manual, admin}, mark}` — admin closes are a separate category forever.

**PIT discipline.** Twelve clocks per `program.md` §6 are heavy; enforce three in code: `source_observed_at`, `feature_computed_at`, `label_end_at`. Features join only on `feature_computed_at ≤ decision_at`; labels live in a schema only the Label Bot and `oideval` can write. Persist the collector's `LagHistogram` (R15) hourly: this becomes the `latency_model_ref` every study is waiting for.

**Storage.** Parquet + DuckDB (installed on the mini) partitioned `date=/ticker=`; 1-min bars for 209 names ≈ 50 MB/month; R2 BBO changes ≈ 1–3 GB/month; comfortably inside 3.6 TB. SQLite stays for the registry and decision tables.

**Data-mini / research-mini split.** Data mini publishes; research mini consumes. Owner decision needed now: install Tailscale on the research mini (or open LAN 8787/8788 on the data mini's firewall) so `archive-pull.sh` can run — as of 10/11 the host silently drops traffic (map 2 §b). Nightly pull into `oidarch/archive`; a root-run job copies dates ≥ D (the seal date, set when the path opens) to `oideval` sealed storage and leaves ≤ D−1 for `oidresearch`. The researcher LLM only ever sees dev dates; live scorecards on sealed dates are produced by the evaluator and shown as numbers, never as rows.

## 6. Additional data sources (ranked)

1. **Own OPRA BBO archive (R2) + Alpaca chain snapshots (R1)** — $0 incremental (Algo Trader Plus already paid, UNVERIFIED-S). PIT: exact. Hypothesis: `L_opt` targets are reachable at a rate that beats spread cost after surges. Start today.
2. **Alpaca historical option bars/trades from Feb 2024** (UNVERIFIED-S; historical quotes not confirmed) — $0. Hypothesis: backfill a lower-fidelity `L_opt` on the 82,190 ticker-minutes already archived to get E4 started before R2 matures. Verify the endpoint first (R4).
3. **Databento OPRA targeted `cbbo-1m` + `definition` pulls** — pay-as-you-go $2/GB and $5/GB (UNVERIFIED-S); run `metadata.get_cost` first; expect tens to a few hundred dollars for surge-day windows only. Hypothesis: S3 contract-policy filters and an option-leg backfill around historical surge bars. Standard $199/mo only if monthly pulls exceed that.
4. **FINRA equity short interest API** — free (UNVERIFIED-S); feeds S5 as registered; weak prior for mega-caps, cheap to collect.
5. **SEC EDGAR full-text + `acceptanceDateTime`** — free (UNVERIFIED-3P); first-seen timestamps for the news gate; hypothesis: filings-driven surges behave differently from flow-driven ones.
6. **FRED/ALFRED vintages, Kalshi candlesticks** — free (UNVERIFIED-3P); macro-print gates and S2 arm C/D. Collect-forward; low priority for the intraday style.
7. **ThetaData Standard $80/mo** (UNVERIFIED-S, tier contents conflict) — only if Databento targeted pulls prove too narrow for a multi-year option backfill.

**Do not buy:** FlashAlpha Alpha $1,499/mo (study 6: walls add ~2 pts; the historical replay would be replaying a null); UW dark pool (SKIP per `DATA_SOURCES_EDGE_REVIEW.md`); Silicon Data Pro $998/mo and DRAMeXchange $5,000/yr (daily/weekly series cannot move a seconds-to-hours book); Massive Options Advanced (non-professional-use licensing risk, UNVERIFIED-3P); more X credits (study 13: news tone adds nothing yet). Cut FA spend instead: study 7 shows 1,300–1,500 free calls/day by trimming VIX/oil polling.

## 7. Strategy and edge techniques

"Consistent arbitrage" for this desk means: a positive expectancy per opportunity after the bid-ask spread and commissions, stable across sessions and not dominated by three tickets. The spread is the tax that decides everything: a +10% target on an option quoted 3% wide pays 30% of the target to the market maker on the round trip; at 6% wide the trade is near-zero EV even at 55% hit rate. Every setup below therefore carries the S3 liquidity filter (spread ≤ 5% of mid, OI ≥ 500) as a hard gate.

**Setups to register (all same-day, ATM 7–21 DTE, bracket from E5):**
- **A. Surge continuation (primary).** 1-min rvol ≥ 3× at a new day high/low, 5-min rvol ≥ 2×, held score of matching sign ≥ 30 s, momentum state ≠ ACCEL at entry (enter on the first RESUME or the second surge minute, not the surge minute itself — `program.md` §18 forbids fills inside the triggering bar anyway). Direction = surge direction; calls on day_high, puts on day_low. This is Jeffrey's trade, written down.
- **B. Sector sympathy lag.** When a sector leader prints setup A, the sector strip shows rvol ≥ 1.5× and a laggard in the same group (144-name universe, study 9) has rvol < 1.5× and |% chg| < half the leader's: buy the laggard's option in the leader's direction. Testable immediately on the 1-min archive; the hypothesis is a 2–10 minute propagation lag.
- **C. DECEL reversal (contrarian, lower priority).** Study 5 says the score is right most when DECEL; register "surge exhausted" (second consecutive DECEL after a ≥ 3× bar, price ≥ 1 ATR from VWAP) as a fade with a tighter bracket. Expect lower hit rate, better payoff ratio.
- **D. Scheduled-print reaction.** Macro Bot's calendar + Kalshi odds: enter only after the first full minute post-print, in the surge direction, on the index ETFs and leveraged funds (the only names with sub-2% option spreads at that moment).
- **E. Index gamma regime as a conditioner, not a signal.** The academic evidence (Baltussen et al. 2021; Barbon & Buraschi; UNVERIFIED-3P) is index-level: negative dealer gamma → intraday momentum, positive → reversal. Use SPY/QQQ GEX sign from UW (already paid) as a regime feature for A vs C; never as a single-name wall.

**Avoid.** 0DTE (retail loses on average, Beckmeyer et al., UNVERIFIED-S; the desk already excludes it); far-OTM substitution to fit the debit cap (map 1 §b.4); wall-presses without volume (study 6); buying into pre-event IV (earnings gate); chasing ACCEL (study 5); LLM-sourced news chases (study 13); stacking correlated names in one sector (the 9/18 cohort); scaling size before the independent-event counts in §4 are met.

## 8. UI/UX changes (ranked)

1. **Decision capture on every tile and in a focus drawer** (Call / Put / Pass / Watch, reason chips, confidence) writing the `decisions` row of §5. This is the single highest-value change because it creates the negatives and the owner baseline that no study has. Build before anything cosmetic.
2. **Now lane**: ≤ 5 ranked candidates, rank = rvol × held-score × liquidity (spread ≤ 5%), with Ack/Ignore/Acted; momentum chips with ≥ 60 s hysteresis; `test`/`shadow` chips collapsed (map 3 §d.3).
3. **Tile hierarchy re-rank**: big glyph = rvol only when ≥ 1.5× else % change; score chip small with a held-for timer (`+2 · 48s`); after close, session summary (map 3 §d.1). Visual weight should match evidence.
4. **One freshness grammar**: single age-pill format per datum colored against its own TTL; header chip amber when any gated feed is past TTL; fix the `()` template bug (map 3 §d.2).
5. **Execution cockpit** (Stage 1+): Row 0 = session, feed ages, FA quota %, risk budget (seats, open debit, day P&L vs loss stop), mode PAPER/LIVE, HALT button. Zone A = Now lane + compact heatmap of names with rvol ≥ 1.5× or a held score. Zone B = focus drawer (why-this-fired breakdown, C/P with coverage %, wall distance %, ATM quote with spread % and age) + decision ticket (contract, debit vs cap, bracket +X/−Y/T, seats). Zone C = positions with mark, MFE/MAE, bracket state; decision-log tail. Zone D = collapsible news (time-sorted), momentum tape, macro.
6. **Scorecard page first on the Research tab**: hit rate and Brier by |S| × horizon with n and CI, calibration curve, conditioner lifts, champion vs challenger, promotion-ladder status (map 3 §d.9).
7. Color/shape separation (volume = amber→red; direction = diverging + ▲▼; walls = C/P/γ letters; ≥ 11 px type); closed-market mode; grouped table columns; replay scrub; mobile watch mode of ≤ 8 names — in that order.

## 9. Additional bots

- **Exit Manager** — purpose: run brackets; inputs: positions, R2 BBO, bracket config hash; outputs: exit orders (paper → live), `exit_events`; cadence: event-driven, ≤ 1 s; authority: exits only; pays for itself the first time a +164% MFE does not become +17.8%.
- **Surge Engine v2** — purpose: one deterministic gate with hysteresis and sector aggregation; inputs: 1-min/10 s bars, same-minute norms; outputs: `surge_events`, sector sympathy candidates; cadence: 10 s; authority: none; replaces the `test` chips.
- **Label Bot (extended)** — adds `L_opt` first-passage and bracket counterfactuals; nightly + intraday 15-min catch-up; writes only to the label schema.
- **Scorecard/Promotion Bot** — daily champion vs challenger on sealed dates via `oideval`; outputs the ladder status and a promotion/demotion recommendation Jeffrey signs; nightly; it is what turns research into a live model without a human copying numbers.
- **Latency/Health Bot (R15)** — persists `LagHistogram`, measures decision→order-ready and order→fill; outputs `latency_model_ref`; hourly; authority: trips kill switch 2.
- **Quota Bot** — tracks FA 2,500/day, UW, X spend; reallocates FA from VIX/oil polling to walls (study 7); hourly; authority: downgrade walls to diagnostic at the floor.
- **Event Gate Bot** — merges Hal's catalysts, Macro calendar, EDGAR first-seen, halts into `no_entry_windows`; 5 min; authority: block entries. Cheap, and it encodes the earnings/FOMC gates Jeffrey currently applies by hand (map 1 §f.2).
- **Owner Mirror Bot** — replays Jeffrey's captured decisions against the Shadow Trader daily and reports where they diverge and who was right; nightly; authority: none; it is how the desk learns what his hand knows that the model does not.
- **Cost/Slippage Bot** — compares every modeled fill to realized; nightly; feeds the fill model and kill switch 4.

## 10. Risks and failure modes

- **Overfitting and consumed data.** The page's studies were unregistered searches on 10/19–10/20; those dates are dev-only now. Campaign 1 has zero budget headroom (50/50, 6/6); every §4 experiment is a campaign-2 registration. The biggest practical risk is re-tuning thresholds on the sealed dates by looking at the live scorecard; mitigation is `oideval` isolation plus the event-count floors.
- **Concentration.** 89% of Rose's paper net is three tickets; correlated AI names on one tape are one bet. Per-sector caps and the top-3-removed report are gates, not nice-to-haves.
- **PDT/margin.** Same-day option round trips are day trades. FINRA's amended Rule 4210 reportedly removed the PDT designation effective 2026-06-04 with a firm-level transition to 2027-10-20 (UNVERIFIED-S); each broker may still apply legacy PDT. Until confirmed in writing, assume $25k equity in a margin account; cash accounts avoid PDT but hit T+1 settlement and cannot hold Level 3 at Robinhood.
- **Latency.** LLM agents decide in seconds-to-minutes; the strategy's horizon starts at seconds. Any LLM in the entry path is a design error. Stream gaps and the Tailscale path are single points of failure; broker-side brackets are the backstop.
- **Vendor quotas and licensing.** FA 2,500/day is already over cap on full wall days; Massive's non-professional terms; Robinhood's bot prohibition (UNVERIFIED-3P). Alpaca's ~1,000 subscription cap bounds R2.
- **LLM nondeterminism.** Mitigate by temperature 0, prompt hashes, logged outputs, and scoring LLM features exactly like numeric ones; never let a prompt edit change a threshold.
- **Cost.** New spend proposed: ~$10/mo Tradier (UNVERIFIED-S), tens to low hundreds of dollars of Databento pulls, $0 otherwise; savings available from FA call trimming. The expensive items (FA Alpha, DRAMeXchange, Silicon Data) are explicitly not recommended.
- **Measurement.** Paper at ask-in/mark-out with no fees overstates everything; the Stage gates use modeled then realized costs.

## 11. First 30 days / first 90 days

**Days 1–7.**
1. Owner decision: open the research-mini → data-mini path (Tailscale or firewall rule); set seal date D.
2. Turn on R5 dated snapshots and R6 append bars (already partly live; register manifests).
3. Start R2: 260 ATM OPRA subscriptions; parquet writer; one-day dry count.
4. Persist `LagHistogram` (R15).
5. Ship decision capture (UI item 1) and the `decisions`/`owner_fills`/`exits` tables; Jeffrey starts logging every live trade and every Pass.
6. Register E1 (drop-C/P confirmatory) and E2 (surge-conditioned hold) with thresholds fixed before any new day is scored.

**Days 8–30.**
7. Exit Manager in paper shadow on Jeffrey's captured entries; bracket grid E5 runs on R2 data as it accumulates.
8. Surge Engine v2 with hysteresis replaces the `test` chips; Now lane shipped.
9. Owner decisions: minimum meaningful improvement (Brier skill 0.01; net $/opportunity ≥ half the modeled spread cost), fee and latency assumptions, Databento cap (`metadata.get_cost` first), broker confirmations (Alpaca options paper levels/GTC, Tradier OTOCO options, Robinhood MCP options and TOS; all UNVERIFIED).
10. Implement the real runner and evaluator on the mini (map 2 §b: both are stubs); run S1 on 30m bars to prove the loop at zero cost.
11. Reconcile the paper ledger: signed cashflows, admin closes separated, top-3-removed, fees modeled (family J).
12. Day 30 review: E1 verdict (change core to v1.2 if supported); E2 interim with event counts; Stage 0 gate check.

**Days 31–90.**
13. Fit B0/B1/B2, logistic, and HGB on dev dates with `L_opt` labels (E4); freeze the first champion; Shadow Trader emits paper entries on Alpaca paper (Stage 1).
14. Scorecard/Promotion Bot, Owner Mirror Bot, Event Gate Bot, Quota Bot live; Research tab becomes the scorecard page.
15. Targeted Databento pulls for S3 and surge-day backfill; register S3.
16. Register setups B (sector lag) and C (DECEL fade) as campaign-2 studies; E3 momentum gate verdict at ≥ 400 events.
17. Execution cockpit v1; kill-switch drills; Tradier (or chosen broker) sandbox with OTOCO option brackets.
18. Day 90 review against the Stage 1 → 2 gate: 30 sessions, ≥ 150 shadow tickets, net expectancy CI excluding 0 after modeled costs, concentration tests passed, latency model registered. Only then does a single live contract at ≤ $500 go through the gateway with one-tap approval.

Owner decisions needed, in one list: network path and seal date; minimum improvement thresholds; fee/latency assumptions; Databento cap; broker for live automation and written confirmation of options/bot terms; PDT regime at that broker; whether the live page's scorer code and replay scripts get committed to `oid-research` so they can be hashed into manifests; permission to remove the C/P input if E1 supports it.