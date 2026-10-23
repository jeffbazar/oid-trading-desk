# Hedge-fund de-grossing, 2026-10-14 → 2026-10-22: what has been published, and what an intraday desk can actually watch

## 0. Access and labelling caveats (read first)

- WebFetch failed with DNS errors on every domain tried (Yahoo, Bloomberg-syndicated FA-mag, Investing.com, CNBC, Tickmill, Seeking Alpha, Hedgeweek, FRED) and `curl` through the sandbox proxy returned `CONNECT tunnel failed, response 403`. I therefore could not open a single primary page. **Every factual claim below is EXTRACT** (seen in search-engine snippets/summaries of the named article), with a quality tag: *EXTRACT/wire* = Bloomberg, Reuters, CNBC, FT-equivalent syndication; *EXTRACT/aggregator* = BigGo, KuCoin, futunn, alpha-maven, Tickmill, Substacks. Nothing is VERIFIED. **UNVERIFIED** = my inference or a rule of thumb.
- **Date reconciliation.** The harness framed this as "before the open on Thu 2026-10-22". The web index already contains closing reports for the 2026-10-22 session (Nasdaq Composite −2.60% to 26,008.86, which chains exactly from the Oct 21 close of 26,702.86). So either the harness clock was stale or the index is ahead; I report both the Oct 22 pre-market and the Oct 22 close, and the framework applies equally to the next session.
- No prime-broker note gives an "X% done" or "typically lasts N days" figure. I say so explicitly in §4.

---

## 1. Session-by-session tape (for context)

| Date | What happened | Source quality |
|---|---|---|
| Wed Oct 14 | Hotter-than-expected CPI pushed back Fed-cut odds; chips hit hardest. 10Y ~5.10–5.12% mid-Oct. Goldman desk: this was the heaviest de-grossing day of the week (Oct 15 was "roughly half" of it). | EXTRACT/wire (Reuters via Yahoo/USNews; CNBC) |
| Thu Oct 15 | KOSPI −7.57% (intraday circuit breaker), Taiwan −3%+. Goldman: all three broad strategies (fundamental L/S, systematic L/S, multi-strat) fell >80 bp on the same day, which "never" happened COVID→end-2025 and has now happened 3x in 2026 (Feb 4, Jul 28, Oct 15). CoreWeave 5y CDS >1,140 bp. | EXTRACT/wire (Reuters Oct 16; CNBC Oct 15) |
| Fri Oct 16 | SOX −3.8%, 8th straight loss (−15.7% over the streak; longest since Oct 2008 or 2006 depending on outlet). Week: NDX −5.5% (worst since Apr 2025), Nasdaq Comp −4.5%, SOX −11.4%. VIX closed ~20 (19.99), intraday high 22.31; VXN 27.1. Fri SPX/XSP option volumes 4th/5th highest on record. October OPEX (~$1T notional). Goldman's Laicini: "broader deleveraging", both sides of book cut; Asia epicentre. | EXTRACT/wire + aggregator |
| Mon Oct 19 | Nasdaq +1.11% to 26,430.89; SPX +0.41% 7,690.73; SOX snapped streak (SMH/SOXX +3%). Equal-weight and most stocks fell: "relief bounce, not broad recovery". Goldman Oct-19 note hit the tape (see §2). Wilson "prepare to buy" note. 10Y back above 5.1%. | EXTRACT/wire (TheStreet, USNews, CNBC) |
| Tue Oct 20 | Dow +1.02% 52,495.88; SPX +0.28% 7,712.57; Nasdaq −0.02% 26,424.82; SOX −0.29% 11,283.81; VIX 17.31. Brent ~$110–112, WTI >$110 at six-month peaks before easing. Griffin "almost certainly a bubble" remarks at Citadel conference. | EXTRACT/wire |
| Wed Oct 21 | Nasdaq +1.05% 26,702.86; SPX +0.58% 7,757.17; SOX +1.97% (SpaceX AI results). Breadth narrow: NYSE adv/dec only 1.37:1; Nasdaq 216 new lows vs 53 new highs on an up day. JPM Panigirtzoglou "selling nearing its limit" note published. Meta and Tesla report after close. | EXTRACT/wire + Substack |
| Thu Oct 22 pre-mkt | Asia: KOSPI −3.52% to 5,533.78 (41% below its 52-wk high of 9,385.6), Nikkei −2.65%; BoK held at 3%; Brent back >$110 after Houthi attacks on Saudi facilities. 7:50 ET: ES −1.0%, NQ −1.7%; TSLA −4.9%, LRCX −8.4%, AMD −4.2%, MU −3.3%, NVDA −2.2% pre-market. | EXTRACT/wire (Yahoo/Stocktwits, Benzinga, Invezz, AJU) |
| Thu Oct 22 close | Nasdaq −2.60% to 26,008.86 (worst since Jun 5), SPX −1.21% to 7,663.43 (worst since July), Dow +0.02% 52,867.98. **SOX −6.72% to 10,731.98**, worst day since Jun 23, lowest close since Jul 29, all 30 members down, broke the ~11,000 support that held twice since Sept. LRCX −11.76%, MRVL −8.7%, AMD −8.1%, MU ~−6%, NVDA −4.4%, META −6.98% to 648.85 (negative FCF −$2.12B, capex $135–145B, new non-voting share class, Meta 5y CDS at all-time highs). Huang on CNBC: neocloud demand "off the charts" but capital "scarce". VIX close ~19.03 (+14%), intraday high 20.30 (< Oct 16's 22.31). 10Y fell below 5% for first time since Sep 23. NYSE adv/dec 1.01:1; Nasdaq dec/adv 1.37:1; rotation into staples/utilities/health care ("average stock rose"). Yahoo chip basket: >$3T lost since Oct 6, >$900B of it on Oct 22. | EXTRACT/wire (Reuters via Yahoo/TradingView, CNBC, Bloomberg live blog, SBS) |

---

## 2. Prime-broker and positioning-desk publications, by house

### 2a. Goldman Sachs Prime Services (the dominant data source this episode)

| Pub date | Vehicle | Measure | Reported value | Quality |
|---|---|---|---|---|
| Oct 16 | GS Prime daily, via Reuters ("Global hedge funds hammered by AI selloff…") | Fundamental L/S performance | Lost money **every day** of week to Oct 15; **−2.9%** for the week; +14.3% YTD | EXTRACT/wire |
| Oct 16 | same | Multi-strat & systematic L/S, Oct 15 | **~−1%** each; fundamental −0.9% same day | EXTRACT/wire |
| Oct 16 | same | Correlated-strategy event | All three >80 bp down same day: 3x in 2026 (Feb 4, Jul 28, Oct 15), never COVID→2025 | EXTRACT/wire |
| Oct 16 | same | Asia fundamental L/S | −2.6% on Oct 15; **−6.8% MTD (1H Oct)**; YTD cut to 16.7% from >40% at late-June peak | EXTRACT/wire |
| Oct 16 | same | Tech-focused funds Oct 15 | −2.0% | EXTRACT/aggregator |
| Oct 16 | same | **Pace of de-grossing** | "Yesterday's [Oct 15] global de-grossing activity, long selling and short covering combined, was roughly half of what was seen on Wednesday [Oct 14]" | EXTRACT/wire (Reuters quote) |
| Oct 16/19 | GS Prime (Marco Laicini) via aggregators | Character of Oct 16 selling | "Broader deleveraging": managers cut both sides; Asia epicentre; Korea/Taiwan AI longs unwound; Taiwan positioning 99th pct 5y; Taiwan ~$9.3B single-day foreign outflow | EXTRACT/aggregator |
| Oct 16/19 | same | Gross leverage, whole prime book | **310.3%** (−0.4 pp), near 5-yr highs | EXTRACT/aggregator (single source) |
| Oct 16/19 | same | AI net allocation | **26.1%** vs 31.7% peak early June; "middling over 1y, still high over 3y; room for further deleveraging" | EXTRACT/aggregator |
| Oct 16/19 | same | Risk-model remark | Three "once-in-five-years" events in 10 months → VaR models "systematically underestimate extreme risk" | EXTRACT/aggregator |
| ~Oct 15–16 | GS Prime (Vincent Lin) via GuruFocus/KuCoin | Global AI basket (~100 semis/DC/cloud/power names) | Net sold **5 consecutive sessions Oct 8–14** (one outlet says 6), **fully reversing all cumulative net buying since start of 2025**; 2nd-largest/fastest in a year behind July; **long:short selling ≈ 3.5:1** (long liquidation dominated); proceeds rotated to health care/staples | EXTRACT/aggregator |
| Oct 19 | GS Prime weekly, via Bloomberg "Hedge Funds Cut Tech at Fastest Pace in a Decade" | Tech net selling, 5 sessions to Oct 15 | **Largest proportional cut since records began 2016**; semis & semi-equipment = **57% of US tech net selling**; global equities net sold at **−2.0 SD** vs past year (Tickmill) — one write-up says "3.3 SD below normal over two weeks" (conflict, unresolved) | EXTRACT/wire + aggregator |
| Oct 19 | same (Tickmill repost "Tech Liquidation & Retail ETF Chase") | Long vs short | **Long sales : short sales ≈ 2.6:1** → long liquidation, not new shorting, drove the week | EXTRACT/aggregator |
| Oct 19 | same | Net leverage, global fundamental L/S | **48.6%**, −4.2 pp, 1-yr low; overall prime-book net leverage 72.7% | EXTRACT/wire |
| Oct 19 | same | Tech net allocation | **23.5% of global prime book, 90th pct of 5y** → "room for further selling" | EXTRACT/wire |
| Oct 19 | same | Interpretation | "Tactical portfolio adjustments rather than a full exit"; many kept core AI conviction | EXTRACT/wire |
| Oct 19/20 | GS "What Matters Today" (Lee Coppersmith) via futunn | Driver of net-leverage decline since late July | "Almost entirely due to increased short positions, not reduced longs" (longer window than the Oct 9–15 week; not a contradiction) | EXTRACT/aggregator |
| Oct 19/20 | same | US fundamental L/S net leverage | ~2nd percentile of 5y; one outlet says US net leverage 43.7% as of Oct 18 | EXTRACT/aggregator (single sources) |
| Oct 19 | GS via CNBC live blog | Sector | IT "by far the most net sold global sector last week"; largest % de-grossing in two months; largest % net selling on record since 2016 | EXTRACT/wire |
| Oct 19 | GS flows/CTA model via Tickmill (attribution ambiguous with Nomura, see §2e) | Global CTA equity length | ~$43.5B, from $125B a month earlier and $67B the prior week | EXTRACT/aggregator |
| ~Oct 16–19 | Tony Pasquariello (GS) via Seeking Alpha/TipRanks | Positioning | "A round of risk reduction across global equity and credit markets"; AI exposure at its lowest of the year in October; turbulence through end-October then year-end rally to new highs | EXTRACT/wire-ish |
| Oct 19 | GS credit (Amanda Lynam) via Yahoo/Axios | AI-related USD HY spreads | +25 bp Oct 13→14 to **360 bp**, record; non-AI HY +2 bp; expects "some near-term reversal" but high dispersion | EXTRACT/wire |
| **Oct 22** | **GS Prime via Bloomberg "Hedge Funds Pile Into Shorts as Goldman Flags Stock Squeeze Risk"** | Short sales vs long buys, global equities, MTD | **~5:1**; short leverage **99th pct of 5y**; desk labelled it "short squeeze risk alert?" (with the question mark) | EXTRACT/wire (FA-mag syndication) |
| Oct 22 | same | Performance to Mon Oct 19 | Global fundamental L/S **−2.5% MTD** (YTD 10.1%); **TMT funds −7.4% MTD** | EXTRACT/wire |
| Oct 22 | same | IT net selling, two weeks to Oct 16 | Heaviest two-week net selling in >decade of records | EXTRACT/wire |
| Oct 22 | same | Net vs gross | Fundamental L/S net leverage near 3-yr low **while gross rises** (bigger books both sides, tilted short) | EXTRACT/wire |
| Oct 22 | same, via futunn | AI basket | Net allocation **38th pct (1y)**; sector **L/S ratio 6th pct**; Mag7 net exposure at record highs; "any catalyst that lifts tech will run headlong into short positions that need to be covered" | EXTRACT/aggregator |

Not found: any GS daily note covering flows on Oct 19, 20, 21 or 22; any GS "CTA Corner" estimate for the week of Oct 19 (older notes: $6–33B/week scenarios, SPX pivot 6,707 — stale with SPX at 7,663).

### 2b. JPMorgan

| Date | Item | Content | Quality |
|---|---|---|---|
| ~Oct 16–19 (relayed Oct 20) | JPM Positioning Intelligence (via Neo Reports Substack) | Global HF perf **−2.1% MTD**, equity L/S **−2.3%**; "multi-strat de-grossing close to the worst in two years even though net flows were not that negative" | EXTRACT/aggregator (single source) |
| Oct 15 | JPM note | AI infrastructure stocks "do not yet appear oversold" | EXTRACT/wire (Investing.com) |
| **Oct 21** (reported Oct 21–22) | Panigirtzoglou team, "AI stock selling may be nearing its limit as positioning resets" | HFs and CTAs "have largely unwound their elevated long semiconductor exposures"; overall equity-positioning gauge "dropped substantially from a mid-September peak"; semis ≈ **one-fifth of total risk capital in global equity markets** → vol-driven selling risk; HF equity P&L closely tracks semis; tight risk limits forced cuts; neocloud/financing fears "excessive" | EXTRACT/wire (Investing.com, investingLive, TokenPost) |
| Oct 22 | investingLive follow-up | The call "was immediately tested" by Oct 22's ~7% SOX drop; "the key signal is whether forced selling stops" | EXTRACT/wire-ish |
| Aug 4 | JPM (via Reuters/Kitco) | Context: July multi-strat −2.2%; July de-grossing "more pronounced than any year apart from 2020 and 2022" | EXTRACT/wire |

### 2c. Morgan Stanley

- **Oct 19, Mike Wilson** (Bloomberg/Investing.com): months-long pullback "nearing its end", "prepare to add risk"; two paths — "very rapid reconciliation" or "slower bleed into November", which is when to add; quality factor at 52-wk high (+~6% since mid-Aug) vs equal-weight S&P −~4%; rates/dollar/energy composite "tightest since 2022"; earnings-revision-breadth spread high-vs-low quality ~10%, 2nd widest since 2010. EXTRACT/wire.
- **MS Prime Brokerage / QDS October leverage or flow data: NOT FOUND.** Only a ~1-yr-old Reuters item (US HF gross leverage >2x, exceeded 1% of the time in 15 yrs) and CNBC Oct 21 on MS/GS/JPM taking ~80% of top-5 equities revenue on "insatiable" HF financing demand for AI hardware/Asian semis.

### 2d. Barclays, UBS, Deutsche Bank, BofA

| House | Date | Content | Quality |
|---|---|---|---|
| Barclays (via Neo Reports Oct 20) | ~Oct 16–19 | Long-only generalist PMs cut semis underweight to just over **−200 bp**, software ~neutral; HFs took equity exposure "back to long-run neutral"; vol-control exposure ~95% | EXTRACT/aggregator |
| Barclays (Pascale) via Reuters | Oct 1 | Typical 10%-vol-target fund ~88% equity; mild bear scenario → <40% → **>$100B** equity selling; vol-control AUM $300–500B industry-wide | EXTRACT/wire |
| Barclays via Bloomberg/Investing.com | ~Oct 20–21 | Barclays hit max financing limits for Asian HF clients over the summer; shifted balance sheet from rates to prime via internal auction; **Barclays and Goldman encouraged clients to add shorts to cut net financing needs**; GS said financing demand "continued to outstrip industry supply" | EXTRACT/wire |
| UBS | late Aug | Two-sigma move → ~5x more systematic selling on downside than buying on upside | EXTRACT/wire |
| UBS | Jan 2026 | CTAs entered 2026 risk-on, equity exposure near top of range | EXTRACT/wire |
| UBS Prime / October note | — | **NOT FOUND** | — |
| Deutsche Bank (via Reuters) | Oct 1 | Vol-control equity allocation **98th pct since 2010**; CTAs 82nd pct | EXTRACT/wire |
| Deutsche Bank (Thatte) | ~Oct 12 | Tech positioning still overweight near top of long-run trend; earlier notes: discretionary below neutral, systematic top-decile | EXTRACT/wire (dates only relative) |
| BofA Systematic Flows Monitor | Sep 25 | Down-market systematic selling **$84B** over coming week vs $4B buying up; CTAs "stretched long" equities, short USTs | EXTRACT/aggregator |
| BofA | Sep 11 / Aug 28 | $157B / $163B down-market estimates; fast trend models stopped out of SX5E and RTY | EXTRACT/aggregator |
| BofA October edition | — | **NOT FOUND** |  |

### 2e. Nomura (Charlie McElligott)

- **~Oct 13 ("BINARIES", via Tickmill):** global CTA equity length "modeled down to ~$43.5B (from $125B)"; US equity systematic positioning 86th pct; SPX 10-day realized vol 7.0; collapsing RV had forced vol-scalers (vol-control + CTA + risk parity) to mechanically buy back exposure. This is *pre-crash*; the same Tickmill figure is attributed by another snippet to a GS flows note, so attribution is ambiguous. EXTRACT/aggregator.
- **Oct 20 (Seeking Alpha):** "reverse dispersion" rally; momentum (MTUM) unwind "kicked off by perceived AI negative catalysts" (revenue trajectories, neocloud sustainability, financing costs); squeeze in crowded bond shorts; Iran-deal-progress headlines; rotation to value (VTV) and small caps (IWM). EXTRACT/wire-ish.
- **Oct 21 (paywalled Substack summary):** selling "driven primarily by the unwinding of crowded positions rather than a decisive shift toward a recessionary macro outlook". EXTRACT/aggregator.
- Mid-2026 rebalance model (date uncertain, not October): 4% SPX decline → ~$149.8B systematic selling; 5% → ~$191.5B; vs ~$24B buying on +5%; SMH 3m ATM vol at 100th pct. EXTRACT/aggregator.
- **No Oct 22 note found. No post-Oct-16 vol-control selling estimate found from any house.** Saxo's Oct 20 options brief had SPX 20-day realized vol at only 8.81% (VIX 18.44), i.e. the realized-vol input to vol-control models had barely moved as of Oct 20 ("SPX realized volatility measures barely budged" per a Vol Vibes Oct 19 note). UNVERIFIED inference: Oct 22's −1.2% SPX / −2.6% Nasdaq day will lift 10–20d realized vol and should produce modest vol-control selling over the following 1–5 sessions, but no house has published a number.

### 2f. Citadel, Millennium and pod-shop context

- **Ken Griffin, Oct 20, Citadel Future of Global Markets conference:** AI "almost certainly" a bubble; "any radical transformation of our economy is generally intertwined with a bubble"; not a sell call. Citadel bought Situational Awareness's public-equity book in late July after that fund faced margin calls, and had **shed >80% of that risk** per Griffin's August letter. Market reaction to remarks negligible (NVDA −0.29%). EXTRACT/wire.
- **Millennium / Point72 / Balyasny / Jain / ExodusPoint / Verition October figures: NOT FOUND.** October returns print ~Nov 10. Last hard data is July: Millennium −2.1%, Point72 flagship −3.3%, Turion (AI fund) −11.4%, Balyasny −1.5%, Situational Awareness −67%. EXTRACT/wire.
- **Pod drawdown mechanics** (blogs/explainers, not this episode): Millennium reportedly halves a pod's capital at ~5% drawdown and terminates at ~7.5%; Citadel/Point72 negotiate comparable per-PM limits. UNVERIFIED (secondary, approximate). JPM's Oct 21 note independently cites "tight risk limits" as the amplifier of chip losses (EXTRACT/wire).
- **IMF GFSR, Oct 13:** HF assets ~$13T (>3x 2013); leverage and crowded positions can trigger "synchronized deleveraging and asset sales" spilling into prime brokers; regulators have limited visibility. Dimon (Aug): industry leverage "the highest it's ever been". EXTRACT/wire.

### 2g. Other flow/positioning data points published this episode

- **S3 Partners via Bloomberg, Oct 16:** chip short sellers ~**$32B gross paper gains Oct 7–15**. EXTRACT/wire.
- **Leveraged ETFs, week to Oct 16:** ~$9.2–9.5B record inflow (sources differ); **SOXL $6.1–7B, record**; US-listed ETFs +$58B; "last week was a financing scare, not a demand scare" (WisdomTree). Korean retail piled into KODEX Leverage. EXTRACT/wire.
- **Options/vol (Cboe, SpotGamma, Saxo):** 1-month SPX 30-delta skew moved 15th → 82nd pct in the Oct 12–16 week; MAGS ~40k puts (2-yr high); 110k QQQ Oct-30 $700 puts (~$111M premium); SPX gamma flip ~7,700, negative-gamma below with 7,400 as a downside magnet, OPEX "mean-reverts ~2/3 of the time"; Oct 20: VIX 18.44, 1-day vol 11.93 (front-end hedges unwound), 1-yr vol 22.30 near top of 60-session range, SKEW 161.86 (tails did **not** cheapen), SPX implied ±1.21% into Oct 23; Oct 21: VIX 17.31, SKEW 160.40; FOMC Oct 28. EXTRACT/wire + vendor.
- **Credit:** ICE BofA HY OAS 3.33% on Oct 20 (+10 bp; from ~260 low); CCC spreads 4-yr highs; CoreWeave 5y CDS ~1,082 bp Oct 19 (peak >1,140 Oct 15); Oracle CDS 288 bp; iTraxx Crossover 329 bp (7-mo high); Meta 5y CDS record on Oct 22. EXTRACT/wire.

---

## 3. Long selling vs short covering, and the long/short ratio — reconciled

- Week of Oct 9–15 (GS): long liquidation dominated — long sales : short sales ≈ 2.6:1 overall, ≈ 3.5:1 in the AI basket. Oct 15 and Oct 16: Goldman explicitly counts "long selling and short covering combined" as de-grossing, and Oct 16 was "both sides of the book".
- Since late July (GS Coppersmith): net-leverage decline came "almost entirely" from added shorts; by Oct 22 MTD short sales ≈ 5x long buys, short leverage 99th pct, sector L/S ratio 6th pct. The two statements cover different windows and are consistent: the crash week was long dumping; the broader October profile is short-building on a book whose gross is still ~310%.
- Implication for a same-day options desk (UNVERIFIED): the market is now set up for violent two-sided days — crowded shorts (squeeze risk per GS) sitting beneath still-crowded tech longs (90th pct) with tight pod stop-losses. Oct 22 (−6.7% SOX on fresh catalysts) shows the long-liquidation leg can restart on any capex/financing headline; the Oct 19/21 rallies show the covering leg is also live.

---

## 4. "How far through is the de-grossing?" — every published statement

| Source | Statement | Direction |
|---|---|---|
| GS Oct 16 | Oct 15 de-grossing ≈ half of Oct 14 | slowing (as of Oct 15) |
| GS Oct 19 | Tech still 23.5% of book, 90th pct 5y → "room for further selling"; AI net alloc 26.1% vs 31.7% peak, "room for further deleveraging" | not done |
| GS Oct 19 | "Tactical adjustment, not full exit" | not a regime change |
| GS Oct 22 | Shorts 5:1, 99th pct; "short squeeze risk alert?"; AI basket 38th pct, L/S ratio 6th pct | de-grossed enough to be squeezable |
| JPM Oct 21 | HFs/CTAs "largely unwound" semis longs; positioning gauge down sharply from mid-Sep peak → "may constrain additional declines" | mostly done (tested next day) |
| Barclays ~Oct 19 | HF equity exposure "back to long-run neutral" | mostly done |
| MS Wilson Oct 19 | Pullback "nearing its end"; or bleeds into November | mostly done, timing open |
| GS Pasquariello ~Oct 16 | Turbulence "for the remainder of October" | not done until month-end |
| GS Lin ~Oct 16 | AI basket selling "second only to July" | precedent: July episode ran weeks, Feb and Jul episodes also produced >80 bp cross-strategy days |

**No source gives a percentage-complete, a typical duration, or a "levels back to date X" beyond: net leverage at 1-yr low (Oct 19) / near 3-yr low (Oct 22); AI net allocation back to early-2025 cumulative levels (all net buying since start-2025 reversed); tech allocation still at 90th pct.** UNVERIFIED rule of thumb from the 2026 precedents (Feb 4, Jul 28): the cross-strategy >80 bp day has marked the peak-intensity day of each episode, with aftershocks for 1–3 weeks; Oct 22 may be such an aftershock, but Goldman has not yet published whether Oct 22 was a de-grossing day.

---

## 5. Metrics that can show whether the de-grossing is slowing, by availability and cost

| Metric | What it tells you | Timing | Cost | Notes / this episode's readings |
|---|---|---|---|---|
| GS Prime daily/weekly flow notes (long sales vs short covering, SD of net selling, sector %, net/gross leverage, AI basket percentile) | The actual answer | Next-morning (daily) / Mon-Tue (weekly), **after** the fact | Prime-broker clients; leaks via Bloomberg/CNBC/Tickmill same day or next | Last leaked daily: Oct 16. No Oct 19–22 dailies seen. |
| JPM Positioning Intelligence, MS QDS/Prime, UBS Prime, BofA Systematic Flows Monitor, Nomura McElligott | Second opinions; systematic $ estimates | Weekly / ad hoc, after close | Client-only; partial leaks | BofA/UBS/MS October editions not found publicly |
| HF performance by strategy (GS, JPM) | Whether pods are near limits | Next morning, after close | Client / leaks | L/S −2.5% MTD, TMT −7.4% MTD to Oct 19; Asia −6.8% 1H Oct |
| CTA / vol-control model levels (SPX, NQ trend thresholds; realized-vol windows) | Mechanical selling ahead | Published weekly, inputs real-time | GS/Nomura/BofA/DB models paid; realized vol is free to compute | Vol-control AUM 98th pct allocation (Oct 1); 20d RV 8.81% on Oct 20 (benign); Oct 22 will lift it |
| FINRA short interest | Confirms short build | Bi-monthly, ~8 trading days lag | Free | Mid-Oct settlement data lands ~Oct 24–27 (UNVERIFIED timing) |
| S3 Partners / Ortex daily short-interest estimates, borrow rates, utilization | Real-time proxy for short covering vs new shorting | Daily, intraday updates | Paid | S3: $32B chip-short gains Oct 7–15 |
| Cboe: VIX, VXN, VVIX, SKEW, 1-day vol, term-structure inversion, equity vs index put/call | Hedging demand vs capitulation | **Real-time** | Free (delayed) / paid (live) | Oct 16: VIX 22.31 high, inverted; Oct 20: front end drained, SKEW 161.86 held; Oct 22: VIX high 20.30 < Oct 16 high (lower high on a worse SOX day) |
| SpotGamma-style dealer gamma (SPX/QQQ/SMH gamma flip, 0DTE flows, charm) | Whether dealer hedging amplifies or dampens intraday moves | Daily, real-time updates | Paid | SPX flip ~7,700; SPX closed 7,663 on Oct 22 → negative-gamma regime per their framework |
| Breadth internals: RSP−SPY, NYSE and Nasdaq adv/dec, new highs/lows, equal-weight semis vs SOX | Whether selling is index/factor-driven (de-grossing) or broad | **Real-time** | Free | Oct 19 & 21 up-days had negative breadth (de-grossing covering, not buying); Oct 22 NYSE flat breadth, Nasdaq 1.37:1 down → tech-specific |
| Factor/basket proxies: MTUM vs SPY, GS Hedge Fund VIP (GVIP) vs GS most-shorted basket, VTV/VUG, IWM/QQQ | Whether crowded longs are still being hit and shorts squeezed | Real-time | Free via ETFs; GS baskets paid | McElligott "reverse dispersion" Oct 20 = MTUM unwind, value/IWM bid |
| Leveraged ETF flows (SOXL, TQQQ creations) | Retail dip-buying absorbing HF supply | Next day | Free (ETF.com, issuer) | Record $6–7B into SOXL week to Oct 16 |
| Semis vs NDX vs SPX relative strength; SOX 11,000 / 10,732 levels | Where the forced selling is | Real-time | Free | SOX broke 11,000 on Oct 22 |
| Credit: HY/IG OAS (FRED, T+1), HYG/JNK (real-time), AI-issuer CDS (CoreWeave, Oracle, Meta), iTraxx Crossover | Whether "financing scare" is spreading beyond AI issuers | HYG real-time; OAS daily lag; CDS via Bloomberg | Mostly paid for CDS | HY OAS 333 bp Oct 20; CoreWeave >1,000 bp; Meta CDS record Oct 22 |
| Asia overnight (KOSPI, TWSE, SK Hynix/Samsung, foreign net flows) | Leading indicator since Asia was the epicentre of Oct 15–16 de-grossing | Before US open | Free | KOSPI −3.52% Oct 22 led the US session |
| Prime-broker financing tightness (Barclays/GS cap stories) | Structural ceiling on gross → forced de-grossing on losses | Ad hoc news | Free | Banks pushing clients to add shorts (Bloomberg ~Oct 20) |

---

## 6. Is there genuine same-day predictive edge? (UNVERIFIED assessment)

1. **Nothing published is real-time.** The prime-broker data that answers "is de-grossing slowing" arrives the next morning at the earliest and leaks to the public 1–3 days later. The only Goldman "slowing" datapoint in this episode (Oct 15 ≈ half of Oct 14) was public on Oct 16, i.e. after the move it described.
2. **What is real-time are proxies:** VIX/VXN lower-highs relative to the Oct 16 peak (22.31) on a worse chip day (Oct 22 high 20.30) is the classic signature of long-liquidation exhausting while index hedging demand fades; a SKEW that refuses to fall says tail hedges are still held, so dealers remain short-gamma-ish below ~7,700. Breadth that is flat on NYSE while Nasdaq decliners dominate (Oct 22) says the selling is still tech/factor-specific, consistent with pod de-grossing rather than macro de-risking.
3. **For a 3x-relative-volume, seconds-to-hours single-leg desk**, the exploitable implications are regime-level, not signal-level: (a) a 99th-pct short book plus "squeeze alert" means upside gaps on headlines will be sharper and faster than downside grinds; (b) tight pod limits and 310% gross mean a −3% morning in semis can accelerate into the close rather than mean-revert (Oct 15, Oct 22); (c) the equal-weight/breadth divergence means index puts bought against single-name strength (and vice versa) will have unusual basis risk.
4. **Catalyst dependence:** every leg of this episode was headline-driven (Oct 14 CPI; Oct 15 Korea/financing; Oct 22 Meta FCF/CDS, Lam supply, Huang "capital scarce", Houthi/oil). The de-grossing is the amplifier, not the trigger; news-first-seen flags remain the primary input, and positioning data only sets the amplitude.
5. **What would mark a real slowdown, in publicly checkable form:** a GS daily showing short covering ≥ long selling on a down day; SOX reclaiming ~11,000 on positive breadth; 20-day realized vol topping out before vol-control sells; VIX closing below ~17 (Oct 21 level) with SKEW falling; Asia-session foreign flows turning net positive in Korea/Taiwan; HY OAS stalling below ~340 bp.

---

## 7. Open items not found (said explicitly)

- Goldman daily prime notes for Oct 19, 20, 21, 22; any Oct 23 CTA Corner.
- Morgan Stanley Prime/QDS, UBS Prime, BofA October Systematic Flows Monitor.
- Any Nomura note dated Oct 22; any post-Oct-16 vol-control selling estimate from any bank.
- Millennium, Point72, Balyasny, Citadel Wellington October MTD returns or any confirmed risk-cut/pod-shutdown reports for this episode.
- Oct 22 exchange volume vs average, Oct 22 Cboe put/call and skew closes.
- The full Reuters "Trading Day: Maximum pAIn" (Oct 22) text beyond its lede.
- Any statement of "X% done" or "typically N days".

---

## Sources (all EXTRACT via search snippets; none opened directly)

**Goldman Prime coverage**
- Bloomberg, Oct 19: https://www.bloomberg.com/news/articles/2026-10-19/hedge-funds-cut-tech-at-fastest-pace-in-a-decade-goldman-says (syndicated: https://finance.yahoo.com/markets/stocks/articles/hedge-funds-dumped-tech-stocks-133527326.html ; https://247wallst.com/investing/2026/10/20/hedge-funds-dumped-tech-stocks-at-the-fastest-pace-in-a-decade-goldman-says/ ; https://hedgeweek.com/news/hedge-funds-slash-tech-exposure-at-fastest-pace-in-a-decade)
- Investing.com, Oct 19–20: https://www.investing.com/news/stock-market-news/hedge-funds-cut-tech-stocks-at-record-pace-goldman-says-4958101
- Bloomberg, Oct 22: https://www.bloomberg.com/news/articles/2026-10-22/hedge-funds-pile-into-shorts-as-goldman-flags-stock-squeeze-risk (syndicated: https://www.fa-mag.com/news/hedge-funds-pile-into-shorts-as-goldman-flags-stock-squeeze-risk-88912.html ; https://www.ibtimes.com/hedge-funds-are-ramping-stock-shorts-five-year-highs-goldman-warning-squeeze-3808879 ; https://news.futunn.com/en/post/1001958991/goldman-sachs-warns-of-short-squeeze-risk-hedge-fund-equity)
- Reuters, Oct 16 (HF losses, "half of Wednesday"): https://finance.yahoo.com/markets/stocks/articles/ai-selloff-hammers-hedge-funds-020957793.html ; https://money.usnews.com/investing/news/articles/2026-10-15/ai-selloff-hammers-hedge-funds-this-week-asia-managers-lead-losses ; https://www.investing.com/news/economy-news/ai-selloff-hammers-hedge-funds-this-week-asia-managers-lead-losses-4952963
- Tickmill repost of GS weekly (−2.0 SD, 2.6:1): https://www.tickmill.com/blog/institutional-insights-goldman-sachs-tech-liquidation-retial-etf-chase
- GS AI basket / Lin / Laicini / 310% gross (aggregators): https://www.gurufocus.com/news/9127726/goldman-sachs-reports-hedge-funds-selling-global-ai-stocks-rapidly-aiq-faces-valuation-pressure ; https://www.kucoin.com/news/flash/hedge-funds-sell-off-2-year-ai-positions-in-5-days-goldman-warns-of-ongoing-deleveraging ; https://finance.biggo.com/news/b165edfc-390b-4dd7-a38f-3c795dc989b1 ; https://www.itiger.com/news/1150649522
- GS "What Matters Today" / Coppersmith: https://news.futunn.com/en/post/1001617868/hedge-funds-are-reducing-their-holdings-of-us-technology-stocks
- CNBC live blog Oct 19 (GS weekly): https://www.cnbc.com/2026/10/18/stock-market-today-live-updates.html
- Pasquariello: https://seekingalpha.com/news/4654202-goldmans-pasquariello-sees-october-choppiness-giving-way-to-year-end-rally ; https://www.tipranks.com/news/goldman-sachs-gs-sees-a-year-end-rally-ahead-for-stocks
- GS credit (Lynam): https://finance.yahoo.com/markets/stocks/article/why-coreweave-nebius-and-other-neocloud-stocks-are-being-pounded-goldman-sachs-explains-125730269.html ; https://www.axios.com/2026/10/20/ai-debt-coreweave-goldman ; https://www.cnbc.com/2026/10/19/coreweave-oracle-ai-credit-stress.html
- GS CTA (older): https://cryptobriefing.com/goldman-sachs-cta-sellers-all-scenarios/ ; https://www.tickmill.com/blog/institutional-insights-goldman-sachs-sp500-flows-positioning-update-131026

**JPMorgan**
- https://www.investing.com/news/stock-market-news/jpmorgan-says-ai-stock-selling-may-be-nearing-its-limit-as-positioning-resets-4965415 ; https://investinglive.com/stock-market-update/jpmorgan-sees-hedge-fund-de-risking-limiting-stock-downside-with-chips-the-key-gauge/ ; https://www.tokenpost.com/news/investing/38223 ; https://neoreports.substack.com/p/daily-ai-investment-brief-261020 ; https://www.kitco.com/news/off-the-wire/2026-08-04/hedge-funds-2026-gains-dented-tech-trades-july-jpmorgan-says

**Morgan Stanley**
- https://www.bloomberg.com/news/articles/2026-10-19/morgan-stanley-s-wilson-says-get-ready-to-buy-as-stock-drop-ends ; https://www.investing.com/news/stock-market-news/prepare-to-buy-the-dip-as-us-stock-selloff-nears-its-end-morgan-stanley-4957025 ; https://news.futunn.com/en/post/1001540881/quality-factor-hits-new-highs-signaling-strategic-positioning-morgan-stanley ; https://www.cnbc.com/2026/10/21/goldman-sachs-jpmorgan-morgan-stanley-ai-trading.html

**Barclays / UBS / Deutsche / BofA / Nomura**
- Barclays financing caps (Bloomberg via Investing.com): https://www.investing.com/news/stock-market-news/barclays-shifts-capital-to-boost-hedge-fund-lending-in-asia--bloomberg-93CH-4960667 ; https://news.futunn.com/en/post/1001869906/is-leverage-in-us-stocks-maxed-out-with-wall-street
- Vol-control (Reuters Oct 1; DB, Barclays, UBS, JPM): https://finance.yahoo.com/markets/stocks/articles/analysis-volatility-control-funds-near-100442724.html
- Deutsche Bank Thatte: https://uk.investing.com/news/stock-market-news/tech-positioning-nears-longrun-trend-top-deutsche-bank-says-93CH-4904854 ; https://www.investing.com/news/stock-market-news/deutsche-bank-says-discretionary-investor-positioning-falls-below-neutral-93CH-4931216
- BofA Systematic Flows Monitor: https://finvaulta.com/research/bank-of-america/systematic-flows-monitor-ctas-ride-the-equity-rally-2026-09-25 ; https://finvaulta.com/research/bank-of-america/systematic-flows-monitor-cta-equity-positioning-2026-09-11 ; https://www.thestreet.com/investing/bank-of-america-163-billion-forced-selling-stocks
- Nomura McElligott: https://www.tickmill.com/blog/institutional-insights-nomura-mcelligott-binaries ; https://seekingalpha.com/news/4654821-nomuras-mcelligott-sees-bond-squeeze-and-ai-jitters-driving-reversals ; https://www.tradingview.com/news/seekingalpha:f2ce91a7b094b:0-nomura-s-mcelligott-sees-bond-squeeze-and-ai-jitters-driving-reversals/

**Citadel / pod shops / IMF**
- Griffin: https://investinglive.com/stock-market-update/citadel-s-griffin-says-ai-almost-certainly-a-bubble-even-as-demand-signals-stay-strong/ ; https://www.benzinga.com/trading-ideas/movers/26/10/62499736/ken-griffin-calls-ai-a-bubble-after-citadel-bought-the-dip ; https://247wallst.com/investing/2026/10/21/ken-griffin-there-are-almost-certainly-bubbles-in-ai-right-now/
- July pod losses: https://aiweekly.co/alerts/millennium-loses-21-in-july-as-ai-stock-selloff-hits-its-pods ; https://www.briefs.co/news/july-s-ai-fueled-slide-hit-hedge-funds-hard/
- Pod stop-loss mechanics (secondary): https://www.navnoorbawaresearch.com/p/millennium-and-balyasnys-stop-loss ; https://youngandcalculated.substack.com/p/why-market-neutral-funds-can-still
- IMF GFSR Oct 2026: https://www.imf.org/en/publications/gfsr/issues/2026/10/13/global-financial-stability-report-october-2026 ; https://www.cnbc.com/2026/10/18/hedge-funds-bond-market-turmoil.html

**Tape, options, credit, flows**
- Oct 22 close: https://finance.yahoo.com/markets/stocks/articles/nasdaq-futures-drop-over-1-093849296.html (Reuters) ; https://www.investing.com/news/stock-market-news/us-stock-futures-fall-as-investors-weigh-tesla-meta-earnings-4964498 ; https://cnbc.com/2026/10/21/stock-market-today-live-updates.html ; https://news.sbs.co.kr/english/article.do?news_id=N1008811300 ; https://cappnotes.substack.com/p/closing-look-thursday-october-22 ; https://www.investing.com/news/economy-news/trading-day-maximum-pain-4967585
- SOX levels: https://finance.yahoo.com/markets/article/chip-stocks-break-a-bear-trap-after-a-3-trillion-rout--here-are-the-levels-bulls-need-to-hold-155619334.html
- Meta / Huang: https://www.cnbc.com/2026/10/22/meta-stock-q3-earnings-free-cash-flow.html ; https://www.cnbc.com/2026/10/22/nvidia-jensen-huang-neocloud-demand-capital.html ; https://www.nbcnews.com/business/markets/iran-war-ai-spending-oil-prices-selloff-rcna604994
- Oct 22 pre-market: https://finance.yahoo.com/markets/stocks/articles/why-nasdaq-futures-falling-premarket-085201550.html ; https://www.benzinga.com/trading-ideas/movers/26/10/62522553/tesla-lam-research-rollins-and-other-big-stocks-moving-lower-in-thursdays-pre-market-session
- Asia Oct 22 / Oct 15: https://invezz.com/news/2026/10/22/heres-why-kospi-and-nikkei-225-are-crashing-on-oct-22/ ; https://www.ajupress.com/view/20261022153542644 ; https://www.cnbc.com/2026/10/15/sk-hynix-samsung-softbank-stocks-asia-tech-rout-ai-funding-worries.html
- Oct 19–21 sessions: https://www.thestreet.com/stock-market-today/stock-market-today-oct-19-2026-nasdaq-futures-climb-as-tech-rebound-from-sell-off ; https://finance.yahoo.com/markets/stocks/articles/markets-news-oct-20-2026-103252254.html ; https://cappnotes.substack.com/p/closing-look-wednesday-october-21 ; https://www.investing.com/news/economy-news/trading-day-tech-it-away-4964198
- Week of Oct 12–16: https://www.chartmill.com/news/AA/Chartmill-56386-stock-market-today-chip-selloff-day-eight-nasdaq-worst-week-2026-10-16 ; https://finance.yahoo.com/markets/stocks/articles/nasdaq-100-records-worst-week-221534484.html ; https://www.zerohedge.com/markets/futures-rise-dip-buyers-rush-back-chips-after-worst-nasdaq-week-liberation-day
- Short sellers (S3/Bloomberg): https://www.bloomberg.com/news/articles/2026-10-16/longest-chip-selloff-since-2006-mints-short-sellers-32-billion ; https://qz.com/chip-short-sellers-32-billion-paper-gains-selloff-101626
- Leveraged ETF flows: https://www.etf.com/sections/weekly-etf-flows/investors-buy-dip-chips-etf-inflows-near-58b ; https://www.investing.com/news/stock-market-news/leveraged-chip-fund-sees-record-7-billion-inflow-amid-selloff-93CH-4957271 ; https://www.advisorperspectives.com/articles/2026/10/15/1-trillion-chip-draws-billions-leveraged-etf-bets
- Options/vol: https://spotgamma.com/vix-20-negative-gamma-october-opex/ ; https://spotgamma.com/cpi-options-positioning-spx-gamma/ ; https://www.home.saxo/en-mena/content/articles/options/the-front-end-drains-the-tails-do-not---options-brief---20-october-2026-20102026 ; https://tradersunion.com/news/institutions/show/3879488-vix-hedging-demand-megacap-earnings/ ; https://finance.biggo.com/news/30628c15-02f6-41e0-a646-156600ee15eb ; https://volvibes.substack.com/p/market-overview-october-19th-2026
- Credit: https://clintsmith.substack.com/p/tech-is-taking-the-hit-breadth-is ; https://seekingalpha.com/news/4650575-u-s-high-yield-credit-stress-mounts-as-ccc-spreads-hit-4-year-highs ; https://www.cnbc.com/2026/10/15/coreweave-credit-default-swaps-hit-distress-levels-as-investors-sour-on-ai-debt.html
- Catalysts (CPI, yields): https://www.roic.ai/news/chip-stocks-slump-as-inflation-fears-and-ai-financing-doubts-mount-10-15-2026 ; https://www.cnn.com/2026/10/15/business/tech-selloff-nasdaq-ai-intl