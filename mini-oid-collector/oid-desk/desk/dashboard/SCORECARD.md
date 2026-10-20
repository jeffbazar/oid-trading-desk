# OID Paper Scorecard

Updated **2026-09-30 12:34 PM PT** · Mandate V1.8 · Research only

## Summary

| Metric | Value |
|--------|-------|
| Closed win rate | **54.3%** (25/46) |
| Avg win % | 55.25 |
| Avg loss % | -20.17 |
| Expectancy $/ticket (closed) | **$199.27** |
| Closed P&L sum | $9166.5 |
| Open unrealized | **$1510.0** (5 ticket) |
| Tickets total | 51 |

## Live ticket MFE/MAE

**OID-PAPER-20260928-3** · AMZN 2026-10-16 245 call

| | |
|--|--|
| Entry ask | $7.25 |
| Last mark | $9.08 |
| Peak (MFE) | $10.8 · **48.97%** / $355.0 |
| Trough (MAE) | $6.48 · **-10.62%** / $-77.0 |
| Unrealized | 25.24% / $183.0 |
| Hold hours | 53.36 |
| Tag | `win_open` |

## By catalyst

- **CW approach Soft A + flip held; FRESH FA CW 320 (~1.4% under); owner soft-seat override**: n=1, closed-wins=0, pnlUsdSum=$0.0
- **FLEX-proxy; Alpha_Ex NBIS Jan27 FLEX print color**: n=1, closed-wins=1, pnlUsdSum=$383.0
- **FOMC / Fed calendar**: n=12, closed-wins=8, pnlUsdSum=$6622.0
- **UW flow**: n=4, closed-wins=3, pnlUsdSum=$271.0
- **earnings Sep 30 AMC (Q4 FY2026) — Jeffrey override soft noElevateIntoPrint for this LEAP paper**: n=1, closed-wins=0, pnlUsdSum=$-407.5
- **ex-div / calendar**: n=2, closed-wins=2, pnlUsdSum=$306.0
- **unknown**: n=13, closed-wins=4, pnlUsdSum=$-1711.0
- **wall+thesis**: n=17, closed-wins=7, pnlUsdSum=$3703.0

## By symbol

- **AMD**: n=3, wins=2, open=0, pnlUsdSum=$5137.5
- **AMZN**: n=5, wins=2, open=1, pnlUsdSum=$-168.5
- **GOOGL**: n=4, wins=2, open=1, pnlUsdSum=$-91.5
- **INTC**: n=2, wins=2, open=0, pnlUsdSum=$1072.5
- **LRCX**: n=2, wins=0, open=2, pnlUsdSum=$1370.0
- **META**: n=2, wins=1, open=0, pnlUsdSum=$4222.5
- **MU**: n=1, wins=0, open=0, pnlUsdSum=$-407.5
- **NBIS**: n=1, wins=1, open=0, pnlUsdSum=$383.0
- **NFLX**: n=1, wins=0, open=0, pnlUsdSum=$-92.0
- **NVDA**: n=8, wins=4, open=0, pnlUsdSum=$-214.0
- **PLTR**: n=3, wins=3, open=0, pnlUsdSum=$533.0
- **QQQ**: n=7, wins=5, open=1, pnlUsdSum=$76.5
- **SPY**: n=4, wins=2, open=0, pnlUsdSum=$-369.5
- **TSLA**: n=7, wins=1, open=0, pnlUsdSum=$-628.0
- **TSM**: n=1, wins=0, open=0, pnlUsdSum=$-147.5

## Top lessons

- **OID-PAPER-20260910-1** (`win_exit`): Wall+thesis reclaim above flip toward call 220 worked enough for Rose to bank ~+14.3% at $4.40; path showed MFE ~+24% then gave back — early scale worked.
  - Refine: When live paper is ≥~+15–20% into the named wall with thesis intact, prompt a take-profit / trim check rather than only invalidation monitoring.
- **OID-PAPER-20260914-1** (`thesis_fail`): Long-call press-370 failed within ~15 minutes when spot broke FA flip 363.74 and tested put 360 into FOMC week — short DTE + event risk + under-wall entry.
  - Refine: Do not elevate short-DTE long calls into FOMC week when spot is already under the call wall and the named fail is a nearby flip with thin cushion.
- **OID-PAPER-20260914-2** (`thesis_fail`): Press/break call 80 worked briefly (MFE ~+29%) on Mon, then Tue open lost STALE flip 78.60 into FOMC day-1 — chase soft + short DTE into Fed both named.
  - Refine: Gate harder on FOMC-week short-DTE call presses that already show chase soft and rely on STALE walls; invalidate faster on first flip loss, don't wait for −70%.
- **OID-PAPER-20260916-1** (`win_exit`): Fresh FA call-wall press (215) with flip held through FOMC day-2 produced large MFE; paper TP locked a win after overnight MAE ~−26%.
  - Refine: Repeat: fresh call-wall press ≤~0.5%, flip held, liquid short-dated call; thesis floor intact can survive event whip.
- **OT2-PAPER-20260910-A** (`win_exit`): Paper-closed SPY 755/750P credit at Jeffrey's request ahead of Sep 18 expiry; locked +55.2% ($+64) vs entry.
  - Refine: When put credits are near max value with <1 DTE, prompt take-profit / paper close rather than holding to print.
- **OT2-PAPER-20260910-B** (`win_exit`): Paper-closed QQQ 700/695P credit at Jeffrey's request ahead of Sep 18 expiry; locked +88.9% ($+72) vs entry.
  - Refine: When put credits are near max value with <1 DTE, prompt take-profit / paper close rather than holding to print.
- **OT2-PAPER-20260910-C** (`win_exit`): Paper-closed NVDA 220/215P debit at Jeffrey's request ahead of Sep 18 expiry; locked +14.7% ($+22) vs entry.
  - Refine: Scale/exit put debits when the bounce reclaim of the broken put wall eats MFE after the event.
- **OID-PAPER-20260917-1** (`time_decay`): Sep18 OPEX expired while still open on blotter; Hal seat-cleanup Sat 9/19 to free a seat for NBIS LEAP FLEX-proxy. Last mark 2.035 vs entry 1.3.
  - Refine: Auto-expire 0DTE / expiry-day tickets at cash close so seats don't stick open overnight.
- **OID-PAPER-20260917-2** (`thesis_fail`): Wall-press long call invalidated when named flip failed even though put wall still held. On OPEX 0DTE, flip break + magnet to put (FA zero_dte_magnet 360) was enough — do not wait for put break when flip was the explicit gate.
  - Refine: For OPEX-day wall-press seats: require either (a) spot already through call wall, or (b) >=1% cushion above flip before elevate; treat flip-null / sign-mismatch refreshes as risk-off color, not as clearing a prior flip break.
- **OID-PAPER-20260917-3** (`time_decay`): Sep18 OPEX expired while still open on blotter; Hal seat-cleanup Sat 9/19 to free a seat for NBIS LEAP FLEX-proxy. Last mark 1.815 vs entry 1.25.
  - Refine: Auto-expire 0DTE / expiry-day tickets at cash close so seats don't stick open overnight.
- **OID-PAPER-20260918-1** (`win_exit`): BOOK_TP harvest / user-ordered paper close ~9:22 AM PT; locked +247.4% ($+952) on INTC.
  - Refine: When Rose book hits BOOK_TP (+$1k or +30%), harvest winners together on user order rather than letting giveback erode the book peak.
- **OID-PAPER-20260918-2** (`win_exit`): BOOK_TP harvest / user-ordered paper close ~9:22 AM PT; locked +358.94% ($+4918) on AMD.
  - Refine: When Rose book hits BOOK_TP (+$1k or +30%), harvest winners together on user order rather than letting giveback erode the book peak.
- **OID-PAPER-20260918-3** (`win_exit`): BOOK_TP harvest / user-ordered paper close ~9:22 AM PT; locked +115.91% ($+510) on PLTR.
  - Refine: When Rose book hits BOOK_TP (+$1k or +30%), harvest winners together on user order rather than letting giveback erode the book peak.
- **OID-PAPER-20260918-4** (`win_exit`): BOOK_TP harvest / user-ordered paper close ~9:22 AM PT; locked +29.58% ($+105) on AMZN.
  - Refine: When Rose book hits BOOK_TP (+$1k or +30%), harvest winners together on user order rather than letting giveback erode the book peak.
- **OID-PAPER-20260918-5** (`win_exit`): BOOK_TP harvest / user-ordered paper close ~9:22 AM PT; locked +61.95% ($+350) on GOOGL.
  - Refine: When Rose book hits BOOK_TP (+$1k or +30%), harvest winners together on user order rather than letting giveback erode the book peak.
- **OID-PAPER-20260918-6** (`thesis_fail`): Elevated TSLA Sep25 365C on preferred flip-held wall-press with only +0.02% flip cushion; within ~40 min OPEX spot slipped 10¢ under flip 363.32 while the option mark stayed ~flat at entry. Named flip gate failed even though put 360 held and premium had not yet collapsed.
  - Refine: Require a wider flip cushion (or confirmed thru-call) before elevating OPEX-day wall-press calls; do not treat sub-0.1% flip holds as durable on OPEX.
- **OID-PAPER-20260918-7** (`win_exit`): BOOK_TP harvest / user-ordered paper close ~9:22 AM PT; locked +311.64% ($+4550) on META.
  - Refine: When Rose book hits BOOK_TP (+$1k or +30%), harvest winners together on user order rather than letting giveback erode the book peak.
- **OT2-PAPER-20260919-1** (`win_exit`): Jeffrey EOD rotate close of NBIS 2027-01-15 290 call at RH mark 29.38 (entry ask 25.55) → +14.99% / $+383. Fresh Hal seats for Wed open; not thesis_fail.
  - Refine: Operator rotate is scorecard-neutral vs thesis_fail; preserve MFE/MAE for postmortem.
- **OID-PAPER-20260921-1** (`win_exit`): BOOK_TP harvest / user-ordered paper close ~9:22 AM PT; locked +48.27% ($+251) on QQQ.
  - Refine: When Rose book hits BOOK_TP (+$1k or +30%), harvest winners together on user order rather than letting giveback erode the book peak.
- **OT2-PAPER-20260921-1** (`win_exit`): Jeffrey EOD rotate close of INTC 2027-01-15 125 call at RH mark 19.25 (entry ask 18.05) → +6.65% / $+120. Fresh Hal seats for Wed open; not thesis_fail.
  - Refine: Operator rotate is scorecard-neutral vs thesis_fail; preserve MFE/MAE for postmortem.
- **OID-PAPER-20260921-2** (`win_exit`): User-ordered Wed-reset harvest at Tue cash-close marks; SPY Sep25 772C locked small green (+6.6%) under FRESH call wall roll to 785 — wall-press soft while index coil held.
  - Refine: When FA call wall rolls up materially after elevate, treat remaining edge as soft carry and prefer harvest on user reset rather than chasing the new wall AH.
- **OID-PAPER-20260921-3** (`loss_exit`): User-ordered Wed-reset harvest; AMZN Sep25 260C deep red (−61%) as spot faded under 260 call wall with theta into Fri OPEX — wall-press without reclaim failed.
  - Refine: Cut or soft-invalidate AMZN-style wall presses earlier when MAE >50% and spot holds under wall into DTE≤3; do not wait for book harvest.
- **OID-PAPER-20260922-1** (`thesis_fail`): META Sep25 750C call-wall press failed when spot rejected and held under named ~740 invalidate with wall still 750 (~1.4% away); short DTE wall-press without flip cushion faded mid-session.
- **OID-PAPER-20260922-2** (`win_exit`): User-ordered Wed-reset harvest; AMD Sep25 620C locked +20.6% even after HARD call-wall roll 620→650 — residual ITM/near premium survived the thesis wall move.
  - Refine: On HARD call-wall roll away from strike, score FORCE_REVIEW same day; harvesting residual green on user reset is OK but do not re-elevate the old strike.
- **OID-PAPER-20260922-3** (`win_exit`): User-ordered Wed-reset harvest; PLTR Sep25 185C flat/tiny green at cash close with spot ~at FRESH call 185 — wall glue worked, limited expansion.
  - Refine: At-wall presses into OPEX week can pin; prefer tighter profit-take or next-expiry if expansion stalls by cash close.
- **OID-PAPER-20260922-4** (`win_exit`): User-ordered Wed-reset harvest; QQQ Sep25 745C best Rose winner (+42%) as spot pressed toward FRESH 750 call wall — classic index wall-press payoff.
  - Refine: Keep preferring liquid index call-wall presses (QQQ/SPY) when FA stamp FRESH and spot ≤~0.5–1% under wall into OPEX week.
- **OT2-PAPER-20260922-1** (`loss_exit`): Jeffrey EOD rotate close of NVDA 2027-01-15 230 call at RH mark 19.58 (entry ask 19.90) → -1.61% / $-32. Fresh Hal seats for Wed open; not thesis_fail.
  - Refine: Operator rotate is scorecard-neutral vs thesis_fail; preserve MFE/MAE for postmortem.
- **OT2-PAPER-20260922-2** (`win_exit`): Jeffrey EOD rotate close of TSLA 2027-01-15 420 call at RH mark 23.25 (entry ask 22.80) → +1.97% / $+45. Fresh Hal seats for Wed open; not thesis_fail.
  - Refine: Operator rotate is scorecard-neutral vs thesis_fail; preserve MFE/MAE for postmortem.
- **OT2-PAPER-20260922-3** (`win_exit`): Jeffrey EOD rotate close of PLTR 2027-01-15 200 call at RH mark 17.18 (entry ask 17.00) → +1.06% / $+18. Fresh Hal seats for Wed open; not thesis_fail.
  - Refine: Operator rotate is scorecard-neutral vs thesis_fail; preserve MFE/MAE for postmortem.
- **OT2-PAPER-20260922-4** (`loss_exit`): Jeffrey EOD rotate close of SPY 2027-01-15 800 call at RH mark 15.17 (entry ask 15.23) → -0.39% / $-6. Fresh Hal seats for Wed open; not thesis_fail.
  - Refine: Operator rotate is scorecard-neutral vs thesis_fail; preserve MFE/MAE for postmortem.
- **OT2-PAPER-20260922-5** (`win_exit`): Jeffrey EOD rotate close of QQQ 2027-01-15 780 call at RH mark 22.97 (entry ask 21.82) → +5.27% / $+115. Fresh Hal seats for Wed open; not thesis_fail.
  - Refine: Operator rotate is scorecard-neutral vs thesis_fail; preserve MFE/MAE for postmortem.
- **OID-PAPER-20260922-5** (`loss_exit`): User-ordered Wed-reset harvest; NVDA Sep25 230C ~flat (−0.5%) with spot still ~0.5% under FRESH call 230 — thesis intact but no expansion by cash close.
  - Refine: NVDA 230C remains the crystal-clear Wed-open carryover press; restage as AH_STAGED shortlist only — elevate only on live ≤120s Wed open.
- **OID-PAPER-20260922-6** (`loss_exit`): User-ordered Wed-reset harvest; TSLA Sep25 380C small red (−6.4%) after intraday wall whip (380↔400) then close rollback to 380 — whippy single-name wall.
  - Refine: Treat mid-session HARD wall rolls on TSLA as whip risk into OPEX; prefer harvest/reset over overnight hold when wall is unstable.
- **OT2-PAPER-20260923-1** (`loss_exit`): Jeffrey Hormuz soft risk-off trim of MU 2027-01-15 1600 call at RH mid 37.425 (entry ask 41.5) → -9.82% / $-407.50. Macro Hormuz soft risk-off; trim weakest longs — not thesis_fail.
  - Refine: Operator macro trim is scorecard-neutral vs thesis_fail; preserve MFE/MAE; freeze new Hal long-call elevates until oil/USO/Hormuz clarifies.
- **OT2-PAPER-20260923-2** (`other`): Operator clear-rotate closed SPY 2027-01-15 785 call at RH mid 19.34 (entry ask 22.59) → -14.36% / $-324.50. Seat freed for fresh CW-breakthrough book; not a thesis_fail scorecard event.
  - Refine: Preserve MFE/MAE; treat jeffrey_clear_rotate as operator book reset — re-elevate only on live ≤120s RH through named CW with fresh soft catalyst, avoid identical thesis re-open without new wall state.
- **OT2-PAPER-20260923-3** (`other`): Operator clear-rotate closed QQQ 2027-01-15 750 call at RH mid 33.85 (entry ask 38.09) → -11.13% / $-424.00. Seat freed for fresh CW-breakthrough book; not a thesis_fail scorecard event.
  - Refine: Preserve MFE/MAE; treat jeffrey_clear_rotate as operator book reset — re-elevate only on live ≤120s RH through named CW with fresh soft catalyst, avoid identical thesis re-open without new wall state.
- **OT2-PAPER-20260923-4** (`other`): Operator clear-rotate closed NVDA 2027-01-15 240 call at RH mid 12.47 (entry ask 15.20) → -17.93% / $-272.50. Seat freed for fresh CW-breakthrough book; not a thesis_fail scorecard event.
  - Refine: Preserve MFE/MAE; treat jeffrey_clear_rotate as operator book reset — re-elevate only on live ≤120s RH through named CW with fresh soft catalyst, avoid identical thesis re-open without new wall state.
- **OT2-PAPER-20260923-5** (`other`): Operator clear-rotate closed TSLA 2027-01-15 400 call at RH mid 28.62 (entry ask 30.00) → -4.58% / $-137.50. Seat freed for fresh CW-breakthrough book; not a thesis_fail scorecard event.
  - Refine: Preserve MFE/MAE; treat jeffrey_clear_rotate as operator book reset — re-elevate only on live ≤120s RH through named CW with fresh soft catalyst, avoid identical thesis re-open without new wall state.
- **OT2-PAPER-20260923-6** (`loss_exit`): Jeffrey Hormuz soft risk-off trim of AMZN 2027-01-15 260 call at RH mid 15.925 (entry ask 19.4) → -17.91% / $-347.50. Macro Hormuz soft risk-off; trim weakest longs — not thesis_fail.
  - Refine: Operator macro trim is scorecard-neutral vs thesis_fail; preserve MFE/MAE; freeze new Hal long-call elevates until oil/USO/Hormuz clarifies.
- **OT2-PAPER-20260923-7** (`loss_exit`): Jeffrey Hormuz soft risk-off trim of GOOGL 2027-01-15 370 call at RH mid 16.25 (entry ask 20.9) → -22.25% / $-465.00. Macro Hormuz soft risk-off; trim weakest longs — not thesis_fail.
  - Refine: Operator macro trim is scorecard-neutral vs thesis_fail; preserve MFE/MAE; freeze new Hal long-call elevates until oil/USO/Hormuz clarifies.
- **OID-PAPER-20260923-1** (`thesis_fail`): TSLA Sep25 380C elevated on FH call-wall press after roll 385→380; mid-session WP-3 HARD-rolled call to 400 and put up to 380 so the strike became the put rail, not the call wall. Invalidate on material FA call-wall roll-away even if spot has not broken the old ~375 put gate.
- **OT2-PAPER-20260924-1** (`other`): Operator clear-rotate closed AMD 2027-01-15 720 call at RH mid 47.65 (entry ask 47.80) → -0.31% / $-15.00. Seat freed for fresh CW-breakthrough book; not a thesis_fail scorecard event.
  - Refine: Preserve MFE/MAE; treat jeffrey_clear_rotate as operator book reset — re-elevate only on live ≤120s RH through named CW with fresh soft catalyst, avoid identical thesis re-open without new wall state.
- **OID-PAPER-20260924-1** (`win_exit`): Paper harvest under jeffrey_start_closing. Strong pick: MFE ~+164% (peak $6.03) with spot pressing FA CW 345; exit mark $2.685 = +17.8% / +$40 vs entry ask $2.28 after ~55% giveback from peak. Refine: on 0DTE FORCE_REVIEW + hug CW, paper-close nearer peak / into wall — do not wait for more. Research/paper only — zero RH execution.
  - Refine: 0DTE + FORCE_REVIEW + near CW → harvest sooner; trail/giveback from peak should paper-close without waiting for user ping
- **OT2-PAPER-20260924-2** (`other`): Operator clear-rotate closed TSM 2027-01-15 450 call at RH mid 37.52 (entry ask 39.00) → -3.78% / $-147.50. Seat freed for fresh CW-breakthrough book; not a thesis_fail scorecard event.
  - Refine: Preserve MFE/MAE; treat jeffrey_clear_rotate as operator book reset — re-elevate only on live ≤120s RH through named CW with fresh soft catalyst, avoid identical thesis re-open without new wall state.
- **OID-PAPER-20260925-1** (`win_exit`): Soft A AMZN Oct02 250C paper-closed +26.47% / +$90.0 on FA wall roll (CW 250→260). Spot tagged old CW then wall redefined: new PW 250 / CW 260. Early cut correct — do not hold a Soft A harvest plan after the target wall rolls away, even when green. Research/paper only — zero RH.
  - Refine: On Soft A seats: if FRESH FA rolls CW ≥1 strike away from the ticket target, paper-close same Q5 cycle (approach_fail) rather than re-anchoring to the new wall mid-flight.
- **OID-PAPER-20260928-2** (`other`): NVDA Oct16 230C paper-closed -32.7% / $-260 vs entryMark 7.95 (−33.1% vs entryAsk 8.0) on loss_backstop after wall roll 235→230. SoftOnly chase elevate into Soft A that then rolled against the seat — cut at −25% backstop, do not wait for −40% or hope into CW when MFE never printed. Research/paper only — zero RH.

## Current refine rules (from losses)

1. (OID-PAPER-20260914-1 / TSLA) Do not elevate short-DTE long calls into FOMC week when spot is already under the call wall and the named fail is a nearby flip with thin cushion.
2. (OID-PAPER-20260914-2 / NFLX) Gate harder on FOMC-week short-DTE call presses that already show chase soft and rely on STALE walls; invalidate faster on first flip loss, don't wait for −70%.
3. (OID-PAPER-20260917-2 / TSLA) For OPEX-day wall-press seats: require either (a) spot already through call wall, or (b) >=1% cushion above flip before elevate; treat flip-null / sign-mismatch refreshes as risk-off color, not as clearing a prior flip break.
4. (OID-PAPER-20260918-6 / TSLA) Require a wider flip cushion (or confirmed thru-call) before elevating OPEX-day wall-press calls; do not treat sub-0.1% flip holds as durable on OPEX.
5. (OID-PAPER-20260921-3 / AMZN) Cut or soft-invalidate AMZN-style wall presses earlier when MAE >50% and spot holds under wall into DTE≤3; do not wait for book harvest.
6. (OT2-PAPER-20260922-1 / NVDA) Operator rotate is scorecard-neutral vs thesis_fail; preserve MFE/MAE for postmortem.
7. (OID-PAPER-20260922-5 / NVDA) NVDA 230C remains the crystal-clear Wed-open carryover press; restage as AH_STAGED shortlist only — elevate only on live ≤120s Wed open.
8. (OID-PAPER-20260922-6 / TSLA) Treat mid-session HARD wall rolls on TSLA as whip risk into OPEX; prefer harvest/reset over overnight hold when wall is unstable.
9. (OT2-PAPER-20260923-1 / MU) Operator macro trim is scorecard-neutral vs thesis_fail; preserve MFE/MAE; freeze new Hal long-call elevates until oil/USO/Hormuz clarifies.
10. (OT2-PAPER-20260923-2 / SPY) Preserve MFE/MAE; treat jeffrey_clear_rotate as operator book reset — re-elevate only on live ≤120s RH through named CW with fresh soft catalyst, avoid identical thesis re-open without new wall state.

## Ticket blotter

| ID | Sym | Status | Tag | P&L% | MFE% | MAE% | Hold h |
|----|-----|--------|-----|------|------|------|--------|
| OID-PAPER-20260928-3 | AMZN | open | `win_open` | 25.24 | 48.97 | -10.62 | 53.36 |
| OID-PAPER-20260910-1 | NVDA | closed | `win_exit` | 14.29 | 24.03 | -3.9 | 23.4 |
| OID-PAPER-20260914-1 | TSLA | invalidated | `thesis_fail` | -33.88 | 0.0 | -33.88 | 0.24 |
| OID-PAPER-20260914-2 | NFLX | invalidated | `thesis_fail` | -70.23 | 29.39 | -70.23 | 24.5 |
| OID-PAPER-20260916-1 | NVDA | closed | `win_exit` | 77.88 | 95.19 | -25.96 | 24.87 |
| OT2-PAPER-20260910-A | SPY | closed | `win_exit` | -55.17 | 0.0 | -55.17 | 170.44 |
| OT2-PAPER-20260910-B | QQQ | closed | `win_exit` | -88.89 | 0.0 | -88.89 | 170.44 |
| OT2-PAPER-20260910-C | NVDA | closed | `win_exit` | 14.73 | 168.84 | 0.0 | 170.44 |
| OID-PAPER-20260917-1 | NVDA | expired | `time_decay` | 56.54 | 56.54 | -86.54 | 28.2 |
| OID-PAPER-20260917-2 | TSLA | invalidated | `thesis_fail` | -84.24 | -0.17 | -84.24 | 21.98 |
| OID-PAPER-20260917-3 | QQQ | expired | `time_decay` | 45.2 | 45.2 | -95.6 | 27.36 |
| OID-PAPER-20260918-1 | INTC | closed | `win_exit` | 247.4 | 281.3 | -44.94 | 74.79 |
| OID-PAPER-20260918-2 | AMD | closed | `win_exit` | 358.94 | 385.62 | -16.61 | 74.0 |
| OID-PAPER-20260918-3 | PLTR | closed | `win_exit` | 115.91 | 115.91 | 1.14 | 73.59 |
| OID-PAPER-20260918-4 | AMZN | closed | `win_exit` | 29.58 | 30.99 | -17.18 | 73.13 |
| OID-PAPER-20260918-5 | GOOGL | closed | `win_exit` | 61.95 | 73.45 | -7.96 | 72.58 |
| OID-PAPER-20260918-6 | TSLA | invalidated | `thesis_fail` | 0.0 | 0.35 | -1.42 | 0.65 |
| OID-PAPER-20260918-7 | META | closed | `win_exit` | 311.64 | 311.64 | -14.73 | 68.63 |
| OT2-PAPER-20260919-1 | NBIS | closed | `win_exit` | 14.99 | 32.49 | -5.58 | 80.83 |
| OID-PAPER-20260921-1 | QQQ | closed | `win_exit` | 48.27 | 48.27 | -0.29 | 1.89 |
| OT2-PAPER-20260921-1 | INTC | closed | `win_exit` | 6.65 | 12.35 | -3.71 | 37.53 |
| OID-PAPER-20260921-2 | SPY | closed | `win_exit` | 6.56 | 39.11 | -5.25 | 27.72 |
| OID-PAPER-20260921-3 | AMZN | closed | `loss_exit` | -61.23 | 0.0 | -67.69 | 24.51 |
| OID-PAPER-20260922-1 | META | invalidated | `thesis_fail` | -21.48 | 28.07 | -21.48 | 3.97 |
| OID-PAPER-20260922-2 | AMD | closed | `win_exit` | 18.88 | 22.33 | -20.24 | 5.67 |
| OID-PAPER-20260922-3 | PLTR | closed | `win_exit` | 1.52 | 1.52 | -18.79 | None |
| OID-PAPER-20260922-4 | QQQ | closed | `win_exit` | 41.81 | 45.61 | -1.66 | None |
| OT2-PAPER-20260922-1 | NVDA | closed | `loss_exit` | -1.61 | 0.9 | -1.86 | 11.21 |
| OT2-PAPER-20260922-2 | TSLA | closed | `win_exit` | 1.97 | 3.73 | -1.1 | 11.21 |
| OT2-PAPER-20260922-3 | PLTR | closed | `win_exit` | 1.06 | 1.06 | -1.59 | 11.21 |
| OT2-PAPER-20260922-4 | SPY | closed | `loss_exit` | -0.39 | 4.01 | -0.66 | 11.21 |
| OT2-PAPER-20260922-5 | QQQ | closed | `win_exit` | 5.27 | 5.82 | -0.46 | 11.21 |
| OID-PAPER-20260922-5 | NVDA | closed | `loss_exit` | -0.92 | 15.6 | -1.15 | None |
| OID-PAPER-20260922-6 | TSLA | closed | `loss_exit` | -7.24 | 4.31 | -7.33 | 2.04 |
| OT2-PAPER-20260923-1 | MU | closed | `loss_exit` | -9.82 | 0.0 | -9.82 | 10.06 |
| OT2-PAPER-20260923-2 | SPY | closed | `other` | -14.36 | 0.0 | -21.87 | 38.88 |
| OT2-PAPER-20260923-3 | QQQ | closed | `other` | -11.13 | 0.0 | -18.25 | 38.88 |
| OT2-PAPER-20260923-4 | NVDA | closed | `other` | -17.93 | 0.0 | -25.33 | 38.88 |
| OT2-PAPER-20260923-5 | TSLA | closed | `other` | -4.58 | 8.83 | -8.57 | 38.88 |
| OT2-PAPER-20260923-6 | AMZN | closed | `loss_exit` | -17.91 | 0.0 | -17.91 | 10.06 |
| OT2-PAPER-20260923-7 | GOOGL | closed | `loss_exit` | -22.25 | 0.0 | -22.25 | 10.06 |
| OID-PAPER-20260923-1 | TSLA | invalidated | `thesis_fail` | -7.48 | 8.04 | -22.9 | 3.94 |
| OT2-PAPER-20260924-1 | AMD | closed | `other` | -0.31 | 0.17 | -16.42 | 5.32 |
| OID-PAPER-20260924-1 | GOOGL | closed | `win_exit` | 17.76 | 164.47 | -15.35 | 23.81 |
| OT2-PAPER-20260924-2 | TSM | closed | `other` | -3.78 | 0.51 | -5.56 | 2.3 |
| OID-PAPER-20260925-1 | AMZN | closed | `win_exit` | 26.47 | 26.47 | -16.76 | 2.5 |
| OT2-PAPER-20260928-1 | LRCX | open | `win_open` | 14.39 | 14.39 | -14.97 | 53.98 |
| OID-PAPER-20260928-1 | LRCX | open | `win_open` | 33.98 | 34.47 | -29.13 | 53.87 |
| OID-PAPER-20260928-2 | NVDA | closed | `other` | -32.7 | -0.62 | -34.38 | 30.15 |
| OID-PAPER-20260930-1 | GOOGL | open | `win_open` | -1.97 | 24.05 | -6.01 | 5.72 |
| OT2-PAPER-20260930-1 | QQQ | open | `win_open` | -1.78 | 3.7 | -7.12 | 5.21 |

_Research / paper tracking only. Zero live execution from OID._
