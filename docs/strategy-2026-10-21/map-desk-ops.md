# OID desk operating map — as built, Oct 2026 (from `/home/user/oid-trading-desk`)

Legend: **DOC** = documented only (prompt/spec) · **CFG** = code/config present in repo · **OBS** = verified by a run artifact (feed file, ledger row, page snapshot) · **NB** = explicitly NOT BUILT. Repo snapshot is 2026-10-05; the Alpaca data mini, live-page scorers and research mini are **not in this repo** and are not mapped here.

## (a) Bot roster — owner feeds, cadence, authority

| Bot | Role / authority | Owns (writes) | Cadence (ET unless PT stated) | Status |
|---|---|---|---|---|
| **Rose (OID)** | Short-term trader; decision bot **and** primary collector; paper-elevate only; alert-only close; site publisher | `fa-levels`, `fa-flow-levels`, `uw-flow-alerts`, `uw-net-prem`, `uw-form4`, `rh-quotes` (sole writer via `dashboard/refresh_marks.py`, TTL 120 s, 38 syms), `support-map`, live RH book pulse, paper ledger (`paper-trades/trades.json`, not in repo), `api-quotas` notes, premarket EDGAR | 8:15 premarket EDGAR/Form-4 · 9:45 first-hour · 10:15 opening intel · Q5 qualifier every 5 min 9:00–15:55 (FA pull only on miss AND `:00/:15/:30/:45` OR near-wall OR ≥1% move) · walls pulse 11:45/12:45/13:45/14:45 (primary FA writer) · NVDA driver watch :19/:49 10–15 · 15:15 afternoon validation · 15:50 close carry · support-levels watch every 15 min 6:05 AM–1:50 PM PT · X Core-8 **DISABLED** · dashboard every-5m **disabled** (`hal/HAL-CADENCE-V1.md`, `market-data/QUERY-DEDUP.md`) | OBS (ledger ids `OID-FH-…`, `OID-Q5-20261005-23` writer stamp in `hal-rh-watch-pulse.json`) |
| **Hal (OT2)** | Longer-term trader; FA/UW **reader-only**; paper only; "never place/modify/cancel/exercise RH unless Jeffrey separately names a live Agentic ticket"; chat-notify Jeffrey on each seat | `hal-intraday-marks`/`hal-marks.json`, `hal-rh-watch-pulse.json` (Soft A annotate), `hal-x-scan.json` + `x-spend`, `desk-catalysts.json` (30 events, restamped 10/05 7:38 AM PT), `hal-cw-leap-queue.json` | Premarket 8:00 · open 9:35 · marks `:11/:26/:41/:56` 9–15 (flat = idle) · RH watch `:05/:35` RTH · paper P&L 4:05 · X scan every 2 h 8:11–20:11 PT, 7 days, 11 handles | OBS (`hal-marks.json` stamp `HAL-INTRADAY-20261005-1135`, `openHalSeats 0/7`) |
| **Chart Bot** | Producer; soft only; never elevates; forecasts null; pattern detector off | `chart-daily` → `chart-bot/observations/{SYM}.json`, `market-data/latest/chart-daily-observations.json`, `chart.html` | Weekdays 2:24 PM PT after close; RH `get_equity_historicals` day/regular/split from 2024-01-01; ≈37 calls/day; universe `RH-TECH-CHIP-20261004` (37, GOOG Class C only); EMA9/21 + SMA50/200 (Shay lineage), SMA20/ATR14 unvalidated; RS 20-session vs QQQ/SMH; material trend-flip handoff to Rose/Hal (Jeffrey 2026-10-05) | OBS (last write 10/04 2:33 PM PT) |
| **Macro Bot** | Producer; soft color; never elevates | `macro-morning.json` (daily_macro + macro_tech −2..+2, seven `metric_scores`: 10Y_yield, oil_WTI_Brent, USD_DXY_or_USDJPY, VIX, NQ_vs_ES, credit_HYG_day, event_calendar), `macro-econ-calendar.json`, `macro-x-scan.json` | ~5:45 AM PT chat pack (file ~6:14) · ~5:50 AM PT calendar + one-shot post-prints · `macro-x-tech` hourly 9:10–3:10 ET, clear deltas only; sources Yahoo public pages + BLS/BEA/Census/EIA; Google Calendar `needsAuth` | OBS (10/05 7:15 AM PT file). Note: `dashboard/MARKET-TAPE.md` documents a **hard-coded seed formula** (VIX day% ≥+5% → −1, SPY ≤−0.75% → −1, HY OAS Q4 → −1, WTI ≥+3% → −1; Tech: QQQ−SPY ≤−0.3pp → −1 …) while `prompts/03` forbids any score-to-word mapping — two definitions coexist |
| **Peanut (News)** | Producer; wire/headline lane; chat + Rose/Hal alerts | `peanut-news.json` (±1..5 scores, Tech∪chip ~37); writer `dashboard/peanut_news.py` | Weekdays 5:30 AM PT + every 5 min 6:11 AM–1:56 PM PT; X search + public web only; file rewritten only on a move-worthy alert | OBS. NB: SEC, IR, Form 4, Benzinga websocket, read API |
| **X Summarizer / Startup Hunter** | X-edge lane (lane split with Peanut: "do not double-count"); draw on the shared X pool | not in repo | — | DOC only here |
| **Customer/Supplier Bot** | Identity snapshot; `collector:false` | `supply-chain-identity.json`: 37 entities / 37 instruments / **0 relationships / 0 claims** | On demand | OBS (10/04 4:57 PM PT) |
| **Soft Grader** | Typed second opinion on a PAPER_CANDIDATE packet (~400-token snapshot): PAPER lean iff `setup_quality ≥ 2`, `direction_confidence ≥ 0.80`, `risk_state != reduce`, not `toxic_flow`, `regime != crisis`; WATCH iff `setup_quality == 1` / conf 0.60–0.79 / `near_limit`; else SKIP | `market-data/latest/soft-grader.json` | On candidate | CFG; page says "No graded elevates yet — schema live"; two ledger rows cite it (LRCX WATCH conf 0.68; NVDA SKIP) |
| **Shared infra** | `dashboard/live_refresh.py` (single publisher: market-tape, rh-option-marks, macro-spot, fidelity-three, FRED OAS, site build → here.now `bold-tulip-nejq`), `refresh_support_map.py` + `support_notify_diff.py`, close-trigger scorer (`CLOSE-TRIGGERS-V1.md`, "scored 2026-10-02 6:26 PM PT · review alerts: 0"), `market-data/cache_io.py` | — | — | CFG/OBS |

Seats: Rose 8, Hal 7, 15 total (`hal_seats max 7` in pulse file; blotter "Open seats 0/15"). Research Bot and Data Ops Bot: not in this repo.

## (b) Entry pipeline — signal to paper ticket (as actually practiced)

Reconstructed from the 57 closed-ticket "Why" rationales in `data/snapshot.json` plus `hal-rh-watch-pulse.json` `elevate_decisions`, the Soft Grader hard-gate list, and `trader-intel.html` promoted rules. Order below is the order the rationales cite.

1. **Universe & structure read (OBS).** RH Tech∪chip union (37) + SPY/QQQ; PRIMARY support list of 13 (SPY, QQQ, NVDA, TSLA, PLTR, GOOGL, NFLX, META, AMZN, AMD, CBRS, INTC, TSM). Each name is annotated from `fa-levels`: call wall (CW), put wall (PW), gamma flip, `fa_status` ∈ {FRESH (≤600 s), STALE_CARRY, WALLS_DATA_INSUFFICIENT}, `gap_to_cw_pct`, `thru_cw`, `above_flip`, `above_pw`. **No walls ⇒ no seat** ("never invent walls").
2. **Setup family (OBS, 4 variants in ledger).**
   - *Wall-press / "hold above flip & put → press/break call wall"* (13 Rose rows, Sep 10–18, "NVDA-215C-style"): spot within ~0.1–0.5% under FRESH CW, flip and PW held.
   - *Preferred-band FRESH FA call-wall press* (8 rows): spot −0.01% to −0.5% of CW, "flip/put held", liquid weekly call, "soft #1+#2(+#3)" trader-intel claims, "not chase".
   - *Soft A approach / harvest-into-wall* (11 rows, Sep 25–Oct 2): spot 0.14–2% under FRESH CW, flip/PW held, **UW call-led** (C/P ≈ 2.14, 6.11; "TOP premium at K345"), day% below the chase gate; Hal's `:05/:35` pulse "Soft A auto-elevate" used gaps of 0.14–0.56% and "thin room → short-dated Oct16 ATM".
   - *Path B / CW breakthrough LEAP* (Hal; AMD 720C, TSM 450C, INTC 125C): live RH spot through a **Jeffrey-named** CW ("named gate governs" even when the FA store shows 630/650) → Jan'27 LEAP; the 10/05 pulse requires "thru-and-hold ≥~0.5% + FA re-pull", not a single print.
   - Also seen once each: FA HARD wall-roll with spot "kissing" the new wall (TSLA 380C, AMD 620C), X-sourced (MentoviaX MU 1600C), FLEX-footprint proxy (NBIS 290C), three Sep-10 verticals.
3. **Hard gates "that always win" (CFG, Soft Grader page; thresholds OBS in rationales).**
   - Freshness: live RH equity **and** option quote ≤120 s at elevate/invalidate — never from `rh-quotes` cache (`QUERY-DEDUP.md` critical rule).
   - Walls FRESH (TTL 600 s); STALE = color only.
   - **Chase gate: day% ≥ ~3% = SKIP** (NVDA "+3.03% ≥3% … SKIP"; AVGO "+2.9754% no chase (<~3%)"; TSLA "+2.7% near chase line").
   - **Earnings gate `noElevateIntoPrint`** (overridden once by Jeffrey: MU into Sep 30 AMC).
   - **OPEX gate (promoted never_again):** no OPEX-day wall-press unless spot already through CW **or** ≥1% cushion above named flip; "sub-0.1% flip holds are not durable".
   - FOMC-week: no short-DTE presses on STALE walls with chase soft.
   - Seats (8/7/15) and **$5,000 debit ceiling, 1 contract**.
   - Re-seat bans at exact-contract and family level (GOOGL Oct16 350C ban → 345C; "no TSLA short-dated wall-press re-seat into the same OPEX week").
   - "Soft C never alone"; Soft Grader, MA, macro, news, X, chart never elevate alone.
   - No stacking the other trader on the same name/structure ("NVDA … Rose Soft A WATCH — no stack").
   - Standing avoids: WDC/STX/SNDK Soft A "unless Jeffrey lifts it"; Hal uses GOOG not GOOGL.
4. **Contract selection (OBS).** Liquidity by OI/ask (OI 4,654; 6,121; 28,548; 60,549 cited), ask → debit ≤ $5k, prefer ATM/just-under-wall over at-wall; when ATM exceeds the cap the practice was **substitute a farther-OTM strike** (AMD 720C ~15.5% OTM, MU 1600C ~46% OTM) — the Oct-4 prompts now prohibit this.
5. **Owner step (OBS).** Elevates are frequently Jeffrey-initiated or Jeffrey-approved: "Jeffrey 'lrcx yes' paper-elevate"; "Owner-requested Soft A paper seat on shortlist #1 … despite Soft A chase SKIP and Soft Grader SKIP … owner override"; `hal-cw-leap-queue.json` `orderedByJeffrey: true`, "notify Jeffrey on each elevate".
6. **Ticket (OBS).** Paper id (`OID-PAPER-YYYYMMDD-n` / `OT2-PAPER-…`), entry = **ask**, rationale string, `paper-open.json` update, `live_refresh.py` rebuild/publish, chat notify. "Chat approval ≠ ticket" is printed on the close-trigger panel, but in practice the owner's chat "yes" is the trigger.

## (c) Exit and management rules

**CFG (scored after each marks refresh, `CLOSE-TRIGGERS-V1.md`, verbatim from blotter):**
- Hard: thesis fail (named flip/put break) → `INVALIDATE` alert.
- Theta tax: long θ$/day ≥ max($10, 1.5% premium) while P&L < +25% → `CLOSE_TRIGGER_REVIEW`.
- Arm: MFE ≥ +50% → Armed. Giveback: armed AND (mark ≤ 50% of peak OR still-green half-MFE giveback) → `CLOSE_TRIGGER_REVIEW`.
- Time: DTE ≤ 1 or 0DTE morning → `FORCE_REVIEW`.
- Rose book: unrealized ≥ +$1k OR ≥ +30% premium → `BOOK_CLOSE_REVIEW` (BOOK_TP); giveback ≥ 50% of book peak → `BOOK_GIVEBACK`. All "soft; never auto-close".

**Close Playbook V1.1 (DOC, cited in rationales, file not in repo):** harvest into CW / BOOK_TP; early cut on thesis fail / `approach_fail`; FA HARD roll that turns the seat strike into the put wall (~≥3% under new CW) → invalidate immediately, do not re-anchor to a new Path B; "Hal LEAP soft −40% if thesis maybe"; Rose "~−25% soft backstop" for zero-MFE under-wall seats into DTE ≤3 (promoted lesson; one `loss_backstop` tag, GOOGL 350C −55.2%); promoted: on DTE ≤1 with trail armed and spot hugging CW, "paper-close into the wall without waiting for a user ping".

**DOC-only proposals (prompts 01/02):** `PROFIT_WATCH` at +20% bid-based gain → `PROFIT_PROTECTION_REVIEW`; `STALLED_SETUP_REVIEW` at 15/30 min; short-swing first-hour and EOD continuation reviews; Hal 90/60/45/30-DTE `DURATION_REVIEW`; `EXPIRED_PENDING_RECONCILIATION`; 60-second P0 escalation. None scored.

**What actually closed the 57 tickets (OBS):** 43 of 57 were batch/administrative events on eight timestamps — Rose: 7 at 9/21 9:23 AM PT and 7 at 9/22 1:09 PM PT (BOOK_TP "harvest winners together on user order"), 3 at 10/02 6:26 PM PT ("Weekend flatten for Monday Agentic live test… Not a structure or % gate"); Hal: **all 26** (3 spreads 9/17 8:38; 7 at 9/22 9:15 PM PT; 3 `jeffrey_hormuz_trim` 9/23 7:18; 6 `jeffrey_clear_rotate` 9/24 12:08; 7 weekend flatten 10/02 6:26 PM). Only 14 Rose closes were ticket-level: 6 `thesis_fail` invalidations (17 min to 1 day), 2 expiries booked at last mark (`time_decay`), 1 `loss_backstop`, 1 wall-roll `approach_fail`, 1 `FORCE_REVIEW` (GOOGL 340C: MFE +164% at 6:36 AM, exit +17.8% at 7:07 AM), 2 TP, 1 "other". The close-trigger engine has **never auto-closed anything** and produced 0 review alerts in the snapshot; the exit decision is Jeffrey's.

## (d) Data/caching contract and vendor quotas

- **Contract (CFG):** `market-data/cache_io.py` `read_fresh(feed, ttl)` / `write_feed(...)`; envelope `{as_of, as_of_pt, source, writer, feed, symbols, ttl_seconds, payload, error}`; missing/expired/`error≠null` = miss; read-before-pull, owner-only pull on miss, write back including error records. TTLs: `fa-levels` 600 · `uw-flow-alerts`/`uw-net-prem` 900 · `uw-form4` 21600 · `rh-quotes` 120 · `rh-option-marks` 300 · `market-tape` 300 · `support-map` 300 · `hal-marks` 900 · `hal-x-scan` 7200 · `desk-catalysts` 21600 · `macro-morning` 21600/86400 (two values documented) · FRED OAS 86400.
- **One writer per feed (CFG/OBS):** Rose = FA/UW/RH quotes/Form-4; Hal = marks/watch/X/catalysts; Chart = daily bars; piggyback helpers (`piggyback_rh_quotes`) for support-map and market-tape; `oid-support-levels-watch` "NEVER writes rh-quotes". **Observed deviation:** `hal-rh-watch-pulse.json` (10/05 10:41 AM PT, same day the duplicate was "resolved") still records "RH get_equity_quotes live union (2 batches)".
- **Quotas:** FlashAlpha Growth **2,500 calls/day shared** (verified `get_account` 2026-10-01); non-Rose working budget ~5/day logged on Rose; at quota 0 → `STALE_CARRY`, no retry (10/02 walls were STALE_CARRY "because FlashAlpha quota was 0"). X: one credit pool, ~$55.72 left (10/05), drawn by Hal/Macro/Peanut/X Summarizer/Startup Hunter; per-bot caps in `x-spend.json` only proposed. Robinhood: no metered quota recorded. UW: plan quota not recorded. FlashAlpha OAuth and Google Calendar: `needsAuth`.
- **Source health 10/04 (OBS, 34 rows):** 5 OK, 25 CARRY, 1 DISABLED (`x-core8`), 3 NOT_BUILT (`fa-soft`, `uw-oe`, `rh-rvol`).
- **History:** `latest/` is overwrite-in-place; immutable `market-data/snapshots/` bundles are DOC-only (`data/live-bridge.md`); only the eight public here.now pages are archived (`data/reference-snapshots/<sha256>/`).
- **Latency reality:** RH ≤120 s gate; Hal marks every 15 min; watch `:05/:35`; walls hourly + Q5-gated; the 5–10 s / 15–30 s / 60 s cadences in prompts are "targets only" (`HANDBOOK-ERRATA.md` #11). Page auto-refresh 60 s is presentation, not collection.

## (e) DOCUMENTED-ONLY vs BUILT

| Built / observed | Documented only (Oct 4 kit: `prompts/01-05`, `docs/source-registry.json` 27 feed families, `record-field-catalog.json`, `trader-alignment-and-goals.txt`) | Explicit NOT BUILT |
|---|---|---|
| Shared cache + owner matrix; Rose/Hal/Chart/Macro/Peanut/C&S feeds with 10/05 stamps; walls/support map/notify diff; close-trigger scorer; Soft Grader schema; CW LEAP queue (expired 9/25); paper ledger + blotter; here.now publish; local review dashboard (43 tests); promoted never_again rules | Shared collector service with streams/queues/dispatcher; immutable record API + change log + push receiver/outbox; P0/P1/P2 with ack and 60 s escalation; Databento/Massive/ORATS/Benzinga/FactSet/Trading Economics/CME FedWatch/live rates; Chart intraday/weekly bars, patterns, validated forecasts; News Bot SEC/IR/policy streams, relationship edges, project milestones; Macro three briefs/day + 1/5/15-min follow-ups + versioned releases; PROFIT_WATCH, STALLED_SETUP_REVIEW, DURATION_REVIEW; R definition, NAV/TWR, campaign IDs, override records, WATCH/NO_TRADE logging; `market-data/snapshots/` archive | `fa-soft`, `uw-oe`, `rh-rvol` (no writer); Rose X Core-8 (DISABLED); Hal 60 s quote cadence; dashboard every-5m; Chart SOXX/1-min RVOL/pattern detector; C&S edges; graded elevates (0 so far) |

`source-registry.json` self-labels `RECOMMENDATION_SPECIFICATION_NOT_A_DEPLOYED_CONFIGURATION`; every prompt header says "no bot, scheduler, trade, or site has been changed."

## (f) Decisions still made in Jeffrey's head (must be encoded for an automated trader)

1. **Go/no-go on every seat.** Soft color never elevates alone, so the "soft catalyst" judgment (is this UW lean/news/X claim enough?) plus the final "yes" is human: `'lrcx yes'`, owner-requested shortlist picks, `orderedByJeffrey` LEAP queue, "notify Jeffrey on each elevate".
2. **Gate waivers.** Chase gate (NVDA +3.03%), Soft Grader SKIP, `noElevateIntoPrint` (MU), and **which wall level counts** ("Jeffrey named FA CW 620 … named gate governs" over the FA store's 630/650). No override schema exists in the ledger (owner-requested rows are tagged `other`/`loss_backstop`).
3. **Exit timing and book harvests.** 43/57 closes were his batch decisions: BOOK_TP harvests "on user order", Wednesday reset, Hormuz trim (geopolitical read), clear/rotate into new strikes, weekend flatten. FORCE_REVIEW/CLOSE_TRIGGER_REVIEW outcomes wait "for a user ping".
4. **Loss acceptance.** The −25% (Rose) and −40% (Hal) levels are "soft backstop/review", applied by him; the AMZN 260C bled to −61% awaiting a book harvest.
5. **Contract geometry under the cap.** ATM-over-$5k → OTM substitution vs WATCH; short-dated vs Jan'27 on the same wall; single contract always (no risk-based size).
6. **Universe and avoid lists.** PRIMARY 13, Tech∪chip 37, WDC/STX/SNDK avoid "unless Jeffrey lifts it", GOOG vs GOOGL, Hal X handle allowlist, Rose Core-8 off.
7. **Vendor economics.** Who owns `rh-quotes`, FA burn priorities (VIX/oil/walls/agents), whether to pay for Alpha/Databento.
8. **Rule promotion.** Weekly review turns lessons into never_again gates (OPEX cushion, flip-break invalidate, no FOMC-week stale-wall presses) — a human changelog, not a versioned policy file.
9. **Macro discount.** Daily Macro/Macro Tech are read and discounted ("Macro −2/−2 soft headwind noted" on seats he opened anyway).
10. **Direction and instrument.** The paper desk is **long calls only** (54/57 rows; 3 Sep-10 verticals; zero outright puts); Jeffrey's live style (calls *and* puts, seconds-to-hours holds, +10–20% exits) is not expressed in any routine, and his live fills are not in the repos.
11. **Live authority.** "Unless Jeffrey separately names a live Agentic ticket" — the only path to a real order is a human sentence.

## (g) Accounting/measurement gaps that block scaling

- **No R.** Returns are P&L ÷ entry debit per ticket; `initial_max_risk_R` (long = debit + costs; credit vertical = width − credit) is proposed only (`trader-alignment-and-goals.txt` §5).
- **No NAV, cash, or sleeve capital** (`NAV_UNAVAILABLE` validation). Blotter "+20.3%" = +$14,888.50 / $73,384 cumulative recycled ticket debit — "not a fund NAV return". Header mixes scopes (Day −$228/−3.2%, Week +$282/+4.0%, open $0).
- **Administrative closes dominate:** 43/57 batch exits; 10 weekend-flatten closes at last RTH mark stamped 6:26 PM PT; **7 Hal entries stamped 2026-09-22 9:15 PM PT** (after-hours bookkeeping booked as entries). Entry = ask, exit = mark/mid, **zero fees or slippage** modeled.
- **Arithmetic/sign errors (OBS, `data_validation`):** GOOGL 8.65→3.80 ×100 reported −$467.50 (vs −$485); NVDA 8.00→5.35 reported −$260 (vs −$265); SPY 755/750P and QQQ 700/695P credit spreads show −$64/−$72 yet tagged `win_exit`; 3 MFE/MAE timestamps outside the holding interval; one exit time "2026-09-11 morning (Rose reported)".
- **MFE is a sampled maximum** (Q5 / 15-min marks), so trail-arm and giveback stats are not executable peaks.
- **Concentration:** Rose top 3 (AMD 550C +$4,917.50, META 670C +$4,550, LRCX 310C +$1,975) = $11,442.50 of +$12,844 (89%); the 9/18 cohort of seven wall-presses closed together 9/21 and Hal's seven LEAPs opened/closed together — one market move counted as many wins; no shared-shock or correlated-exposure report exists.
- **No denominators for the gates:** BOOK_TP "premium baseline", peak-reset rules, Hal portfolio rules are undefined (`CONFIGURATION_REVIEW` proposed).
- **Missing records:** no WATCH/NO_TRADE/suppressed-alert log; no override table; no campaign IDs linking rotations (SPY 800C→785C, QQQ 780C→750C, NVDA 230C→240C, TSLA 420C→400C); `paper-trades/trades.json` and `CLOSE-TRIGGERS-V1.md`/`Close Playbook V1.1` live only on the box.
- **Sample:** 31 Rose / 26 Hal rows, Sep 10–Oct 4, one regime; the desk's own audit says this "cannot support a credible monthly growth target", and the Oct-20 live-page studies (near coin-flip scores; only 1-min rvol ≥3x robust) are not linked to any routine in this repo — the bots' Soft A workflow and the live page's Direction/Light/Momentum scores are two undocumented-to-each-other systems.