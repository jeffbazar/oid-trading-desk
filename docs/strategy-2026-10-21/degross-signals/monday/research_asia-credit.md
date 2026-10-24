# Monday 10/26 watch: de-grossing slowing or resuming — research status and watch framework

## 0. Research status (read first)

**No new market data could be retrieved in this run.** Every research path failed:

| Path | Result |
|---|---|
| WebSearch (8 queries, Korean/Japanese/English, mode extended) | Refused: "this turn's web search budget is used up (limit: 200 WebSearch calls per turn, shared by every agent in it)". Zero searches executed by this agent. |
| WebFetch (fred.stlouisfed.org, twse.com.tw, krx.co.kr, reuters.com, cnbc.com, news.skhynix.com, boj.or.jp) | `getaddrinfo ENOTFOUND` on all; reuters.com "unable to fetch". |
| curl via agent proxy (FRED CSV for BAMLH0A0HYM2/BAMLC0A0CM/BAMLH0A3HYC, BoJ, TWSE, KRX, ICE MOVE, Cboe, SK hynix newsroom, SEC EDGAR) | `CONNECT tunnel failed, response 403` on every host. Proxy status page confirms policy denial. |

Consequence: **every numeric item requested in both legs is NOT FOUND in this run.** Nothing below is invented; where a figure is given it comes from the workflow's supplied background (originally search-snippet grade, 10/22) and is labelled as such. To fill the tables, a follow-up message after this reply (new turn, fresh search budget) or a raised `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` is needed.

Label key used below:
- **CONTEXT** = supplied by the workflow from the 10/22 research; snippet-grade (EXTRACT-equivalent) but no URL available to me; not re-verified here.
- **COMPUTED** = calendar / time-zone arithmetic, verifiable without a network.
- **UNVERIFIED** = my inference or rule of thumb.
- VERIFIED / EXTRACT: none in this run (no page or snippet was readable).

One factual inconsistency in the supplied context, resolvable by arithmetic: today is Saturday 2026-10-24, so **10/26 is Monday and 10/27 is Tuesday**. "Taiwan reopens Monday 10/27" cannot be right as written; it is either Monday 10/26 or Tuesday 10/27. Which one is NOT FOUND (see Asia table).

---

## 1. Asia leg — requested items, status, and where/when the desk can get them itself

| Item | Status this run | What is known (label) | Where the desk can pull it before the US open |
|---|---|---|---|
| KOSPI close Fri 10/23 | NOT FOUND | Opened -2.4%, low -4.1%, -1.75% at 10:00 KST (CONTEXT). Close unknown. | KRX market data (data.krx.co.kr), Naver Finance 국내증시 |
| KOSDAQ close Fri 10/23 | NOT FOUND | — | same |
| KRX investor-type net flows Fri 10/23 (foreign / institution / retail, won) | NOT FOUND | Foreign net selling ran ~1T won/day early Oct, 113B won on 10/22, ~145B won by 10:00 KST Fri (CONTEXT). Full-day Friday figure unknown. | KRX 투자자별 매매동향; published after the 15:30 KST close daily (UNVERIFIED on exact publication time) |
| Samsung Electronics / SK hynix foreign net (won) Fri 10/23 | NOT FOUND | — | KRX by-stock investor data; Naver Finance 외국인·기관 순매매 per ticker |
| Nikkei 225 close Fri 10/23; Japan investor flows | NOT FOUND | — | JPX weekly investor-type flows publish Thursday for the prior week (UNVERIFIED on 2026 schedule); Nikkei close on JPX/Nikkei sites |
| Hang Seng / Shanghai Fri 10/23 | NOT FOUND | — | HKEX, SSE |
| TSM ADR Fri 10/23 | NOT FOUND | — | Any US quote source; ADR vs. 2330.TW implied price is the Taiwan reopening catch-up gauge |
| Taiwan reopening date and typhoon status | NOT FOUND | Closed Fri 10/23 for typhoon (CONTEXT). Reopening day ambiguous in context (see note above). | TWSE announcements page. UNVERIFIED rule of thumb: TWSE closes when Taipei City announces a work/school stoppage and reopens the next business day the order is lifted; a weekend typhoon could push reopening to Tue 10/27 |
| Monday-morning Asia previews | NOT FOUND | — | — |
| SK hynix Q3 2026 earnings date and consensus | NOT FOUND | UNVERIFIED pattern only: SK hynix has reported Q3 in the last week of October in recent years. The 2026 date is unknown to me and must be checked. | SK hynix IR / newsroom |
| Samsung preliminary Q3 2026 results | NOT FOUND | UNVERIFIED pattern only: Samsung's preliminary Q3 guidance normally lands in the first ~8 days of October, so it would predate this selloff; final Q3 results and the divisional breakdown normally come in the last days of October. Neither confirmed for 2026. | Samsung Newsroom / DART filings |
| USDJPY Fri close; BoJ 10/30 expectations | NOT FOUND | BoJ meets 10/30 (CONTEXT). No pricing data. | — |

### Asia-session clock for Sunday night / Monday (COMPUTED; US is still on EDT until Nov 1, 2026; UK/EU switched to standard time Sun 10/25, so Europe is one hour closer to New York than last week)

| Market | Local hours | EDT (Sun night / Mon) |
|---|---|---|
| Korea (KRX) | 09:00–15:30 KST | 20:00 Sun – 02:30 Mon |
| Japan (TSE) | 09:00–15:30 JST | 20:00 Sun – 02:30 Mon |
| Taiwan (TWSE), if open | 09:00–13:30 CST | 21:00 Sun – 01:30 Mon |
| Hong Kong | 09:30–16:00 HKT | 21:30 Sun – 04:00 Mon |
| London | 08:00 GMT | 04:00 Mon (was 03:00 EDT last week) |
| Frankfurt / Paris | 09:00 CET | 04:00 Mon (was 03:00 EDT last week) |

Desk implication (UNVERIFIED): the Europe cash open and the Asia closes now coincide at 04:00 ET, so the pre-market read on NQ/ES and SOX-proxy names (TSM, ASML ADR behaviour) compresses into one window rather than two.

### What "slowing vs. resuming" looks like in Asia on Monday (UNVERIFIED decision rules, built on the CONTEXT trajectory)

- **Slowing**: KRX foreign net selling for Mon 10/26 stays in the low hundreds of billions of won or flips to net buying; Samsung and SK hynix foreign flows diverge from the index (foreigners buying the two chip names while selling the rest would indicate the semis unwind is done and the selling has rotated). KOSPI holds Friday's low (the -4.1% intraday level; exact index value NOT FOUND). Taiwan, if open, falls less than the two-day US SOX move it missed (SOX -6.7% on 10/22 plus Friday's change, which is NOT FOUND) and TSM ADR trades at a premium to the 2330.TW close rather than a discount.
- **Resuming**: foreign net selling re-accelerates toward the early-October ~1T won/day pace; KOSPI takes out Friday's low; Taiwan gaps down a full catch-up and does not recover intraday; USDJPY falls sharply alongside equities (carry unwind signature, which would tie the de-grossing to macro positioning rather than a pure semis rotation).
- **Ambiguous**: index down but foreign flow small. Treat as retail/local institutional selling, not the hedge-fund de-gross the desk is tracking.

---

## 2. Credit leg — requested items and status

| Item | Status this run | What is known (label) |
|---|---|---|
| FRED BAMLH0A0HYM2 (HY OAS) 10/21, 10/22, 10/23 | NOT FOUND (fetch blocked) | UNVERIFIED on mechanics: FRED posts ICE BofA series one business day after the index date, so the 10/23 print should be visible by Monday morning at the latest; the desk's existing FRED feed will have it |
| FRED BAMLC0A0CM (IG OAS) same dates | NOT FOUND | — |
| CCC OAS (BAMLH0A3HYC) | NOT FOUND | — |
| HYG / JNK / LQD Fri 10/23 | NOT FOUND | HYG was flat Thu 10/22 (CONTEXT) |
| CDX HY / CDX IG | NOT FOUND | — |
| CDS: Meta, Oracle, CoreWeave, Amazon | NOT FOUND | — |
| AI-capex financing news over the weekend (bond deals, private credit, neocloud, data-centre debt) | NOT FOUND | — |
| MOVE index | NOT FOUND | — |

### Did credit confirm the equity move?

- **Thursday 10/22**: on the supplied CONTEXT (SOX -6.7%, all 30 members down, average stock up, HYG flat, 10Y below 5%, VIX ~19 in contango) credit **did not confirm**. A one-day 6.7% drop in a sector index with the equal-weight market up and HY ETFs flat is the signature of a positioning unwind inside equities, not a credit or macro event (UNVERIFIED interpretation; the underlying prints are CONTEXT-grade, not re-verified).
- **Friday 10/23**: **cannot be judged** — no Friday credit, ETF, CDS or MOVE data was retrievable in this run. State of knowledge is "unknown", not "did not confirm".

### Credit thresholds to apply when the desk's own feed updates (UNVERIFIED rules of thumb)

| Signal | Non-confirmation (de-gross is equity-internal) | Confirmation (broadening) |
|---|---|---|
| HY OAS daily change | within roughly ±10 bp | widening of 15–25 bp or more on the day, or 30 bp+ cumulative over 10/22–10/26 |
| HY OAS percentile vs. the desk's own history | stays in the same decile it was in on 10/21 | jumps a decile or more |
| IG OAS | within ±3 bp | +5 bp or more in a day |
| CCC minus BB spread | flat | widens faster than headline HY (lowest-quality stress) |
| HYG / JNK | within ±0.3% | -0.75% or worse on a day when SPX is down less than 1% |
| LQD | moves with the 10Y only | falls while the 10Y rallies (spread-driven) |
| Single-name CDS (META, ORCL, AMZN; CoreWeave as the levered neocloud proxy) | drift of a few bp | 10 bp+ wider in a day on ORCL or AMZN; CoreWeave widening materially more than the hyperscalers |
| MOVE | holds below where it was on 10/21 | rises into the FOMC (10/28) and the 2y/5y/7y auction week together with HY widening |

Weekend AI-capex financing: the specific thing to check is whether any announced hyperscaler, neocloud or data-centre debt deal was **pulled, downsized or repriced wider**; a deal that prints on schedule at or inside talk is non-confirmation. NOT FOUND in this run.

---

## 3. Monday sequence for the desk (times EDT; COMPUTED clock, UNVERIFIED judgments)

| When | What to look at | Reading |
|---|---|---|
| Sun 20:00 | KRX open; first 30 min of foreign net flow (KRX / Naver Finance preliminary), Samsung and SK hynix separately | Foreign net buy in the two chip names on a down tape = unwind exhausted; renewed heavy selling = resuming |
| Sun 21:00 | Does TWSE open? If yes, TAIEX gap vs. the two-session US SOX move it missed; TSM ADR implied vs. 2330.TW | Catch-up smaller than the implied gap = buyers waiting; full catch-up with no bounce = resuming |
| Sun 21:30–Mon 02:30 | KOSPI vs. Friday's intraday low; USDJPY direction; NQ futures vs. ES futures ratio from the Globex reopen | Yen strength + NQ underperformance together = macro de-gross; NQ/ES stable while KOSPI weak = Korea-specific |
| Mon ~morning (timing UNVERIFIED) | Goldman Prime weekly (via Bloomberg) for the week to 10/23: tech net flow, net leverage, short-sale/long-buy ratio, short leverage percentile | Short sales still ~5x long buys and short leverage at the 99th percentile (CONTEXT levels as of 10/22) = squeeze fuel is intact; a drop in short additions and a rise in long buys = de-gross slowing |
| Mon by 08:00 | FRED 10/23 HY and IG OAS prints in the desk's existing feed; HYG/JNK/LQD pre-market; MOVE | Apply thresholds in Section 2 |
| 09:30–10:30 | Breadth: RSP minus SPY intraday; SOX members up/down count at 10:00; 1-minute relative-volume surges on the desk's 144-name universe (3x+) in **calls** vs. **puts** | 10/22 pattern was all-30-down with the average stock up. A repeat (narrow, all-down semis, positive breadth) = de-gross still running; semis mixed with breadth positive = slowing |
| Intraday | VIX term structure (contango held at ~19 on 10/22, CONTEXT); 10Y vs. 5% | VIX front inverting while HY widens would be the first sign of a broader regime change; contango holding with semis weak keeps this an equity-positioning story |

Event risk in the week (CONTEXT): FOMC 10/28; MSFT and GOOGL 10/28; GDP and PCE 10/29; AMZN and INTC 10/29; BoJ 10/30; month-end 10/30; 2y/5y/7y auctions. For a seconds-to-hours options desk, Monday is the only full session before the FOMC blackout lifts and mega-cap prints begin, so Monday's flow read (Goldman Prime, KRX foreign flows, credit non-confirmation) is the cleanest window to decide whether to lean long calls on squeeze setups or stay with puts on relative-volume breakdowns.

---

## 4. Items that must be filled by a follow-up (ordered by Monday usefulness)

1. KRX Friday full-day investor-type flows (foreign/institution/retail, won) with Samsung and SK hynix breakdown; KOSPI and KOSDAQ closes.
2. TWSE reopening date (Mon 10/26 or Tue 10/27) and typhoon status; TSM ADR Friday close.
3. FRED HY/IG/CCC OAS for 10/21–10/23; HYG/JNK/LQD Friday; CDX HY/IG; MOVE.
4. US Friday closes (SOX, Nasdaq Composite, S&P 500, VIX) — needed to size any Taiwan catch-up gap.
5. SK hynix Q3 2026 earnings date and consensus; Samsung Q3 final results date.
6. USDJPY Friday close and BoJ 10/30 pricing; Nikkei, Hang Seng, Shanghai Friday closes.
7. Weekend AI-capex financing headlines; Meta/Oracle/CoreWeave/Amazon CDS.

---

## Sources

No source was readable in this run. Attempted and failed (all policy-blocked or DNS-unresolvable from this sandbox):

- https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2,BAMLC0A0CM,BAMLH0A3HYC&cosd=2026-10-01 (proxy 403 / ENOTFOUND)
- https://fred.stlouisfed.org/series/BAMLH0A0HYM2 (ENOTFOUND)
- https://www.twse.com.tw/en/ (proxy 403 / ENOTFOUND)
- https://www.krx.co.kr/main/main.jsp (proxy 403 / ENOTFOUND)
- https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm (proxy 403 / ENOTFOUND)
- https://www.ice.com/report/MOVE (proxy 403)
- https://www.cboe.com/tradable_products/vix/ (proxy 403)
- https://news.skhynix.com/ (proxy 403 / ENOTFOUND)
- https://www.reuters.com/markets/asia/ (fetch refused)
- https://www.cnbc.com/world-markets/ (ENOTFOUND)
- WebSearch: 8 queries submitted, 0 executed (per-turn budget of 200 shared across agents already consumed).

Background figures cited as CONTEXT were supplied by the workflow from the 10/22 research (Bloomberg on Goldman Prime 10/19 and 10/22; JPMorgan 10/21; Korean market reports 10/22–10/23) and were not re-verified here; no URLs for them are available to this agent.