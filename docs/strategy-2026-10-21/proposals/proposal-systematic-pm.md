# OID: From Discretionary Desk to Rule-Based Book — A Staged Conversion Proposal

## 1. Diagnosis

**What the edge actually is today.** Strip away the bots and the page, and the desk's demonstrated edge is one human doing three things at once: (a) reading a volume surge on a liquid AI/semi name within seconds of it starting, (b) choosing a near-ATM short-dated option where a 0.3–0.8% underlying move produces +10–20% on the premium, and (c) exiting fast, before the move decays. That is a *reaction-speed and exit-discipline* edge on a high-gamma instrument. It is not a forecasting edge. Nothing in the maps shows a predictive signal that works unconditionally.

**What the 10/20 studies say (MAP 2 §e, Research rows 2–6, 10–13).** Every "all nonzero" hit rate is below 50%: 34% (row 10), 38% (row 3), 38.8% (row 2), 41.8% (row 4), 47.6% (row 12). Bearish extremes were wrong 67% of the time (−2.5 raw → 33%), and the most extreme core reading (±3) got *worse* with a 30 s wait (34.8% → 22.2%). Scores are right most often when momentum is *decelerating* (46.7%) and worst when *accelerating* (31.3%). The honest reading: the scores saturate after the move and chase it. The live C/P flow input, with its small classified coverage, is churn: dropping it lifted ±2 from 50.3% to 55.8% (row 12). Walls are noise at the single-name level: 46.9% vs 44.9% chance (row 6), consistent with the academic literature (MAP 4 §9), which finds dealer-gamma effects at the index/regime level only.

The one conditioner present in every positive cell is **1-minute rvol ≥ 3×**: it triples 15-min breakout odds away from walls (8.7% → 26.7%) and lifts held-score hit rates to 61.5–67.5% (n = 26 and 40, 95% CI roughly 51–81%, clustered on one or two sessions). That is a hypothesis, not evidence, and 10/19–10/20 are now consumed development dates under `program.md` §15.

**What the paper ledger says (MAP 1 §c, §g).** +$14,888 on 57 tickets looks good until you see that Rose's top three winners are 89% of her net, 43 of 57 closes were Jeffrey's batch administrative decisions on eight timestamps, the 9/18 cohort of seven wall-presses closed together on 9/21 (one market move counted seven times), entry = ask / exit = mid / zero fees, and the close-trigger engine has never auto-closed anything. The paper desk is long-calls-only (54/57) with median holds of 24 h; Jeffrey's live style (calls *and* puts, seconds-to-hours) is expressed in no routine and his live fills are in no repo. So the thing that works (Jeffrey's live trading) is unmeasured, and the thing that is measured (paper wall-presses) is not the thing that works.

**Where it is fragile.**
1. *Unrecorded policy.* MAP 1 §f lists eleven decisions that live only in Jeffrey's head, including go/no-go, gate waivers, exit timing, loss acceptance and which wall level "governs." You cannot automate what you have not written down.
2. *No negatives.* No WATCH/NO_TRADE/REJECT log exists (DATA_GAP_REPORT row J; R7 not built), so no classifier can be trained on his selection.
3. *No option-leg label.* Family C is ABSENT (MAP 2 §c). The target variable, "did the option bid reach +10% over my entry ask before my stop," has never been computed for a single event.
4. *Latency unmeasured.* `latency_model_ref` is `OWNER_DECISION_REQUIRED` everywhere; the LLM agent path on the box is seconds to minutes; Jeffrey's holds start at seconds.
5. *Two disconnected systems.* The bots' Soft A wall-press workflow and the live page's Direction/Light/Momentum scores do not reference each other (MAP 1 §g, last bullet). The page is where Jeffrey trades from; the bots trade something else.
6. *One regime.* Sep 10 – Oct 20, 2026, up-tape in AI names. The +/− asymmetry in row 11 is an up-day base rate, not skill.

**Working thesis for this proposal.** The edge to encode is *surge → fast gamma entry → mechanical exit*, with Jeffrey's selection judgment as the thing to be learned from his own logged decisions. The scores stay in shadow until they beat a base rate on 10+ sealed sessions. Walls become a diagnostic feature, not a trigger.

## 2. Scaling strategy

Four stages. Each has one gate, one metric, one owner decision. Nothing advances on vibes; nothing advances on n < 30 independent sessions.

| Stage | What runs | Who places orders | Gate to leave the stage |
|---|---|---|---|
| **S0 Discretionary + capture** (now → day 30) | Jeffrey trades live as today; every decision, pass and exit is captured as a structured row (§8 decision ticket); bots produce candidates in shadow | Jeffrey, manually | ≥ 20 sessions of complete decision rows (entries, passes, exits with reason chips); ≥ 100 option-leg labels computed; latency histogram persisted |
| **S1 Assisted** (day 30 → ~90) | Cockpit ranks a "Now" lane; a pre-filled ticket (contract, debit, bracket) is one click; bracket exits are *alerted* with a one-click close; shadow policies log what they *would* have done | Jeffrey, one click, paper broker in parallel | Shadow policy P1 (surge-conditioned, §7) shows net expectancy per eligible opportunity > 0 after modeled fees/slippage on ≥ 30 sessions, session-block bootstrap 90% CI excluding 0; Jeffrey's own logged hit rate on the same events is reported alongside |
| **S2 Supervised auto** (~day 90 → 180) | Bot submits *paper* orders to Alpaca paper (Level 3 automatic, MAP 4 §1, UNVERIFIED-S) on P1 with a 1-contract cap; exits are mechanical (bracket emulated client-side); Jeffrey can veto within a 10 s window and kills any time | Bot, paper; then bot, live with $1 risk unit = 1 contract, ≤ 3 seats | Paper and then live-small: ≥ 40 sessions, realized P&L per opportunity within the bootstrap CI of the shadow forecast (no "paper-to-live decay" beyond modeled slippage); zero gate violations; kill switch exercised at least twice in drills |
| **S3 Autonomous within budget** | Bot trades the registered policy within a daily loss limit and seat budget; Jeffrey sets policy and budget weekly, does not approve tickets | Bot | Monthly re-certification: rolling 60-session expectancy > 0 and drawdown within the registered envelope; any breach reverts to S2 |

**Measured how.** One metric throughout: *net expectancy per eligible opportunity* (program.md §17–18 fills: buy at ask after `decision_at` + measured latency, sell at bid at exit + latency), reported with B0 (same-window base rate) and B1 (QQQ 5-min return) baselines, Brier for the direction component, top-3-contributor share (must be < 50%), and a session-block bootstrap. Hit rate alone never gates anything.

**What gets automated first and why.**
1. *Exits* (S1). Jeffrey's exit rule is already nearly mechanical (+10–20% target, time stop, MFE trail). Mechanical exits remove the "awaiting a user ping" losses (AMZN 260C bled to −61%, MAP 1 §f.4) and make every entry comparable. They are low-risk to automate because a wrong exit costs basis points, not a position.
2. *Negative decisions* (S0). Logging passes costs nothing and creates the training set.
3. *Candidate ranking* (S1). The cockpit decides *what Jeffrey looks at*, not what he does. That is where the surge conditioner belongs.
4. *Entries* last (S2). Entries are where the unmeasured judgment lives.

**Keeping Jeffrey the policy owner.** He owns `policy.yaml` (gates, thresholds, universe, budgets), versioned in git with a signed changelog, which replaces the "human changelog" of promoted never_again rules (MAP 1 §f.8). Bots read it; no bot writes it. Every override he makes in S0–S1 is a row in `overrides` with a reason chip, so his waivers become data rather than exceptions. His weekly job in S2+ is policy review against the scorecard (§8 item 9), not ticket approval.

## 3. Bot architecture

Keep the existing roster; change the authority lines and insert a deterministic execution layer between any LLM and any broker. Principle: **LLMs produce candidates, explanations and summaries; deterministic code produces orders.**

| Bot | Owner feed(s) | Deterministic vs LLM | Authority after conversion |
|---|---|---|---|
| **Collector** (data mini, Alpaca) | 1-min SIP bars, OPRA trades/BBO for subscribed contracts, score_features (15 s), surge events, chain snapshots (R1), lag histogram (R15) | 100% code | Publishes; never decides |
| **Signal Engine** (data mini, new; absorbs the page's scorers) | `signals` table: per ticker per 5 s: rvol, held-score + duration, momentum state, wall distance, C/P + coverage, conditioner flags | 100% code; versioned configs (`core v1.1`, `light-v1.0` …) | Emits candidates to the Now lane and to Rose/Hal |
| **Rose** (short-term) | `rose-candidates`, ticket rationale, paper ledger | LLM: reads candidate packet + news/X context, writes a structured `decision` with reason chips and confidence; **code**: gate check (`policy.yaml`) and contract selection | S0–S1: proposes; S2+: submits to Execution Gateway for *registered policy* trades only; every LLM free-text field is advisory |
| **Hal** (catalyst / longer) | catalysts, LEAP queue, marks | LLM for catalyst reading; code for DTE/duration reviews | Stays paper until Hal's book has its own ≥ 40-session expectancy (profit factor 1.75 on 26 tickets with 13/13 W/L is not a book) |
| **Chart / Macro / X Summarizer / News (Peanut)** | as today | LLM summarizers | **Soft only**, as today; outputs become *features* in `signals` (macro −2..+2, news tone, X score), tested by add-one studies, never gates |
| **Research Bot** (research mini) | registry, studies, verdicts | Code runner/evaluator; LLM drafts study specs and reads results | No deploy authority (program.md §22); emits `PAPER_VALIDATED` packages only |
| **Data Ops** | source health, quotas, lag | Code with LLM daily summary | Can flip feeds to `STALE_CARRY` and *halt the Execution Gateway* on data-health failure (one of the kill switches) |
| **Execution Gateway** (new, box or data mini) | `orders`, `fills`, `positions`, `risk_state` | **100% deterministic code** (Python, alpaca-py); no LLM in the process | The only process holding broker credentials |
| **Risk Monitor** (new) | `risk_state`, daily P&L, seat count, open debit, consecutive losses | 100% code | Hard kill; cannot be overridden by any bot; Jeffrey re-arms manually |

**Execution/risk layer (the Gateway contract).** An order request is a typed row: `{policy_id, policy_version, snapshot_id, ticker, right, occ_symbol, side, qty, limit, bracket:{tp_pct, stop_pct, time_stop_s}, decision_at, feature_available_at}`. The Gateway rejects anything that fails: quote age ≤ 120 s (keep the desk rule, but measured at the Gateway, not by the agent), `policy_version == current`, debit ≤ $5,000 (keep), seats (Rose ≤ 8, total ≤ 15), chase gate, earnings gate, OPEX gate, re-seat bans, daily loss limit, consecutive-loss limit (3 → pause 30 min), per-name cooldown (no re-entry within 10 min of a stop). Brackets: Alpaca has no native options bracket (MAP 4 §1, UNVERIFIED-S), so the Gateway emulates OCO client-side: a resting limit at +target and a software stop evaluated on every BBO tick with a market-to-close fallback at time stop. Log every evaluation; the emulated bracket's own latency is a measured number.

**Kill switches, in order of reach.**
1. `risk_state = HALT` file watched by the Gateway (any bot or Data Ops can set it; only Jeffrey clears).
2. Daily loss limit and max-open-debit limits in the Gateway (hard-coded ceilings that `policy.yaml` can only lower).
3. Broker-side: Alpaca paper/live account-level "disable trading" and position-close script runnable from Jeffrey's phone.
4. Physical: launchd job disable on the data mini; Gateway refuses to start without a fresh `arm` token (24 h).

**Broker choice.** Robinhood is not the execution venue for bots: its only sanctioned agent path is the Agentic MCP, stocks-only at launch with options "coming soon," trades in a separate account, and bots are reportedly prohibited by the customer agreement (MAP 4 §2, all UNVERIFIED). Keep Robinhood for Jeffrey's manual trading if he likes it. For the bot: **Alpaca** first, because the data pipeline already lives there, paper accounts get Level 3 automatically, alpaca-py is verified, and the same symbols/feeds drive signals and fills (no symbol-mapping bugs). Confirm before S2 (UNVERIFIED-S): options GTC/day TIF, no trailing stop, `mleg` support, and Alpaca's current PDT regime after the June 2026 FINRA change. Fallback is **Tradier** (native OTOCO with option legs, $10/mo flat options plan) if emulated brackets prove too slow; IBKR only if the book outgrows both.

## 4. Models

**What to model.** Two separate questions, two separate models; never confuse them (program.md §17).
- *Opportunity model* (UNDERLYING track): P(underlying moves ≥ k·ATR_1m in direction d within H minutes | state at `decision_at`), for H ∈ {2, 5, 15, 30}.
- *Executable model* (OPTION track): P(bid of the chosen contract reaches ≥ +10% / +20% over entry ask before (a) a −X% stop, (b) a time stop, within the session). This is the label Jeffrey's style needs and the one that cannot be computed today.

**Labels.** Per candidate event (every surge event, every score change, every Jeffrey decision including Pass): `{snapshot_id, decision_at, contract_at_decision (nearest 0.50Δ, 3–21 DTE call/put), entry_ask, entry_ask_size, latency_s, mfe_bid_pct, mae_bid_pct, t_to_+10, t_to_+20, t_to_stop, exit_policy_outcomes[tp10, tp20, stop25, time30m, trail50]}`, plus underlying forward returns at 2/5/15/30 m and close, B0 same-window base rate per name/day. Labels are computed nightly by `oideval`-side code, never visible to the feature side (MAP 3 §e storage rule).

**Features (registered, with `feature_available_at`).** Volume: 1-min rvol vs same-minute norm, 10 s pace, surge flag and age, day-vs-norm. Price: distance to day high/low, 5 s return over 30 s/2 m, ATR_1m. Micro: NBBO spread % of mid, ask size, option volume vs OI. State: momentum state (DECEL/QUIET/RESUME/ACCEL) with hysteresis, held-score duration, score value. Context: sector rvol, QQQ/SMH 5-min return, market-momentum gauge, VIX level/change, time of day. Soft: UW lean (+age), news tone (+age), X score, macro ±2. Walls: distance % to CW/PW/flip, wall age, OI at strike (diagnostic; expected to wash out per row 6).

**Model classes, in order.** (1) Hand rules frozen as `policy v0` (the surge-conditioned rule in §7), to establish the baseline the models must beat. (2) L2 logistic regression, as `config.draft.json` already specifies, with Platt calibration on the last 20% of each outer window. (3) Shallow gradient-boosted trees (depth ≤ 3, ≤ 200 trees) only once ≥ 60 sessions exist. No deep models, no sequence models: n is in the low thousands of *independent* events at best. Walk-forward by session with purge by `label_end_at` and ≥ 2-session embargo; many names reacting to one tape are one observation, so bootstrap by session block.

**Calibration.** Reliability diagrams by score bucket with n; a model is "calibrated" when the 10-session rolling bucket hit rate is within ±5 pts of the forecast for every bucket with n ≥ 50. Trade only buckets whose *executable* expectancy after fees is positive; the row-11 result (+2.0 raw → 58% at 5 m) is an underlying number and says nothing about fills.

**Promotion ladder (makes rows 1 steps 5–8 concrete).** `DRAFT → REGISTERED (hypothesis, thresholds, baselines, dates frozen in registry) → DEVELOPING (research mini, dev dates only) → FROZEN (hash) → SHADOW (runs live on the data mini, writes forecasts to `shadow_forecasts`, zero authority) → CHALLENGER (shadow ≥ 10 sessions; compared against incumbent on identical events; promote only if Brier skill ≥ 0.01 *and* executable expectancy ≥ incumbent + registered margin, bootstrap CI excluding 0) → INCUMBENT (drives the Now lane / S2 orders) → RETIRED`. Only Jeffrey flips CHALLENGER → INCUMBENT, by editing `policy.yaml`. Shadow forecasts are logged for every challenger, so there is always a counterfactual for the incumbent.

**What LLMs should and should not do.** Should: write study specs from a template; summarize news/X into typed tone scores with evidence spans; explain why a candidate fired in plain English for the focus panel; draft the daily scorecard narrative; review Jeffrey's logged reasons and propose new *features* (not rules). Should not: compute a number that gates an order; choose a contract; decide an exit; be in the latency path of a seconds-horizon entry; see sealed dates or label columns. LLM nondeterminism (§10) is tolerable for candidates and prose; it is unacceptable for anything a fill depends on.

## 5. Data collection and archive

**Capture from today (zero cost, all on the data mini; R5/R6/R7/R15 from `RESEARCH_FEED_ADDITIONS.md`).**
1. R5: dated append-only copies of everything that currently overwrites `latest/` (fa-levels, uw-*, rh-quotes, macro, peanut, hal-marks). Every day without this is unrecoverable.
2. R6: 1-min SIP bars for the 209 names + QQQ/SPY/SMH/SOXX (already partially there: 82,190 ticker-minutes).
3. R2: streamed OPRA BBO + trades for a fixed ATM set (±2 strikes, nearest two expiries) on the 65 core names, rolled daily; budget the ~1,000 subscription cap as 65 × 2 × 4 = 520 contracts, leaving headroom for sector names after a surge. This is the option-leg label source.
4. R1: chain snapshots every 5 min RTH for the 144 sector names (BBO + size, 3–45 DTE, ±15% strikes) for OI walls and label fallback. Dry-count one day first against the data plan's REST limits.
5. R7: the decision log (§8) for Jeffrey, Rose, Hal and every shadow policy, including Pass/Watch/Reject.
6. R15: persist the collector `LagHistogram` and a `decision_at → gateway_received → broker_ack` chain for every ticket.
7. Jeffrey's live fills: daily export from Robinhood (even by screenshot-to-CSV if there is no API) into `owner_fills` with timestamps; this is the only ground truth for the style being scaled.

**PIT discipline.** Every row carries program.md's clocks (`source_observed_at`, `feature_available_at`, `decision_at`, `label_end_at`, `label_available_at`). Features are computed by a job that is forbidden from reading anything with `label_available_at > now`. Replays must be flagged `OBSERVED_DESK_REPLAY` (from the archive) vs `RECONSTRUCTED_PROVIDER_REPLAY`; the research mini accepts only the former for executable studies.

**Storage.** Parquet partitioned by `date/feed` written by one writer per feed (keep the one-writer rule); DuckDB over Parquet on both minis; the SQLite registry stays for budgets/manifests. Sizes are small: 1-min bars ≈ 70 MB/yr; OPRA BBO for 520 contracts is the only heavy stream (tens of GB/yr uncompressed; store 1 s-aggregated BBO plus every trade, keep raw for 30 days).

**Data-mini / research-mini split.** Data mini = producer, hot store, serving the page and the Gateway. Research mini = sealed consumer. Build the missing network path (Tailscale on the research mini; `archive-pull` as `oidarch` over SSH with a read-only key, nightly 5 PM PT), then root-run copy of dates ≥ D into `sealed/` that `oidresearch` cannot read. Future dates are the only uncontaminated holdout this desk has (MAP 2 §f.1); D is set the day the pull first runs. Nightly: data mini computes labels → research mini pulls features and labels into separate roots → evaluator runs challengers → scorecard published back to the page. The page never reads the research mini.

**Labeling pipeline.** Nightly `score_labels` extended with the option-leg labels (§4) from R2/R1, with the exit-policy counterfactuals (tp10/tp20/stop/time/trail) so Jeffrey's manual exits and the mechanical brackets are compared on identical events.

## 6. Additional data sources

Ranked by expected value for the +10–20% same-day style, given what already exists. Costs are from MAP 4 and `DATA_SOURCES_EDGE_REVIEW.md`; everything vendor-priced is UNVERIFIED-S unless noted.

1. **Own OPRA BBO/trade archive via Alpaca (R2/R1)** — $0 incremental. PIT: native (observed desk replay). Hypothesis: the executable label exists; +10% targets are reachable within 15 min after a ≥3× surge at a measurable rate. Prerequisite for everything else.
2. **Latency instrumentation (R15)** — $0. Hypothesis: the agent decision path is > 30 s and kills seconds-horizon edge; the Gateway path is < 2 s.
3. **Jeffrey's live fills** — $0. Hypothesis: his realized expectancy is positive after fees, and it concentrates in a specific state (surge + first 90 min, say). Without this there is nothing to scale.
4. **Databento OPRA targeted historical pulls** (`definition` + `cbbo-1m` or `cmbp-1` around the 325 surge ticker-days already archived) — tens to low hundreds of dollars pay-as-you-go (MAP 2 §d), or $199/mo Standard for 12 months top-of-book. PIT: vendor replay, well-timestamped. Hypothesis: the surge → option-mark response seen forward since 9/25 holds on 2024–2026 history, turning a 20-session forward study into a 500-session one. Buy only after R2 is running and the label definition is frozen (so the pull is targeted).
5. **Kalshi (and Polymarket) macro/event prices** — free, collect-forward + candlestick backfill. PIT: good. Hypothesis: moves in event probabilities within the session lead sector rvol (S2 family D).
6. **FINRA short interest + UW borrow (S5)** — free. Weak for mega-caps by the repo's own prior; cheap to register; swing-horizon only.
7. **Korea 10/20-day semi exports (data.go.kr)** — free, ~36 events/yr. Hypothesis: a first-print surprise drives next-session SMH rvol. Campaign-2 item; the series endpoint is UNVERIFIED.
8. **UW analyst-revision feed** — already paid; register as a feature inside S1.
9. **ThetaData Standard ($80/mo)** — a cheaper historical-options fallback if Databento pulls grow; otherwise skip.

**What NOT to buy.** FlashAlpha Alpha ($1,499/mo) for replay: the desk's own wall-magnet study says walls carry no information at the single-name level, and the thing worth replaying (volume and option marks) comes from Alpaca and Databento for a fraction of the price. Instead, implement the row-7/8 savings (trim VIX/oil polling, switch to UW GEX or Alpaca-OI walls) and consider dropping to Basic. Massive options plans: non-professional-only licensing is a real exposure for a desk. UW dark pool (SKIP per the review). DRAMeXchange ($5k/yr), Silicon Data Pro ($998/mo), Estimize: all swing-horizon fundamentals with no path to a same-day option exit; revisit only if Hal's book earns its own budget. More X credits: the add-one news study showed nothing and the pool is a shared cost sink.

## 7. Strategy / edge techniques

"Consistent arbitrage" for this desk means: *a repeatable positive expectancy per eligible opportunity, in a defined state, with a mechanical exit, measured after fees and slippage, that survives a fresh month.* It is not riskless; it is a small, positive, frequently-sampled edge that compounds only because it is traded identically every time. Everything below is a pre-registered hypothesis with a frozen rule and a stated kill criterion.

**P1 — Surge continuation (primary; the rule to freeze now).** Trigger: 1-min rvol ≥ 3× same-minute norm *and* bar closes within 0.15% of day high (calls) / day low (puts) *and* not in ACCEL state for ≥ 60 s (hysteresis; row 5 says ACCEL is the worst state) *and* 09:35–11:30 or 13:00–15:30 ET. Contract: nearest 0.50Δ, 3–14 DTE, NBBO spread ≤ 6% of mid, ask size ≥ 10. Entry: limit at ask, cancel if unfilled in 5 s. Exit: +12% target, −20% stop, 30-minute time stop, trail to breakeven after +8%. Kill: 30-session expectancy ≤ 0 or top-3 share > 50%.

**P2 — Held-score + surge (secondary).** Core ±2 held ≥ 30 s with a surge in the last 2 min (61.5%, n = 26) and Light ±3 held 5 min with surge (67.5%, n = 40). Same contract/exit rules. Explicitly tested *with* and *without* the C/P input (row 12). This is the page's own hypothesis; it gets its 10 sessions in shadow before any ticket.

**P3 — Opening-range gamma scalp.** For the 20 highest day-norm names: first 15-min range; break with rvol ≥ 2× → P1 contract rules, +10% target, 20-min time stop. Tests whether the edge is specifically a time-of-day effect.

**P4 — Decel fade (contrarian).** DECEL state after a ≥ 5× surge away from any wall and extended ≥ 1.5 ATR_1m from VWAP: buy the *opposite* right, +10% target, −15% stop, 15-min time stop. Row 5's DECEL 46.7% suggests the tape pauses; this tests whether it reverts. Expected to fail; cheap to register.

**P5 — Event-anchored surge.** Same as P1 but only when a Benzinga/EDGAR first-seen item for the name is < 3 min old. Tests whether news-anchored surges continue more than unexplained ones (add-one row 13 was flat for *score* inputs; this is a gate, not a score input).

**P6 — Sector sympathy.** When ≥ 3 names in one of the 16 groups surge within 2 min, enter the group's highest-day-norm name that has not surged yet. Tests the market-momentum gauge as an entry.

**What to avoid.** 0DTE on index products: retail loses in aggregate and the spread tax is the edge (MAP 4 §9). Far-OTM substitution to fit the $5k cap (AMD 720C at 15.5% OTM; already prohibited). Wall-press entries as a *trigger*: run them only as a diagnostic overlay on P1. Selling premium or spreads to "add income": different risk engine, different evaluation, not this desk's edge. Holding past the time stop "because the thesis is intact": that is Hal's book, not Rose's. Stacking correlated names on one tape: cap concurrent seats per sector group at 2.

## 8. UI/UX changes

Ranked by impact per unit of effort; items 1–5 are the S0/S1 cockpit and build on MAP 3 §d.

1. **Decision ticket with structured capture** (the single most valuable change). On every tile / focus panel: Call · Put · Pass · Watch. Writes `{ts, ticker, actor, action, snapshot_id, score+version, rvol, C/P+coverage, wall distances, lean+age, news tone, lane, reason_chips[surge|wall|flow|news|sector|gut], confidence 1–3, planned_bracket, contract, debit}`. Exit requires a reason chip at exit time; administrative closes get their own category. This turns Jeffrey's day into the training set.
2. **Now lane**: ≤ 5 ranked candidates (rank = rvol × held-duration × 1/spread%), each with Ack / Ignore / Acted; ignored-but-ran candidates become "missed" labels. Momentum flips get ≥ 60 s hysteresis; `test`/`shadow` chips collapse into a muted lane.
3. **Tile hierarchy re-rank**: big glyph = rvol only when ≥ 1.5×, else % change; score chip demoted to a corner mark with a held-for timer (`+2 · 48s`); surge gets the strongest color; closed-market tiles switch to session summary (kills the sea of `0.0×`).
4. **One freshness grammar**: single age-pill format per datum colored against its own TTL; header chip amber when any gated feed is past TTL; fix the `()` template defect and the five clock formats.
5. **Focus panel ("why this fired")**: per-input score contribution, C/P with coverage %, wall distances in %, lean + age, news tone + source, 5 s bars for 5 min, three conditioner checkboxes (rvol ≥ 3×, held ≥ 30 s, not-ACCEL), and the pre-filled ticket.
6. **Row-0 status bar / risk meter**: session · feed ages · FlashAlpha quota % · open debit vs cap · seats · day P&L vs loss limit · mode PAPER/LIVE · Gateway state (ARMED/HALT).
7. **Positions zone** with mark, MFE/MAE, bracket state, time-to-stop, one-click close; replaces the 60 s here.now blotter for intraday use.
8. **Color/shape separation** for CVD and glyph size ≥ 11 px; volume = amber→red ramp only; direction = diverging with ▲▼.
9. **Scorecard-first Research tab**: today vs 10-session hit rate by |S| × horizon with n and CI, calibration curve, conditioner lifts, promotion-ladder status, then the studies table.
10. **Replay/scrub** of one ticker from the 15 s feature table overlaid with the decision log (for post-mortems and for Jeffrey to annotate missed trades).
11. **Mobile watch mode**: ≤ 8 names, one line each, plus the HALT button.

Execution cockpit layout: Row 0 status; Zone A (left 60%) Now lane + compact heatmap showing only rvol ≥ 1.5× or held-score names; Zone B (right 40%) focus panel + ticket; Zone C positions + decision-log tail; Zone D collapsible news/momentum/macro.

## 9. Additional bots

| Bot | Purpose | Inputs | Outputs | Cadence | Authority | Why it pays |
|---|---|---|---|---|---|---|
| **Execution Gateway** | Only process that talks to the broker; enforces gates and emulated brackets | typed order requests, policy.yaml, risk_state, live BBO | orders, fills, positions, rejections with reason | event-driven, < 1 s | Places orders for registered policies only | Removes LLMs and humans from the fill path; every rejection is a logged gate decision |
| **Risk Monitor** | Daily loss limit, seat/sector caps, consecutive-loss pause, data-health halt | fills, positions, Data Ops health | risk_state (ARMED/PAUSE/HALT), alerts | 1 s | Hard kill, human re-arm | One bad hour cannot become a bad month |
| **Shadow Trader** | Runs every FROZEN/SHADOW/CHALLENGER policy on live events with the same contract/exit rules, no orders | signals, OPRA BBO, policy versions | shadow_forecasts, counterfactual P&L per policy | 5 s | None | Produces the challenger comparison that gates every promotion; free counterfactuals for Jeffrey's own trades |
| **Labeler** | Nightly option-leg labels and exit-policy counterfactuals | R2/R1 archive, decision log, fills | score_labels, option_labels, owner_fill_labels | nightly 5:30 PM PT | None (eval side) | Converts raw capture into the target variable; nothing trains without it |
| **Scorecard Bot** | Daily/10-session scorecard, calibration, top-3 share, latency summary, with a short LLM narrative | labels, shadow_forecasts, fills | scorecard.json + Research tab | nightly | None | Makes promotion decisions evidence-based and visible to Jeffrey in 2 minutes |
| **Contract Selector** (library inside Gateway) | Deterministic choice of strike/expiry under liquidity and debit rules; rejects far-OTM substitution | chain snapshot, NBBO, OI, debit cap | occ_symbol or NO_QUALIFYING_CONTRACT | on request | None | Removes the single biggest discretionary distortion in the paper ledger (MAP 1 §f.5) |
| **Quota Steward** (extends Data Ops) | Allocates FlashAlpha/X/UW budgets per bot per day; switches walls to Alpaca-OI when FA budget < 20% | api-quotas, call logs | per-bot caps, STALE_CARRY flags | 5 min | Can throttle any bot's vendor calls | Row 7 shows a full wall day over cap; this prevents silent STALE_CARRY days |
| **Fill Reconciler** | Matches broker fills to tickets, computes realized vs modeled slippage, flags sign/arithmetic errors | broker API, tickets | reconciled ledger, slippage model | every 5 min + EOD | None | Fixes the ledger defects in MAP 1 §g and produces the slippage parameter every study needs |
| **Post-Mortem Bot** (LLM) | Weekly narrative over missed/ignored candidates, overrides, and worst 5 trades; proposes *features*, not rules | decision log, labels, scorecard | weekly memo + proposed study drafts | weekly | None | Replaces the human changelog with evidence-linked proposals Jeffrey can accept into policy.yaml |

Rose and Hal stay; Chart/Macro/X/News are demoted explicitly to feature producers (as they already are in spirit).

## 10. Risks and failure modes

- **Overfitting and selection.** Two correlated sessions, overlapping 15 s snapshots, and a researcher who has seen everything. Mitigation: registration before search, session-block bootstrap, sealed future dates, Brier vs B0, top-3 share reported, campaign budgets enforced by `budget.py`. Any study on 10/19–10/20 is exploratory by definition.
- **Concentration.** 89% of Rose's net in three tickets; cohorts closed together. Mitigation: per-sector seat cap of 2, top-3 share < 50% as a promotion gate, expectancy reported per opportunity not per book.
- **Regime.** One up-tape in AI names; puts never traded in paper. Mitigation: no S2 before the book has traded through at least one −5% QQQ week; symmetric call/put policies registered from the start.
- **PDT / margin.** FINRA replaced PDT with intraday-margin effective June 4, 2026, but brokers may keep legacy rules until Oct 2027 (MAP 4 §4, UNVERIFIED-S). A seconds-to-hours options book is 100% day trades. Mitigation: confirm Alpaca's regime in writing before S2; keep equity above $25k regardless; cash-account T+1 settlement is a hard throughput limit if a margin account is not used.
- **Latency.** The agent path is seconds to minutes; Jeffrey's holds start at seconds; emulated brackets add their own delay. Mitigation: Gateway on the data mini next to the stream; measured `latency_model_ref`; no policy with a target horizon < 5× measured latency.
- **Vendor quotas and single points of failure.** FA cap breached on full wall days; X pool shared; Alpaca ~1,000-contract cap (UNVERIFIED); one data mini publishes everything. Mitigation: Quota Steward, Alpaca-OI walls, stream-subscription budget, Data Ops halt on health failure, nightly archive to the research mini as a cold copy.
- **LLM nondeterminism and prompt drift.** The same packet yields different candidates on different runs; prompt edits silently change behaviour. Mitigation: LLM outputs are advisory and typed; prompts are versioned and hashed into the decision row; no LLM in the order path.
- **Execution risk.** No native options bracket at Alpaca; a stop that fails to fire in a gap is a real loss. Mitigation: 1-contract sizing in S2, daily loss limit, broker-side close-all script, drills.
- **Broker/ToS.** Bots on Robinhood may breach the agreement; Massive plans are non-professional. Mitigation: Alpaca/Tradier for bots; read the agreements.
- **Cost creep.** Current run-rate (FA $299 + Alpaca $99 + UW + X) is fine; the temptation is FA Alpha ($1,499) and Databento Unlimited. Rule: no new subscription without a registered study that names the hypothesis it unblocks.
- **Measurement debt.** No NAV, no R, no fees, sign errors. Nothing in §2 advances until the ledger is re-stated with signed cashflows, fees and administrative closes separated.

## 11. First 30 days / first 90 days

**Days 1–7 (capture starts; owner decisions marked OD).**
1. Turn on R5 append-only snapshots and R15 lag persistence on the data mini (Data Ops). OD: none.
2. Subscribe the fixed ATM OPRA set for the 65 core names (R2); dry-count the R1 chain snapshot budget. OD: approve the 520-contract allocation.
3. Ship the decision ticket (§8 item 1) in paper mode, writing to a `decisions` table keyed to `snapshot_id`; Jeffrey uses it for every live trade and every pass for the rest of the month. OD: commit to logging passes.
4. Start a daily `owner_fills` export. OD: how (CSV, screenshots, or a Robinhood statement parser).
5. Freeze P1 and P2 as registered hypotheses in the registry with thresholds, baselines and D = the first archive-pull date. OD: sign the registration.

**Days 8–14.**
6. Install Tailscale on the research mini; build `archive-pull` as `oidarch`, root-run `sealed/` copy; re-run `20-verify.sh`. OD: approve the network path.
7. Restate the 57 paper tickets with signed cashflows, fees ($0.65/contract assumption), administrative closes separated, top-3 removed; publish as the baseline scorecard.
8. Implement the FA savings (row 7): VIX/oil polling cut, Alpaca-OI walls for sector names. OD: FA plan tier decision.

**Days 15–30.**
9. Labeler v1: option-leg labels and exit counterfactuals (tp10/tp20/stop/time/trail) nightly from R2.
10. Shadow Trader v1 running P1/P2 with full contract/exit rules; Scorecard Bot publishing to the Research tab.
11. Now lane + tile re-rank + freshness grammar on the live page.
12. Day-30 review: ≥ 20 sessions of decisions, ≥ 100 option labels, latency histogram. OD: proceed to S1 or extend S0.

**Days 31–60 (S1).**
13. Execution Gateway v1 against Alpaca *paper* with emulated brackets; Contract Selector; Risk Monitor with HALT; kill-switch drill. OD: confirm Alpaca options TIF/bracket/PDT facts (UNVERIFIED-S) in writing; open the account.
14. Mechanical exit alerts with one-click close on Jeffrey's positions; compare his exits to the bracket counterfactuals weekly.
15. First Databento targeted pull around the archived surge ticker-days once the label definition has held for 20 sessions. OD: approve spend (expected < $300).
16. Research mini campaign 1 runs S1 on 30-min bars to prove the runner/evaluator; register drop-C/P (row 12) as confirmatory on new dates.

**Days 61–90.**
17. P1 paper trading through the Gateway, 1 contract, ≤ 3 seats; weekly scorecard vs shadow forecast; fill reconciler live.
18. Challenger process: logistic model over P1 features enters SHADOW; promotion rules as in §4.
19. Day-90 gate review against §2 S1 criteria. OD: authorize S2 live-small on Alpaca (or stay in paper), set the daily loss limit (proposal: 2% of sleeve capital, with sleeve capital finally defined), set seat caps, sign `policy.yaml` v1.

Owner decisions needed throughout, collected: sleeve capital and NAV definition; broker for bots and account type; FA tier; the 520-contract allocation; registration signatures on P1–P6; the daily loss limit; who can set HALT and who clears it; and the standing rule that no subscription is bought without a registered study naming it.