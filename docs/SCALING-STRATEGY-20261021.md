# OID desk: scaling a discretionary options book with bots

**Strategy, data, models, UI and bot roster. Prepared 2026-10-21 for the desk owner. Research and paper only; nothing in this document changes any bot, schedule, feed or order authority.**

All clocks are Pacific. Regular trading hours are 6:30 AM to 1:00 PM PT.

## 0. How this was produced and what is verified

This report was built from both repositories (`jeffbazar/oid-trading-desk` at commit `3f9399a`, 2026-10-05, and `jeffbazar/oid-research` at `b29a1bc`, 2026-10-11), the three live-page screenshots dated 2026-10-20 (heatmap, header strip plus table, research studies), and the Oct 4 paper ledger, plus the owner's Robinhood order list for 2026-10-20 supplied as a screenshot. The live site on the Tailscale network was not reachable from the analysis environment; the Field Guide and the study files behind the Research tab were therefore read only as they appear in the screenshots.

The work ran as a four-stage review: four readers mapped the desk operations, the research program, the interface and the current vendor and broker facts; five independent proposals were written from different lenses (systematic portfolio manager, execution and risk engineer, data engineer, quant research scientist, skeptical risk manager plus product designer); three judges scored them; one synthesis merged them; then twelve factual claims the plan depends on were handed to pairs of adversarial fact-checkers. Three claims were wrong as written and are corrected here (Robinhood agentic options, the pattern-day-trader rule at Alpaca, the FlashAlpha Basic cap). The supporting material is in `docs/strategy-2026-10-21/`: the three maps, the vendor fact sheet with corrections, the five proposals, the judge summary, the synthesis draft and the full verification log.

Status vocabulary follows the repositories: **documented** (in a doc), **configured** (code or config present), **observed** (verified by a run artifact), **not built**. Vendor facts carry **verified** (an official page or SDK source was read), **extract** (an official page quoted through a search engine because the sandbox could not open it) or **unverified**.

## 1. Executive summary

- **The edge to scale is the owner's hand, and it is unrecorded.** Live fills are in neither repository (one session, 10/20, arrived as a screenshot during this review and is analyzed in section 2.5), and no decision has ever been written at decision time. The two measured systems, a long-calls-only paper desk with a 24-hour median hold and page scores that are near coin-flips, are not the thing that works. Capture comes before any automation and costs nothing.
- **The one conditioner that survives every study is a 1-minute volume surge (rvol at or above 3x).** On the wall-magnet sample it roughly triples 15-minute breakout odds away from walls (8.7% to 26.7%). Walls are noise at the single-name level (46.9% vs 44.9%). The live call/put flow input appears to hurt the core score (plus or minus 2: 50.3% right without it against 55.8% with it removed). Holding a score for 30 seconds to 5 minutes before acting helps. All of this rests on one or two correlated sessions and on page-local scripts that are not in either repository.
- **Automate in this order: capture, then exits, then candidate ranking, then entries.** Exits are deterministic and are where the paper desk demonstrably failed: 45 of 57 closes landed on eight shared timestamps, one ticket bled to minus 61% waiting for a book harvest, another gave back a +164% excursion to +17.8%. Entries, where the human edge lives, are automated last.
- **No language model ever touches an order.** A deterministic Execution Gateway on the data mini is the only process with broker credentials. An intent that did not originate from a human click or a frozen, hash-pinned policy is rejected by construction. Rose and Hal become proposers and narrators.
- **Alpaca paper now, Alpaca live first, Robinhood Agentic as a second venue to measure, not to assume.** The fact-check found that Robinhood's agentic account has supported single-leg options orders since July 2026 and that its customer agreement authorizes agent orders; "zero orders" is OID's own policy. Alpaca still goes first for technical reasons (the collector, the clock and the symbology already live there; paper accounts carry options Level 3; the order API is documented), and a venue-latency study decides whether Robinhood becomes the second live path.
- **The target variable changes.** Not "direction right at 5 minutes" but the option-leg label: did the contract's bid reach +X% over the entry ask before a minus Y% stop or a time stop. That label needs the streamed OPRA quote archive (R2 in the research repo's feed-additions plan) that does not exist yet. Starting it is a day-one item.
- **Gates are measured in events, not days.** Detecting a 50% to 55% lift needs roughly 785 independent events; with overlapping 15-second snapshots and correlated names the design effect is three to five times that. Promotion needs at least 800 events over at least 15 sessions, Brier skill of at least 0.01 against the surge-only baseline, and executable expectancy whose session-block bootstrap interval excludes zero.
- **The first live envelope is tiny and widens one notch per 20 clean sessions:** one contract, $500 debit, two open seats, $750 daily loss stop, 15-second veto window. Autonomous entries are a 2027 question, for one setup only.
- **Buy nothing new.** No FlashAlpha Alpha, no DRAMeXchange, no Silicon Data, no Massive options, no X top-up. The one likely add is a targeted Databento history pull, realistically $25 to $100 after the $125 new-account credit, capped at $300, after a cost query.
- **Day-one owner decisions:** open the research-mini network path and set the seal date; approve the 260-contract OPRA subscription set; commit to clicking Call, Put, Pass or Watch on every decision; approve Alpaca paper as the execution target; commit the live page's scorer and replay scripts to `oid-research` so their results can be hashed and re-run.

## 2. Diagnosis

### 2.1 What the edge is today

The owner reads a genuine volume event on a liquid AI or semiconductor name, commits to a direction in seconds, buys a near-the-money option so that a 0.3% to 0.8% move in the underlying becomes +10% to +20% on the premium, and exits before the move decays. That is a reaction-speed and exit-discipline edge on a high-gamma instrument, not a forecasting edge. Nothing in either repository can confirm or deny that it works, because the live fills are in no repository and no decision row has ever been written at decision time (`docs/strategy-2026-10-21/map-desk-ops.md`, section f; `oid-research/docs/DATA_GAP_REPORT.md`, family J: "no structured rejected/no-trade candidate records").

### 2.2 Three systems that do not know about each other

1. The owner's hand: unmeasured.
2. The paper desk: Rose and Hal running wall-press and Soft A setups, long calls only (54 of 57 tickets, zero outright puts), Rose's median hold 24 hours, closes in administrative batches.
3. The live page: Direction, Light and Full scores whose own Research tab rates them near coin-flip.

The bots' Soft A workflow and the page's scores do not reference each other. The thing that reportedly makes money has no data trail; the things that have data trails are not the thing that makes money.

### 2.3 What the 10/20 studies say, read plainly

Every "all nonzero scores" hit rate is below 50%: 34% (direction first look), 38% (core waiting), 38.8% (light replay), 41.8% (call/put agreement), 47.6% (drop-one baseline). The most extreme core reading (plus or minus 3) gets worse with a 30-second wait (34.8% to 22.2%, n = 27). The score is right most often when momentum is decelerating (46.7%) and worst when accelerating (31.3%): it saturates after the move and chases. The raw direction score correlated minus 0.39 with the close return on its one live day, which is one or two effective observations of market direction, not an inverted signal. The plus/minus asymmetry in calibration (core +2.0 raw right 58%, minus 2.5 raw right 33%) is an up-day base rate; no same-window base rate is reported anywhere.

The positive cells share one conditioner:

| Cell | Hit rate | n |
|---|---|---|
| Core plus or minus 2, held 30 s | 37% to 43.2% | 782 |
| Core plus or minus 2, with surge, held 2 min | 61.5% | 26 |
| Light plus or minus 3, with surge, held 5 min | 67.5% | 40 |
| 15-min breakout after 1-min rvol of 3x or more, away from walls | 8.7% to 26.7% | subset of 82,190 ticker-minutes (n not shown) |

The binomial 95% interval for n = 40 at 67.5% is roughly 51% to 81%; for n = 26 at 61.5% roughly 41% to 80%. Fifteen-second snapshots labeled at 5 minutes overlap about twenty times, so n = 14,703 behaves more like n of about 700, clustered on correlated names in one or two sessions. Under the research program's own rules (`program.md` sections 13 to 16) this is hypothesis generation, not evidence, and 10/19 and 10/20 are consumed development dates for any study of these cells.

Two further results shape the design. Removing the 15-second and 1-minute call/put input raised "plus or minus 2 right after 5 minutes" from 50.3% to 55.8% (n 1,552 to 1,034) and cut score changes by 31%; the plus-or-minus-3 cell moved the other way (54.3% to 42.9%, n 46 to 14). The wall-magnet study found walls add about two points over chance, consistent with the literature, where dealer-gamma effects are index-level and regime-level, not single-name levels.

**Reproducibility caveat.** These figures transcribe the Research tab correctly, but the scripts (`score_replay_changes.py`, `score_replay_wide.py`, `daily_scorecard.py`, `score_learn.py`) and their output files are in neither repository, and `oid-research/README.md` still states that no experiment has been run. Until they are committed and hashed they are unaudited page claims. That is a day-one item, not a day-30 one.

### 2.4 What the paper ledger says

| | Rose | Hal | Desk |
|---|---|---|---|
| Closed tickets (Sep 10 to Oct 4) | 31 | 26 | 57 |
| Net paper P&L | +$12,844 | +$2,044 | +$14,888 |
| Wins / losses | 19 / 11 | 13 / 13 | 32 / 24 (1 flat) |
| Average win / average loss | $778 / minus $175 | $366 / minus $209 | $610 / minus $193 |
| Median ticket return | +17.8% | +0.4% | +2.1% |
| Top three winners as share of net | 89.1% | over 100% | 77% |
| Median hold | 24 h (41% within 8 h) | 31 h | 24.5 h |

Rose's top three tickets (AMD 550C +$4,917.50, META 670C +$4,550, LRCX 310C +$1,975) are $11,442.50 of her +$12,844. Forty-five of 57 closes landed on eight shared timestamps (43 on the seven timestamps carrying three or more closes); 26 carry explicit owner or administrative tags and the rest are inferred from same-timestamp batching. The 9/18 cohort of seven wall-presses closed together on 9/21, one market move counted seven times. Seven Hal closes are stamped 9:15 PM PT on 9/22. Entry is the ask, exit is a mark, with zero fees or slippage; two credit spreads carry negative cash yet are tagged `win_exit`; MFE is a 5-to-15-minute sampled maximum, so the +50% trail-arm has never been tested against an executable peak. The close-trigger engine has never auto-closed anything and produced zero review alerts. Profit factor 7.7 is three correlated tickets closed together; Hal's 1.75 with a median of +0.4% is noise. The desk's own audit is right that this sample supports no return target. It also cannot serve as a baseline for the owner's style: wrong instruments, wrong horizon, wrong exits. The 10/09 ledger on the box has 64 tickets; any restatement should use it.

### 2.5 A session of live fills (10/20, from the owner's order list)

The order list for 2026-10-20 is the first set of real fills the desk has seen. It covers 06:44 to 07:46 AM PT, the first 76 minutes of the session, in two names on one up-day, so it demonstrates the style rather than establishing a track record.

| Time PT | Contract | Side | Qty | Avg fill | Realized | Hold | Return |
|---|---|---|---|---|---|---|---|
| 06:44:01 | CRWV 10/23 60C | Buy | 300 | $1.90 | | | |
| 06:56:49 | CRWV 10/23 60C | Sell | 300 | $2.10 | +$6,000 | 12 m 48 s | +10.5% |
| 06:59:24 | NVDA 10/23 215C | Buy | 1 | $3.05 | | | probe lot |
| 07:05:45 | NVDA 10/23 215C | Buy | 100 | $3.60 | | | |
| 07:07:50 | NVDA 10/23 215C | Sell | 101 | $4.00 | +$4,095 | 2 m 05 s | +11.1% on the 100 lot |
| before 07:15 | CRWV 10/23 65C | Buy | about 247 | about $1.18 | | | not in the visible list; implied by the two sells |
| 07:15:12 | CRWV 10/23 65C | Sell | 216 | $1.30 | +$2,592 | | +10.2% |
| 07:16:36 | CRWV 10/23 65C | Sell | 31 | $1.25 | +$214 | | +5.9% |
| 07:22:06 | CRWV 10/23 65C | Buy | 400 | $1.45 | | | |
| 07:23:33 | CRWV 10/23 65C | Sell | 400 | $1.60 | +$6,000 | 1 m 27 s | +10.3% |
| 07:24:43 | CRWV 10/23 65C | Buy | 300 | $1.75 | | | |
| 07:29:09 | CRWV 10/23 65C | Sell | 300 | $2.00 | +$7,500 | 4 m 26 s | +14.3% |
| 07:39:28 | CRWV 10/23 65C | Sell | 81 | $2.10 | +$810 | | buy not in the visible list |
| 07:40:47 | CRWV 10/23 65C | Buy | 300 | $2.20 | | | |
| 07:46:00 | CRWV 10/23 65C | Sell | 300 | $2.60 | +$12,138 | 5 m 13 s | +18.2% |

Realized +$39,349 across eight sells, zero losses shown, largest ticket $66,000 of premium (300 contracts at $2.20).

What it shows:

- **Instrument:** the nearest weekly (Monday for a Friday expiry, 3 DTE), near the money. Not the 5-to-21-DTE range the research profiles proposed.
- **Size:** 100 to 400 contracts, $36,000 to $66,000 of premium per ticket, 7 to 130 times the paper desk's single contract.
- **Holds:** 87 seconds to 13 minutes; exits at +10% to +18%, consistent with the stated rule.
- **Re-entry:** the same contract (CRWV 65C) bought four times at rising prices ($1.18, $1.45, $1.75, $2.20) and sold each time for about +10%: a tranche pattern riding one trend, which the paper desk never did and no bot models.
- **Probe:** a one-contract buy (NVDA at 06:59) preceded the 100-lot entry.
- **Survivorship of the day itself:** eight winners in a row on an AI up-day. The losing days are needed before any hit rate is quoted.

What it changes in the plan:

1. **Contract policy.** The Contract Selector and the label grid include the nearest weekly (2 to 5 DTE); 0 and 1 DTE stay excluded. The label resolution must be the 15-second OPRA stream (R2); 1-minute bars cannot label an 87-second hold.
2. **Sizing.** The bot ladder is a fraction of the actual ticket: $500, $1,500 and $5,000 are roughly 1%, 2.5% and 8% of a $60,000 ticket. The human-click live track through the Gateway at full size is the larger prize, because mechanical exits on tickets of this size matter more than a small engine book.
3. **Capacity.** At 300 to 400 contracts in a 3-DTE weekly the desk is a visible participant. The Capacity Bot moves into the day-15 set and measures the desk's own footprint (fill against the mid at decision, share of displayed ask size consumed).
4. **Fees by venue.** Robinhood charges no options commission (regulatory fees only). Alpaca at $0.65 a contract is about $390 on a 300-contract round trip, 0.6% of debit: small against +10% targets, but it belongs in the per-venue fee model and it slightly strengthens the case for the Robinhood Agentic venue study.
5. **Setup A2, continuation re-entry.** After a target exit, re-enter the same contract on the next surge at a higher price with the same bracket. Register it with its own label and a cap on tranches per name per hour.
6. **Capture.** This list is the `owner_fills` table. The Robinhood MCP read tools pull it nightly with timestamps to the second, so the manual-export question is closed.

### 2.6 Where it is fragile

1. Eleven decisions live only in the owner's head (map-desk-ops, section f): go/no-go, gate waivers, which wall "governs", exit timing, loss acceptance, contract geometry under the debit cap, universe, vendor economics, rule promotion, macro discount, live authority. You cannot automate what is not written down.
2. No negatives. No WATCH, NO_TRADE or REJECT log exists, so no classifier can learn the selection and no detector can be scored for precision.
3. No option-leg label. Options history (family C) is absent; every study is `UNDERLYING_ONLY`; "did the option bid reach +10% over my entry ask" has never been computed for a single event.
4. Latency is unmeasured. `latency_model_ref` is `OWNER_DECISION_REQUIRED` in every study; the collector's lag histogram is not persisted; the agent path on the box is seconds to minutes while the owner's holds start at seconds.
5. No archive the research sandbox can reach. The data mini now holds 1-minute bars, 1,045 wall snapshots, a 15-second `score_features` table and nightly `score_labels`, but none of it is in git, hashed, or reachable by the research mini, which has users, budget and isolation checks but zero datasets and no network path (the data mini silently drops traffic from 192.168.5.199).
6. One regime: Sep 10 to Oct 20, an up-tape in AI names. Puts have never been traded in paper.
7. Governance drift: two Macro score definitions coexist (the formula in `dashboard/MARKET-TAPE.md` and the judgment-only rule in `prompts/03`); "chat approval is not a ticket" is printed on the blotter while a chat "yes" is in practice the trigger; the shared X pool was at $55.72.

**Working thesis.** The edge to encode is *surge, then fast gamma entry, then mechanical exit*, with the owner's selection judgment learned from logged decisions. Scores stay in shadow until they beat the surge-only rule on sealed future sessions. Walls are a diagnostic feature, never a trigger.

## 3. Scaling strategy

Four stages. Each adds authority only after a gate measured by code the owner does not edit, on data that post-dates the rule, in event counts rather than day counts. Every stage keeps the previous stage's kill switches.

### Stage 0: discretionary with capture (now to about day 30)

Trade exactly as today. Every Call, Put, Pass or Watch and every exit is written at decision time, keyed to the 15-second `score_features` snapshot id. Live fills are joined daily (the Robinhood MCP read tools can export positions and orders from the primary account; CSV is the fallback). The Exit Manager runs in paper shadow against the owner's entries, so the first bracket counterfactuals exist from week two.

Gate to leave: at least 20 sessions; at least 150 decision rows including at least 50 Pass or Watch negatives; at least 60 live fills with timestamps; at least 100 option-leg labels computed from the R2 stream; the decision-to-order-acknowledgment latency histogram persisted; the paper tickets restated with signed cashflows, fees and administrative closes separated.

### Stage 1: assisted (about day 30 to 90)

A deterministic Candidate Ranker puts at most five names in a Now lane with the three study-backed conditioners. The ticket drawer is pre-filled with contract, debit, bracket, break-even win rate and gate results; the button reads "Send to gateway (PAPER)". The owner clicks; the Gateway sends to Alpaca paper and runs the synthetic bracket. A frozen Shadow Trader emits entries on the same snapshots.

Gate: at least 20 sessions and at least 60 Gateway tickets (the ledger ran about two tickets a day, so a 100-ticket bar would stall); slippage-adjusted net expectancy per ticket above zero with a session-block bootstrap 90% interval excluding zero; top-three share of net below 40%; lane precision (lane candidates acted on that hit the target before the stop) of at least 45% with a lower bound of at least 35%, reported separately from the owner's own hit rate on the same events; zero unreconciled fills; bracket exits dominate (administrative closes below 10%); the kill switch drilled weekly with logged cancel-all latency.

**Human-click live track.** The owner's own tickets through the Gateway with mechanical brackets are a separate track from engine-generated entries. That path is the existing style plus disciplined exits, so it may go live after 20 clean paper sessions and zero reconciliation mismatches, independent of the engine gate, at the Stage 2 envelope below.

### Stage 2: supervised auto (about day 90 to 150)

The Candidate Engine sends paper orders itself; the owner has a 15-second veto window on entries and none on exits. After 20 clean paper sessions, live with hard caps: one contract, $500 debit per ticket, two open seats, $750 daily loss stop. Caps rise one notch per 20 clean sessions ($500 to $1,500 to $5,000 debit; two to four to eight seats) only while live expectancy after real fills and fees is not statistically worse than paper, paired by session; realized slippage is at or below modeled; expected calibration error is at most 0.05 on live labels; there are zero risk-limit breaches; and the reconciliation mismatch count is zero. The day-90 review authorizes; a realistic first live order is day 90 to 120.

### Stage 3: autonomous inside an envelope (not before 2027)

For the one setup that passed Stage 2. Entries and exits run automatically within per-name, per-sector and daily caps; the owner edits `policy.yaml` weekly and does not approve tickets. Any gate metric that fails on a rolling 20-session window demotes to Stage 2 automatically. The desk never becomes autonomous in the sense of unlimited; it becomes autonomous inside a config file the owner signs.

### Capital frame

Define a sleeve for the bot book, separate from the discretionary Robinhood book. Risk per ticket is the planned stop times the debit (a minus 20% stop on a $500 debit risks $100, which is 0.5% of a $20,000 sleeve). State the notch ladder in both contracts and percent of sleeve, so "2% of sleeve" means something. The Correlation Sentinel counts the owner's live Robinhood positions (read through the MCP) in its seat and group caps, because the two books share the same names on the same tape.

### Measured how, throughout

One primary metric: net expectancy per eligible opportunity under the research program's fill rules (buy at the ask after the decision plus measured latency, sell at the bid at exit plus latency), reported with the B0, B1 and B2 baselines (section 5), Brier skill for the probability component, the top-three contributor share, and a session-block bootstrap. Hit rate alone never gates anything.

### What never gets automated

Gate waivers, contract geometry under the debit cap (the far-out-of-the-money substitution habit that produced a MU 1600C at 46% out of the money), universe changes, and anything on 0DTE.

## 4. Bot architecture

Three planes with a hard boundary. The **data plane** and the **execution plane** are deterministic Python on the data mini, next to the Alpaca stream. The **reasoning plane** is the language-model agents on the box, which produce slow features, proposals and reviews, never orders. The box is a shared 8-vCPU host with 0.8 to 5.4 GiB free; it never holds broker credentials.

| Component | Host | Deterministic | Owns | Authority |
|---|---|---|---|---|
| Collector (exists, port 8787) | data mini | yes | SIP and OPRA streams, 15 s `score_features`, R2 quote archive | none |
| Archiver (R5) | data mini | yes | append-only Parquet of every feed, manifests | write archive |
| Feature Service | data mini | yes | one `features(symbol, as_of)` used by the live scorer and research | none |
| Surge Engine v2 (exists as `vol_surge` dry run) | data mini | yes | `surge_events` with hysteresis, sector aggregation | gate input |
| Candidate Ranker | data mini | yes | Now lane, at most five candidates, `lane_version` | propose |
| Contract Selector | data mini | yes | 0.45 to 0.55 delta, nearest weekly to 21 DTE, spread cap, OI at least 500, debit cap, break-even win rate, per-name capacity | propose; rejects far-OTM substitution |
| Risk Sentinel | data mini, separate process | yes | pre-trade checks, caps, daily loss, kill flag; sole writer of `risk_state` | REJECT / HALT |
| Execution Gateway and Bracket Manager | data mini | yes | `order_intent`, idempotent sends, fills, brackets, time stops; sole broker-API writer | the only order path |
| Reconciler | data mini | yes | broker positions and orders versus the OMS every 10 s; HALT on any delta | halt |
| Labeler (extends nightly `score_labels`) | data mini, label schema | yes | forward returns, option-leg first passage, bracket counterfactuals, baselines | none |
| Shadow Trader and Scorecard | data mini | yes | challengers beside the champion on identical snapshots; promotion-ladder status | demote on drift |
| Gate Keeper | data mini plus cockpit | yes (agents propose) | versioned `gates.yaml` and `policy.yaml`, waiver queue | only the owner approves exposure-raising changes |
| Rose and Hal | box | agent | rationale, catalyst context, structured candidate and REJECT log (R7) | propose only; read-only on the OMS |
| Macro, X Summarizer, News (Peanut) | box | agent | typed slow features: event flags, tone, macro scores | exposure-reducing gate flags only |
| Research Bot | research mini | agent plus code (`editable/` only) | campaigns, evidence packages | `trade_authorization = NONE`, always |
| Data Ops | box | agent plus scripts | feed health, quotas, archive integrity, latency objectives | can flip feeds STALE and HALT the Gateway on a data-health failure |

**The owner owns `policy.yaml`.** Gates, thresholds, universe, budgets and caps live in one git-versioned file with a signed changelog. Bots read it; no bot writes it. Hard ceilings ($5,000 debit, 15 seats, the daily loss limit) are coded into the Gateway, and `policy.yaml` can only lower them. Every override is a row in `overrides` with a reason chip, so waivers become data instead of chat sentences. This replaces the human changelog of promoted never-again rules and the "named gate governs" pattern.

**Order path contract.** An intent is a typed row:

```
order_intent {
  intent_id (uuid, idempotency key), ts_decision, snapshot_id, setup_id, policy_version,
  actor in {jeffrey, engine:<hash>}, symbol, occ_symbol, side = buy_to_open, qty, limit_px, max_debit,
  bracket {tp_pct, stop_pct, time_stop_s}, risk_check_id, status }
risk_check  { checks[] {name, value, limit, pass}, verdict in {PASS, REJECT, HALT} }
fill        { broker_order_id, ts_broker, px, qty, fee, slippage_vs_mid_at_decision }
position    { peak_mark, bracket_state in {OPEN, TP1_DONE, TRAILING, CLOSING}, time_stop_at }
recon_event { broker_qty, oms_qty, delta, action }
```

SQLite in WAL mode on the data mini, mirrored to Parquet nightly.

**Risk Sentinel checks, in order. Any failure is a REJECT; two REJECTs in a row on different intents is a HALT.**

1. Kill flag absent.
2. `actor` is a human click or a frozen policy hash listed in `policy.yaml`. Anything else is rejected by construction; this is the "agent-touched" switch.
3. Mode (PAPER or LIVE) matches the intent.
4. `policy_version` equals the current version.
5. Quote age at most 5 seconds on both the underlying and the contract, from the stream. The desk's 120-second rule survives only for Hal-cadence paper tickets; the core score's median hold on 10/20 was 40 seconds, so two minutes of staleness is longer than the trade.
6. Spread over mid at most 5% for core names, at most 8% at half size for sector names.
7. Debit at or below the cap, and open debit plus the new debit at or below the book cap.
8. Seats below the cap; one per name; two per sector group; the Correlation Sentinel allows at most three correlated seats across groups, counting the discretionary Robinhood book.
9. No earnings inside the hold window and no scheduled macro print within 15 minutes, from the deterministic Event Gate file.
10. Account buying power (intraday buying power under Alpaca's intraday-margin framework) covers the debit; the day's P&L is above the daily loss limit.
11. Consecutive-loss pause (three losses pauses entries for 30 minutes); a per-name cooldown of 10 minutes after a stop.
12. Order rate at most six per minute desk-wide; duplicate `intent_id` rejected.
13. Underlying day change below 3% (the existing chase gate, kept until evidence says otherwise).
14. Session clock between 6:35 AM and 12:50 PM PT for new entries.
15. Latency budget: no policy may run whose target horizon is shorter than five times the measured decision-to-broker-acknowledgment latency.

**Synthetic brackets.** Alpaca's options order classes are `simple` and `mleg` only, and order types are market, limit, stop and stop-limit; there is no bracket, OCO, OTO or trailing stop for options (verified in the alpaca-py SDK source and confirmed by Alpaca staff on the forum). Single-leg options accept a native stop or stop-limit, but with no OCO two resting sells can both execute, so the stop stays in software. The Bracket Manager therefore runs the bracket itself: on fill, post a resting GTC limit sell at the target (GTC is accepted on options limit orders per the 2026-08-28 changelog; GTC orders auto-cancel after 90 days, irrelevant for a same-day book); a software stop evaluated on every quote tick cancels the resting take-profit and sends a marketable limit at bid minus one tick, re-priced every 2 seconds up to five times, then market as the last resort; a time stop flattens at `time_stop_at`; a hard flat for everything at 12:55 PM PT. A stream disconnect longer than 10 seconds with open positions triggers the flatten-at-limit sequence, then HALT. Reconnect always reconciles before any new send, so a double fill cannot survive a reconnect. A day-8 paper probe records the broker's response to an options order with `type=trailing_stop` and one with `time_in_force=gtc`, so the gateway's assumptions are tested rather than read.

**Kill switches, independent and drilled weekly.** (1) A file flag `/opt/oid/KILL` on the data mini, checked before every send and every second by the Bracket Manager: cancel all, flatten, refuse new; any bot or Data Ops can set it, only the owner clears it. (2) Daily loss limit and max-open-debit ceilings hard-coded in the Gateway. (3) Broker side: a trading-key revocation script (the data key stays) and a close-all script runnable from a phone. (4) Feed health: Alpaca stream lag over 5 seconds or an OPRA gap over 10 seconds blocks new entries while exits continue; FlashAlpha quota below 200 makes walls diagnostic, no block. (5) Drift halt: today's realized hit rate on at least 20 decisions below the 10-session 5th percentile, or a model probability-distribution shift (Kolmogorov-Smirnov test against the last 10 sessions), drops the engine to shadow only. (6) Three consecutive fills worse than modeled by more than one tick halts entries. (7) Heartbeat: the cockpit shows the Gateway heartbeat age and goes red at 10 seconds. (8) Physical: launchd disable; the Gateway refuses to start without a fresh 24-hour `arm` token. The weekly drill flips (1), verifies cancel-all latency under 2 seconds and zero residual orders, and logs it.

**Broker decision (corrected after fact-check).**

| Venue | Facts | Role |
|---|---|---|
| Alpaca | Options levels 0 to 3; paper accounts get Level 3 automatically, live needs a Level 2 application with lead time; order classes for options are `simple` and `mleg`, types market, limit, stop, stop-limit; GTC accepted on options limit orders; OPRA quote feed with 1,000 quote subscriptions and one websocket connection per endpoint (the R2 archive sink must share the collector's connection); historical option bars and trades from February 2024, no historical quotes documented; Algo Trader Plus $99 a month is the data plan, and a brokerage account with paper keys is separate and must be created; intraday-margin framework since 2026-06-04 (no pattern-day-trader lockout, no $25,000 minimum; PDT API fields removed 2026-07-06). | **Paper now, live first.** Same vendor, clock and symbology as the collector; documented order API; paper-to-live slippage comparison is not venue-confounded. |
| Robinhood Agentic Trading | Official MCP service launched 2026-05-27 with equities; single-leg options rolled out from 2026-06-12 and reached all US customers by 2026-07-06; crypto later; trades execute in a separate funded Agentic account, other accounts are read-only; trade approvals are off by default for external MCP agents; the Customer Agreement revised 2026-10-01 authorizes and binds AI-agent orders (sections 4.13 and 29.8); multi-leg orders are not supported through agents; no documented streaming data or bracket orders through the MCP; acknowledgment latency unmeasured. The desk's "zero orders" rule is OID policy, and the desk's own notes already anticipate a sanctioned "live Agentic ticket". | **Second venue to measure, not to assume.** During Stage 1 run a venue-latency study: one-lot orders in the Agentic account, decision-to-acknowledgment latency and reconciliation cleanliness. Evaluate as a second live path if acknowledgment latency is under 2 seconds and reconciliation is clean. Use the MCP read tools now as the automated source of the owner's fills. |
| Tradier | Native OTO, OCO and OTOCO with option legs on the free Lite tier ($0.35 a contract); Pro $10 a month removes commissions; the sandbox is 15-minute delayed with no market-data stream, so it cannot be paper-tested at seconds scale. | **Fallback** if synthetic brackets fail a 20-session paper test; $0 to evaluate. |
| Interactive Brokers | TWS API with full bracket and OCO support; `ib_async` maintained; $0.65 a contract on Lite. | Only if the book outgrows both. |
| tastytrade | Open API, official MCP server, sandbox; $1 a contract to open, $0 to close. | Not needed now. |

Confirm in writing before Stage 2, from Alpaca: the options order classes and time-in-force behavior above, the `mleg` constraints, the subscription cap, and whether the 4x intraday multiplier applies to options buying power. Robinhood's margin regime for the owner's own account remains unverified; note it rather than assume it.

## 5. Models

**Model the thing the exit rule pays on.** Two tracks, never confused (research program section 17).

**Executable label (primary).** For a decision at t0 on the nearest 0.50-delta call or put listed at t0, from the nearest weekly (2 to 5 DTE) out to 21 DTE: `L_opt(X, Y, T)` in {target, stop, timeout}, where target means the contract **bid** reaches at least (1 + X) times the entry **ask** before the bid falls to (1 minus Y) times the entry ask, or t0 + T, or 12:55 PM PT. Registered grid: X in {10, 12, 15, 20}%, Y in {15, 20, 25}%, T in {20, 45, 90 minutes}. Secondary continuous label: `ret_policy`, the signed net return of each bracket under the fill rules and the registered latency. `L_exc`: the 15-minute maximum favorable excursion in ATR units from the true stream, not sampled. Because the label is bid against entry ask, the spread is already inside it: a quote 5% wide needs about a 17% move in the mid to show +12%.

**Underlying label (cheap, interim).** The 5, 15 and 30-minute excess return against QQQ; the existing `score_labels`, published as `UNDERLYING_ONLY` while the option archive is shallow.

**From option target to underlying move.** For a near-the-money option with premium P on an underlying at S, the premium's percentage move is roughly delta times S over P times the underlying's percentage move, plus a gamma term that helps on the way up. On the AMZN ticket in the ledger (ask $7.25, spot 245.7, delta about 0.5) that leverage is about 17, so +12% on the option is about +0.7% on the stock before the spread. The Contract Selector reads delta and gamma from the chain snapshot, computes the implied underlying move for each bracket target, and prefers 0.40 to 0.50 delta when gamma per dollar matters more than probability of touch. This is also why wide spreads are the tax that decides everything.

**Baselines, always reported.** B0: same-name, same-session, same-time-of-day up-fraction. B1: QQQ h-minute return sign. B2: the naive surge rule, enter on every rvol at or above 3x at the day high or day low with no score. A model earns nothing until it beats B2, which is what the owner's eye already does.

**Features (at most 30, all with `feature_available_at` at or before `decision_at`, enforced in code).** Tier 1 (some evidence): 1-minute rvol against the same-minute norm, 5-minute rvol, 10-second pace, surge flag, side and age, held-score seconds, score value and config hash, momentum state with hysteresis, distance to the day high or low in ATR, sector-group rvol and change, QQQ and SMH 5-minute return, minutes since the open, the page's market-momentum breadth reading (names making new 15-minute highs on 2x volume). Tier 2 (option microstructure, new from the R1 and R2 archives): at-the-money spread as a percent of mid, ask size, option volume against open interest, implied-volatility change over 15 minutes, IV rank against the trailing 60 sessions, 15-minute call/put premium with coverage percent. Tier 3 (diagnostic): wall distance percent and age, UW lean with age, news first-seen within 15 minutes (presence and tone), VIX 15-minute change, macro scores, index gamma sign from UW as a regime flag. Excluded: raw 15-second call/put at under 20% coverage, UW lean of unknown age, anything an agent produced without a prompt hash.

**Model classes, in order; each earns its place on out-of-fold Brier skill.** (1) Stratified hit-rate tables with Wilson intervals, which is what the Research tab already does, made the registered B2 and B3. (2) L2 logistic regression, as `config.draft.json` specifies, Platt-calibrated on the last 20% of each outer window. (3) Histogram gradient boosting (scikit-learn 1.9.1 is installed on the research mini), depth 3, at most 200 trees, minimum 50 samples per leaf, monotone constraints on rvol and held duration; admitted only if Brier skill over logistic is at least 0.01 with the interval excluding zero. Nothing deeper: the independent-event count is in the hundreds. Walk-forward by session with purging by actual `label_end_at` and an embargo of at least two sessions; session-block bootstrap; probability of backtest overfitting reported once more than five configurations are compared. Retraining happens only by promotion of a new frozen version, never in place.

**Calibration.** A trading threshold is set on calibrated probability and expected net dollars per opportunity, not on hit rate. Isotonic calibration at n of 2,000 or more, Platt below. Reliability by decile with n is the first chart on the Research tab; a model is calibrated when the 10-session rolling bucket hit rate is within five points of the forecast for every bucket with at least 50 observations; expected calibration error of at most 0.05 is a live gate.

**Sample sizes, stated once.** Detecting 50% to 55% at two-sided alpha 0.05 and power 0.8 needs about 785 independent events. With a three-to-five-times design effect from 15-second overlap and cross-name correlation, budget 2,500 to 4,000 snapshots or about 800 non-overlapping decision events. The "plus or minus 2 held 30 seconds" cell produced about 780 holds on 10/20, so 10 to 15 sessions; the "plus or minus 2 with surge held 2 minutes" cell produced 26, so 30 to 60 sessions; the option-leg label at 5 to 10 trades a day needs 50 to 100 sessions to separate 40% from 46%. The page's plan to "beat the current score on 10+ days" needs an event floor, not just a day count.

**Promotion ladder (steps 5 to 8 of the page's score-learning plan, made concrete).** DRAFT, then REGISTERED (hypothesis, thresholds, baselines and dates frozen in the registry), then DEVELOPING (development dates only), then FROZEN (hashed), then SHADOW (live on the data mini, forecasts to `shadow_forecasts`, zero authority), then CHALLENGER (at least 15 live sessions and at least 800 events; compared with the incumbent on identical snapshot ids; promoted only if Brier skill is at least 0.01 and executable expectancy is at least the incumbent plus a registered margin, interval excluding zero, winning at least 11 of 15 sessions, expected calibration error at most 0.05, no single session over 30% of the lift), then INCUMBENT, then RETIRED. Only the owner flips CHALLENGER to INCUMBENT, by editing `policy.yaml`; the scorer loads only hashed configurations and the page shows the hash. Demotion is automatic on the mirror test over a rolling 20 sessions. The research-to-live handoff is a configuration (`model_<hash>.json`, `features_<hash>.py`), never agent-written code without a human diff review.

**Registered experiments, dates from 10/21 onward only.** Campaign 1 has zero headroom (50 of 50 configs, 6 of 6 families), so these are campaign 2, which needs its own budget: proposed 60 configs, 6 families, 6 wall-clock hours, 2 workers, stop after 10 non-improving trials.

- E1, drop call/put flow, confirmatory: removing the 15-second and 1-minute call/put input raises the plus-or-minus-2 5-minute hit rate by at least 3 points over 10 sessions; falsified if the session-block 90% interval includes zero. If supported, core v1.1 becomes v1.2.
- E2, surge-conditioned hold: core plus or minus 2 held at least 30 seconds with rvol at least 3x; light plus or minus 3 held 5 minutes with a surge; against B2; at least 15 sessions and at least 400 events.
- E3, momentum gate: act only on DECEL, act on all, never on ACCEL; ACCEL (n = 163 on 10/20) registered as the fragility flag.
- E4, surge event study with the option leg: after rvol at least 3x at the day high or low, the distribution of `L_opt` by rvol bucket, time of day and sector rvol. Needs R2.
- E5, bracket grid: counterfactual net dollars per opportunity for X by Y by T on E4 events; the winner becomes the Exit Manager configuration. A contextual bandit over bracket arms is the right end state, but with under 500 trades it mostly explores; Stage 3 only, Thompson sampling over at most six arms per regime with doubly-robust off-policy evaluation on logged paths first.

**Language models: should and should not.** Should: classify news and filings into typed gate flags (earnings, guidance, halt, macro print) with confidence and an evidence quote; produce the structured REJECT and NO_TRADE log for Rose and Hal (R7); write and review study specifications and code inside the sandbox; explain why-this-fired in plain English; draft the weekly post-mortem and propose features, not rules. Should not: sit in the sub-minute decision path; compute a number that gates an order; choose a contract, size or exit; waive a gate; hold broker credentials; score their own experiments; read sealed dates. Any agent output used as a feature runs at temperature zero, is versioned by prompt hash, logged, and scored like any numeric feature. Before any agent flag may reduce exposure, build a 200-item gold set of headlines and filings scored by hand and require a precision floor on it. Use a small, fast model for classification routines and a large model only for research, post-mortems and code review; measure the token run rate in week one, because about eighteen routines a day is a real cost line that nobody has quantified.

## 6. Data collection and archive

**Principle.** Every byte that reaches the data mini is appended once, immutably, with its own clocks, before anything derives from it. Overwrite files stay for the page; they are views, not records. Every day without this is unrecoverable (R5 in `oid-research/docs/mini/RESEARCH_FEED_ADDITIONS.md`).

**Capture from today, ordered by what is lost per day it is absent.**

| # | Dataset | Source | Row | Why now |
|---|---|---|---|---|
| 1 | `decisions` | cockpit, Rose, Hal, shadow | one per CALL, PUT, PASS, WATCH, EXIT (schema below) | the owner's edge; unrecoverable |
| 2 | `opra_quotes` (R2) | collector stream | every quote change for the 260 fixed plus dynamic contracts: t, contract, bid, bid size, ask, ask size, received_at | option-leg labels |
| 3 | `opra_trades` | collector stream | every print with aggressor class | call/put provenance |
| 4 | `score_features_15s`, `score_changes_5s` | scorer | exists; add config hash and `feature_computed_at` | feature store |
| 5 | `bars_1m` (R6) | SIP | 209 names plus SPY, QQQ, SMH, SOXX, IWM, DIA with the same-minute norms as computed that day | rvol norms |
| 6 | `surge_events`, `momentum_events` | detectors | every emit with detector version | precision labels |
| 7 | `walls` (R5) | FlashAlpha and Alpaca open interest | every snapshot including STALE_CARRY, with `source_observed_at` | already 1,045; keep going |
| 8 | `uw_lean`, `uw_flow`, `uw_tide` | Unusual Whales | every pull with age | diagnostic |
| 9 | `news_firstseen` | Alpaca (Benzinga), X, EDGAR | `first_seen_at`, source timestamp, tickers, finbert score, agent tone, owner correction | text features |
| 10 | `chain_snapshots` (R1) | Alpaca options snapshots endpoint | every 5 minutes in regular hours, 144 sector plus 65 core names, 5 to 45 DTE, strikes within 15% of spot; one-day dry count first | contract selection, open-interest walls |
| 11 | `open_interest_daily`, `security_master`, `universe_versions` | Alpaca | daily | $0 walls (about 300 calls a day, adopted in study 8); membership history |
| 12 | `latency` (R15) | collector, Gateway | lag histogram hourly; decision to order-ready to broker-ack to fill per intent | `latency_model_ref` |
| 13 | `owner_fills` | Robinhood MCP read tools (primary account positions and orders); CSV fallback | fill time, contract, side, quantity, price, decision id | the only ground truth for the style being scaled |
| 14 | OMS tables | Gateway | intents, risk checks, fills, positions, reconciliation events | execution evidence |
| 15 | `trading_status` | SIP stream | halt and LULD messages per symbol | surge gating, setup E, Halt/Resume Bot |

Sizes are estimates until the dry count: R2 at 260 to 600 contracts, conflated to one second on change, is on the order of 0.3 to 1 GB a day in Parquet; 1-minute bars for 215 names are about 85,000 rows a day; R1 about 100 MB a day. The research mini's 3.6 TB holds years of this.

**Layout and point-in-time discipline.** `/Users/oidarch/archive/<dataset>/date=YYYY-MM-DD/hour=HH/part-n.parquet` with a per-date `MANIFEST.json` (sha256, rows, minimum and maximum `source_observed_at` and `received_at`, writer, schema version). Three clocks on every row (`source_observed_at`, `received_at`, and `feature_computed_at` or `decision_at` where relevant; `label_end_at` and `label_available_at` on labels). `availability_basis` is `OBSERVED_DESK_REPLAY` for live capture and `RECONSTRUCTED_PROVIDER_REPLAY` for backfills, never mixed in one partition. A closed hour is made read-only and never rewritten; corrections are new rows with `supersedes`. STALE and error records are archived too (a wall carried on quota zero is a fact about the desk). No derived table without the config hash of the code that made it. Parquet plus DuckDB (already in the venv); SQLite WAL for the registry, decisions and OMS. One writer per feed, as today. All three hosts (box, data mini, research mini) run NTP and log their offset daily, because three clocks per row are worthless if the hosts disagree.

**The decisions schema (the one new table that matters).**

```
decisions(decision_id, decision_at, actor in {jeffrey, rose, hal, ranker, shadow:<hash>},
  symbol, action in {CALL, PUT, PASS, WATCH, EXIT}, snapshot_id,
  score_cfg_hash, score, held_seconds, rvol_1m, rvol_5m, surge_id, momentum_state,
  wall_dist_call_pct, wall_dist_put_pct, cp_1m, cp_coverage_pct, lean_5m, lean_age_s,
  news_tone_15m, news_firstseen_age_s, lane, lane_version,
  reason_codes[] in {surge, wall, flow, news, sector, gut}, confidence 1..3,
  contract, quote_at_decision {bid, bid_size, ask, ask_size, t, age_ms},
  planned_bracket {tp_pct, sl_pct, time_stop_s},
  override_flag, override_reason, intent_id,
  exit_tag (required at EXIT; administrative is its own category), note)
```

Pass and Watch rows are the negatives the desk has never had. The seven existing exit tags are kept and one is required at exit time, with `jeffrey_clear_rotate`, `USER_REQUESTED_FLAT` and `user_ordered_book_tp_harvest` in a separate administrative category forever.

**Feature service.** One function `features(symbol, as_of)` computed from the archive, not the live cache, used by the live scorer, the Candidate Ranker, the Shadow Trader and the research loop. Same code path, same numbers; the config hash is stamped on every row and shown on the page. This is the fix for two systems that do not know about each other.

**Labeling pipeline.** Nightly at 5:30 PM PT on the data mini, deterministic, writing only to a label schema the scorer and the Gateway cannot read: for every `decisions` row, every `score_changes_5s` row and every surge event, join `opra_quotes` for the contract and compute `L_opt` over the registered grid, `ret_policy` per bracket, true-stream MFE and MAE, the underlying 5, 15 and 30-minute excess return, and B0, B1 and B2 for the same window. `label_available_at` is the run time. Labels never enter the feature store. The labels are mirrored to the research mini's sealed store when the path opens, where `oideval` re-scores on sealed dates.

**Data-mini and research-mini split.** The data mini is the single writer (it already is since mid-October), the hot store, the page and the Gateway. The research mini is the immutable archive (`oidarch`), the development sandbox (`oidresearch`) and the sealed evaluator (`oideval`). The missing network path is the blocker: install Tailscale on the research mini (the data mini already serves on the tailnet) or fix the LAN access rule; expose only the archive-pull port; pull-only from the research side; no route from research to the OMS. A nightly `archive-pull` runs as `oidarch` over a read-only key; a root-run job copies dates from D onward into the sealed directory that `oidresearch` cannot read. Future dates are the only uncontaminated holdout this desk has; D is set the day the pull first runs. The evaluator re-scores champion and challengers on sealed dates and publishes numbers, never rows, back to the Research tab. Add a nightly encrypted off-site copy, because one Mac mini is collector, publisher and gateway.

**Study disposition.** S1 (Rose breakout quality) runs on the research mini on 30-minute bars as the zero-cost smoke test of the runner and evaluator. S2 (macro) stays blocked until R9 and R10 land; its Kalshi arm is collect-forward. S3 (option duration and pricing filters) becomes evaluable from R2 forward or from a targeted Databento pull. S4 (Hal expectations) stays a note. S5 (short interest and borrow) runs after its data registration, no purchase. C2-S6 (option volume concentration) is campaign 2 and needs the Databento `tcbbo` cost query first.

## 7. Additional data sources

Ranked by expected value for the +10% to +20% same-day style, divided by cost.

1. **Own OPRA quote and trade archive through the existing Alpaca stream (R2) and chain snapshots (R1).** $0 incremental (Algo Trader Plus is already paid). Point-in-time exact. Hypothesis: the +10% to +20% exit on the option is reachable net of spread after a surge of 3x or more at a rate that beats the bracket's break-even. Prerequisite for everything; starts today.
2. **The owner's own decisions and live fills.** $0. Hypothesis: the discretionary hit rate on the option-leg label exceeds B2 and the scorer, and the lift concentrates in a specific state (surge plus the first 90 minutes, for example). Without this there is nothing to scale. The Robinhood MCP read tools make the fill export automatic.
3. **Latency instrumentation (R15).** $0. Not a source, but no study is executable without it. Hypothesis: the agent path is over 30 seconds; the Gateway path is under 2 seconds.
4. **Alpaca historical option bars and trades, February 2024 onward.** $0 if the Algo Trader Plus entitlement covers it (unprobed); trade and bar based (OHLC, VWAP), not quotes. Hypothesis: a lower-fidelity option-leg label can be backfilled onto the 82,190 ticker-minutes of surge events already archived (9/25 to 10/20) to start E4 before R2 matures. Verify the endpoint and the trade-history lookback first (the SDK docstring suggests a 7-day window on one call).
5. **Databento OPRA targeted pulls.** Pay-as-you-go `cbbo-1m` about $2 per GB and `definition` about $5 per GB; `cmbp-1` $0.16 per GB; history from 2013-04-01 (subsampled before 2023-03-28); a $125 new-account credit; the $199 a month Standard plan includes 12 months of top-of-book. For 325 surge ticker-days the realistic cost is $25 to $100. Run `metadata.get_cost` in days 15 to 30; buy in days 31 to 60 if under $300 and the label definition has held 10 sessions. Hypothesis: the surge-to-option-mark response seen forward holds on 2024 to 2026 history, turning a 20-session study into a multi-hundred-session one; it also unblocks S3.
6. **SEC EDGAR full-text search and acceptance timestamps** (free). Hypothesis: a filing first seen within 3 minutes of a surge explains it, and filing-driven surges continue more than flow-driven ones. Presence, not tone, is the variable (the add-one news study showed nothing for tone).
7. **SIP trading-status and LULD halt messages** (free, already on the stream). Surge gating and the Halt/Resume Bot.
8. **FINRA short interest API plus UW borrow** (free). S5 as registered; weak prior for mega-caps; swing horizon only.
9. **Kalshi candlesticks for CPI, FOMC and payrolls** (free; official docs unverified). Macro-print gating for the first 15 minutes after a print; nests in S2.
10. **FRED and ALFRED vintages, intraday macro ETF proxies (R9, R10)** (free). Unblocks S2 arm C; low priority for the intraday style.
11. **Korea 10-day and 20-day semiconductor exports through data.go.kr** (free; about 36 events a year; endpoint unverified). Hal catalyst lane, campaign 2.
12. **UW analyst-revision feed and UW expected-move for the earnings gate** (already paid). Pre-open gap feature inside S1; expected move feeds the Event Gate.
13. **ThetaData Standard ($80 a month; tier contents conflict across the vendor's pages).** Only if Databento targeted pulls prove too narrow for a multi-year backfill.

**Do not buy.**

- **FlashAlpha Alpha ($1,499 a month).** The desk's own study says walls carry no single-name information; its historical replay is a replay of a null, and the things worth replaying (volume, option marks) come from Alpaca and Databento for a fraction of the price. Do not drop to Basic either: Basic is 250 requests a day on the vendor's current pages (100 on stale ones) and the page already makes about 325 wall calls on a full day. Instead implement the study-7 savings (VIX and oil polling to a 5-minute cadence; Alpaca open-interest walls for sector names). The burn breakdown itself (2,122 by 4:32 PM PT; VIX about 700, oil 450, walls 325, agents about 650) is a live-page claim present in neither repository and inconsistent with `docs/API-INVENTORY.md`, which says FlashAlpha is Rose-only and Macro makes no FlashAlpha calls; produce `api-quotas.json` or the account's call history and reconcile who is polling VIX and oil. The quota resets at midnight UTC (5 PM PDT), so 4:32 PM PT is effectively end of cycle.
- **Massive (ex-Polygon) options plans.** Non-professional licensing is a live exposure once a bot trades.
- **DRAMeXchange ($5,000 a year), Silicon Data Pro ($998 a month), Estimize, ORTEX.** Swing-horizon series with no path to a same-day option exit.
- **More X credits.** Add-one news showed no lift and the pool is a shared sink.
- **A second GEX vendor to resolve NVDA 230 versus 220.** Resolving a null.

Standing rule: no new subscription without a registered study that names the hypothesis it unblocks.

## 8. Strategy and edge techniques

**What "consistent arbitrage" means here.** There is no arbitrage available to this desk: latency arbitrage, market making and dispersion need co-located infrastructure and capital the desk does not have. There is a repeatable conditional edge: after a genuine volume event in a liquid name, short-horizon continuation is more likely than the base rate, and option convexity turns a 0.5% to 1% underlying move into +10% to +20% on a near-the-money contract. The edge is in event selection, speed, refusing to chase, and exiting by rule, traded identically every time so the law of large numbers works in weeks. The bid-ask spread is the tax that decides everything: retail options flow pays about 12.6% effective spread on cheap weeklies and loses on average (Bryzgalova, Pavlova and Sikorskaya, Journal of Finance 2023), which is why every setup carries a hard liquidity gate.

**The cost arithmetic that must hold before any setup goes live.** With the label defined on bid against entry ask, a +X target and a minus Y stop give expected value p times X minus (1 minus p) times Y minus fees, so the break-even hit rate is Y over (X + Y) plus a fee term.

| Bracket (target / stop) | Break-even hit rate before fees | With about 0.65% round-trip fees on a $2 option |
|---|---|---|
| +10 / minus 20 | 66.7% | about 68.5% |
| +12 / minus 20 | 62.5% | about 64.5% |
| +15 / minus 15 | 50.0% | about 52% |
| +20 / minus 15 | 42.9% | about 44% |
| +20 / minus 20 | 50.0% | about 52% |

The 61.5% and 67.5% headline cells therefore straddle break-even for a +12 / minus 20 bracket, which is exactly why the bracket is chosen from the E5 grid on logged option paths and not asserted. Wider targets are reached less often and timeouts land in between. The Contract Selector computes the per-ticket break-even from the live spread and fees and rejects any ticket whose break-even exceeds the calibrated probability. A proposal that said 40% to 50% precision is profitable at a 12/20 payoff was wrong; it is a losing policy at any latency.

**Capacity.** As seats grow from one to eight the desk must not become the market in a sector name. The Contract Selector enforces a per-name maximum: contracts at most the smaller of half the displayed ask size and 5% of the contract's session volume, and total exposure per name scaled by spread (a quote 8% wide gets half the size of a quote 4% wide).

**Setups to register (all same-day, at the money, nearest weekly (2 to 5 DTE) out to 21 DTE, bracket from E5, interim shadow default +12 / minus 20 / 45 minutes).**

- **A. Surge continuation (primary; the rule to freeze now).** Trigger: 1-minute rvol at least 3x the same-minute norm at a new day high (calls) or day low (puts); 5-minute rvol at least 2x; the bar closes in the top or bottom 30% of its range; momentum state not ACCEL for at least 60 seconds (hysteresis; ACCEL is the worst state); underlying day change under 3%; QQQ 5-minute return the same sign or flat; the page's market-momentum breadth reading not collapsing against the direction; IV rank below 80; no earnings within 24 hours; no scheduled macro print within 15 minutes; 6:35 to 11:30 AM or 12:00 to 12:50 PM PT. Entry on the next 5-second bar after the triggering minute closes (the research program forbids fills inside the triggering bar), limit at the ask, cancel if unfilled in 5 seconds, no chase. Contract: nearest 0.50 delta, spread at most 5% of mid (core) or 8% at half size (sector), open interest at least 500, ask size at least 10. Kill: 30-session expectancy at or below zero or a top-three share over 50%. This is the owner's trade, written down; the Owner Mirror Bot measures how far it is from the owner's actual hand.
- **B. Held score plus surge (challenger, shadow only).** Core plus or minus 2 held at least 30 seconds with a surge in the last 2 minutes (61.5%, n = 26); light plus or minus 3 held 5 minutes with a surge (67.5%, n = 40). Tested with and without the call/put input. It becomes a trade source only if it beats A's base rate; n at least 300 before anyone calls it anything.
- **C. Sector sympathy lag.** When a group leader prints setup A and the sector strip shows rvol at least 1.5x, buy the laggard in the same group (144-name universe) with rvol 1.5x to 3x, absolute change under half the leader's, tightest spread, no own news. The SMH and SOXX lead over single semiconductor names is the prior. Testable now on the 1-minute archive; the hypothesis is a 2-to-10-minute propagation lag.
- **D. Surge fade (the put side the paper desk never traded).** rvol at least 5x at the day high followed by a DECEL event, absolute score 3 for at least 2 minutes, price at least 1.5 one-minute ATRs from VWAP, a 5-minute close back inside the prior range: opposite right, tighter bracket (+10 / minus 15 / 15 minutes). Study 3 (plus or minus 3 degrades to 22.2% after 30 seconds) and study 5 (DECEL best, ACCEL worst) are the prior. Expected to fail; cheap to register.
- **E. Filing-confirmed surge.** Setup A plus an EDGAR or Benzinga first-seen at most 3 minutes before the surge: a 60-minute time stop instead of 45. Presence of a filing, not tone, is the variable.
- **F. Opening-range break.** 6:35 to 7:15 AM PT, first 5-minute range break on rvol at least 2x with SMH or QQQ confirming; +10 target, 20-minute time stop. S1's intraday cousin; tests whether the edge is a time-of-day effect.
- **G. Scheduled-print reaction (register, not in the first campaign).** After the first full minute after a print, surge direction, index ETFs and leveraged funds only (the only names with sub-2% spreads at that moment); Kalshi odds as the gate (unverified source).
- **Index gamma regime as a conditioner, not a signal.** SPY and QQQ GEX sign from UW (already paid) as a regime feature for A versus D; never a single-name wall.

**Option-specific filters that belong in every setup.** IV rank below 80 against the trailing 60 sessions (do not buy a surge that is also an IV spike); no entries in the 24 hours before earnings and none in the 15 minutes around a scheduled print; prefer 0.40 to 0.50 delta for gamma per dollar; reject any contract whose spread-implied underlying move to reach the target exceeds the setup's typical excursion.

**Avoid.** 0DTE (retail loses in aggregate, roughly $350,000 a day on SPX 0DTE in the academic sample; the research program already excludes it). Wall-press entries as a trigger (null); walls run as a diagnostic overlay only. Far-out-of-the-money substitution to fit the debit cap: take WATCH instead. Flow-agreement filters (study 4). Buying into pre-event IV. Chasing ACCEL. Agent-sourced news chases. Stacking correlated names on one tape (the 9/18 cohort): per-group cap 2, correlated cap 3. Selling premium or spreads for income: a different risk engine, and credit spreads stay out until the sign bug in the ledger is fixed. Holding past the time stop because the thesis is intact: that is Hal's book. Any entry with a contract quote older than 5 seconds, or any policy whose horizon is shorter than five times the measured latency.

## 9. UI and UX changes

The page is a research instrument posing as a cockpit: 209 tiles by about 12 datums at 6 to 7 pixel type, the largest glyph reading 0.0x on about 200 tiles after the close, the score chip second-largest while the Research tab rates it near coin-flip, and the one robust conditioner (rvol at least 3x) encoded as pulsing and a "0 hot" counter. Rebuild it as two surfaces: a **cockpit** for 6:30 AM to 1:00 PM PT and a **scorecard** for everything else. Ranked by impact per effort:

1. **Decision ticket with capture (build first; it is the dataset).** Click or tap a tile, or press c, p, x or w, and a right drawer opens pre-filled: contract (at the money, nearest weekly to 21 DTE, spread percent, open interest, ask size), debit against cap, bracket (+12 / minus 20 / 45 minutes, editable), break-even win rate from the live spread, seats against cap, gate results as green or red pills (quote age, spread, chase, earnings, macro print, session clock), reason chips (surge, wall, flow, news, sector, gut), confidence 1 to 3, a 140-character note. Buttons Call, Put, Pass and Watch write the `decisions` row keyed to `snapshot_id`. In Stage 0 the submit button says **Log**; in Stage 1 it says **Send to gateway (PAPER)**; same schema both times. Exit requires a tag at close time; administrative closes are their own category. Keyboard: j and k move between tiles, c call, p put, x pass, w watch, Enter submit, Esc cancel. Pass and Watch are mandatory for any name dismissed from the Now lane. Because the owner is also clicking in Robinhood at the same time, the fill join from the MCP read tools removes the double-entry burden: the ticket captures the intent, the broker read captures the fill.
2. **Now lane.** Replace the five test-stamped surge chips and the 12-chip momentum tape with one ranked lane of at most five candidates (rank = rvol times a held-score factor times a state factor times spread fitness, versioned `lane v0.1`), each a card: symbol, rvol, score with held-for timer, state, wall distance percent, spread percent, age, Ack, Ignore, Open ticket. Hysteresis of at least 60 seconds on state flips. Every Ignore is a precision label; ignored candidates that ran become "missed" rows. An audible chime on a new lane entry and a distinct sound on a surge, because a seconds-scale trader cannot watch 209 tiles.
3. **Tile hierarchy by evidence.** Big glyph = rvol only when at least 1.5x, otherwise percent change; the score chip shrinks to a corner mark with a held-for timer; surge gets the strongest color; closed-market tiles become session summaries (day against norm, close); remove the 0.0x and the dashes after the close; fix the empty parentheses in the closed-market note.
4. **One freshness grammar.** Every datum gets an age pill in one format (12s, 4m, 9h) colored against its own time-to-live; the header chip goes amber when any gated feed is past its TTL; unify the five last-trade clock formats; show page poll latency in the status bar; "page updated" is never conflated with "data fresh". Fix or retire the market-momentum detector that reads "9h old".
5. **Status and risk bar (row 0).** Session, Alpaca stream lag, FlashAlpha quota percent, UW age, Gateway heartbeat (red at 10 seconds), mode PAPER or LIVE, seats, open debit against cap, day P&L against the loss stop, a two-step red KILL button.
6. **Focus panel ("why this fired").** Each score input times its weight, call/put with coverage percent (never without it), wall distances in percent, lean plus age, news tone plus source plus first-seen, the at-the-money quote with spread percent and age, the last 5 minutes of 5-second bars, and the three conditioners as checkboxes (rvol at least 3x, held at least 30 seconds, not ACCEL). A shadow-bracket chip: "+12% would have hit at 10:41:07".
7. **Positions zone.** Mark, MFE and MAE from the true stream, `bracket_state`, resting take-profit order id, time-stop countdown, slippage at entry, Flatten and Flatten-all buttons (gateway-backed in Stage 1). One P&L scope: realized today, unrealized, week, net of fees. Replaces the here.now blotter's mixed scopes for intraday use.
8. **Color and shape separation.** Volume = an amber-to-red ramp only; direction = blue and orange or green and red plus up and down glyphs; walls = C, P and gamma letters on the rail, hollow retained for low confidence; minimum 11-pixel type; italic retired as semantics; safe for red-green color vision deficiency.
9. **Alert ledger.** Every surge, momentum and news alert gets Ack, Ignore or Acted, deduplicated; shadow and test items in a muted lane; news sorted by time and score-filtered with a triage rule for the 770-a-day volume (followed names first, score at least 2 or a first-seen filing, everything else collapsed); thumbs up or down on each finbert score (the visible +2 on a bearish post is exactly the correction signal needed).
10. **Scorecard page first on the Research tab.** Today against the 10-session hit and option-leg rates by setup and by score size and horizon with n and intervals; calibration by decile; conditioner lifts; lane precision and human-versus-lane agreement; champion against challenger; promotion-ladder status; latency histogram; archive coverage (rows per day per dataset, gaps); then the studies table; then the Field Guide gap audit.
11. **Replay and scrub** of one ticker's last N minutes from the 15-second feature table with decision rows overlaid: the weekly review tool, and the Replay/Practice Bot's drill surface.
12. **Mobile watch mode.** At most eight names, one line each, Flatten only. No entries from a phone.
13. **The other tabs.** Table: group the 22 columns as Score, Volume, Flow, Walls, Clocks; freeze the symbol column; default sort by rvol; render INLINE as plain text and reserve pills for out-of-band values; hide the seven live-only columns after the close. Chart: unchanged until the scorecard exists. Field Guide: add the version hashes of the scorer, lane and policy at the top so the guide and the page cannot drift apart.

Cockpit layout: row 0 status bar; zone A (left, about 60%) Now lane plus a compact heatmap of names with rvol at least 1.5x or a held score, the remainder collapsed to the sector strip; zone B (right, about 40%) focus panel plus ticket; zone C (bottom) positions plus the decision-log tail; zone D (collapsible) news, momentum tape, macro.

## 10. Bot roster

The existing roster is Chart, Rose, Hal, Research, Data Ops, X Summarizer and Macro. Two kinds of additions follow: the plumbing bots without which no trade can be sent safely, and the idea-generating bots that find trades or sharpen the owner.

### Plumbing bots (deterministic, data mini unless stated)

| Bot | Purpose | Inputs to outputs | Cadence | Authority | Pays for itself by |
|---|---|---|---|---|---|
| **Execution Gateway and Bracket Manager** | The only order path; synthetic brackets; time stops | `order_intent` to orders, fills, order log, heartbeat | event-driven, 1 s loop | full broker authority inside `policy.yaml` envelopes; no agent access | the first time a +164% excursion does not become +17.8% |
| **Risk Sentinel** | Ordered pre-trade checks, caps, consecutive-loss pause, agent-touched reject, kill flag | intents, positions, P&L, feed ages to PASS, REJECT or HALT | per intent plus 1 s | block everything | one bad hour cannot become a bad month |
| **Reconciler** | Broker against OMS every 10 s; HALT on any delta | broker API, OMS tables to `recon_event` | 10 s plus end of day | halt | the only defense against duplicate sends and ghost fills |
| **Correlation Sentinel** | Live sector and factor exposure of open seats plus the Now lane, across both books | positions, lane, Robinhood read to allow or reject | per intent | hard reject at three correlated seats | ends the seven-presses-one-move cohort |
| **Contract Selector** | Deterministic strike and expiry under liquidity, debit and capacity rules; per-ticket break-even; delta-to-underlying translation | chain snapshot, quotes, open interest to `occ_symbol` or `NO_QUALIFYING_CONTRACT` | on candidate | propose | removes the single biggest discretionary distortion in the ledger |
| **Candidate Ranker (Lane Ranker)** | Produce the Now lane | feature store to at most five candidates with `lane_version` | 5 s | propose | turns 209 tiles into at most five decisions and generates the training set |
| **Surge Engine v2** | One deterministic gate with hysteresis and sector aggregation | 1-minute and 10-second bars, norms to `surge_events`, sympathy candidates | 10 s | gate input | replaces the test chips; the single gate everything else conditions on |
| **Labeler** | Option-leg first passage, bracket counterfactuals, baselines, true-stream MFE and MAE | archive plus decisions to the label schema | nightly 5:30 PM PT plus a 15-minute intraday catch-up | none | nothing trains and no scorecard exists without it |
| **Shadow Trader and Scorecard** | Run every frozen policy on live events with full contract and exit rules; champion against challengers on identical snapshots | signals, R2 quotes, policy hashes to `shadow_forecasts`, scorecard | 5 s and nightly | demote on drift | the promotion ladder's steps 5 to 8; free counterfactuals for the owner's trades |
| **Owner Mirror Bot** | Replay the owner's captured decisions against the Shadow Trader and report divergence and who was right | decisions, owner fills, shadow forecasts to a nightly report | nightly | none | how the desk learns what the owner's hand knows that the model does not |
| **Gate Keeper** | Versioned `gates.yaml` and `policy.yaml`; waiver-request queue; time-boxed exposure-reducing flags from agents accepted, exposure-raising changes approved only by the owner | requests to signed config rows and `overrides` | on request | config writer under owner approval | replaces "named gate governs" and chat-yes-as-ticket |
| **Event Gate Bot** | No-entry windows from `desk-catalysts.json`, the macro calendar, EDGAR first-seen, halts, print odds | files to per-name windows | 5 min | block entries | encodes the earnings, FOMC and OPEX gates applied by hand today |
| **Latency Monitor (R15)** | Persist the lag histogram and decision to order-ready to broker-ack to fill | collector, Gateway to `latency_model_ref` | continuous | trips the feed-health switch | unblocks every fill model |
| **Fill Reconciler and Cost Bot** | Realized against modeled slippage; signed cashflows; fee model; top-three and shared-shock report | fills, intents to a reconciled ledger and a slippage parameter | 5 min plus end of day | none | produces the slippage parameter every study needs; fixes the ledger defect class |
| **Quota Steward (extends Data Ops)** | FlashAlpha, X, UW and Alpaca subscription budgets per bot per day; walls to Alpaca open interest when the FlashAlpha budget is under 20% | call logs to per-bot caps and a STALE policy | 1 min | throttle any bot's vendor calls | keeps a full wall day under 2,500 calls |
| **First-Seen Bot** | EDGAR, Benzinga and X first observation with timestamps, typed as symbol, event type, first-seen time, tone | feeds to `news_firstseen` | continuous | none | the only point-in-time-clean text feature |
| **Post-Mortem Bot (agent)** | Weekly narrative over missed and ignored candidates, overrides and the worst five trades; proposes features and study drafts, never rules | decisions, labels, scorecard to a memo plus draft registrations | weekly | propose | replaces the human changelog with evidence-linked proposals |
| **Data Ops (exists)** | Add archive hash checks, Parquet row counts against expected, subscription count against the cap, Tailscale path health, off-site backup verification | manifests to alerts, STALE flags, HALT on a health failure | hourly | halt the Gateway on a data-health failure | catches silent gaps before they become the holdout |

### Idea-generating bots (the ones that find trades or make the owner faster)

| Bot | Purpose | Inputs to outputs | Cadence | Authority | Why it pays |
|---|---|---|---|---|---|
| **Sector Sympathy Bot** | Setup C as a bot: when a group leader surges, rank the group's laggards by rvol, spread and absence of own news | surge events, sector strip, 1-minute bars to lane candidates tagged `sympathy` | on each leader surge | propose | the 144-name universe exists for exactly this; testable on the archive today |
| **Halt and Resume Bot** | Watch SIP trading-status and LULD messages; on resume, measure the first minute's rvol and direction and feed the lane | status messages, bars to `halt_events`, lane candidates | event-driven | propose; also a hard block during a halt | resumption surges are the cleanest volume events on the tape and the easiest to get wrong without a halt gate |
| **Opening-Range Bot** | Setup F as a bot: 6:35 to 7:15 AM PT first-range breaks on volume with index confirmation | 5-minute bars, SMH and QQQ to lane candidates tagged `orb` | 6:35 to 7:15 AM PT | propose | tests whether the edge is a time-of-day effect, which the paper desk never isolated |
| **Replay and Practice Bot** | Drill the owner on recorded surges: replay the 15-second feature table for a past event, take a decision, score it against the label; track the owner's own calibration by setup | archive, labels, decisions to a drill log and a calibration chart | after the close, on demand | none | makes the human faster and produces labeled decisions without risking a dollar |
| **Capacity and Liquidity Bot** | Per-name maximum size from live ask size, spread and session volume; flags names where the desk's intended size would move the quote | chain snapshots, quotes to `capacity(symbol)` | 1 min | feeds the Contract Selector | at 300 to 400 contracts per ticket in a 3-DTE weekly the desk is already a visible participant; this bot measures its own footprint |
| **Venue Latency Bot** | One-lot probes on Alpaca paper and the Robinhood Agentic account; decision-to-acknowledgment latency and reconciliation per venue | Gateway clocks, broker responses to a latency table per venue | daily, during Stage 1 | sends one-lot probe orders only, inside its own cap | decides the second-venue question with data instead of forum posts |
| **Earnings and IV Bot** | Maintains the earnings calendar with UW expected move and IV rank per name; writes the pre-event no-entry windows and the IV-rank feature | UW, catalysts file, chain snapshots to Event Gate windows and features | daily plus hourly | block entries | the IV-crush and pre-print gates that are applied by hand today |

### Roles that change

- **Chart Bot** becomes a feature producer: it owns the daily indicators, relative strength and the 1-minute norm tables the Surge Engine reads, and its outputs enter the model only through add-one studies. The pattern detector stays off.
- **Rose and Hal** stay as proposers and narrators and write the structured candidate and REJECT log (R7). Hal's book stays paper until it has its own 40-session expectancy.
- **Macro, X Summarizer and Peanut** become typed feature producers whose outputs are tested by add-one studies; their flags can reduce exposure for at most 60 minutes and never raise it.
- **Customer/Supplier Bot** is retired (0 relationships, 0 claims after a month). The Soft Grader's gates move into Sentinel and Gate Keeper code.
- **Research Bot** keeps `trade_authorization = NONE` and gains the archive it has been waiting for.

## 11. Risks and failure modes

- **Overfitting and consumed data.** The 10/20 studies were unregistered searches on two correlated sessions with overlapping snapshots counted as n, and the researcher saw everything; those dates are development-only. Campaign 1 has zero headroom, so every idea here is a campaign-2 registration on dates from 10/21. Mitigation: registration before search, the B2 baseline, session-block bootstrap, event-count floors, sealed future dates on `oideval`, and the practical rule that nobody re-tunes thresholds by watching the live scorecard.
- **Concentration.** 89% of Rose's paper net in three tickets; correlated AI names on one release are one bet; the 10/20 live session was eight winners in two names on one up-tape. Mitigation: per-group cap 2, Correlation Sentinel at 3 across both books, top-three share under 40% as a gate, a shared-shock report in the scorecard, expectancy reported per opportunity not per book.
- **Regime.** All evidence is from an AI up-tape; bearish-extreme calibration is already inverted; puts have never been traded in paper. Mitigation: no live Stage 2 before the shadow book has traded through at least one week in which QQQ fell 5%; validation windows must include at least five down sessions; setup D registered from the start.
- **Margin and day trading.** FINRA replaced the pattern-day-trader designation with an intraday-margin standard effective 2026-06-04 (firm-level phase-in allowed until 2027-10-20). Alpaca adopted it on day one and removed the PDT fields on 2026-07-06, so there is no $25,000 minimum and no 4-in-5 lockout there; the binding constraints are options buying power (premium fully covered) and intraday-margin-deficit calls (orders creating a deficit are rejected before the trade; repeated unmet deficits trigger a 90-day freeze). Mitigation: the Sentinel reads buying power on every intent; the one written question to Alpaca is whether the 4x intraday multiplier applies to options buying power. Robinhood's regime for the discretionary account is unverified and should be confirmed in writing.
- **Latency.** The agent path is seconds to minutes; the live holds on 10/20 ran from 87 seconds to 13 minutes; emulated brackets add their own delay. Mitigation: nothing in the order path is an agent; the Gateway runs on the data mini next to the stream; a p99 budget of 500 ms from decision to order-ready and 2 s to broker acknowledgment, measured not assumed; the five-times rule rejects any policy faster than the measured path; entry on the bar after the trigger costs some edge and the cost is measured by the Owner Mirror Bot.
- **Fill quality and capacity.** Paper at ask-in and mark-out with zero fees flatters everything, and 300-to-400-contract tickets in a 3-DTE weekly are large enough to move the quote. Mitigation: paper marks entries at ask plus one tick and exits at the bid; the label is bid against entry ask; spread caps in the Sentinel; realized slippage reconciled weekly; the per-ticket break-even gate; the Capacity Bot's per-name size limit from live ask size and participation.
- **Execution.** No native options bracket at Alpaca; a software stop that fails in a gap is a real loss; emulated OCO can double-fill on a reconnect; with native stops but no OCO, two resting sells can both execute. Mitigation: one-contract sizing in Stage 2, idempotent intent ids, reconcile before send on reconnect, stream-loss flatten, the daily loss limit, broker-side close-all from a phone, weekly drills.
- **Vendor quotas and caps.** FlashAlpha near its 2,500 cap on partial wall days; the X pool at $55.72; 1,000 OPRA quote subscriptions on one connection; UW limited to 50 end-of-day rows per contract. Mitigation: Quota Steward, the fixed 260-contract R2 set with bounded dynamic slots, Alpaca open-interest walls, Sentinel HALT on any gated feed going STALE.
- **Agent nondeterminism and prompt drift.** Two Macro definitions already coexist. Mitigation: agents outside the order path; typed outputs only; temperature zero and prompt hashes for anything archived as a feature; weekly replay of identical inputs to detect drift; no prompt edit can change a threshold; the 200-item gold set before any flag may gate.
- **Terms of service and licensing.** Robinhood's agreement authorizes agent orders only in the dedicated Agentic account; reverse-engineered access to the primary account remains outside its terms. Massive's individual plans are non-professional only. Mitigation: bots trade only through documented broker APIs in the accounts those APIs are for; read the agreements before Stage 2.
- **Single points of failure.** One data mini hosts the collector, the page and the Gateway; no network path to the research mini; no off-site copy; no UPS mentioned anywhere. Mitigation: nightly archive to the research mini and an encrypted off-site copy; UPS; KILL file and heartbeat; a documented restore drill.
- **Measurement debt.** No NAV, no R, no fees, sign errors, administrative closes mislabeled as wins. Nothing in section 3 advances until the tickets are restated with signed cashflows and fees and the administrative category is separated.
- **Cost creep.** Run rate today is about $99 Alpaca plus $299 FlashAlpha Growth plus Unusual Whales (Basic $150 or Advanced $375; the desk's plan is unrecorded) plus X plus agent tokens. This plan adds $0 recurring, $25 to $100 one-time for Databento (capped at $300), and $0 to evaluate Tradier. The agent token run rate is the one unknown and is measured in week one.
- **Key person.** The edge is the owner. Capture makes it transferable; only capture does.
- **Build capacity.** Days 1 to 30 name about fifteen components for an owner plus one operator plus agents. The minimal day-30 set is the decisions ticket, the R2 sink, the Archiver, the Labeler and the Exit Manager in shadow; the Now lane, focus panel and scorecard polish can slip without losing data. Everything else in the plan is ordered so that slipping it loses time, not evidence.

## 12. First 30 days and first 90 days

Owner decisions are marked **OD**. The critical path is the capture set: items 2, 4 and 8.

**Days 1 to 7.**

1. **OD:** open the research-mini to data-mini path (Tailscale on the research mini or a LAN access-rule fix); set the seal date D. Enable the `archive-pull` launchd job; register datasets in `archive.sqlite`.
2. Enable the Archiver (R5) and 1-minute bar append (R6); add the OPRA append sink (R2) inside the collector's existing websocket connection and lag-histogram persistence (R15); verify manifests for one full session. **OD:** approve the 260-contract fixed set plus dynamic slots; the fixed set must include the nearest weekly expiry, since that is what the live book trades.
3. Run the R1 chain-snapshot one-day dry count against the data plan's REST limits.
4. Ship the `decisions`, `owner_fills` and `exits` tables and the one-click Call, Put, Pass, Watch ticket in Log mode with a required exit tag; wire the Robinhood MCP read tools to export the primary account's fills nightly (the 10/20 order list is the first row set). **OD:** commit to clicking on every name acted on or dismissed from the lane.
5. Commit the live page's scorer, replay scripts and study output files to `oid-research` so they can be hashed into manifests and re-run by the evaluator. **OD:** approve the commit.
6. Freeze and register setup A and setup B, plus E1 and E2, with thresholds, B0, B1 and B2, and dates from 10/21; set the campaign-2 budget; sign `mode_authorization.granted_by`. **OD:** sign the registration.
7. Cut FlashAlpha VIX and oil polling to a 5-minute cadence; switch sector-name walls to Alpaca open interest; produce `api-quotas.json` or the account call history to reconcile who is polling VIX and oil.
8. **OD:** confirm Alpaca paper as the execution target; create the brokerage account and paper keys (separate from the data subscription); apply for live Level 2; ask Alpaca in writing about the options order classes, GTC behavior, the subscription cap, historical option quotes and the 4x intraday multiplier on options buying power. Confirm Robinhood's margin regime for the discretionary account in writing.

**Days 8 to 14.**

9. OMS tables, Execution Gateway and Bracket Manager against Alpaca paper with synthetic brackets; Risk Sentinel with the full ordered check list; Reconciler; KILL file; first drill logged. The Exit Manager runs in paper shadow on the owner's captured entries. Day-8 probe: post an options order with `type=trailing_stop` and one with `time_in_force=gtc` and record the responses; at Gateway boot assert the paper account's options level is at least 3.
10. Latency Monitor wired to Gateway clocks; the first `latency_model_ref` published.
11. Fix the empty-parentheses template defect; ship the one freshness grammar and the row-0 status bar; add the audible surge and lane alerts.
12. Research mini: S1 on 30-minute bars end to end, to prove the runner and evaluator (both are stubs today) at zero cost.

**Days 15 to 30.**

13. Labeler nightly with `L_opt` over the registered grid and bracket counterfactuals; scorecard page with n and intervals; B0, B1 and B2 reported; the Capacity Bot's first per-name size table.
14. Now lane (`lane v0.1`), tile re-rank, focus panel, alert ledger, closed-market mode.
15. Fill Reconciler restates the paper ledger (the 64-ticket 10/09 version) with signed cashflows, a per-venue fee model (zero commission at Robinhood, $0.65 a contract at Alpaca as the assumption), administrative closes separated, top-three-removed figures published as the baseline scorecard.
16. Feature-service refactor: the live scorer and replay scripts call the same `features()`; config hashes shown on the page.
17. `gates.yaml` v1 and `policy.yaml` v1 replace prose gates; the drop-call/put variant and the logistic model enter SHADOW; Owner Mirror Bot nightly; Post-Mortem Bot weekly; retire the Customer/Supplier Bot; fold the Soft Grader into code; build the 200-item news gold set.
18. Databento `metadata.get_cost` for `definition` plus `cbbo-1m` around the 325 archived surge ticker-days; verify Alpaca historical option bars and trades (R4) and start the $0 backfill if the endpoint works.
19. **Day-30 gate review.** At least 20 sessions; at least 150 decision rows with at least 50 negatives; at least 60 owner fills; at least 100 option labels; the latency histogram; the restated ledger; the E1 interim verdict. **OD:** proceed to Stage 1 or extend Stage 0; set the Stage 1 caps (interim: $2,500 per order in paper, sector cap 2, correlated cap 3, spread at most 5% or 8%).

**Days 31 to 60 (Stage 1).**

20. The ticket button becomes "Send to gateway (PAPER)"; human-clicked paper orders with automatic brackets; positions zone live; weekly kill-switch drills with logged cancel-all latency.
21. Candidate Ranker in shadow, measured as lane precision and human-versus-lane agreement; Shadow Trader runs setups A and B and the drop-call/put and logistic challengers with full contract and exit rules; Sector Sympathy, Opening-Range and Halt/Resume bots feed the lane in shadow.
22. Bracket grid E5 runs on accumulating R2 paths; **OD:** approve the Databento pull if under $300 and the label definition has held 10 sessions.
23. Venue Latency Bot runs one-lot probes on Alpaca paper and the Robinhood Agentic account. **OD:** fund the Agentic account at probe size only.
24. **OD:** the minimum meaningful improvement (Brier skill 0.01; net dollars per opportunity at least half the modeled spread cost), fee and latency assumptions, the daily loss limit for live, who may set KILL and who clears it.
25. Register setups C, D and E as campaign-2 studies on dates from day 45.

**Days 61 to 90.**

26. If the Stage 1 gate passes (at least 20 sessions, at least 60 tickets, expectancy interval excluding zero after modeled costs, top-three under 40%, lane precision at least 45%, clean reconciliation), Stage 2 paper: the engine sends with a 15-second veto; 20 clean paper sessions are required before any live order. The human-click live track may go live earlier on its own gate (20 clean paper sessions, zero mismatches).
27. First promotion review for a challenger on at least 15 live shadow sessions and at least 800 events; the E1 verdict applied (core v1.1 to v1.2 only if supported); the E3 momentum-gate verdict at 400 or more events.
28. Execution cockpit v1 complete; replay and scrub; Replay/Practice Bot; mobile watch mode last.
29. **Day-90 review. OD:** authorize live-small on Alpaca (one contract, $500, two seats, $750 daily stop) or stay in paper; decide the Robinhood Agentic venue from the latency table; sign `policy.yaml` v2. Written broker answers on brackets, GTC and the margin regime are a precondition, not a formality. If the gate fails, the desk has lost nothing and has, for the first time, the archive, the labels, the latency model and the execution layer any future edge will need. On today's evidence, a faster human with a labeled record is where most of the value is anyway.

## 13. Open decisions for the owner

1. Open the research-mini network path (Tailscale or LAN rule) and set the seal date D.
2. Approve the R2 subscription set (260 fixed contracts plus bounded dynamic slots) and the R1 dry count.
3. Commit to logging every Call, Put, Pass, Watch and every exit tag; approve the Robinhood MCP read tools as the automatic fill export.
4. Approve committing the live page's scorer code, replay scripts and study outputs to `oid-research` for hashing.
5. Sign the registrations for setups A and B and experiments E1 and E2, and the campaign-2 budget, before any new day is scored.
6. Confirm Alpaca paper as the bot execution target; create the brokerage account; apply for live Level 2; obtain written answers on options order classes, GTC, the subscription cap, historical option quotes and the intraday multiplier on options buying power.
7. Decide the FlashAlpha tier (stay on Growth with the study-7 savings; not Alpha, not Basic) and the X pool policy.
8. Define the bot sleeve and NAV; set the Stage 1 and Stage 2 caps and the daily loss limit in both contracts and percent of sleeve.
9. Decide who may set the KILL flag and who clears it; schedule the weekly drill.
10. Approve the Databento targeted pull up to $300 after the cost query, and the $0 Alpaca historical bars backfill.
11. Fund the Robinhood Agentic account at probe size for the venue-latency study, or decline the second venue.
12. Grant permission to change core v1.1 to v1.2 if E1 is supported, and to retire the Customer/Supplier Bot and fold the Soft Grader.
13. Adopt the standing rules: no subscription without a registered study naming it; no policy with a horizon under five times measured latency; no agent in the order path; autonomous entries not before 2027 and for one setup only.

## 14. Verification log summary

Twelve claims from the synthesized plan were each handed to two adversarial fact-checkers. The full evidence is in `docs/strategy-2026-10-21/verification-log.md`.

| # | Claim (short) | Outcome | Correction applied |
|---|---|---|---|
| 1 | Alpaca options order classes are `simple` and `mleg`; types market, limit, stop, stop-limit; no bracket, OCO, OTO or trailing stop for options | confirmed (SDK source and forum staff replies) | nuance added: native stops exist but no OCO, so two resting sells can both execute |
| 2 | Alpaca accepts GTC on options orders (2026-08-28 changelog) | confirmed | limit orders only; 90-day auto-cancel |
| 3 | Alpaca paper accounts get options Level 3 automatically | confirmed | brokerage account separate from the data plan; live Level 2 application has lead time |
| 4 | About 1,000 option quote subscriptions on the Alpaca stream | confirmed | 1,000 quote subscriptions, one websocket connection per endpoint, OPRA agreement required |
| 5 | Robinhood Agentic MCP is stocks-only and the agreement bars bots | **refuted** | single-leg options since June/July 2026; agreement revised 2026-10-01 authorizes agent orders in the Agentic account (sections 4.13, 29.8); "zero orders" is OID policy |
| 6 | PDT retired 2026-06-04; Alpaca's regime undetermined | **refuted in part** | FINRA facts correct; Alpaca adopted intraday margin on day one and removed PDT fields 2026-07-06 |
| 7 | Tradier sandbox is 15-minute delayed with no streaming; Pro is $10 a month | confirmed | OTOCO is on the free Lite tier at $0.35 a contract; $0 to evaluate |
| 8 | Drop-call/put raised the plus-or-minus-2 rate 50.3% to 55.8%; rvol at least 3x raises breakout odds 8.7% to 26.7% | split | transcription is accurate; the scripts and outputs are in neither repository, so they are unaudited page claims until committed |
| 9 | Top three Rose tickets are 89% of her net; 43 of 57 closes were batch events on eight timestamps | confirmed with precision fix | 45 of 57 on eight shared timestamps (43 on seven); 26 carry explicit administrative tags; the 9:15 PM Hal rows are closes, not entries |
| 10 | Databento OPRA pricing about $2 per GB for `cbbo-1m` and $5 per GB for `definition`, history from 2013 | confirmed | $125 new-account credit; Standard includes 12 months of top-of-book; realistic cost $25 to $100 |
| 11 | Alpaca historical option bars and trades from February 2024, no historical quotes | confirmed | trade and bar based; entitlement unprobed; check the trade-history lookback |
| 12 | FlashAlpha Growth 2,500 a day, Basic 100 a day; the burn breakdown | **refuted in part** | Basic is 250 a day on current pages; the burn breakdown is a page claim absent from both repositories and inconsistent with `API-INVENTORY.md` |

The checkers reached vendor pages through search-engine extracts because the sandbox proxy blocked direct access to most vendor hosts; where a page was read directly (the alpaca-py SDK source, the public GitHub repositories) the log says so.
