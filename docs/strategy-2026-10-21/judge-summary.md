# Judge panel summary (2026-10-21)

Five proposals (one per lens, in `proposals/`) were scored 1-10 on feasibility, evidence grounding, risk control, expected impact and specificity by three judges: a CTO, the desk owner's perspective, and an external quant reviewer. The synthesis (`synthesis-draft.md`) used the top-ranked proposal as its spine and merged the must-keep ideas from the others; the main report then applied the fact-check corrections.

## Judge 1

| # | Lens | Feas. | Evidence | Risk | Impact | Specificity | Total |
|---|---|---|---|---|---|---|---|
| 1 | systematic-pm | 7 | 9 | 8 | 8 | 9 | 41 |
| 2 | execution-risk | 8 | 8 | 10 | 8 | 9 | 43 |
| 3 | data-engineer | 8 | 8 | 7 | 7 | 9 | 39 |
| 4 | ml-scientist | 7 | 9 | 8 | 8 | 8 | 40 |
| 5 | skeptic-product | 7 | 8 | 9 | 7 | 8 | 39 |

Ranking: [2, 1, 4, 3, 5]

Must keep from each proposal:
- P1 (systematic-pm): Jeffrey-owned, versioned policy.yaml that bots read and never write, with Gateway hard ceilings it can only lower, plus the rule that no policy may target a horizon shorter than 5x measured latency.
- P2 (execution-risk): the ordered Risk Sentinel check list with REJECT/HALT semantics, the synthetic-bracket state machine (resting TP, software stop repricing to market, disconnect-flatten), idempotent intent ids and a 10 s Reconciler that HALTs on any broker/OMS delta.
- P3 (data-engineer): the archive contract -- date/hour Parquet partitions with MANIFEST.json hashes and three clocks, closed hours immutable, STALE records archived -- and the full decisions schema with PASS/WATCH negatives and a required exit tag, plus the B2 surge-only baseline.
- P4 (ml-scientist): the triple-barrier option-leg label L_opt(X,Y,T) with a registered bracket grid chosen offline from logged option paths, event-count floors (not day counts) on promotion, and the Owner Mirror Bot comparing Jeffrey's decisions to the shadow policy daily.
- P5 (skeptic-product): the cockpit ticket as a product (Log -> Send to gateway button, gate pills, keyboard shortcuts, alert ledger), the Gate Keeper with versioned gates.yaml where waivers are logged requests only Jeffrey approves, and the 'LLM-touched intent is rejected by construction' kill switch.

Cross-cutting disagreements:
- Quote-age gate at the order path: P2 and P4 tighten to <=5 s on both underlying and contract; P1, P3 and P5 carry the desk's 120 s rule into the gateway. For a seconds-to-hours book the 120 s rule is a Hal-cadence artifact; the synthesis should take <=5 s.
- Live broker: all five use Alpaca paper first and rule Robinhood out of the order path. For live, P1/P2/P3/P5 go Alpaca first with Tradier as fallback; P4 says evaluate Tradier first because native OTOCO option brackets remove synthetic-bracket risk. P2 adds the decisive fact that Tradier's sandbox is 15-min delayed with no streaming, so the bracket code must be built and paper-tested on Alpaca regardless. P5 wants a two-gateway paper trial.
- Where labels are computed: P1 and P5 put the Label Bot on the research mini's oideval side (sealed); P2, P3 and P4 run it nightly on the data mini. The former is cleaner isolation but depends on the still-missing network path; the latter works today.
- Bracket geometry: P3 uses +12%/-8%/20 min; P1 +12/-20/30 min; P5 +12/-20/60 min; P2 +10 on half, -20, 90 min with trail; P4 defers to a registered grid (X 10/15/20, Y -15/-25, T 15m/45m/close). Only P2 computes break-even arithmetic (incorrectly in one number) and only P4 proposes choosing the bracket offline from logged option paths rather than asserting it.
- R2 OPRA subscription set: P2 and P4 260 contracts (1 call + 1 put x 2 expiries x 65 core); P1 520; P3 ~650 (ATM+-2 strikes, one expiry); P5 400-600 on the top 40 by option volume. All are under the ~1,000 cap (UNVERIFIED) but differ on whether sector names get headroom after a surge.
- Stage 2 live sizing: P2 and P4 $500 debit / 2-3 seats / $750 daily stop; P5 $2,500 per order / $1,500 daily stop; P1 '1 contract'; P3 goes to $5,000 debit and 3 seats with a loss limit tied to median winning ticket. Correlated-seat cap per sector: 2 (P1, P3, P4) vs 3 (P2, P5).
- What to automate first: all five say exits before entries and capture before everything; P3 and P5 add candidate ranking as a distinct middle step; P4 makes the surge detector itself the single gate for everything else. No proposal automates entries before day 60.
- Data purchases: unanimous no on FlashAlpha Alpha, DRAMeXchange, Silicon Data, Massive options, more X credits; unanimous yes on targeted Databento pulls after metadata.get_cost (caps of $300 in P1/P2, $500 in P5). P4 uniquely proposes a $0 Alpaca historical option bars/trades backfill first; P3 ranks EDGAR first-seen higher than the others.
- Retirements: P2 and P5 explicitly retire Customer/Supplier Bot and fold Soft Grader into code; P1, P3, P4 keep the roster and demote. P5 adds a Gate Keeper with a waiver-request schema that no other proposal has.
- Baselines: P3 and P4 register a B2 surge-only rule that any model must beat; P1 and P5 use B0/B1 only; P2 uses B0/B1 plus a per-ticket break-even gate.

Factual errors flagged:
- (systematic-pm) R2 sizing is internally inconsistent: '+-2 strikes, nearest two expiries' on 65 names is 5 strikes x 2 rights x 2 expiries = 20 contracts/name = 1,300 (over the ~1,000 cap), not the stated 65 x 2 x 4 = 520
- (systematic-pm) Section 4 says labels are computed by oideval-side code; section 5 says the data mini computes labels and the research mini pulls them -- contradictory placement of the label job
- (systematic-pm) '1-min bars ~70 MB/yr' borrows R6's 67 MB/yr figure, which was for 5/15-min JSON; 1-min bars for 209 names are ~20M rows/yr (still small in Parquet, but not that number)
- (execution-risk) Break-even arithmetic is wrong: with a +10% target netting ~4.4% and a -20% stop plus ~5.6% round-trip cost (~-25.6%), the break-even win rate is ~85%, not '>=62%'; the 2:1 TP:stop conclusion (break-even ~52%) is the valid part
- (data-engineer) 'As of 10/10 only three feeds were append-only (FEEDS_CURRENT.md line 47)' conflicts with map-research s(f).3 ('no archive, append, or snapshot writer' on 10/10); not verifiable from the maps
- (data-engineer) '113 GB free observed' on the box is not in any map or the task context
- (data-engineer) '~23 M rows, 0.4-0.9 GB Parquet at 1,000 subs' is an estimate presented without the one-day dry count the R1 doc itself requires; flagged by the author but still used in the yearly total
- (ml-scientist) Kill switches 2 and 6 assume 'broker-side brackets exist for every live position so a dead mini cannot strand a trade', which contradicts the proposal's own Alpaca-paper plan (no native option bracket, UNVERIFIED-S) unless Tradier/IBKR is the live venue -- the dependency is not stated at the switch
- (ml-scientist) Minor: 'sklearn 1.9 is installed' is correct (1.9.1); '~780 holds/day' and '~26/day' are one-day counts from 10/20 presented as daily rates
- (skeptic-product) 'expect precision ~40-50%, which is profitable at 12/20 payoff only if latency < 10 s' is wrong: at +12%/-20% the break-even win rate is 62.5% before costs, so 40-50% precision is a losing policy regardless of latency
- (skeptic-product) 'R2 at ~500 contracts is 1-3 GB/day compressed' is roughly 3x P3's estimate for every-change BBO at 1,000 subs; unverifiable but inconsistent with the sibling estimate
- (skeptic-product) 'Stage 3 not before 2027' reads as conservative but is ~10 weeks from today (2026-10-21), i.e. the same horizon as the other proposals' day-90 reviews

## Judge 2

| # | Lens | Feas. | Evidence | Risk | Impact | Specificity | Total |
|---|---|---|---|---|---|---|---|
| 1 | systematic-pm | 7 | 9 | 8 | 8 | 9 | 41 |
| 2 | execution-risk | 8 | 8 | 9 | 8 | 9 | 42 |
| 3 | data-engineer | 8 | 8 | 7 | 7 | 8 | 38 |
| 4 | ml-scientist | 7 | 9 | 8.5 | 8 | 9 | 41.5 |
| 5 | skeptic-product | 8 | 8 | 9 | 7 | 8 | 40 |

Ranking: [2, 4, 1, 5, 3]

Must keep from each proposal:
- P1: Jeffrey-owned, git-versioned policy.yaml that bots read and never write, paired with an `overrides` table (reason chip per waiver) and the DRAFT->RETIRED promotion ladder where only Jeffrey flips CHALLENGER->INCUMBENT; plus the Quota Steward that flips walls to Alpaca-OI below 20% FA budget.
- P2: the Risk Sentinel's ordered pre-trade check list in code (5 s quote age on contract and underlying, spread caps, per-name/per-sector seats, order-rate limit, duplicate intent reject, two REJECTs = HALT), the synthetic-bracket state machine for Alpaca's no-OCO options, the 10 s Reconciler, the weekly kill drill, and per-ticket break-even win rate from spread + fees.
- P3: the archive contract: per-date MANIFEST.json with hashes and clocks, closed hours made read-only, corrections as supersedes rows, STALE records archived; the full `decisions` schema with required exit_tag; the B2 surge-only baseline every model must beat; and one `features(symbol, as_of)` code path shared by the live scorer and replay.
- P4: the triple-barrier option-leg label L_opt(X,Y,T) registered up front, the event-count floors (~785 independent events for 50->55%, >= 800 events and >= 15 sessions before any promotion), E1-E5 as registered experiments on dates >= 10/21, the bracket grid before any bandit, the Owner Mirror Bot, and the $0 Alpaca historical option bars backfill before paying Databento.
- P5: the 'never automate' list (gate waivers, contract geometry under the cap, universe changes, 0DTE), the LLM-touched reject switch in the gateway, the Gate Keeper request/approve pattern replacing chat-yes and 'named gate governs', the Correlation Sentinel against one-move-many-wins cohorts, lane precision as the Stage 1 gate, and the stance that autonomous entries are a 2027 question.

Cross-cutting disagreements:
- Quote-age gate for bot entries: P1, P3 and P5 carry the desk's existing <= 120 s rule into the gateway; P2 and P4 tighten it to <= 5 s on both underlying and contract. For a seconds-to-hours book the 5 s number is the right one; 120 s was written for Hal's 15-minute marks.
- Broker for first live orders: P1, P2, P3, P5 say Alpaca first (same vendor as the stream, paper Level 3, alpaca-py verified) with Tradier as fallback; P4 says evaluate Tradier first for live because of native OTOCO option brackets. P2 adds the constraint none of the others weigh: Tradier's sandbox is 15-min delayed with no streaming, so a Tradier gateway cannot be paper-tested at seconds scale. All five reject Robinhood for bots.
- First-live sizing: P2 and P4 start at 1 contract / $500 debit / 2-3 seats / $750 daily loss; P5 at $2,500 per order / $1,500 daily / 10 orders a day; P3 at the full $5,000 debit / 3 seats; P1 defers to '2% of sleeve capital' with sleeve capital undefined.
- Bracket defaults: stops range from -8% (P3) through -15/-25% grid (P4) to -20% (P1, P2, P5); time stops from 20 min (P3) and 30 min (P1) to 60 min (P5) and 90 min (P2). P4 alone says do not pick by hand: run the counterfactual grid E5 on logged option paths and freeze the winner.
- R2 OPRA subscription set: 260 contracts (nearest 0.50-delta call+put, two expiries, P2 and P4) vs ~520-650 (ATM ±2 strikes, P1 and P3) vs top-40 names 400-600 (P5). P1's 520 does not match its own described set; 260 leaves headroom for sector names after a surge.
- When to spend on Databento: P2 wants the targeted surge-day backfill in days 15-30 if `metadata.get_cost` < $300; P1 and P3 say only after R2 is running and the label definition has held 20 sessions; P5 says < $500 after the same cost check; P4 inserts a $0 step first (Alpaca historical option bars/trades from Feb 2024) before paying anyone.
- Where labels are computed: P1 and P5 put the Label Bot on the research mini's oideval side; P2, P3 and P4 run it nightly on the data mini and ship to the research mini. The data-mini version keeps the page scorecard working without a return path; the oideval version is cleaner for sealing but needs the network path that does not exist yet.
- LLM authority over gates: P2 lets LLM agents set exposure-reducing gates directly; P4 treats them as gate inputs; P5 allows only requests into a Gate Keeper that Jeffrey approves on the cockpit; P1 makes every LLM free-text field advisory and every override a row.
- Pace to supervised auto / live: P2 fastest (Stage 2 weeks 10-20, live after 20 clean paper sessions); P4 day 75-150; P1 day 90-180; P3 only after a day-90 review and verified broker facts; P5 live human-clicked orders by ~day 75 but autonomous entries 'not before 2027'.
- Retiring bots: P2 and P5 explicitly retire Customer/Supplier Bot (0 edges) and fold Soft Grader into code; P1, P3, P4 leave the roster intact and demote Chart/Macro/X/News to feature producers.
- The live C/P flow input to the core score: P5 excludes it from features now; P4 registers E1 as a confirmatory 10-session study before flipping core v1.1 -> v1.2; P1 tests P2 with and without; P2 and P3 use the drop-C/P variant as a feature/challenger.
- Gateway host: P1 says 'box or data mini'; the other four put the order path on the data mini next to the stream. The box is the shared LLM host with 0.8-5.4 GiB free and should never hold broker credentials.

Factual errors flagged:
- (systematic-pm) R2 sizing: '±2 strikes, nearest two expiries' for 65 core names is 5 strikes x 2 rights x 2 expiries = 20 contracts/name = 1,300, over the ~1,000 cap; the stated '65 x 2 x 4 = 520' does not describe that set
- (systematic-pm) Suggests FlashAlpha could drop to Basic; per MAP 4 Basic is 100 req/day, which cannot cover the 325 wall calls/day the page already makes (UNVERIFIED-S plan facts, but the arithmetic does not work)
- (execution-risk) Break-even arithmetic: with a +10% target netting +4.4% and a -20% stop netting -25.6%, break-even is ~85% wins, not '>= 62%'; 62% only holds under the 2:1 TP:stop alternative it mentions. The conclusion (the policy loses at 55%) is right and in fact stronger than stated
- (execution-risk) Attributes PF 7.7 to 'three correlated wall-presses closed together on 9/21'; the maps show the top-3 (AMD 550C, META 670C, LRCX 310C) and the 9/18 cohort of seven as two separate facts, not that the top-3 were the 9/21 cohort
- (data-engineer) None material. 'FEEDS_CURRENT.md line 47: three feeds append-only' and 'box 113 GB free' are not verifiable from the maps but are not contradicted
- (ml-scientist) None found in the numbers; the 785-event power calculation checks out, cell rates per day (782, 26) match the studies, and the 260-contract R2 set (65 x 4) is under the cap. The broker-side-bracket assumption is an internal inconsistency rather than a fact error
- (skeptic-product) None material. Applies the 12.6% effective retail spread (Bryzgalova et al., measured on cheap weeklies) to ATM 7-21 DTE liquid names as if it erases a +12% target; it is a caution, not the desk's spread. R2 storage '1-3 GB/day at ~500 contracts' is high relative to P3's 0.4-0.9 GB/day at 1,000 but is an estimate

## Judge 3

| # | Lens | Feas. | Evidence | Risk | Impact | Specificity | Total |
|---|---|---|---|---|---|---|---|
| 1 | systematic-pm | 7 | 8 | 8 | 8 | 8 | 39 |
| 2 | execution-risk | 8 | 7 | 9 | 8 | 9 | 41 |
| 3 | data-engineer | 8 | 8 | 6 | 7 | 8 | 37 |
| 4 | ml-scientist | 7 | 9 | 7 | 8 | 9 | 40 |
| 5 | skeptic-product | 8 | 7 | 8 | 7 | 8 | 38 |

Ranking: [2, 4, 1, 5, 3]

Must keep from each proposal:
- P1 (systematic-pm): Jeffrey-owned, versioned policy.yaml that bots read but never write, plus the rule that no policy runs with a target horizon under 5x measured latency, and the Fill Reconciler that produces the slippage parameter every study needs.
- P2 (execution-risk): the OMS/Risk Sentinel contract — uuid-idempotent order_intent, per-check risk_check rows, 10 s Reconciler that HALTs on any delta, <= 5 s quote age, the synthetic-bracket and stream-loss flatten sequences, the $500/2-seat/$750 first live envelope, and per-ticket break-even-win-rate rejection (with the arithmetic corrected).
- P3 (data-engineer): the archive contract (hourly closed Parquet partitions with MANIFEST.json hashes and three clocks, availability_basis never mixed, STALE records archived), the single features(symbol, as_of) code path shared by live scorer and research, and the B2 surge-only baseline.
- P4 (ml-scientist): sample-size floors (~785 independent events to detect +5 pts; >= 800 events before any promotion), the registered triple-barrier L_opt grid with bracket chosen offline before any bandit, experiments E1-E5 with falsification criteria, and the Owner Mirror Bot.
- P5 (skeptic-product): the 'LLM-touched' switch that rejects any intent not from a human click or the frozen policy, the Correlation Sentinel capping correlated seats at 3, Gate Keeper's gates.yaml with logged waiver requests, and the 'not before 2027, one setup only' stance on autonomy.

Cross-cutting disagreements:
- Quote-age gate for entries: P2 and P4 require <= 5 s on both underlying and contract for a seconds-horizon book; P1, P3 and P5 carry over the desk's 120 s rule into the gateway. Material: 120 s is two minutes of staleness on a 40 s median hold.
- Live broker: P1, P2, P3, P5 say Alpaca paper now and Alpaca live first with Tradier as fallback if emulated brackets fail; P4 says paper at Alpaca but evaluate Tradier first for live because of native OTOCO. All five reject Robinhood Agentic MCP for bots. P2 adds that Tradier's sandbox (15-min delayed, no streaming) cannot be paper-tested at seconds scale, which undercuts both P4's venue switch and P5's 'same intents on two gateways' trial.
- Stop level on the option: P3 uses -8% (inside spread noise on most sector names); P1, P2, P5 use -20%; P4 registers a grid (-15/-25) and picks offline from logged paths. Time stops range from 20 min (P3) to 30 (P1), 60 (P5), 90 (P2) and a 15m/45m/close grid (P4). Targets are +10 to +12 everywhere; only P2 and P4 do any break-even arithmetic, and both P2 and P5 get it wrong in the worked example.
- First live envelope: P2 and P4 at 1 contract / $500 debit / 2-3 seats / $750 daily stop; P5 at $2,500 per order / 3 seats / $1,500 daily; P3 at the existing $5,000 ceiling / 3 seats; P1 at 1 contract / <= 3 seats with a daily loss of 2% of a not-yet-defined sleeve.
- R2 OPRA subscription set: P2 and P4 fix 260 contracts (65 core x call+put x two expiries); P3 ~650 (ATM ±2 for 65 core); P5 400-600 for the top 40 names by option volume; P1 states 520 with arithmetic that does not match its own strike/expiry description. The ~1,000 cap is UNVERIFIED in every case.
- Where labels are computed: P2, P3, P4 run the nightly labeler on the data mini in a schema the engine cannot read (so intraday counterfactual chips and the Now lane can use them); P1 and P5 put label computation on the research mini's oideval side, which keeps the seal cleaner but leaves the page's bracket counterfactuals unsourced.
- Promotion gates: P4 adds event-count floors (>= 800 events, >= 11 of 15 sessions, ECE <= 0.05) to the 10-session rule; P1 and P2 use Brier skill >= 0.01 plus expectancy CI over sessions with no event floor; P5 uses lane precision >= 45% with lower bound >= 35%; P3 uses ranker precision vs Jeffrey's take-rate, which is ill-defined.
- Timing of the Databento targeted pull: P2 within the first 30 days if metadata.get_cost < $300; P5 prices it days 31-60 and buys if < $500; P1 and P4 only after R2 is running and the label definition has held ~20 sessions; P3 only once S3 is funded. P4 alone proposes Alpaca's own Feb-2024+ option bars/trades as a $0 lower-fidelity backfill first.
- Treatment of the C/P flow input: P4 drops it from the score pending confirmatory E1 and P5 excludes it from features until a 10-session drop-one confirms; P2 uses the drop-C/P variant as a feature; P1 tests setups with and without; P3 keeps it as a feature with coverage %.
- Degree of autonomy ever planned: P5 says Stage 3 not before 2027 and only for one setup; P2 month 6+ with caps raised one notch per 20 clean sessions; P1 day 180+; P4 day 150+; P3 gives no calendar. All agree exits are automated first and entries last, and that Rose/Hal become proposers, Chart/Macro/X/News become feature producers.
- Bots to retire: P2 and P5 explicitly retire Customer/Supplier Bot (0 edges) and fold Soft Grader into code; P1, P3, P4 leave them in place.
- Time-zone errors recur: P2's '3:50 PM PT' hard time stop and P5's '15:45 PT' label cutoff are both after the 1:00 PM PT close; the synthesis should state every clock in one zone.

Factual errors flagged:
- (systematic-pm) R2 sizing: '±2 strikes, nearest two expiries' for 65 names is 5 strikes x 2 rights x 2 expiries = 1,300 contracts, not '65 x 2 x 4 = 520'; the arithmetic does not match the stated set
- (systematic-pm) Suggests 'consider dropping to [FlashAlpha] Basic'; MAP 4 lists Basic at 100 req/day, which cannot cover the 325 wall calls/day the desk already makes (study 7)
- (systematic-pm) Quotes a single '95% CI roughly 51-81%' for both the n=26 (61.5%) and n=40 (67.5%) cells; the n=26 interval is roughly 41-80%
- (execution-risk) Claims the cells above 50% with n >= 1,000 include '±2 held >= 30 s to 5 m'; per study 3, ±2 after a 30 s wait was 43.2% (n=782). Only '±2 held 5 m without the C/P input' (55.8%, n=1,034) and |S|=2 at 15 m (55.7%) cleared 50%
- (execution-risk) Break-even arithmetic: with net win +4.4% and a -20% stop (plus the same ~5.6% cost), break-even hit rate is roughly 82-85%, not '>= 62%'; 62% is below even the no-cost 10/20 figure (66.7%)
- (execution-risk) '3:50 PM PT hard' time stop is after the 1:00 PM PT close; its own Sentinel window is 6:35-12:50 PT, so this should be 12:50 PM PT (or 3:50 PM ET)
- (data-engineer) None confirmed against the maps. Two citations are unverifiable here: 'FEEDS_CURRENT.md line 47: only three feeds append-only as of 10/10' (MAP 2 says the mini package had no archive/append/snapshot writer) and '113 GB free observed' on the box
- (ml-scientist) Kill switch 6 asserts 'broker-side brackets exist for every live position so a dead mini cannot strand a trade', which contradicts its own UNVERIFIED-S note that Alpaca offers no option bracket/OCO; it holds only if live execution is at Tradier/IBKR, and then paper and live venues differ
- (skeptic-product) Setup A: 'expect precision ~40-50%, which is profitable at 12/20 payoff' is wrong; with +12% target and -20% stop the break-even hit rate is 62.5% before spread and fees, so 40-50% loses money
- (skeptic-product) Primary label definition uses 'stop at 0.80 x ask OR 90 min OR 15:45 PT'; 15:45 PT is after the 1:00 PM PT close (should be ET or 12:45 PT)
- (skeptic-product) R2 storage estimate '~500 contracts is on the order of 1-3 GB/day compressed' is roughly 3-10x the other proposals' estimates (P3: 0.4-0.9 GB/day at 1,000 subs; P4: 1-3 GB/month at 260); likely overstated by about an order of magnitude
