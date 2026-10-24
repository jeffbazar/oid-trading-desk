# Event map: Monday 2026-10-26 through Friday 2026-10-30 (all times ET)

## 0. Research status — read this first

- **Live research failed in this run.** Every WebSearch call returned "web search budget is used up (limit: 200 per turn, shared by every agent)" before my first query executed; zero searches ran. WebFetch could not resolve any finance, government, exchange or IR host (DNS `ENOTFOUND` for federalreserve.gov, treasurydirect.gov, bea.gov, bls.gov, census.gov, conference-board.org, richmondfed.org, dol.gov, ecb.europa.eu, boj.or.jp, twse.com.tw, cboe.com, cmegroup.com, spglobal.com, opec.org, abc.xyz, ir.aboutamazon.com, intc.com, investor.nvidia.com, investor.apple.com, ir.amd.com, servicenow.com, investors.robinhood.com, investors.seagate.com, investors.teradyne.com, ir.kla.com, investors.sandisk.com, investors.nxp.com, investor.tsmc.com, skhynix.com, samsung.com, investor.fb.com, en.wikipedia.org). curl through the sandbox proxy got `CONNECT 403` on the same hosts. The only reachable host was microsoft.com.
- **Consequence:** exactly one item below is VERIFIED. Everything else is either **CONTEXT** (relayed to me by the workflow from the Thursday-night 10/22 snippet research; I was not given the URLs, so it is weaker than EXTRACT) or **UNVERIFIED** (standard scheduling rules, prior-year patterns, calendar arithmetic, or my recollection). No consensus numbers, FedWatch odds, auction sizes for this week, implied moves or pension-rebalance estimates could be found; I say "NOT FOUND" rather than guess.
- A follow-up message after this reply will reset the search budget and let the verification pass run. The "Sunday-night checklist" in section 10 lists the exact pages to confirm, in priority order.

## 1. Two structural facts that reshape the week (both need confirmation)

| Item | Status | Detail |
|---|---|---|
| Europe/US clock mismatch all week | UNVERIFIED (calendar arithmetic, high confidence) | EU summer time ends Sun 10/25/2026 (last Sunday of October); US DST ends Sun 11/1/2026. For 10/26–10/30 London is only 4h ahead of New York and CET only 5h. European cash open moves to **4:00 AM ET** (not 3:00), London/Eurex closes move to **12:30 PM ET** (not 11:30), ECB decision 14:15 CET = **9:15 AM ET**, presser 14:45 CET = **9:45 AM ET**. Any desk clock or alert keyed to "11:30 Europe close" is one hour early this week. |
| Taiwan likely CLOSED Monday 10/26 for a public holiday, reopening Tuesday 10/27 | UNVERIFIED (recollection of Taiwan's 2025 holiday-law amendment: Retrocession Day 10/25 restored as a holiday with a make-up day when it falls on a weekend; 10/25/2026 is a Sunday → observed Mon 10/26) | This reconciles the context's "reopens Monday 10/27" confusion: 10/27 is a Tuesday. If correct, there is **no TWSE/TSMC cash read Sunday night** after Friday's typhoon closure; the first Taiwan print is Monday night ET (Tue 10/27 09:00 Taipei = 9:00 PM ET Mon). TSM ADR and TSMC-linked US names carry two days of pent-up Taiwan information on Monday. Confirm on the TWSE 2026 holiday schedule before relying on it. |

## 2. Day-by-day map

Times are the standard release times for each series; the **dates** in 10/26–10/30 are UNVERIFIED unless marked otherwise. Consensus: NOT FOUND for every release.

### Monday 10/26
| Time ET | Event | Status |
|---|---|---|
| Sun 6:00 PM | US futures reopen | UNVERIFIED (rule) |
| Sun 8:00 PM | KOSPI/KRX and TSE open (09:00 KST/JST; no DST in Asia, 13h ahead of EDT). KRX close 2:30 AM ET. First Korea foreign-flow print of the week. | UNVERIFIED (rule) |
| Sun 9:00 PM | TWSE would open — likely closed for holiday (see §1) | UNVERIFIED |
| 4:00 AM | Europe cash open (shifted, see §1) | UNVERIFIED |
| 10:00 AM | New home sales (Sept) — Census usually prints ~24th–27th; Monday 10/26 is plausible | UNVERIFIED (date) |
| 10:30 AM | Dallas Fed manufacturing (Oct) — standard last-Monday slot | UNVERIFIED |
| Morning, unscheduled (~10:30–11:30 typical Bloomberg timing) | Goldman Prime weekly (week to Fri 10/23): gross/net leverage, tech net flow, short-sale ratio. The single most important de-grossing datapoint of the day. | CONTEXT (Goldman weekly lands Monday); timing UNVERIFIED |
| 12:30 PM | Europe close (shifted) | UNVERIFIED |
| 1:00 PM | 2-year note auction (standard Monday slot); result ~1:01–1:03 PM | UNVERIFIED (date/size: last widely reported size $69B in 2025; 2026 size NOT FOUND) |
| 3:50–4:00 PM | MOC imbalance | rule |
| After close | NXPI (NXP typically reports the last Monday of October AMC) | UNVERIFIED (2026 date NOT FOUND) |
| All day | Fed blackout — no Fed speakers | CONTEXT (blackout in force Friday); end date see §5 |

### Tuesday 10/27
| Time ET | Event | Status |
|---|---|---|
| Mon 9:00 PM | TWSE reopens (if §1 holds) — first Taiwan cash session since Thursday 10/22; TSMC, Hon Hai, MediaTek, Taiwan semis | UNVERIFIED |
| 8:30 AM | Durable goods (Sept advance) — often lands Tue/Wed of GDP week; may instead be Wed 10/28 | UNVERIFIED |
| 8:30 AM | Advance goods trade balance / wholesale inventories (Sept) — Tue or Wed | UNVERIFIED |
| 9:00 AM | Case-Shiller (Aug) | UNVERIFIED |
| 10:00 AM | Conference Board consumer confidence (Oct) — last Tuesday of month | UNVERIFIED |
| 10:00 AM | Richmond Fed manufacturing (Oct) — fourth Tuesday | UNVERIFIED |
| 1:00 PM | 5-year note auction (standard Tuesday slot; last reported size $70B in 2025; 2026 NOT FOUND) | UNVERIFIED |
| All day | FOMC day 1 (two-day meeting 10/27–28) | CONTEXT (FOMC 10/28) + rule |
| Before open (typical) | UPS, PYPL, SOFI, CORNING, SHW-type names | UNVERIFIED |
| After close (typical) | V, BKNG, **STX** (Seagate reported Tue AMC in late Oct 2025), **TER** (late-Oct Tue/Wed AMC in prior years), QRVO, ENPH, FFIV, MDLZ | UNVERIFIED (2026 dates NOT FOUND) |

### Wednesday 10/28 — FOMC + MSFT/GOOGL
| Time ET | Event | Status |
|---|---|---|
| 8:30 AM | Possible durable goods / goods trade if not Tuesday | UNVERIFIED |
| 10:00 AM | Pending home sales (Sept) — Wed or Thu | UNVERIFIED |
| 11:30 AM | 2-year FRN auction (standard Wednesday slot; last reported size ~$28B reopening; 2026 NOT FOUND) | UNVERIFIED |
| 1:00 PM | Some years Treasury moves the 7-year here when month-end is Friday; otherwise Thursday | UNVERIFIED |
| **2:00 PM** | **FOMC statement.** No SEP/dot plot at October meetings. | CONTEXT (date) + rule (time) |
| **2:30 PM** | **Powell press conference** (~45–60 min) | rule, UNVERIFIED |
| Current target range | NOT FOUND — do not assume; confirm on federalreserve.gov | NOT FOUND |
| CME FedWatch odds (Oct, Dec) as of Fri 10/23 close | NOT FOUND | NOT FOUND |
| What the press expects | NOT FOUND | NOT FOUND |
| **After close** | **MSFT FY27 Q1** — date VERIFIED on microsoft.com (page text: "Wednesday, October 28, 2026"; no time shown; MSFT historically releases ~4:05 PM, call 5:30 PM — time UNVERIFIED) | **VERIFIED** (date) |
| After close | **GOOGL Q3** | CONTEXT (date); time UNVERIFIED |
| After close (typical) | **META** (reported alongside MSFT/GOOGL on the same Wednesday in 2024 and 2025), **NOW** (Wed AMC in 2025), **KLAC** (Wed AMC in 2025), **HOOD** (Wed AMC in Oct 2024; was Nov 5 in 2025 — 2026 unknown), WDC, SBUX, CMG, ALGN, ETSY; BA/CAT/ADP before open | UNVERIFIED (2026 dates NOT FOUND) |
| Implied moves | NOT FOUND for all names | NOT FOUND |

### Thursday 10/29 — GDP/PCE, ECB, AMZN/INTC/AAPL
| Time ET | Event | Status |
|---|---|---|
| Wed ~10:30–11:30 PM | BoJ decision window begins (meeting 10/29–30; decision usually released Fri 10/30 ~11:30–12:30 JST = Thu 10:30–11:30 PM ET) — see Friday row | UNVERIFIED |
| 6:00 AM | Possible German/Spanish/Italian CPI or EZ data (11:00 CET = 6:00 AM ET this week) | UNVERIFIED |
| **8:30 AM** | **Q3 GDP advance** (incl. Q3 core PCE) | CONTEXT (10/29) + rule (time) |
| **8:30 AM** | **September PCE / personal income & outlays** — context puts it on 10/29 with GDP; BEA has sometimes put it the following day. Confirm on bea.gov/news/schedule. | CONTEXT (10/29), flagged |
| 8:30 AM | Initial jobless claims (week to 10/24) | rule |
| **9:15 AM** | **ECB decision** (14:15 CET; shifted hour, see §1). Date UNVERIFIED (my recollection of the ECB 2026 calendar has the October meeting on 10/28–29; confirm). Expectations: NOT FOUND. | UNVERIFIED |
| 9:45 AM | Lagarde press conference (14:45 CET) | UNVERIFIED |
| 10:00 AM | Pending home sales if not Wednesday | UNVERIFIED |
| 1:00 PM | 7-year note auction (standard Thursday slot; last reported size $44B in 2025; 2026 NOT FOUND) | UNVERIFIED |
| Before open (typical) | MA, MRK, LLY, CMCSA, RBLX | UNVERIFIED |
| **After close** | **AMZN Q3**, **INTC Q3** | CONTEXT (dates); times UNVERIFIED |
| After close (typical) | **AAPL FQ4** — Apple reports the last Thursday of October (Oct 30, 2025; Oct 31, 2024); 2026 date NOT FOUND, 10/29 is the pattern. COIN, RDDT, TEAM, FSLR, CVNA, TWLO also Thursday AMC in 2025. **SNDK**: Sandisk reported its FQ1 on Nov 6 in 2025; a 10/29 date is unconfirmed — NOT FOUND. | UNVERIFIED |
| Midnight | Fed blackout ends (see §5) | UNVERIFIED (rule) |

### Friday 10/30 — BoJ, month-end, EOM expiry
| Time ET | Event | Status |
|---|---|---|
| Thu ~10:30–11:30 PM | **BoJ decision + Outlook Report** (October is an Outlook meeting). Expectations: NOT FOUND. USDJPY the transmission channel. | CONTEXT (BoJ 10/30) + rule |
| 2:30 AM | Ueda press conference (15:30 JST) | UNVERIFIED (rule) |
| Before Korea open (~Thu 7:00–8:00 PM ET) | **Samsung Electronics final Q3** — Samsung's final Q3 release has landed 10/30–10/31 in prior years; 2026 date NOT FOUND. **SK hynix Q3** — 2026 date NOT FOUND (late-October pattern; it may already have reported). | UNVERIFIED |
| 6:00 AM | Eurozone October flash HICP and Q3 GDP flash (11:00 CET) — typical last-business-day slot | UNVERIFIED |
| 8:30 AM | **Employment Cost Index Q3** — BLS pattern is the last Thu/Fri of Oct | UNVERIFIED |
| 8:30 AM | PCE if BEA splits it from GDP (see Thursday) | UNVERIFIED |
| 9:45 AM | Chicago PMI (Oct) — last business day | UNVERIFIED (rule) |
| Before open (typical) | XOM, CVX, ABBV, CL | UNVERIFIED |
| Fed speakers | First post-blackout Fed speak possible from Friday | UNVERIFIED (rule) |
| 4:00 PM | **Month-end close**: pension rebalance, SPX EOM expiry, QQQ 10/30 expiry (see §4) | CONTEXT + rule |

### Just beyond the window
| Date | Event | Status |
|---|---|---|
| Sun 11/1 | US DST ends; clocks realign with Europe. Possible OPEC+ eight-country monthly call (they met on the first Sunday of the month through 2025; 2026 pattern NOT FOUND) | UNVERIFIED |
| Mon 11/2 | Treasury quarterly borrowing estimate 3:00 PM (pattern); ISM manufacturing 10:00 AM | UNVERIFIED |
| **Tue 11/3** | **US midterm elections** (first Tuesday after the first Monday in November) | calendar arithmetic, high confidence |
| Wed 11/4 | Quarterly refunding announcement 8:30 AM (pattern); ADP | UNVERIFIED |
| AMD Q3 | Prior pattern: Tue Oct 29 (2024), Tue Nov 4 (2025) → likely Tue 11/3 or Wed 11/4, 2026; NOT FOUND | UNVERIFIED |
| NVDA Q3 FY27 | Prior pattern: Wed Nov 20 (2024), Wed Nov 19 (2025) → likely ~Wed 11/18/2026; NOT FOUND | UNVERIFIED |
| TSMC October monthly sales | Released ~10th of following month (≈Tue 11/10); **no TSMC monthly sales print falls in 10/26–10/30**; the September figure came out ~10/10 and the Q3 call was mid-October | UNVERIFIED (rule) |

## 3. FOMC detail block (10/28)
- Meeting: Tue–Wed 10/27–28 (CONTEXT). Statement 2:00 PM, presser 2:30 PM (rule). No dot plot in October (rule).
- Target range going in: NOT FOUND. FedWatch Oct/Dec odds at Friday's close: NOT FOUND. Press framing: NOT FOUND. The only rates context I hold is CONTEXT: the 10-year fell below 5% on 10/22 while VIX sat ~19 in contango and HYG was flat — a rates-rally-on-growth-fear tape, not a credit event.
- Fed blackout ends: Fed policy runs the blackout from the second Saturday before the meeting through the Thursday after it → ends **Thu 10/29 midnight**; speakers may return Fri 10/30 (UNVERIFIED rule).

## 4. Options expiration and flow structure
| Item | Status | Detail |
|---|---|---|
| Fri 10/30 SPX | rule, UNVERIFIED | Weekly (SPXW PM) and end-of-month expiry coincide; standard monthly was 10/16. Daily SPX expiries every day of the week. |
| Fri 10/30 QQQ | CONTEXT + rule | QQQ has Mon–Fri weekly expiries; the context flags a reported large QQQ 10/30 700 put position. **I could not verify size, open interest, or the holder, and I do not have Friday's QQQ close to say how far 700 is from spot.** If spot is within a few percent of 700 into Thursday night (AMZN/AAPL/INTC) the strike's dealer gamma dominates Friday; check OI Sunday night. |
| Other weeklies | rule | Mon 10/26, Wed 10/28 and Fri 10/30 QQQ/SPY/IWM weeklies; single-stock weeklies Fri 10/30 wrap MSFT/GOOGL/META/AMZN/AAPL. |
| Index rebalance | UNVERIFIED | Nothing scheduled: S&P quarterly was 9/18 (next 12/18), Nasdaq-100 annual is December, MSCI November review announces ~11/10 effective 11/30, Russell's new November semi-annual reconstitution date NOT FOUND. Month-end index share-count changes effective at the 10/30 close are routine. |
| Month-end pension rebalance | UNVERIFIED | Direction depends on October equity vs bond performance. With the 10-year rallying and tech/semis down hard month-to-date (CONTEXT), the mechanical US pension flow would be **equity buying / bond selling at the 10/30 close**, concentrated in the last 30 minutes. No Goldman/UBS/Wells dollar estimate found. September-30 S&P level not available to me, so I cannot size the month's drawdown. |
| Buyback window | UNVERIFIED (rule) | Most issuers reopen 1–2 trading days after reporting; MSFT/GOOGL/META windows reopen ~Fri 10/30, AMZN/AAPL ~Mon 11/2. Semis that reported mid-October (TSMC, LRCX, TXN-type) are already open. Roughly half of S&P market cap is still in blackout entering the week and most is out by ~11/6 (Goldman buyback-desk pattern, not a 2026 figure). |

## 5. Positioning context carried into Monday (CONTEXT, snippet-level, from the 10/22 research)
- Goldman Prime via Bloomberg 10/19 and 10/22: record tech net selling in the five sessions to 10/15; net leverage at a one-year low; tech still 90th percentile of the net book; month-to-date short sales ~5x long buys; short leverage at the 99th percentile of five years.
- JPMorgan 10/21: funds had "largely unwound" semis longs.
- Korea: foreign net selling of KOSPI ~1T won/day early October → 113B won on 10/22 → ~145B won by 10:00 KST Friday 10/23; KOSPI Friday opened −2.4%, hit −4.1%, recovered to −1.75% by 10:00 KST.
- SOX: eight straight down sessions to 10/16, bounce 10/19–21, −6.7% Thu 10/22 to 10,732 with all 30 members down while the average stock rose. Nasdaq Composite 26,009; S&P 500 7,663; VIX ~19 in contango; 10Y <5%; HYG flat.
- Friday 10/23 US close: NOT AVAILABLE to me (the context ends Friday morning Seoul time).

## 6. Geopolitics / oil (scheduled items)
- Iran, Houthi, Hormuz: nothing scheduled could be found; NOT FOUND.
- OPEC/OPEC+: no meeting found inside 10/26–10/30; the eight-country group's first-Sunday cadence would put a call on Sun 11/1 if the 2025 pattern persisted — UNVERIFIED.

## 7. Monday-specific hard windows for a same-day single-leg desk (ET)
| Window | Why | Status |
|---|---|---|
| Sun 8:00 PM – Mon 2:30 AM | Korea session; the foreign net-flow tape (KRX) is the first "slowing or resuming" tell. Japan semis (Advantest, Tokyo Electron, Disco, Lasertec) trade alongside. No Taiwan print if §1 holds. | UNVERIFIED timing |
| 4:00 AM | Europe open (shifted one hour later this week) | UNVERIFIED |
| 9:30–9:45 AM | Opening auction and first relative-volume surges; with 99th-percentile short leverage, Monday open-drive squeezes are the asymmetric risk for put entries | rule |
| 10:00–10:05 AM | New home sales (rates print; low direct tech relevance but moves 10Y) — if the date is confirmed | UNVERIFIED |
| 10:30 AM | Dallas Fed | UNVERIFIED |
| ~10:30–11:30 AM, unscheduled | Goldman Prime weekly headlines via Bloomberg: a sharp gap risk in semis/tech sentiment either way | CONTEXT/UNVERIFIED |
| 12:30 PM | Europe close (shifted from 11:30) — program-flow pulse | UNVERIFIED |
| 1:00–1:05 PM | 2-year auction result (tail/stop-through drives front-end and NQ/ES relative) | UNVERIFIED date |
| 3:50–4:00 PM | MOC imbalance; not month-end, but first session after a −6.7% SOX day plus a Friday the desk did not capture | rule |
| 4:00–4:15 PM | NXPI (if Monday) — auto/industrial semis read-through for Tuesday | UNVERIFIED |

## 8. What to read on Monday as "de-grossing slowing vs resuming" (UNVERIFIED framework, tied to the map)
1. KRX foreign net flow for Monday (sign and size vs the 113B/145B won prints) and KOSPI close.
2. Goldman Prime weekly: did gross leverage fall again, did tech net selling persist in the week to 10/23, did the short-sale/long-buy ratio normalise from ~5x.
3. Pre-open SOX proxies: TSM ADR vs its last Taiwan-close implied level (two days of catch-up), Japan semis' closes.
4. NQ/ES ratio and RSP−SPY at 9:30: Thursday's pattern (all 30 SOX names down while the average stock rose) was the de-grossing signature; its reversal is the first "slowing" sign.
5. 2-year auction and the 10Y around 5%: a strong bid with equities stable would say the rotation is orderly.
6. VIX curve: contango persisting with VIX ~19 argues against forced liquidation; a flip toward backwardation says resuming.
7. HYG/credit OAS: still flat = positioning event, not credit event.

## 9. Items explicitly NOT FOUND in this run
Consensus for every release; 2026 auction sizes and exact auction days; FOMC target range and FedWatch odds; ECB and BoJ expectations and the ECB 2026 date; every 2026 earnings date except MSFT; implied moves; SK hynix and Samsung Q3 dates; TWSE holiday confirmation; QQQ 700 put details and QQQ spot; pension-rebalance estimates; buyback-window percentages; Russell November reconstitution date; OPEC+ 2026 meeting dates; any Iran/Houthi/Hormuz schedule; Friday 10/23 US closes.

## 10. Sunday-night verification checklist (priority order; all were blocked for me)
1. twse.com.tw — 2026 holiday schedule / typhoon-closure notice (Mon 10/26 closed?).
2. federalreserve.gov/monetarypolicy/fomccalendars.htm — meeting dates, current target range; cmegroup.com FedWatch.
3. treasurydirect.gov/auctions/upcoming — 2y/5y/7y/FRN days and sizes.
4. bea.gov/news/schedule — GDP vs PCE day; bls.gov ECI date; census.gov calendar for new home sales and durable goods; conference-board.org.
5. ecb.europa.eu meeting calendar; boj.or.jp MPM schedule.
6. IR pages: abc.xyz, ir.aboutamazon.com, intc.com, investor.apple.com, investor.fb.com, servicenow.com, ir.kla.com, investors.teradyne.com, investors.seagate.com, investors.robinhood.com, investors.nxp.com, investors.sandisk.com, skhynix.com, samsung.com/global/ir.
7. QQQ 10/30 open interest at 700; SPX EOM OI.
8. Goldman/UBS/Wells month-end pension estimates (usually out Thu–Fri before month-end).

## Sources
- VERIFIED: Microsoft Investor Relations, FY27 Q1 earnings event page, https://www.microsoft.com/en-us/investor/events/fy-2027/earnings-fy-2027-q1 — page text "Wednesday, October 28, 2026" (fetched 2026-10-24; no time shown).
- CONTEXT (relayed by the workflow from 10/22 snippet research; URLs not provided to me): Bloomberg on Goldman Prime (10/19, 10/22); JPMorgan note (10/21); Korea foreign-flow and KOSPI figures (10/22–10/23); SOX/Nasdaq/S&P/VIX/10Y/HYG levels for 10/22; FOMC 10/28, MSFT/GOOGL 10/28, GDP/PCE 10/29, AMZN/INTC 10/29, BoJ 10/30, month-end 10/30, 2y/5y/7y auctions, Goldman weekly Monday, Taiwan typhoon closure 10/23.
- Blocked (DNS ENOTFOUND or proxy 403, 2026-10-24): all hosts listed in §0 and §10.
- All search-engine queries: not executed (per-turn WebSearch budget exhausted before the first call).