# Completeness critique and gap-fill — Monday 2026-10-26 de-grossing read

**Research status (read first).** The shared WebSearch budget for this turn was already exhausted when this pass began (all 8 queries refused; no workaround attempted) and every finance/news host is proxy-blocked. Fills below therefore come from (a) GitHub-hosted research ledgers, data mirrors and CSVs reached via `raw.githubusercontent.com` and GitHub code search, (b) the desk mailbox (Gmail connector), and (c) the local 10/23 news capture in the scratchpad. **Nothing is VERIFIED on a primary page; every fact is EXTRACT (mirror/ledger/newsletter, with URL and date) or UNVERIFIED (inference).** Items that could not be found are stated as such.

---

## PART 1 — The five gaps that matter most (highest severity first)

| # | Gap | Type | Why it is load-bearing for Monday |
|---|---|---|---|
| **1** | **No US prime-broker or flow read for Friday 10/23 at all, and Thursday's 10/22 flow is still unsplit between long selling and short covering.** The positioning sheet calls Monday's Goldman weekly "the single most important Monday read" but (a) its publication time is UNVERIFIED, (b) c3's verifier notes the Bloomberg 10/22 piece already carried MTD flows through ~10/19–20, so the weekly may add only two sessions, (c) Morgan Stanley PB is absent for all of October, (d) Friday's SOXL/SOXS/SMH creations were not found, and Thursday's (publishable Friday) were not found either. | Reading that should exist; metric class missed | The entire "slowing vs resuming" question is a flow question. Without a Friday US flow print the desk is inferring hedge-fund behaviour from a +0.44% SOX on 90% volume, which is consistent with both "pause" and "shorts covering into a flat tape." |
| **2** | **Korea: the sheets missed that the ~KRW 55T corporate buyback bid under Samsung/SK hynix has ended, and their foreign-flow prints are on inconsistent bases.** SK hynix's ~40T won buyback finished 10/21 (a month early); Samsung's 15T finished 10/6. "Other corporates" (기타법인, the buyback channel) fell from +4,271/+6,367/+5,145억 on Mon–Wed to +407/+630억 on Thu/Fri. Separately, the sheets' 10/22 base ("113B won foreign sell") is one of three conflicting prints (−399.1B Newspim basis / −113.2B Aju / +59.2B Solution News), and the "~145B at 10:00 KST Friday" print conflicts with a Korean desk feed showing −4,637억 by 10:06 KST. Friday's rebound had KOSPI breadth of 173 up : 719 down. | Metric class missed + contradiction between sheets | The Monday thresholds (≥1T resuming / <300B slowing) are calibrated against a base that is itself ambiguous, and the structural buyer that absorbed foreign selling in the two names that carry ~77% of October's foreign selling is gone. Monday's Korea tape has less cushion than any day in October. |
| **3** | **Credit: the "credit did not confirm / HY untouched" claim in the friday and asia-credit sheets is contradicted by the FRED print.** ICE BofA HY OAS was 3.40% on 10/22, **+13bp on the day and +17bp on the week**, while HYG was +0.16%; the asia-credit sheet's own confirmation threshold is "15–25bp on the day." CoreWeave's 9.625% 2032 bond YTW moved +61bp to 15.34% (price 78.66) on 10/22 and its 5y CDS is reported above 1,100bp; global IG is at a 17–18-month wide. The 10/23 OAS is unpublished until Monday; CDX HY/IG for Friday not found anywhere. | Contradiction between sheets; unsupported load-bearing claim | The HYG-based "positioning event, not credit event" read is the desk's stated reason to lean calls on squeeze setups. On OAS the 10/22 move was two-thirds of the way to the desk's own "confirmation" line. |
| **4** | **Weekend geopolitical tape was not captured (nothing dated 10/24 in any sheet).** Overnight Fri→Sat: Houthi ballistic missile at Riyadh intercepted (two explosions heard), drone downed over the Eastern Province; Saturday missiles toward Taif and Yanbu (Red Sea export terminal) intercepted; IRGC claims two laden supertankers mined on a "southern route" (unverified; CENTCOM: no mines); US envoy Barrack on a strike "this weekend? Absolutely"; Trump: Iran "fabricating hits and mines", "the Hormuz Strait is ours"; US non-emergency staff ordered out of Saudi; Israeli election Tue 10/27; Egypt parliament 10/26 on troop deployment. Brent settle itself is disputed ($116.72 vs $116.91). | Reading that should exist | Determines whether Monday opens as a macro/oil gap (the positioning sheet's 20% "macro shock" branch, which the desk reads via 10Y-at-5% and HY OAS) rather than a positioning day. VZ also reports Monday pre-market after telecoms fell 4–6% Friday. |
| **5** | **Options-structure readings for Friday are missing where they matter most: QQQ spot vs the 10/30 QQQ 700 put, SOX/NDX member counts, VIX term structure, put/call.** QQQ closed Friday at **704.40** (−0.01%), i.e. **0.6% above the 700 strike** the calendar sheet flagged (OI still unverified); QQQ's lows were 701.90 Thu and 701.16 Fri. No sheet had QQQ spot. Cboe 10/22 put/call figures conflict across sources (total 0.87 / equity 0.52 vs 0.94 / 0.69). Friday SOX 30-member up/down count, VIX9D/3M/VVIX/SKEW closes: not found by any sheet or this pass. | Reading that should exist; contradiction | For a single-leg desk, a 700 QQQ strike sitting 4 points under spot into an FOMC/MSFT/GOOGL week is a pin/accelerant level; the desk's "all-30-down" signature test has no Friday baseline. |

Minor items (not ranked): c3's "VIP basket −4.2%, worst since 8/8/2011" is secondary-source only and probably a relative statistic (c3 verifier); SMH −4.56% w/w vs SOX −3.21% unresolved; Nasdaq-100 Friday close unconfirmed (28,957.53 vs 29,037.15); JPX weekly foreign flows for Japan not covered at all; Barron's/WSJ/FT weekend coverage not found.

---

## PART 2 — Fills

### Gap 1 — US prime-broker / flow read for Friday 10/23: **NOT FOUND**

| Attempt | Result | Label |
|---|---|---|
| GitHub code search for Goldman/"prime brokerage"/"net leverage"/"gross leverage" dated 10/23–10/24 (three query variants) | 0 hits | — |
| Desk mailbox, all threads received 10/23–10/24 (73 threads listed; Benzinga Ring the Bell 10/23 11:05Z, Michael Burry chat threads 10/23, x.ai Daily Stock Tracker 10/23 21:21Z read in full) | No prime-broker, Goldman, S3, ETF-flow or de-grossing content. Benzinga's recap is Thursday-only ("credit default swaps on Meta and other hyperscalers signaled growing concerns about debt risk"; 10Y −15bp "biggest drop since 2023"). Burry threads are a subscription-price notice and a song link. x.ai digest is TSLA/BTC only. | EXTRACT (read in full; no positioning content) |
| Local 10/23 Google-News capture (1,975 items to 10/23 ~16:15Z) grepped for hedge fund / prime / short covering / Goldman / Morgan Stanley | Only the Reuters 10/23 "Hedge fund returns worsen" story (already in the sheets), the investingLive JPM "de-risking limiting downside, chips the key gauge" item (~10/21) and a KuCoin item "Morgan Stanley analyzes the sustainability of the US Treasury rally amid the European debt crisis and tech sell-off" (rates, not PB). | EXTRACT |
| Saturday-morning multi-model news captures (JaronKBragg7337/watch, claude/kimi/deepseek 2026-10-24, window Fri 03:00–Sat 03:00 ET) | No hedge-fund or prime-broker bullet in any of the three. | EXTRACT |

**What this means (UNVERIFIED):** as of Saturday there is no public datapoint on whether US hedge funds kept de-grossing on Friday. The only same-day proxy for "the foreign leg" on Friday is Korea (Gap 2), where the answer is unambiguous: foreign cash selling re-accelerated to the largest daily figure of the week. The Monday morning Goldman write-up (if Bloomberg runs one) should be read for (i) whether 10/22's P&L hit was accompanied by net long selling in US semis or mostly short covering, and (ii) whether gross came down; nothing found changes the sheets' stance that this is unknown.

### Gap 2 — Korea: Friday 10/23 full-session flows, the buyback cliff, breadth, intraday path (all EXTRACT from Korean research ledgers mirrored on GitHub; underlying KRX close captures not opened)

**Friday 10/23 KOSPI investor-type flows (억원; source: thci-report daily review, "마감 캡처 · CSV(15:37)")**

| Investor | Net | Of which 비차익 (non-arb program) | Of which 비프로그램 |
|---|---|---|---|
| Foreign (cash) | **−10,939** | −8,640 | −2,299 |
| Institutions | +7,954 (금융투자 +5,272; 투신 +1,656; 보험 +830; 연기금 +529) | | |
| Individuals | +2,336 | −181 | +2,517 |
| Other corporates (기타법인) | +630 | | |
| Program total (KOSPI) | 비차익 −8,686; 차익 −48 | | |
| **Futures (KOSPI200)** | **Foreign +2,828; institutions +1,301; individuals −3,735** | | |

Index: KOSPI 5,550.30 (+0.30%); KOSPI200 862.77 (+0.55%), open 836.73, low 820.84 at 09:05 KST, **close = high**. Breadth: **KOSPI 173 up : 719 down (18.9%)**; KOSDAQ 404:1,248 (23.3%); KOSPI200 sample 23:176 (11.4%). SK hynix +4.42% (opened −1.88%, low −4.25%; turnover 6.55T won); Samsung +0.47% (5.20T won). A second ledger (pwman111 "Genesis" note, 10/23) gives foreign −9,811억 "centred on SK hynix, Samsung Electronics and Samsung Electro-Mechanics" and the same 719:173 breadth — so Friday's foreign figure now spans **−9,811 to −10,939억** across bases, consistent with the sheets' 981B–1,094B range. UNVERIFIED read: foreigners sold ~1.1T of cash while buying 0.28T of futures, i.e. a hedged/basis structure, not outright de-risking of Korea beta; the rebound was institutions (securities firms, likely ETF/arb) plus retail in two names, with four stocks down for every one up.

**Daily foreign flows for the week (억원; thci weekly review 10/19–10/23; 10/20 is a press figure):**

| Date | Foreign cash | Foreign 비차익 basket | 기타법인 | KOSPI close |
|---|---|---|---|---|
| 10/19 Mon | +6,248 | +10,439 | +4,271 | 5,768.01 |
| 10/20 Tue | −5,300 | −5,004 | +6,367 | 5,552.74 |
| 10/21 Wed | +9,528 | +11,666 | +5,145 | 5,735.66 |
| 10/22 Thu | **−3,991** | −6,164 | +407 | 5,533.77 |
| 10/23 Fri | **−10,939** | −8,640 | +630 | 5,550.30 |
| Week | −4,454 | +2,297 | +16,820 | −2.08% |

Three things a PB strategist would flag: (1) **the 10/22 base used by all four sheets (−113B) is a different basis from this −399.1B** (the innerpyg 10/23 brief records the same split: "뉴스핌 3,991억 순매도 vs 솔루션뉴스 592억 순매수"), so the "7–10x re-acceleration" in c4 is really ~2.7x on a like-for-like basis; (2) the foreign basket had alternated sign every day since 10/19 and **Friday broke the pattern with a second consecutive sell day**, which the thci desk sets as its Monday test ("3일 연속 → 매도 추세 확정"); (3) **buybacks: SK hynix's ~40T won programme ended 10/21, one month before its 11/19 deadline; Samsung's 15T ended 10/6**, and the 기타법인 bid collapsed from ~0.5T/day to 0.04–0.06T on Thu/Fri. Also from the same ledger: SOX (prior night) and KOSPI200 (next day) moved in opposite directions on all five sessions of the week; two of four sessions (10/19, 10/23) were gap-down-then-close-at-high.

**Friday intraday foreign-flow path (hk99915-bot desk feed, cumulative, 억원):** 10:06 KST −4,637 (KOSPI 5,443.1) → 11:06 −8,519 (5,404.6) → 12:06 −10,430 (5,425.8) → 13:06 −10,683 (5,482.65) → 14:06 ~−9,986 (5,509.9) → 15:09 −11,310 (5,520.8) → close −10,939. UNVERIFIED implication for Sunday night: the sheets' "~145B at 10:00 KST" was an early KRX-only press print; **do not read Monday's foreign leg before ~11:00 KST (22:00 ET); the 12:06 KST print (23:06 ET) was within 5% of Friday's close figure**, and the selling was front-loaded while the index recovered on institutions.

**October cumulative:** foreign net selling of KOSPI >17T won through 10/22 (17조4,030억, 위키트리 via innerpyg; 93bpm briefing 10/23: ~77% of it in Samsung + SK hynix). EXTRACT.

**Implication for the sheets' Monday thresholds (UNVERIFIED):** compare Monday's close print on the Newspim/KRX+NXT basis (Fri −1.09T, Thu −0.40T), not against −113B. A third consecutive foreign 비차익 sell day plus 기타법인 still <0.1T = resuming with no corporate cushion; foreign cash flat-to-buy with futures still bought = the hedged leg unwinding, i.e. slowing. KOSPI breadth <30% again with the index up = the "two-name squeeze" structure, not broad relief (thci's own rule: ≥40% breadth for a real rebound).

### Gap 3 — Credit: what the 10/22 prints actually say, and what lands Monday

| Series | 10/21 | 10/22 | Δ day | Δ week | Source (all EXTRACT) |
|---|---|---|---|---|---|
| ICE BofA US HY OAS (BAMLH0A0HYM2) | 3.27% | **3.40%** | **+13bp** | +17bp | FRED mirror (LEEYOUNGJIN fred_latest.csv; cool1990 宏观指标 2026-10-23, published 10/24 08:05 +08:00); local FRED file ends 10/21 at 3.27 (10/15 3.23, 10/16 3.31, 10/19 3.29, 10/20 3.33) |
| ICE BofA US IG OAS (BAMLC0A0CM) | 0.88% | **0.89%** | +1bp | — | cool1990; contactexepex macro file |
| CoreWeave 9.625% 2032 (144A 21873SAK4), YTW / price | 14.73% | **15.34% / 78.66** | **+61bp** | — | cool1990 (Kilambi TRACE) |
| CoreWeave 5y CDS | — | ">1,100bp" (Saturday note) | — | — | ShaoxiongYuan morning note 2026-10-24 |
| HYG | 77.10 (+0.16%) Thu; 77.05 (−0.06%) Fri | | | | Paramaribo Letter 10/23; sheets |
| MOVE | — | 103.32 on **10/23**, −3.30% | | | cool1990 (TradingView TVC:MOVE) |
| 10Y / 2Y (FRED DGS10/DGS2) | 5.13 / 4.81 | 4.96 / 4.65 | −17 / −16bp | | FRED mirror; Paramaribo (Treasury par curve 22 Oct: 2y 4.65, 10y 4.96, 30y 5.29) |
| 10Y / 2Y / 2s10s, 10/23 | | 5.00 / 4.69 / +31bp (+4/+4/0) | | | cool1990; FRED T10Y2Y 10/23 = 0.31 |
| 5y5y nominal fwd / real fwd, 10/23 | | 5.18% (+4bp) / 2.98% (+3bp) | | | cool1990 |
| 10Y breakeven (T10YIE) | 2.37 | 2.32 (10/22); 2.34 (+2bp, 10/23) | | | Paramaribo; cool1990 |
| Cboe put/call 10/22 | | total **0.94**, equity **0.69**, index 1.02, SPX+SPXW 1.23, VIX 0.41 | | | contactexepex agentic-stock-prediction 2026-10-23.jsonl — **conflicts with the sheets' marketindicators.net 0.87 / 0.52 / 1.02** (index agrees; total/equity do not — different Cboe tables) |
| **10/23 HY and IG OAS** | | **not yet published** (FRED one-business-day lag; several ledgers explicitly mark "22 October OAS unpublished" as of Saturday) | | | Paramaribo; cool1990 |
| CDX HY / CDX IG, Friday | | **not found** | | | — |

**Reconciliation (UNVERIFIED):** the sheets' "credit did not confirm" rests on HYG/JNK/LQD price action, and on OAS the 10/22 move was the largest single-day widening of the month and took HY from 3.23% (10/15) to 3.40% (+17bp in five sessions) while HYG was flat because the 10Y fell 17bp (duration offset spread). Against the asia-credit sheet's own grid, +13bp is "approaching confirmation," not "non-confirmation"; the CCC and BB legs were not retrievable. Monday's FRED print (10/23 OAS) is therefore the first credit datapoint that can distinguish the two readings: a flat-to-tighter 10/23 (with the 10Y +4bp and HYG −0.06%) keeps "equity-internal"; another +10bp or more, cumulative ≥+25bp since 10/21, meets the sheet's "confirmation" line. MOVE falling 3.3% on Friday and the 10Y back at exactly 5.00% say rates are not yet the stress channel.

### Bonus fills (gaps 4 and 5, obtained in passing)

**Gap 4 — weekend tape (EXTRACT unless marked):**
- Sat 10/24 ~02:00–04:00 UTC: Saudi-led coalition intercepted a Houthi ballistic missile aimed at **Riyadh** (two explosions heard, no casualties) and downed a drone over the Eastern Province; later Saturday it destroyed two ballistic missiles fired toward **Taif and Yanbu** (Yanbu = Red Sea crude export terminal; alerts briefly covered Makkah/Jeddah). US ordered non-emergency staff out of Saudi; flydubai cancellations extended to 10/29. (Gulf News, Anadolu, FinancialJuice via mirrors.)
- IRGC claims two laden supertankers (~4.5M bbl) mined on a "southern route" on 10/23; state TV says all "non-compliant" Hormuz traffic halted; **unverified, CENTCOM maintains there are no mines**; UKMTO confirms one tanker hit off Limah (Oman) on 10/22 that continued its voyage. MUFG and a Bloomberg item say Hormuz/Gulf physical flows are near pre-conflict levels at elevated freight (Bloomberg 10/23: "Physical Oil Prices Drop in Mideast as Flows Via Hormuz Hold Up").
- Washington: envoy Tom Barrack, asked Friday whether a strike could come this weekend: "Absolutely," while saying Trump is "open … to a deal" (he holds no Iran portfolio); Trump on social media: Iran is "fabricating hits and mines" to lift oil before the midterms, and "the Hormuz Strait is ours"; a DNI memo reportedly says Iranian plots against US personnel are at "advanced stages"; Netanyahu (10/21–23) called for regime removal. Polymarket "US–Iran ceasefire continues through the midterms" nonetheless rose to ~75¢ (~07:05 UTC Sat).
- Calendar additions: **Israeli election Tue 10/27** (MEtracker: "27 OCTOBER — the Israeli ballot"; the kimi capture says "Monday Oct 27," a weekday error — 10/27 is Tuesday); Egypt's parliament reconvenes 10/26 on a Saudi deployment; OPEC+ review 11/1; Saudi December OSP due ~11/1–5; **Verizon reports Monday pre-market** (Benzinga 10/23).
- Brent settle conflict: $116.72 +3.14% (Reuters/CNBC/Fortune) vs **$116.91 +3.30%** (TradingEconomics-based captures); WTI $103.27 vs $103.44. Gold 4,007.9 (−1.29%, COMEX); DXY 101.75 (+0.13%).
- Also Saturday: Moody's affirmed France Aa3/negative late Friday (OAT 10Y ~5.06% after 5.14%); the "European debt crisis" framing in the MS rates note refers to France.

**Gap 5 — QQQ and Friday microstructure (EXTRACT, yfinance-derived CSV in timhun/daily-podcast-stk):**

| Date | QQQ open | high | low | close | chg | volume |
|---|---|---|---|---|---|---|
| 10/21 | 722.22 | 727.95 | 719.71 | 725.20 | +1.05% | 32.5M |
| 10/22 | 713.61 | 715.43 | **701.90** | 704.47 | −2.86% | 64.6M |
| 10/23 | 702.10 | 709.30 | **701.16** | **704.40** | −0.01% | 30.0M |

QQQ sits **4.40 points (0.6%) above the 700 strike** flagged for the 10/30 expiry, having tested 701–702 on both Thursday and Friday on half Thursday's volume; FlashAlpha's QQQ flip (729.08) is 3.5% above spot. 700 put OI, SOX member counts and VIX9D/3M/VVIX/SKEW Friday closes remain **not found**. SPY/SOXX Friday closes from the same source: 759.97 (−0.52%), 478.20 (+0.53%).

---

## Not found in this pass (explicit)
Goldman/MS/JPM PB read for Fri 10/23; split of 10/22 long sales vs short covers; SOXL/SOXS/SMH/QQQ creations for 10/22 and 10/23; 10/23 HY/IG/CCC OAS; CDX HY/IG; QQQ 700 OI; SOX and NDX member counts Friday; VIX term structure Friday; Cboe put/call Friday; Samsung/SK hynix foreign flow **by stock** for Friday (only aggregate and institutional by-stock exist); JPX weekly foreign flows; confirmation of the Israeli election weekday beyond the two ledgers; any Barron's/WSJ/FT weekend piece.

## Sources (all EXTRACT via GitHub mirrors/ledgers or mailbox; none is a primary page)
- Korea Friday close/flows: https://raw.githubusercontent.com/premier2124-stack/thci-report/main/reports/2026-10-23_한국증시_데일리리뷰.md ; weekly: https://raw.githubusercontent.com/premier2124-stack/thci-report/main/reports/2026-10-19_2026-10-23_한국증시_주간리뷰.md ; intraday feed: https://raw.githubusercontent.com/hk99915-bot/market-screener/main/docs/desk_kb/rounds/2026-10-23-hf-intraday.md ; https://github.com/pwman111-debuge/stockanalysis/blob/main/content/market-analysis/2026-10-23-market-analysis-genesis.mdx ; https://github.com/innerpyg/innerpyg.github.io/blob/main/_posts/2026-10-23-morning-brief.html ; https://github.com/93bpm/stock-ai-pages/blob/main/briefing/2026-10-23.json ; https://github.com/nonojin99/Daily-Card-News/blob/main/2026-10-23_daily-brief.html (뉴시스 10/22 buyback-completion items)
- Credit/rates: https://raw.githubusercontent.com/LEEYOUNGJIN-GIT/fred-macro-review/main/data/fred_latest.csv ; https://github.com/cool1990/invest-dashboard_v1/blob/main/inbox/notes/每日/宏观指标_2026-10-23.md ; https://github.com/contactexepex/agentic-stock-prediction/blob/main/data/us/macro/2026/10/2026-10-23.jsonl ; https://github.com/edta27/paramaribo-letter/blob/main/public/issue-pages/2026-10-23-the-outflow-printed.html ; https://github.com/ShaoxiongYuan/ShaoxiongYuan.github.io/blob/master/morning-notes/2026-10-24-brent-six-month-high-fed-france-dodges.md ; local <local path>
- Weekend geopolitics: https://github.com/JaronKBragg7337/watch/blob/master/kimi/2026-10-24.md ; https://github.com/JaronKBragg7337/watch/blob/master/claude/2026-10-24.md ; https://github.com/JaronKBragg7337/watch/blob/master/deepseek/2026-10-24.md ; https://raw.githubusercontent.com/8gara8/MEtracker/main/content/context.md (Day 239, 2026-10-24) ; https://github.com/vlknCC26/cargocrew-daily/blob/main/ed-2026-10-24.html ; https://github.com/sindhplusmedianetwork/sindhplusmedianetwork.github.io/blob/main/news/saudi-led-coalition-says-it-destroyed-houthi-missiles-fired.html ; cited therein: https://gulfnews.com/world/mena/middle-east-war-houthi-missile-targets-riyadh-tankers-hit-mines-near-hormuz-1.500721804 ; https://www.aa.com.tr/en/middle-east/saudi-led-coalition-says-it-intercepted-11-houthi-drones-and-a-ballistic-missile/4097904 ; https://www.cbsnews.com/live-updates/iran-war-trump-us-oil-gas-prices-strait-of-hormuz-midterms/ ; https://www.jpost.com/israel-election-2026/article-912649
- QQQ/SPY/SOXX: https://raw.githubusercontent.com/timhun/daily-podcast-stk/main/data/market/daily_QQQ.csv ; https://raw.githubusercontent.com/timhun/daily-podcast-stk/main/docs/podcast/20261024_us/daily-podcast-stk-20261024_us.txt
- Mailbox (read in full, no positioning content): Benzinga Ring the Bell 2026-10-23 https://benzingaringthebell.beehiiv.com/p/wall-street-s-recession-warning-moderna-s-meltdown ; Michael Burry Substack chat threads 2026-10-23 ; x.ai Daily Stock Tracker 2026-10-23 21:21Z ; FlashAlpha SPY Open Digest 2026-10-23 (already covered by c2 verifiers)
- Local news capture grepped: <local path> (items to 10/23 ~16:15Z; the 10/24 file is empty)
- Not executed: WebSearch (shared per-turn budget of 200 already exhausted before the first query); blocked: all finance/news/exchange hosts via WebFetch/proxy.