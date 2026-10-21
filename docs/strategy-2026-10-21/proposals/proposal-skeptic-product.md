# OID: Scaling a Discretionary Options Desk Without Blowing It Up

## 1. Diagnosis

**What the edge actually is today.** The only P&L anyone can point to is Jeffrey's own hand: fast call/put buys on volume-and-flow reads, exited at +10–20% on the option, same day. Those fills are in no repo (map-desk-ops §f.10). Everything that *is* measured is a different system: a long-calls-only paper desk (54/57 tickets) run by Rose/Hal on wall-press setups with 24 h median holds, and a live page whose scores are near coin-flips.

**What the ledger says.** +$14,888 on $73,384 recycled debit looks like +20%, but: Rose's top 3 tickets are 89% of her net; 43 of 57 closes were batch owner events on eight timestamps (map-desk-ops §c); 7 Hal entries were stamped 9:15 PM; zero fees or slippage; entry at ask and exit at mark; two credit spreads tagged `win_exit` with negative cash; MFE is a 5–15-min sampled max so the trail/giveback stats are not executable. The 9/18 cohort of seven wall-presses closed together on 9/21 — one market move counted seven times. Hal's profit factor of 1.75 with median +0.4% is noise. The desk's own audit is right: this sample cannot support a return target, and it certainly cannot license a bot.

**What the 10/20 studies say.** Every "all nonzero" hit rate is below 50% (34%, 38%, 38.8%, 41.8%, 47.6%). The raw direction score correlates −0.39 with close return on its one live day (study 10). ACCEL state is the worst bucket (31.3%) and DECEL the best (46.7%, study 5): the score fires *after* the move. The only conditioner that shows up in every positive cell is **1-min rvol ≥ 3×** (study 6: away-from-wall 15-min breakout 8.7% → 26.7%; studies 2–3: +surge cells at 67.5%/61.5% with n = 40/26). Walls are not magnets (46.9% vs 44.9%). The C/P flow input appears to hurt (drop-one 50.3% → 55.8%, study 12). All of this is one or two correlated sessions, hit rate instead of Brier vs. a base rate, 15 s snapshots counted as independent n, and the researcher saw everything — so 10/19–10/20 are consumed dates under `program.md` §15 (map-research §e).

**Honest reading.** The desk's demonstrated, robust edge is: *a human recognizing a genuine volume event on a liquid AI/semis name and getting out fast.* The volume part is measurable and the studies support it; the "recognizing" and "getting out" parts live in Jeffrey's head and have never been logged at decision time (map-desk-ops §f.1–5). The scores, walls and flow pills that dominate the page's visual weight are, on current evidence, decoration (map-ui §b: "visual weight is inversely proportional to evidence").

**Where it is fragile.** (a) Concentration: three tickets and one cohort. (b) One regime: Sep 10–Oct 20, an up-tape in AI names; the +/− asymmetry in calibration (core −2.5 raw → 33% right) is an up-day base rate, not skill. (c) Latency: the LLM-agent decision path is seconds-to-minutes while the target holds are seconds-to-hours and no `latency_model_ref` exists (map-research §f.5). (d) No negatives: no WATCH/NO_TRADE/REJECT log, so no study can estimate precision. (e) Option-leg blindness: family C options history is ABSENT; every label is `UNDERLYING_ONLY`, yet the P&L target is a move *on the option*. (f) Vendor fragility: FlashAlpha at 2,122/2,500 by 4:32 PM with a full wall day projected at 2,850 (study 7); X pool at $55.72. (g) Governance drift: two Macro score definitions coexist; "chat approval ≠ ticket" is printed while chat "yes" is in practice the trigger.

## 2. Scaling strategy

Four stages. No stage is entered until the gate below it is *measured* and passed, and every stage keeps the previous stage's kill switches.

**Stage 0 — Discretionary with capture (now → day 30).** Jeffrey trades exactly as today, but every entry, exit, pass and watch goes through the decision ticket (§8) and is keyed to a 15 s `score_features` snapshot id. Live fills are imported from the broker nightly. *Nothing is automated.* Gate to leave: ≥ 20 sessions and ≥ 150 decision rows (including ≥ 50 Pass/Watch), a reconciled signed-cashflow ledger with fees, and a measured `decision_at → order_ack` latency histogram (R15).

**Stage 1 — Assisted (day 30 → ~90).** Deterministic code (not LLMs) ranks a "Now" lane of ≤ 5 candidates by the only supported conditioner (rvol ≥ 3× with held score and DECEL/RESUME state), pre-fills the ticket with contract, debit, bracket and seat check, and the human clicks. Exits become real bracket orders (+10%/+20% limit-to-close, stop, time stop) placed *by the human's click*, managed by code. Gate: over 20 sessions, the lane's precision (fraction of lane candidates the human acted on *and* that hit +10% before stop) ≥ 45% with a session-block bootstrap CI whose lower bound ≥ 35%; human-vs-lane agreement measured; no missed-exit incidents.

**Stage 2 — Supervised auto (~day 90 → 180).** A frozen, shadow-validated policy (§4) proposes entries; the human has a 15 s veto window per order on the cockpit; code places exits automatically. Per-day cap of 10 orders, 3 open seats, $2,500 debit per order, $1,500 daily loss stop, all enforced in the execution layer, not the policy. Gate: ≥ 30 sessions of shadow with Brier skill ≥ 0.01 vs. B0 base rate *and* net expectancy per eligible opportunity > 0 after modeled fees/slippage, top-3-removed, on sealed future dates with the evaluator on the research mini.

**Stage 3 — Autonomous (not before 2027).** Only for the one narrow setup that passed Stage 2 (surge-continuation, §7). Human veto removed only inside pre-set risk envelopes; everything else still assisted. I would not plan beyond this: a 15-seat autonomous options book run by LLM agents is how retail automation blows up.

**What gets automated first and why.** *Exits*, not entries. The ledger shows exit timing is where the owner's attention goes (43 batch closes, AMZN 260C bled to −61% awaiting a harvest, GOOGL 340C gave back +164% MFE to +17.8%). Bracket management is deterministic, latency-sensitive, and does not need a model. Second: *capture* (negatives, latency, fills). Third: *candidate ranking*. Last: *order placement* for entries.

**What never gets automated:** gate waivers (chase, earnings, OPEX), contract geometry under the cap (the OTM-substitution habit that produced MU 1600C at 46% OTM), universe changes, and anything on 0DTE.

## 3. Bot architecture

Split the roster into three tiers with a hard boundary: **LLM agents never hold order authority.** They write proposals into a queue; deterministic code decides whether a proposal is eligible; a human or (Stage 2+) a frozen policy accepts; the execution layer is the only process with broker credentials.

| Tier | Component | Deterministic / LLM | Owns |
|---|---|---|---|
| Collect | Alpaca collector (data mini) | code | SIP bars, OPRA stream, archive (§5) |
| Collect | Feed owners: Rose→FA/UW/Form-4, Hal→marks/X/catalysts, Chart, Macro, Peanut | LLM routines calling MCP, write-once per feed | `latest/` + append-only mirror |
| Signal | `lane_ranker` (new, data mini) | code | Now-lane candidates, 5 s |
| Signal | Shadow policy (`editable/model.py` frozen build) | code | shadow proposals, scored nightly |
| Judgment | Rose, Hal, Soft Grader, Macro, X Summarizer | LLM | *soft* context: catalyst, news tone, gate waiver *requests* (never waivers) |
| Risk/Exec | `exec_gateway` (new, data mini, single process) | code | broker session, order placement, brackets, kill switches, risk meters |
| Research | Research Bot on research mini | LLM proposes, code runs/scores | experiments; `trade_authorization=NONE` always |
| Ops | Data Ops Bot | LLM + checks | feed health, quota, latency, archive integrity |

**Execution/risk layer (`exec_gateway`).** One Python process, one broker account, one credential, no MCP exposure. Inputs: a signed `order_intent` row (schema in §8) from the cockpit or the policy. Checks, in order, all hard: quote age ≤ 120 s on equity *and* option; spread ≤ 8% of mid; debit ≤ cap; seats; day-loss stop; per-name exposure ≤ 2 seats; earnings/OPEX gates from a versioned `gates.yaml`; chase gate day% < 3%; mode ∈ {PAPER, LIVE}. On accept: limit order at ask + 1 tick, 20 s fill timeout, then cancel; on fill, immediately place the exit bracket as OCO (or emulated OCO where the broker lacks it, with a 1 s loop). Every state transition is appended to `orders.jsonl` with `intent_id`, `snapshot_id`, `policy_version`, `gate_results`.

**Kill switches (all independent, all tested weekly).** (1) Physical: a `KILL` file on the data mini checked every loop; (2) daily loss stop → flatten and halt; (3) broker-side: paused agentic account / API key rotation; (4) feed-health: if Alpaca stream lag > 5 s or FA quota = 0, no new entries, exits still run; (5) heartbeat: the cockpit shows gateway heartbeat age and goes red at 10 s; (6) "LLM-touched" switch: any order whose intent originated from an LLM routine rather than a human click or the frozen policy is rejected by construction.

**Broker choice.** Not Robinhood for bots: no public equities/options API; the Agentic MCP launched stocks-only in May 2026 and options support is **UNVERIFIED** (MAP 4 §2); its design (an LLM agent holding a trading MCP) is exactly the pattern to refuse. Keep Robinhood for Jeffrey's hand if he likes it. For the gateway I recommend **Alpaca** first: the desk already pays for its data, paper accounts get Level 3, the SDK is verified, multi-leg exists; caveats are **UNVERIFIED-S**: no native bracket/OCO for options and `trailing_stop` absent, so emulate brackets in the gateway; confirm GTC on options and the post-June-2026 margin regime. Second choice **Tradier** ($10/mo flat, native OTOCO with option legs, **UNVERIFIED-S**) if emulated brackets prove unreliable. IBKR only if the desk outgrows both; ib_async is solid but the operational surface is larger. Decide after a two-week paper trial on each gateway with the same intents.

## 4. Models

**What to model.** Not "direction." The target is the owner's exit rule. Primary label, per candidate event *e* at `decision_at` on the nearest 0.50Δ 7–21 DTE call/put listed at that time: `y_hit10 = 1` if bid ≥ 1.10 × entry ask before (stop at 0.80 × ask OR 90 min OR 15:45 PT), else 0; secondary `y_hit20`; auxiliary `ret_5m`, `ret_15m` on the underlying with B0 = same-window up-fraction per name-day and B1 = QQQ return (map-research §g.1–2). Costs: entry at ask + 1 tick, exit at bid, $0.65/contract, registered latency.

**Features (all `feature_available_at ≤ decision_at`).** rvol_1m, rvol_5m, same-minute norm, day_high/low surge flag, bars-since-surge, held-score duration, momentum state (with hysteresis), distance to day high/low, spread % of option mid, option volume/OI, UW 5 m lean age, news tone (as a candidate for drop), sector rvol, VIX level/change, time of day. **Exclude** the 15 s/1 m C/P input until the drop-one study is confirmed over 10 sessions.

**Model classes, in order.** (1) Hand rules — the frozen surge-continuation rule (§7) as the baseline to beat. (2) L2 logistic (already in `config.draft.json`), Platt-calibrated on the last 20% of each outer window. (3) Small gradient-boosted trees (depth ≤ 3, ≤ 200 trees) only if (2) shows Brier skill. Nothing deeper; n is in the hundreds of real events per month.

**Calibration and evaluation.** Brier and log loss vs. B0/B1, reliability curve by bucket with n, session-block bootstrap, purge by actual `label_end_at`, ≥ 3 outer blocks, top-3-contributor removal, PBO reported. Hit rate alone is never a result.

**Promotion ladder (steps 5–8 of study 1, not built).** `DRAFT → REGISTERED (thresholds frozen) → DEVELOPING (dev dates only) → FROZEN (hash) → SHADOW (≥ 20 sessions on future dates, proposals logged with latency) → CHALLENGER (beats incumbent on Brier and net expectancy on ≥ 10 of 15 sessions, CI excludes 0) → LIVE-ASSISTED → LIVE-SUPERVISED`. One incumbent, at most two challengers. Demotion is automatic on 10 consecutive non-improving sessions or any gate breach.

**What LLMs should do:** write hypotheses and feature code into `editable/`, draft study registrations, summarize news and filings into typed fields (tone, event type, first-seen time), explain why-this-fired in the cockpit, review the nightly scorecard and propose (not apply) gate changes, operate the archive/health checks. **What LLMs should not do:** choose contracts, size, waive gates, hold broker credentials, score their own experiments, or read sealed data. Their nondeterminism is fine for proposals and lethal for orders.

## 5. Data collection and archive

Build the archive *before* any more studies; every day without it is unrecoverable (RESEARCH_FEED_ADDITIONS R5). The 10/20 page shows page-local history now exists but it is not hashed, not in git, and not reachable by the research mini (map-research §c).

**Capture from today (data mini, append-only Parquet partitioned by date/symbol, DuckDB catalogue):**
1. R5: dated snapshot of every `latest/*.json` on each write (`as_of`, `writer`, sha256).
2. R6: 1-min SIP bars + 5 s bars for the 65 core names, QQQ/SPY/SMH/SOXX; same-minute norms as computed that day.
3. R2: streamed OPRA BBO + trades for a fixed ATM±2 strike set, 7–21 DTE, for the top 40 names by option volume (≈ 400–600 of the ~1,000 subscription cap, **UNVERIFIED** cap), re-selected daily at 06:00 PT. This is the option-leg label source.
4. R1: Alpaca chain snapshots every 5 min RTH, ±30% strikes, for all 209 names (one-day dry count first against quota).
5. R7: the decision ticket rows (§8) and alert ack/ignore rows.
6. R15: collector `LagHistogram` and gateway `decision_at → order_ack` latencies.
7. Score-change log, `score_features` (15 s), momentum tape, surge alerts, FA wall snapshots, UW lean with age — already exist; bring them under the same manifest.
8. Broker fills (paper and Jeffrey's live) nightly, with order timestamps.

**PIT discipline.** Every row carries `source_observed_at`, `received_at`, `feature_computed_at`; labels are computed only by a nightly job on the research mini's `oideval` side. Score and lane configs are versioned (`core v1.1`, `light-v1.0`, `lane v0.1`) and the version is stamped on every row. Norms are stored as-of, never recomputed retroactively.

**Labeling pipeline.** Nightly at 17:30 PT: join decisions and lane candidates to R2/R1 option quotes → `y_hit10/y_hit20/stop/time` counterfactuals under the registered exit rule; join to 5 s bars → underlying forward returns with B0/B1; write `labels_YYYYMMDD.parquet`; append the scorecard (§8 item 9).

**Storage.** R2 at ~500 contracts is on the order of 1–3 GB/day compressed; R6 ~70 MB/yr; R1 ~2 GB/month. The research mini's 3.6 TB covers > 2 years. Keep raw on the data mini for 30 days, archive to the research mini nightly.

**The split.** Data mini = collector + publisher + gateway + 30-day hot store; research mini = immutable archive (`oidarch`), dev sandbox (`oidresearch`), sealed evaluator (`oideval`). Owner decisions needed now: open the LAN path (Tailscale on the research mini or a firewall rule for 192.168.5.191:8787/8788), enable the `archive-pull` launchd job, and implement the root-run copy into `sealed/` for dates ≥ D. Sealed means future dates only; historical holdouts are contaminated.

## 6. Additional data sources

Ranked by expected value for the +10–20% same-day exit. Costs per MAP 4; **UNVERIFIED** where marked.

1. **Own OPRA BBO archive via the existing Alpaca stream (R2) — $0.** PIT quality: observed. Hypothesis: the option-leg label; without it nothing else matters.
2. **Alpaca OI-derived walls — $0, ~300 calls/day.** Already adopted (study 8). Hypothesis: walls add nothing beyond volume (expected null; confirms the FA Alpha decision).
3. **Databento OPRA targeted pulls (`cbbo-1m`, `definition`) — pay-as-you-go, estimate < $500 for event-day backfills (UNVERIFIED-S).** PIT: reconstructed, no desk latency. Hypothesis: backfill option-leg labels for the 325 ticker-days of surge events already archived, giving a 2-month head start on §7 setup A.
4. **FINRA short interest + UW borrow — $0.** S5 as registered. Hypothesis: surge-continuation is stronger in high-SI names (squeeze fuel). Weak for mega-caps; cheap.
5. **SEC EDGAR full-text + acceptance timestamps — $0 (UNVERIFIED-3P).** Hypothesis: 8-K/Form-4 first-seen within 2 min of a surge explains the surge and predicts continuation vs. fade (news-driven surges fade less than flow-driven ones).
6. **Korea 10/20-day semis exports via data.go.kr — $0 (UNVERIFIED-S on the endpoint).** Already COLLECT-FORWARD; campaign 2; HAL_SWING only.
7. **Kalshi candlesticks — $0.** Nests in S2 family D; macro-event-day gating for Rose (do not trade surges in the 15 min around a print).
8. **ThetaData Standard $80/mo (UNVERIFIED-S)** as the fallback options-history source if Databento costs surprise.

**Do not buy:** FlashAlpha Alpha ($1,499/mo) — the wall null and the free OI path make replay worthless for this desk; UW Advanced upgrade — the lean input is "soft only" and unmeasured; ORTEX, Estimize, DRAMeXchange, Silicon Data Pro — swing-horizon sources for a seconds-to-hours desk; Massive options — personal-use licensing is a risk once there is a bot; any X API top-up beyond the current pool until X tone shows lift (study 13 says none). Cut FA spend instead: trim VIX (700/day) and oil (450/day) calls to a 5-min cadence, saving ~1,300 calls (study 7).

## 7. Strategy and edge techniques

**What "consistent arbitrage" means here.** There is no arbitrage. There is a repeatable *conditional* edge: after a genuine volume event in a liquid name, short-horizon continuation is more likely than the base rate (8.7% → 26.7% for 15-min breakouts), and options convexity turns a 0.5–1% underlying move into +10–20% on a near-ATM contract. The edge is in event selection, speed, and refusing to chase. The academic record (MAP 4 §9) says retail 0DTE flow loses on spread; the desk should trade 7–21 DTE, pay less spread, and exit on a rule.

**Setup A — Surge continuation (the first thing to shadow, then automate).** Trigger: 1-min rvol ≥ 3× at a new `day_high` (calls) or `day_low` (puts), bar closes in the top/bottom 30% of its range, momentum state not ACCEL-for-> 3 bars already, no earnings within 24 h, not an OPEX day, not within 15 min of a scheduled macro print, day% < 3%. Entry: next 5 s bar, 0.50Δ 7–21 DTE, spread ≤ 8% of mid, debit ≤ $2,500. Exit: +12% limit, −20% stop, 60-min time stop, 15:45 flat. Register now with B0; expect precision ~40–50%, which is profitable at 12/20 payoff only if latency < 10 s — which is why R15 matters.

**Setup B — Held-score + surge (shadow only).** Core ±2 held ≥ 30 s AND rvol ≥ 3×; Light ±3 held 5 min AND surge. The studies' best cells (61.5%/67.5%, n 26/40). Treat as a confirmatory study, not a strategy, until n ≥ 300.

**Setup C — Sector sympathy.** When ≥ 3 names in one sector group surge within 5 min and the sector strip rvol ≥ 2×, buy the laggard with the tightest spread. Testable from the group-header stats already on the page. Hypothesis only.

**Setup D — Surge fade (puts after exhaustion).** rvol ≥ 5× at day_high followed by a DECEL event and a 5-min close back inside the prior range → put. This exploits the "ACCEL is worst, DECEL is best" pattern (study 5) and gives the desk the put side the paper ledger never traded.

**Setup E — News-confirmed surge.** Setup A plus an EDGAR/Benzinga first-seen within 2 min: expect higher continuation; the drop-one news result (study 13) says tone alone adds nothing, but *presence* of a filing is a different variable.

**Avoid:** 0DTE; wall-press entries as a primary trigger (null); flow-agreement filters (study 4); OTM substitution when ATM exceeds the cap (take WATCH instead); credit spreads until the sign bug is fixed; anything that requires an LLM in the decision loop at seconds horizon.

## 8. UI/UX changes (ranked)

The page is a research instrument posing as a cockpit. Rebuild it as two surfaces: a **cockpit** for 6:30–13:00 PT and a **scorecard** for everything else. Priorities:

1. **Decision ticket and capture (build first; it is the dataset).** Right-drawer ticket pre-filled from the focused tile: `Call / Put / Pass / Watch`, contract (ATM, nearest 7–21 DTE, spread %, OI), debit vs. $2,500/$5,000 cap, bracket (+12% target, −20% stop, 60-min time stop; editable), seats vs. 8/15, gate results (quote age, chase, earnings, OPEX) as green/red pills, reason chips (`surge | wall | flow | news | sector | gut`), confidence 1–3, 140-char note. Submit writes `decision_rows` as `{intent_id, ts, actor, action, symbol, snapshot_id, score_cfg, score, held_s, rvol_1m, momentum_state, cp_15s, cp_cov_pct, wall_dist_pct, lean, lean_age_s, news_tone, lane, reasons[], confidence, bracket{}, contract{}, mode}`; Pass/Watch capture the negatives that do not exist today. In Stage 0 the button says `Log`; in Stage 1 it says `Send to gateway (PAPER)`. Exit requires a tag at close time with administrative closes in their own category.

2. **Now lane.** Replace the five `test`-stamped surge chips and the 12-chip momentum tape with one ranked lane of ≤ 5 candidates (`rank = rvol_1m × held-score factor × state factor`, versioned `lane v0.1`), each a card: symbol · rvol · `+2 · 48s` · state · wall distance % · spread % · age · `Ack / Ignore / Open ticket`. Hysteresis ≥ 60 s on state flips. Every Ignore is a precision label.

3. **Tile hierarchy re-rank.** Big glyph = rvol only when ≥ 1.5×, otherwise % change; score chip shrunk to a corner mark with a held-for timer; remove `0.0×` and all `—` after close; closed-market tiles become session summaries. Fix the `()` template bug.

4. **One freshness grammar.** Every datum gets an age pill in one format (`12s / 4m / 9h`) colored against its own TTL; the header chip goes amber when any gated feed is past TTL; a Row 0 status bar shows Alpaca stream lag, FA quota %, UW age, gateway heartbeat, mode PAPER/LIVE, seats, open debit, day P&L vs. loss stop.

5. **Focus panel ("why this fired").** Each score input × weight, C/P with coverage % (never without it), wall distances %, lean + age, news tone + source + first-seen, last 5 min of 5 s bars, and the three conditioners as checkboxes (rvol ≥ 3×, held ≥ 30 s, DECEL/RESUME). Keyboard: `j/k` tiles, `c` call, `p` put, `x` pass, `w` watch, `Enter` submit, `Esc` cancel.

6. **Positions zone.** Live page gets its own positions strip: mark, MFE/MAE from 5 s bars, bracket state, time-to-stop, `Flatten` and `Flatten all` buttons (gateway-backed in Stage 1). The here.now blotter's mixed P&L scopes are replaced by one scope: realized today / unrealized / week, all net of fees.

7. **Color and shape separation.** Volume = amber→red ramp only; direction = blue/orange plus ▲▼; walls = `C/P/γ` letters; minimum 11 px type; italic retired; red-green CVD safe.

8. **Alert ledger.** Every surge/momentum/news alert has Ack/Ignore/Acted and is deduplicated; `shadow`/`test` items go to a muted lane; news sorted by time, score-filtered, with thumbs-up/down on finbert scores.

9. **Scorecard page replaces the Research tab's top.** Today vs. 10-day: hit10/hit20 by setup and |S| with n and CI, calibration curve, conditioner lifts, lane precision, human-vs-lane agreement, promotion-ladder status; studies table beneath; Field Guide 13 gap audit last.

10. **Replay/scrub** over one ticker's last N minutes from `score_features` with decision rows overlaid — the review tool for weekly rule promotion.

11. **Mobile watch mode**: ≤ 8 names, one line each, `Flatten` only. No entries from a phone.

**Cockpit layout.** Row 0 status bar; Zone A (left 60%): Now lane + compact heatmap of names with rvol ≥ 1.5× or held score, rest collapsed to sector strip; Zone B (right 40%): focus panel + ticket; Zone C (bottom): positions + decision-log tail; Zone D (collapsible): news, macro, momentum tape.

## 9. Additional bots

1. **Exec Gateway (code, not a "bot").** Purpose: the only order path. Inputs: `order_intent` rows. Outputs: `orders.jsonl`, fills, bracket state, heartbeat. Cadence: event-driven, 1 s loop. Authority: full broker authority inside `gates.yaml` envelopes; no LLM access. Pays for itself the first time a bracket catches a giveback like GOOGL 340C's +164% → +17.8%.

2. **Lane Ranker (code).** Purpose: produce the Now lane. Inputs: 5 s bars, norms, score log, momentum tape, walls, spreads. Outputs: ranked candidates with `lane_version`, logged for precision labels. Cadence: 5 s. Authority: none. Value: converts 209 tiles into ≤ 5 decisions and generates the training set.

3. **Label Bot (code, research mini `oideval`).** Purpose: nightly outcome labels and scorecard. Inputs: decisions, lane candidates, R1/R2 quotes, 5 s bars. Outputs: `labels_*.parquet`, `scorecard.json`. Cadence: 17:30 PT. Authority: none; the only process that sees labels on sealed dates.

4. **Shadow Trader (code with LLM-drafted features).** Purpose: run frozen challengers on live data and log proposals with latency. Outputs: `shadow_proposals.jsonl`. Cadence: 5 s. Authority: none. Value: the promotion ladder's steps 5–8.

5. **Reconciler Bot (LLM + code).** Purpose: nightly ledger reconciliation — broker fills vs. intents, signed cashflows, fees, administrative-close separation, top-3 concentration, correlated-exposure report. Outputs: `ledger_reconciled.parquet`, exceptions to chat. Cadence: 17:45 PT. Authority: none. Value: fixes the GOOGL/NVDA arithmetic errors and credit-spread sign bugs class of problems before they reach a model.

6. **Quota & Latency Warden (Data Ops Bot extension).** Purpose: FA/UW/X/Alpaca budget pacing and latency SLOs. Inputs: `api-quotas`, `LagHistogram`, gateway heartbeat. Outputs: throttle flags the collectors must honor; red status on the cockpit. Cadence: 1 min. Authority: can *disable* non-essential pulls (VIX/oil cadence) and halt new entries on feed degradation. Value: prevents the 10/02 `STALE_CARRY`-at-quota-zero failure and keeps FA under $299.

7. **Gate Keeper (code, LLM proposes changes).** Purpose: versioned `gates.yaml` (chase, earnings, OPEX, FOMC, macro-print windows, re-seat bans, avoid lists) with a changelog; LLM agents and Jeffrey submit *requests*; only Jeffrey approves via the cockpit; waivers are logged as rows, never silent. Value: replaces the "named gate governs" and chat-override pattern with data.

8. **Filing/News First-Seen Bot (LLM typed extraction).** Purpose: EDGAR 8-K/Form-4 and Benzinga headlines to typed `{symbol, event_type, first_seen_at, tone}` within 60 s. Authority: none. Value: the one news variable (presence, not tone) with a plausible edge.

9. **Correlation Sentinel (code).** Purpose: block the "seven wall-presses on one move" cohort; computes live sector and factor exposure of open seats and the Now lane; caps correlated seats at 3. Cadence: on each intent. Authority: hard reject.

**Retire or demote:** Customer/Supplier Bot (0 edges, 0 claims) → archive; Chart Bot's pattern detector stays off; Soft Grader folds into the Gate Keeper's request schema. Rose and Hal become *context writers* and shadow proposers, not traders.

## 10. Risks and failure modes

- **Overfitting and selection:** 1–2 correlated sessions, 15 s overlapping snapshots, researcher-seen dates. Mitigation: registration before search, Brier vs. B0, session-block bootstrap, sealed future dates, zero campaign-1 headroom respected.
- **Concentration:** 3 tickets = 89%; one cohort = seven "wins." Mitigation: Correlation Sentinel, top-3-removed reporting, per-name and per-sector seat caps.
- **Regime:** all evidence is from an AI up-tape; bearish-extreme calibration is already inverted. Mitigation: require ≥ 5 down sessions in any validation window; puts side (Setup D) tested separately.
- **PDT / margin:** FINRA's intraday-margin regime is effective June 2026 with a firm transition to Oct 2027 (**UNVERIFIED-S**); each broker may still apply legacy PDT. A same-day options desk under $25k equity at a legacy-PDT broker gets locked out. Action: ask the chosen broker in writing which regime applies; size the account accordingly.
- **Latency:** LLM paths are seconds-to-minutes; the edge may live inside 10 s. Mitigation: no LLM in the loop; measure R15 before Stage 1.
- **Vendor quotas and cost creep:** FA over cap on full wall days; X pool near zero; FA Alpha and UW upgrades tempting. Mitigation: Warden throttles; the "do not buy" list; monthly vendor bill reviewed against the scorecard.
- **LLM nondeterminism and prompt drift:** two Macro definitions coexist; owner overrides are untyped. Mitigation: LLMs produce typed proposals only; gates and policies are versioned files with hashes.
- **Execution:** no native option brackets at Alpaca (**UNVERIFIED-S**); emulated OCO can double-fill on reconnect. Mitigation: idempotent intent ids, state machine with reconciliation on every reconnect, paper trial on two gateways.
- **Robinhood Agentic:** an LLM holding a trading MCP is the single worst-case architecture; options support unconfirmed. Refuse.
- **Slippage and fees:** paper books at ask/mark with zero fees; the 12.6% effective spread documented for retail options flow would erase a +12% target. Mitigation: spread ≤ 8% gate, label at bid, fees modeled.
- **Operational:** single data mini is collector, publisher and gateway. Mitigation: KILL file, heartbeat, nightly archive to the research mini, a documented restore drill.

## 11. First 30 days / first 90 days

**Days 1–7.** Open the data mini → research mini path (owner decision: Tailscale or firewall rule). Enable R5/R6 append-only mirrors and the archive-pull job. Freeze and register Setup A and Setup B as studies with B0/B1 and thresholds (owner signs `mode_authorization.granted_by`). Cut FA VIX/oil cadence to 5 min. Decide the gateway broker candidate list (Alpaca + Tradier paper) and open paper accounts.

**Days 8–14.** Ship the decision ticket and Pass/Watch capture (§8.1) in Log mode; Jeffrey uses it on every live trade. Start R2 OPRA BBO archive for the top-40 ATM set; run the R1 dry count. Persist `LagHistogram`. Import Jeffrey's live fills nightly. Fix the `()` bug and the freshness grammar.

**Days 15–30.** Ship the Now lane (`lane v0.1`), tile re-rank, Row 0 status bar, and the scorecard page. Label Bot runs nightly on the research mini. Reconciler Bot re-encodes the 57 paper closes with signed cashflows, fees, and administrative separation; publishes top-3-removed numbers. `gates.yaml` v1 replaces prose gates. Owner decisions: $2,500 per-order cap, $1,500 daily loss stop, 3 correlated-seat cap, spread ≤ 8%.

**Day 30 gate review:** ≥ 150 decision rows, ≥ 50 negatives, latency histogram, reconciled ledger. If not met, stay in Stage 0.

**Days 31–60.** Build `exec_gateway` in PAPER mode against the chosen broker; bracket emulation with reconnect reconciliation; weekly kill-switch drills. Shadow Trader runs Setup A/B challengers; scorecard shows lane precision and human-vs-lane agreement daily. Run S1 on 30 m bars to prove the runner/evaluator on the research mini. Price a Databento targeted pull via `metadata.get_cost` for the 325 archived surge ticker-days; buy only if < $500.

**Days 61–90.** If lane precision passes its gate, enter Stage 1: human-clicked paper orders through the gateway with automatic brackets for two weeks, then live with the per-order cap at $1,000 for two weeks. Retire Customer/Supplier Bot; fold Soft Grader into Gate Keeper. Register campaign 2 (Setup D puts, sector sympathy, filing first-seen) on dates ≥ day 60. Written answers from the broker on options brackets, GTC, and the PDT/intraday-margin regime before any live order.

**Day 90 review:** Stage 2 is considered only if ≥ 30 shadow sessions show Brier skill ≥ 0.01 and positive net expectancy after costs with the top 3 removed, on sealed future dates. Otherwise the desk stays assisted — which, given today's evidence, is where most of the value is anyway: a faster human with a labeled record, not a bot with a story.