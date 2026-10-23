# Credit, funding and cross-asset lens — 2026-10-22 session (de-grossing episode 2026-10-14 → 10-22)

## 0. What could and could not be retrieved this turn (read first)

- **Web search**: the shared per-turn budget (200 calls across all agents) was already exhausted before my first query, so zero searches ran.
- **WebFetch / curl**: every data and news host was policy-denied at the egress proxy (CONNECT 403): fred.stlouisfed.org, api.stlouisfed.org, markets.newyorkfed.org, federalreserve.gov, home.treasury.gov, cboe.com, ice.com, data.nasdaq.com, stooq.com, api.coingecko.com, x.com, google.com, yahoo, reuters, bloomberg, cmegroup, nyse. The owner's credit page (`oid-mini.tail3d8d4d.ts.net/credit`, Tailscale) is unreachable from this environment. GitHub REST reached only the configured repo (`jeffbazar/oid-trading-desk`), whose upstream has no commit after 2026-10-05.
- **Consequence**: nothing below is VERIFIED from a web page this turn. Labels used:
  - **LOCAL** = read from the desk's own repo files (path and file stamp given). These are the desk's own prior pulls, not fresh data.
  - **EXTRACT** = inherited from the sibling briefs, which were themselves snippet-only; not re-read by me.
  - **UNVERIFIED** = my inference, a rule of thumb, or a pre-cutoff fact recalled from memory and not re-read this turn (numbers marked "approx.").
- **Bottom line on the data request**: HY OAS, IG OAS, CDX HY/IG, HYG day moves, SOFR, SRF usage, cross-currency basis, USDJPY, MOVE, gold and bitcoin for 2026-10-14 → 10-22 were **not retrievable**. I say so in each row rather than fill from memory. The framework, lag structure and the honest edge assessment do not depend on those readings; the "how wide did HY get" question does, and stays open.

## 1. Last known readings for the credit and cross-asset set

| Metric | Last reading I can stand behind | Observation date | Label | Source |
|---|---|---|---|---|
| HY OAS (BAMLH0A0HYM2) | **2.70%**, Δ1y −0.09, 11th percentile of ~10y, Q1 ("soft-calm") | desk pull stamped 2026-10-02 1:02 PM PT; FRED observation most likely 2026-10-01 (lag, see §4) | LOCAL | `/home/user/oid-trading-desk/data/raw/data-sources.html` line 119; `/home/user/oid-trading-desk/data/snapshot.json` card "Credit spreads (FRED OAS)" |
| IG OAS (BAMLC0A0CM) | **0.78%**, Δ1y +0.02, 16th percentile, Q1 | same | LOCAL | same, line 120 |
| HY/IG OAS 2026-10-14 → 10-21 | **not retrieved** | — | — | FRED blocked; no sibling value |
| CDX HY / CDX IG | **not retrieved**; no sibling value | — | — | — |
| CoreWeave 5y CDS | > 1,140 bp | 2026-10-15 | EXTRACT | sibling cites Reuters Oct 16 / CNBC Oct 15; URL not supplied |
| Meta 5y CDS | "at all-time highs" after Q3 print (negative FCF −$2.12B, capex $135–145B) | 2026-10-22 | EXTRACT | sibling cites Bloomberg live blog / CNBC; URL not supplied |
| HYG day move | **not retrieved** for Oct 14–22. Desk's own macro feed had "No premarket read" for `credit_HYG_day` on 10-05 | — | LOCAL | `/home/user/oid-trading-desk/market-data/latest/macro-morning.json` |
| 10Y UST | 4.96% (2026-09-22, FRED/UW) → ~5.26–5.28% premarket 2026-10-05, 30Y ~5.62% ("20+ year high"; FedWatch ~80% hold Oct, Dec hike largely priced) | as stated | LOCAL | `data-sources.html` line 121; `macro-morning.json` `rates_note` |
| 10Y UST, mid-Oct | ~5.10–5.12% mid-Oct; back above 5.1% on relief day 10-19; **fell below 5.00% on 10-22, first time since 09-23** | as stated | EXTRACT | sibling (Reuters/CNBC); URL not supplied |
| USDJPY / DXY | USDJPY ~158.1–158.3, DXY ~102.5 (+0.6% "safe-haven bid amid global bond selloff: record JGB yields, France") | 2026-10-05 premarket | LOCAL | `macro-morning.json` metric `USD_DXY_or_USDJPY` and driver 3 |
| USDJPY Oct 14–22 | **not retrieved** | — | — | — |
| VIX | 15.31 close 10-02; **17.31 at 2026-10-20 1:14:46 PM PT** (FlashAlpha tile); closes per sibling: 16.87 (10-14), 16.46 (10-15), 19.99 (10-16, intraday high 22.31), 18.44 (10-19), 17.31 (10-20), 16.68 (10-21, below VIX3M 18.72), ~19.03 (10-22, intraday high 20.30) | as stated | LOCAL for 10-02 and 10-20 (`docs/strategy-2026-10-21/map-ui.md` line 13); EXTRACT for the rest | — |
| Oil | WTI CLZ26 $99.18 (+1.39%), Brent BZZ26 $110.39 (CME front-month via FlashAlpha) | 2026-10-20 | LOCAL | `map-ui.md` line 13 |
| MOVE, SOFR, SRF take-up, cross-currency basis, gold, bitcoin | **not retrieved**; no sibling values | — | — | — |

Note on the desk's own pipeline (LOCAL): the FRED feeds `fred-hy-oas` / `fred-ig-oas` have TTL 86,400 s and were in **CARRY** status with last success 2026-10-02 in the imported snapshot (`data-sources.html` lines 119–123). The macro bot explicitly does **not** use FRED OAS as its credit input; it uses `credit_HYG_day` (`/home/user/oid-trading-desk/macro/README.md` "Not applicable yet"; `docs/HANDBOOK-ERRATA.md` row 14). If the oid-mini credit page inherits that pipeline, check its observation stamp before trusting the percentile.

## 2. What the available cross-asset tape says about the nature of this selloff (UNVERIFIED inference on EXTRACT/LOCAL inputs)

1. **Treasuries rallied on the worst equity day** (10Y < 5% on 10-22 while Nasdaq −2.6%, SOX −6.7%; EXTRACT). That is the flight-to-quality pattern, not the "stocks down, yields up" pattern of April 2025 / March 2020 that marks basis-trade or margin-driven forced deleveraging. A stock-bond correlation that turns negative on the down day is the single strongest public tell that this is an **equity-positioning de-gross, not a funding event**.
2. **Vol structure did not escalate on the second leg**: VIX high 20.30 on 10-22 vs 22.31 on 10-16; VIX below VIX3M on 10-21 (EXTRACT). Contango through a −6.7% SOX day says the vol market is pricing a sector event, not a systemic one.
3. **Breadth inverted on the down day**: "average stock rose", NYSE adv/dec ~1:1 on 10-22, rotation into staples/utilities/health care (EXTRACT). True deleveraging sells everything (Aug 5 2024, Mar 2020); rotation is positioning.
4. **The visible credit stress is idiosyncratic**: CoreWeave CDS > 1,140 bp and Meta CDS at highs (EXTRACT) are the AI-capex funding channel, not index HY. This is the one credit channel that can lead a subset of a 144-name tech universe (neoclouds, memory, optical, AI-capex beneficiaries), see §8.
5. **Open question**: without HY/IG OAS for 10-14 → 10-21 I cannot rule out a meaningful HY widening. Rule of thumb for when you fill the gap (UNVERIFIED): HY OAS within ~+30–40 bp of 2.70 and IG within ~+10 bp of 0.78 over the week = credit not confirming; HY > ~3.5% (+80 bp) = credit confirming, and the episode's time scale lengthens.

## 3. Metric catalogue: what each one tells you, when it exists, what it costs

### 3a. Credit spreads

| Metric | Reads | Timing | Cost | Notes (UNVERIFIED unless stated) |
|---|---|---|---|---|
| ICE BofA HY OAS, IG OAS (FRED) | regime level and percentile | daily, **prior business day**, posted next morning (§4) | free | End-of-day dealer marks; partly stale, so the daily change contains yesterday's equity move. Regime only. |
| CDX HY / CDX IG 5y (S&P/Markit) | the only continuously traded index-credit price | real-time US hours | paid (Bloomberg CDX HY CDSI GEN 5Y / CDX IG; Tradeweb, MarketAxess); EOD on S&P site with login; press quotes free | Moves with ES within seconds; same information, no lead. CDX HY quoted in price, CDX IG in spread; series roll Mar/Sep. |
| HYG, JNK (HY ETFs), LQD (IG ETF) | credit + duration + ETF flow | real-time | free | HYG ≈ 3.5–4y duration: on a day 10Y falls 10 bp HYG can be flat while spreads widen. Strip rates before reading it (next rows). |
| **HYGH** (rate-hedged HY), **LQDH** (rate-hedged IG) | ~pure spread exposure intraday | real-time | free | Thin volume; use quotes (mid) not prints. Best free intraday OAS proxy. |
| HYG% − IEI% ; LQD% − IEF% | duration-adjusted spread proxy | real-time | free | Buildable from the desk's existing Alpaca SIP snapshots. Calibrate the coefficient on the desk's own 10y FRED history (§9). |
| HYG premium/discount to iNAV | forced one-way selling in credit | real-time (iNAV every 15 s on most platforms; EOD on iShares product page) | free | Discount beyond ~0.5% intraday = liquidation; Mar 2020 HYG traded ~5% below NAV (approx., recalled). |
| HYG options: put volume, put/call, IV30 vs VIX | macro-hedge demand in credit | real-time (broker), delayed/EOD on CBOE | free/delayed | HYG IV normally a fraction of VIX; a HYG IV spike relative to VIX = credit-specific fear. |
| BKLN / SRLN (leveraged loans), FALN / ANGL (fallen angels) | lower-quality credit, LBO-funding channel | real-time | free | Loans are floating-rate, so no duration noise; slow to mark. |
| BDC / private-credit equities (ARCC, OBDC, FSK, BIZD; BX, ARES, OWL, APO) | private-credit stress, relevant to AI data-centre financing | real-time | free | Equity proxies for a market that otherwise has no intraday print. |
| Single-name CDS: CRWV, ORCL, META; neocloud bonds | the AI-capex funding channel | real-time (Bloomberg CDS), TRACE prints delayed on FINRA public site | paid for CDS; TRACE free, delayed | The only credit series that can plausibly *lead* names in this universe (§8). |

### 3b. Funding and balance-sheet stress

| Metric | Reads | Timing | Cost | Normal vs stress (UNVERIFIED rules of thumb) |
|---|---|---|---|---|
| SOFR vs IORB; SOFR 99th pct − median | reserve scarcity, dealer balance-sheet | NY Fed, ~8:00 AM ET for **prior** day | free | SOFR at or a few bp above IORB is normal in a reserves-"ample-to-scarce" regime; sustained > +10 bp on ordinary days = stress. **Seasonal**: the Oct 15 corporate tax date and mid-month coupon settlement push SOFR up around 10-15/10-16 every year. Do not read that as de-grossing. |
| TGCR / BGCR; DTCC GCF Treasury index | same, GC repo | prior day | free | — |
| Standing Repo Facility take-up | dealers paying the ceiling rate | results shortly after each op (afternoon op 1:30 PM ET; a morning op also exists) | free | Multi-billion take-up on a non-month-end day = balance-sheet stress. Pre-cutoff context (approx., recalled): SRF usage spiked at 2025 quarter/month-ends; the Fed ended QT 2025-12-01 and began reserve-management T-bill purchases. Not re-read. |
| H.4.1 (reserves, SRF outstanding, discount window) | weekly plumbing | Thu 4:30 PM ET | free | Weekly, lagged; regime only. |
| 10y/30y SOFR swap spreads | balance-sheet scarcity / basis-trade unwind | real-time | paid (Bloomberg); FRED has no intraday | Swap spreads lurching more negative while stocks fall = deleveraging of levered Treasury positions (Apr 2025 pattern, approx. recalled). |
| SOFR futures vs fed-funds futures; 3m T-bill − OIS; CP − OIS (Fed CP rates, daily) | term funding premium | real-time (CME) / daily | CME data paid-ish; CP free, lagged | FRA-OIS is gone with LIBOR; these are the replacements. |
| Cross-currency basis (USDJPY, EURUSD 3m) | offshore dollar funding scarcity | real-time | paid (Bloomberg) | Q4 "turn" widening is seasonal; a sharp intraday move with JPY strength is the carry-unwind tell. |
| CFTC COT: leveraged funds in NQ/ES/2y/10y | positioning and basis-trade size | Fri 3:30 PM ET for Tuesday | free | Weekly, 3-day lag. |
| Prime-broker leverage and de-gross pace (GS, MS, JPM) | the actual de-gross flow | T+1 to clients; press T+2 to T+5 | prime-broker-only | The only direct pace metric that exists. GS: Oct 15 de-grossing "roughly half" of Oct 14 (EXTRACT, sibling citing Reuters). |
| OFR Hedge Fund Monitor; Fed SCOOS | leverage, financing terms | quarterly, months lag | free | Regime only. |

### 3c. FX, rates, risk proxies

| Metric | Reads | Timing | Cost | How to read it on a de-gross day (UNVERIFIED) |
|---|---|---|---|---|
| USDJPY (spot, 6J futures), JGB 10y, BoJ calendar | yen-carry channel | 24h | free | Carry unwind = JPY **strengthens** before/with US equity weakness, Nikkei −5%+, VIX futures backwardation. USDJPY firm or rising while stocks fall = not carry. |
| MOVE | Treasury implied vol; collateral haircuts | ICE EOD; Yahoo ^MOVE delayed; intraday on Bloomberg | free (EOD) / paid | <100 calm; 100–120 elevated; >130 funding-relevant (approx. levels recalled: ~120 Aug 2024, ~140 Apr 2025). |
| 10Y, 2s10s, TLT/IEF intraday | stock-bond correlation sign | real-time | free | Yields **down** with stocks down = healthy hedge, positioning selloff. Yields **up** with stocks down = forced deleveraging or inflation shock; do not fade. |
| DXY, EURUSD | dollar funding demand | real-time | free | Dollar up sharply + JPY up = global de-risking; dollar flat = sector story. |
| Gold, silver | liquidation vs safety | real-time (futures 23h) | free | Gold **down** on a stock-down day = margin-call selling of winners (liquidation); gold **up** = flight to safety. |
| Bitcoin, ETH | 24/7 liquidity and risk appetite | continuous | free | Only risk asset that prints over the weekend; a BTC −5% overnight with ES −1% says liquidity is being pulled, not just tech rotated. High noise. |

## 4. Lag structure: why FRED OAS is a next-day number, and what fills the gap

- **FRED OAS** (BAMLH0A0HYM2 / BAMLC0A0CM): ICE BofA indices are priced at the US close; FRED posts the observation the **following business day** (morning, US Central time). So on the morning of Thu 2026-10-22 the newest observation is Wed 2026-10-21; Thursday's own spread appears Friday. **I could not open the FRED page to confirm the exact posting hour this turn** (host blocked). Confirm it yourself by reading the "Updated:" stamp on https://fred.stlouisfed.org/series/BAMLH0A0HYM2 and, for a permanent record of the lag, the vintage dates on ALFRED (https://alfred.stlouisfed.org/series?seid=BAMLH0A0HYM2). Label: UNVERIFIED (high confidence on the one-business-day lag, not re-read).
- **The desk compounds the lag**: `refresh_market_tape.py` caches the FRED CSV with TTL 86,400 s and falls back to the prior block on failure (LOCAL, `/home/user/oid-trading-desk/dashboard/refresh_market_tape.py` lines 155–165, 501–560). A pull at 1 PM PT reused the next morning is two observations stale. Re-pull at ~9:15 AM ET daily and store the observation date next to the level.
- **SOFR/TGCR/BGCR**: ~8:00 AM ET, prior day (UNVERIFIED recall of the NY Fed schedule).
- **SRF**: results posted after each operation the same day (UNVERIFIED on exact minutes).
- **MOVE**: ICE end-of-day; intraday only on paid terminals.
- **CDX**: continuous intraday on paid venues; nothing free intraday.
- **Intraday fills for the OAS gap**, in order of signal quality: CDX HY/IG (paid) > HYGH/LQDH mid (free, thin) > HYG−IEI and LQD−IEF (free, liquid, needs calibration) > HYG alone (what the macro bot uses now; duration-contaminated).

## 5. Credit versus equity divergence: what the evidence actually supports

- **Direction of information flow at daily frequency runs equity → credit, not credit → equity.** Hilscher, Pollet and Wilson, "Are Credit Default Swaps a Sideshow? Evidence That Information Flows from Equity to Credit Markets," *Journal of Financial and Quantitative Analysis* 50(3), 2015: equity returns predict CDS changes at daily/weekly horizons; CDS changes do not predict equity. Norden and Weber, "The Co-movement of Credit Default Swap, Bond and Stock Markets," *European Financial Management* 15(3), 2009: stock returns lead CDS and bond-spread changes. (UNVERIFIED: recalled pre-cutoff references, not re-read this turn.)
- **The exception is name-specific**: Acharya and Johnson, "Insider Trading in Credit Derivatives," *Journal of Financial Economics* 84(1), 2007: CDS lead equity only for high-spread, distressed names around credit-relevant news (bank private information). That exception is exactly CoreWeave/neocloud-type credits, not NVDA or the index (UNVERIFIED, recalled).
- **Index OAS has a mechanical lag**: end-of-day dealer marks mean part of today's OAS change is yesterday's equity move catching up. A "credit confirms" print on T+1 is partly arithmetic.
- **Macro horizon only**: Gilchrist and Zakrajšek, "Credit Spreads and Business Cycle Fluctuations," *AER* 102(4), 2012: the excess bond premium predicts activity at monthly–quarterly horizons. Regime, not intraday (UNVERIFIED, recalled).
- **Analogues for "equities fall, credit does not confirm"** (all approx., recalled, verify on FRED before quoting):
  - Jul 10–17 2024 megacap-to-small-cap rotation: NDX ≈ −8%, HY OAS ≈ flat at ~3.0–3.1; NDX at new highs by year-end.
  - Jan 27 2025 DeepSeek day: NVDA −17%, SOX −9%, HY OAS ≈ unchanged; NDX recovered within weeks.
  - Aug 2024 yen-carry unwind: HY OAS ~3.05 (Jul 31) → ~3.93 (Aug 5), ≈ +88 bp in three sessions, IG ~0.93 → ~1.11; spreads back near ~3.2 within ~2 weeks and SPX at a new high in September.
  - Apr 2025 tariffs: HY ~3.2 → ~4.6 (Apr 7) **with 10Y rising**, the forced-deleveraging signature; recovered by mid-May.
  - Dec 2018: HY to ~5.3–5.4 with an equity bear; fundamental, took months.
  - Pattern: when HY stays within a few tens of bp and the bond market rallies, the equity drawdown is positioning and retraces fast; when HY widens >100 bp and funding metrics move, the time scale is weeks. The read is available only on T+1 OAS or intraday via CDX/HYGH, so it is a **confirmation**, never a same-day predictor.

## 6. The yen-carry channel

- **August 2024 analogue** (approx., recalled, not re-read): BoJ hike to 0.25% on 2024-07-31; USDJPY from ~161.9 (Jul 3) to ~141.7 (Aug 5); Nikkei −12.4% on Aug 5, +10% Aug 6; VIX intraday ~65 on Aug 5; SPX −3.0%; bitcoin to ~$49k; HY OAS +88 bp in three sessions. Signature: **JPY strength led and accompanied** US equity weakness; VIX term structure inverted; everything sold at once; the whole thing retraced within three weeks because it was leverage, not earnings.
- **October 2026 as far as visible**: USDJPY ~158 and "record JGB yields" with a **global bond selloff** on 2026-10-05 (LOCAL), i.e. the yen was weak and the dollar bid going into the episode, the opposite of a carry unwind. KOSPI −7.6% (10-15) and −3.5% (10-22), Nikkei −2.65% (10-22) (EXTRACT) came with GS PB describing Korea/Taiwan AI-long unwinds (EXTRACT). I have **no USDJPY reading for 10-14 → 10-22**. If USDJPY held ~155–160 through the week, this is an Asian AI-equity positioning unwind transmitting into US semis, not a funding-currency unwind.
- **Intraday watch**: USDJPY 1-min and 6J volume from the Tokyo open; Nikkei futures overnight; JGB 10y; the BoJ meeting date (check the calendar, late October is a scheduled meeting month). Trigger (UNVERIFIED): JPY +2% on the day with Nikkei −3% or worse and VIX > VIX3M = carry signature, size down and stop fading.

## 7. Funding stress: how to avoid a false positive this week

- The Oct 15 corporate tax date and mid-month coupon settlement drain reserves every year; a SOFR print above IORB for 10-15/10-16 is seasonal (UNVERIFIED rule of thumb). The de-gross signal in funding is a **non-seasonal** SRF take-up or SOFR dispersion on an ordinary day like 10-20 or 10-21.
- In a 5%-handle 10Y / 5.6% 30Y regime with a December hike partly priced (LOCAL, 10-05), the relevant "funding" question for a tech-options desk is less dealer repo and more the **AI-capex financing channel**: hyperscaler IG issuance, neocloud HY and private credit, and the CDS prints on CRWV/ORCL/META. That is where credit can transmit into this universe within the session.

## 8. The one place credit can lead this universe: the AI-capex credit channel

- CoreWeave 5y CDS > 1,140 bp on 10-15 and Meta CDS at highs after a negative-FCF quarter and a $135–145B capex guide on 10-22 (EXTRACT) are the market pricing the funding of the AI build-out. Per the Acharya-Johnson exception, distressed-spread names are where credit holds information equities do not yet have.
- **Build a watch**: CRWV, ORCL, META 5y CDS (paid), CRWV/ORCL bond prices via TRACE (delayed), and the equity proxies that already sit in or near the 144-name universe: CRWV, NBIS, IREN, APLD, WULF, plus the data-centre lenders (BX, ARES, OWL, BDCs). A credit headline (financing pulled, covenant, CDS gap) in one of these shows up as a 1-minute rvol surge in the equity, which is the desk's existing entry trigger. Credit here is a **news-first-seen flag** feeding the existing scorer, not a separate signal.

## 9. Making the desk's HYG input informative (concrete, buildable)

1. Replace `credit_HYG_day` with **HYG% − IEI%** (and LQD% − IEF%) from the existing Alpaca SIP snapshots; add HYGH mid as a cross-check.
2. Regress next-day FRED ΔHY OAS on same-day (HYG−IEI) over the desk's 10y FRED history (already pulled by `refresh_market_tape.py`) to get a **nowcast OAS tile** with its own standard error. That removes the one-day lag and gives a percentile that moves intraday.
3. Store the FRED observation date and the ALFRED vintage date beside the level so the page shows "HY 2.70 (obs 10-01, posted 10-02)" instead of a bare number.
4. Regime flags for the session (UNVERIFIED thresholds, calibrate on the regression):
   - **Credit not confirming**: HYG−IEI > −0.3% while ES ≤ −1%, 10Y yield down, VIX < VIX3M. Positioning selloff; capitulation prints in single names are fadeable; call entries on rvol-surge flushes are in regime.
   - **Credit confirming**: HYG−IEI ≤ −0.75%, HYG at a discount to iNAV, HYG put volume elevated. Beta shock; favour puts, do not fade.
   - **Deleveraging**: the above plus 10Y yield **up** on the day, MOVE > 130, SOFR−IORB > +10 bp on a non-seasonal day, USDJPY −2%, gold down with stocks. Cut size; the day-after-Aug-5 pattern.

## 10. Verdict: one-day predictive value for a same-day tech options desk

- **No demonstrated intraday predictive edge from credit.** The daily-frequency evidence runs equity → credit; index OAS is a stale-marked, T+1 series; CDX moves with ES within seconds and carries no lead; HYG as used today is dominated by duration. For a +10–20%, seconds-to-hours book on 144 names, credit cannot tell you *when* a flush ends.
- **Genuine value is as a regime gate**, set pre-open and re-checked at 10:00 ET: it decides the session's lean (calls vs puts), size, and whether single-name capitulation is fadeable. On the evidence available (Treasuries rallying on the worst day, VIX contango, breadth positive, idiosyncratic rather than index credit stress), the gate for 10-22/10-23 reads "positioning de-gross, credit not confirming", with the explicit caveat that the actual HY/IG OAS prints for the week are unretrieved.
- **The only direct pace metric for de-grossing is prime-broker flow** (GS: Oct 15 ≈ half of Oct 14; EXTRACT), available T+1 to clients and later in the press. Credit does not measure de-grossing pace; equity microstructure does (short-covering in high-short-interest names vs long-selling in hedge-fund-VIP names, intraday reversal frequency, close-vs-VWAP), which is another lens's territory.
- **The exception worth the desk's time**: single-name AI-capex credit (CRWV/ORCL/META CDS and bonds) as a news-first-seen input to the existing rvol-surge scorer.

## 11. Session checklist for 2026-10-22 (ET; cost in brackets)

| Time | Check | Why |
|---|---|---|
| 07:30–09:25 | ES/NQ vs 10Y direction; USDJPY vs Tokyo fix; Nikkei/KOSPI close; BTC overnight; gold; Brent | classify the day: flight-to-quality vs deleveraging vs sector |
| ~08:00 | SOFR, TGCR for 10-21 [free]; compare to IORB; note it is post-tax-date | non-seasonal funding stress? |
| ~09:00 | FRED HY/IG OAS for 10-21 [free]; record obs date and posting stamp (confirms §4) | close the biggest data gap in this report |
| 09:30–10:00 | HYGH mid, HYG−IEI, LQD−IEF, HYG iNAV premium, HYG put volume [free]; CDX HY/IG if available [paid] | intraday OAS nowcast; set the regime flag |
| 10:00 | Re-gate: VIX vs VIX3M, 10Y, DXY, gold | lean and size for the session |
| 13:30–13:45 | SRF operation results [free] | balance-sheet stress on a non-month-end day |
| Close | MOVE close, HYG−IEI close, VIX term structure | T+1 regime read for Friday |
| Thu 16:30 | H.4.1 [free] | weekly plumbing |
| Fri 15:30 | CFTC COT leveraged funds NQ/ES [free] | positioning as of Tuesday |
| Mon/Fri press | GS/MS prime-broker weekly via Reuters/Bloomberg [press free, data PB-only] | the only direct de-gross pace metric |

## Sources

**LOCAL (read this turn, desk repo)**
- `/home/user/oid-trading-desk/data/raw/data-sources.html` lines 119–123 (FRED HY/IG OAS feeds, CARRY, stamp 2026-10-02 1:02 PM PT; 10Y 4.96% as of 2026-09-22)
- `/home/user/oid-trading-desk/data/snapshot.json` card "Credit spreads (FRED OAS) HY 2.70 Δ1y −0.09 · 11th · Q1 IG 0.78 Δ1y +0.02 · 16th · Q1"
- `/home/user/oid-trading-desk/market-data/latest/macro-morning.json` (2026-10-05: 10Y ~5.26–5.28%, 30Y ~5.62%, USDJPY ~158.1–158.3, DXY ~102.5, VIX 15.31 at 10-02 close, `credit_HYG_day` "No premarket read", indicator logic "HY OAS Q4 → −1")
- `/home/user/oid-trading-desk/macro/README.md` and `/home/user/oid-trading-desk/docs/HANDBOOK-ERRATA.md` row 14 (FRED OAS not the macro credit input; HYG day is)
- `/home/user/oid-trading-desk/dashboard/MARKET-TAPE.md` and `/home/user/oid-trading-desk/dashboard/refresh_market_tape.py` (FRED CSV URLs, 86,400 s TTL, percentile logic)
- `/home/user/oid-trading-desk/docs/strategy-2026-10-21/map-ui.md` line 13 (VIX 17.31 at 2026-10-20 1:14:46 PM PT; WTI 99.18, Brent 110.39 on 2026-10-20)

**EXTRACT (sibling briefs; not re-read; URLs as the siblings supplied them, none opened this turn)**
- Bloomberg 2026-10-19, hedge funds cut tech at fastest pace in a decade (Goldman PB): https://www.bloomberg.com/news/articles/2026-10-19/hedge-funds-cut-tech-at-fastest-pace-in-a-decade-goldman-says
- CNBC live blogs 2026-10-18 and 2026-10-21: https://www.cnbc.com/2026/10/18/stock-market-today-live-updates.html ; https://www.cnbc.com/2026/10/21/stock-market-today-live-updates.html
- Bloomberg 2026-10-16, short sellers $32B: https://www.bloomberg.com/news/articles/2026-10-16/longest-chip-selloff-since-2006-mints-short-sellers-32-billion
- Yahoo/Reuters, SOX longest losing streak: https://finance.yahoo.com/technology/ai/articles/chip-index-sox-posts-longest-123436535.html
- CoreWeave CDS > 1,140 bp (10-15), Meta CDS at highs (10-22), 10Y below 5% (10-22), VIX3M 18.72 (10-21), GS "roughly half" de-gross pace: sibling cited Reuters/CNBC/Bloomberg live blog without URLs; not located this turn.

**Standard primary pages for the metrics (not opened this turn; host blocked)**
- FRED HY OAS: https://fred.stlouisfed.org/series/BAMLH0A0HYM2 ; IG OAS: https://fred.stlouisfed.org/series/BAMLC0A0CM ; CSV: https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2 ; ALFRED vintages: https://alfred.stlouisfed.org/series?seid=BAMLH0A0HYM2
- NY Fed SOFR: https://www.newyorkfed.org/markets/reference-rates/sofr ; rates API: https://markets.newyorkfed.org/api/rates/all/latest.json ; repo operations (SRF): https://www.newyorkfed.org/markets/desk-operations/repo
- Fed H.4.1: https://www.federalreserve.gov/releases/h41/ ; SCOOS: https://www.federalreserve.gov/data/scoos.htm
- CFTC COT: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- OFR Hedge Fund Monitor: https://www.financialresearch.gov/hedge-fund-monitor/
- CBOE VIX3M: https://www.cboe.com/us/indices/dashboard/VIX3M/ ; MOVE (delayed): https://finance.yahoo.com/quote/%5EMOVE/
- iShares HYG product page (iNAV, holdings): https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf

**UNVERIFIED academic references (recalled, not re-read)**
- Hilscher, Pollet, Wilson (2015), *JFQA* 50(3), "Are Credit Default Swaps a Sideshow?"
- Norden, Weber (2009), *European Financial Management* 15(3)
- Acharya, Johnson (2007), *Journal of Financial Economics* 84(1), "Insider Trading in Credit Derivatives"
- Gilchrist, Zakrajšek (2012), *American Economic Review* 102(4), "Credit Spreads and Business Cycle Fluctuations"

**Not retrieved this turn (explicit gaps)**: HY/IG OAS 2026-10-14 → 10-21; CDX HY/IG levels; HYG daily moves; SOFR/SRF/cross-currency basis readings; USDJPY, MOVE, gold, bitcoin for the week; the owner's oid-mini credit page contents. A follow-up message after this reply can re-run the searches once the per-turn budget resets, and the egress policy would need to allow fred.stlouisfed.org and markets.newyorkfed.org for direct reads.