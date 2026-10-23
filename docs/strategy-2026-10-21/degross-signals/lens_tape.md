# Breadth, tape and liquidity lens: can market internals show de‑grossing exhausting, and is there same‑day edge?

## 0. Access and labelling (read first)

- **No external page could be opened.** The shared WebSearch budget (200/turn across all agents) was already exhausted before my first query. WebFetch failed with DNS errors on every host. `curl` through the sandbox proxy returned `CONNECT 403` for ~90 hosts tried: NYSE, Nasdaq Trader, CME, CBOE (incl. cdn.cboe.com), FRED, StockCharts, WSJ, CNBC, Reuters, Bloomberg, Finviz, CNN Fear & Greed API, Lowry, SentimenTrader, Quantifiable Edges, mcoscillator.com, Barchart, Investing.com, SSRN, ScienceDirect, arXiv, Semantic Scholar, OpenAlex, Crossref, RePEc, Ken French library, Stooq, Yahoo, X, Google/Bing/DDG. Only `github.com` / `raw.githubusercontent.com` (repo-scoped API) and `pypi.org` were reachable.
- **Labels.** VERIFIED = I read it (only two sources qualified: the desk's own repo at `/home/user/oid-trading-desk`, and the CBOE-mirror CSV `datasets/finance-vix` on GitHub, which ends **2026‑09‑22** so it does not cover the episode). EXTRACT = taken from the sibling briefs' search-snippet reconstruction (I could not confirm any of it; URLs reproduced as they gave them). UNVERIFIED = definition from memory, rule of thumb, or my arithmetic on EXTRACT numbers.
- **No Oct 12–22 breadth reading (90% days, TRIN, NYMO, new lows, % above 50‑day, MOC imbalances, ES depth) could be found from a primary source.** Where the sibling briefs carried a breadth number I repeat it as EXTRACT; otherwise I say "not findable" rather than fill in.
- Clock: the proxy log stamps this session at 2026‑10‑22T22:57Z (6:57 PM ET), i.e. after the Oct 22 close that the sibling brief already reports. Everything below applies equally to the Fri Oct 23 session.

## 1. Bottom line for a seconds‑to‑hours call/put buyer

1. **The classic capitulation statistics will not fire for this episode, and that is itself the finding.** Oct 22 NYSE advancers/decliners were 1.01:1 and the "average stock rose" while SOX fell 6.72% with all 30 members down (EXTRACT). Oct 19 the Nasdaq rose 1.11% with NYSE decliners 1,761 vs 945 advancers and RSP −0.32% (EXTRACT). This is a narrow, sector‑specific liquidation, not a market‑wide one. NYSE‑universe tools (Lowry 90% days, Zweig thrust, $NYMO, NYSE new lows, $TRIN) measure the wrong population; they can read "benign" on the day semis are being dumped. The breadth universe that matters is the desk's own 144‑name tech/semi list (or SOX's 30 members), computed intraday from the 1‑minute archive the desk already has (VERIFIED: 82,190 ticker‑minutes of 1‑min SIP bars, 9/25–10/20, on the data mini; `docs/strategy-2026-10-21/map-research.md` line 67).
2. **Nothing in the breadth toolkit has documented same‑day predictive value for "the de‑grossing is over."** Breadth/capitulation statistics are end‑of‑day signals with multi‑week horizons (UNVERIFIED, from the Lowry/Zweig/McClellan literature as I remember it). The intraday effects with published academic support are (a) market intraday momentum: the first half‑hour's return predicts the last half‑hour's, stronger on high‑volatility, high‑volume days (Gao, Han, Li, Zhou, *JFE* 2018; UNVERIFIED from memory, could not open), and (b) the overnight/intraday split: institutions trade intraday, retail overnight (Lou, Polk, Skouras, *JFE* 2019; UNVERIFIED). Both are about the *shape of the day*, not about whether a multi‑day liquidation is finished.
3. **The signature of de‑grossing still in progress, in this episode (EXTRACT):** worst days closed at or near the lows (Oct 14 "declines of more than 2% late in the day"; Oct 16 SOX −3.83% eighth straight; Oct 22 SOX −6.72%, lowest close since Jul 29, broke ~11,000), and every bounce was sold intraday (Oct 19 SOXX +3.7% / SMH +3.2% intraday → SOX closed +1.61%; Oct 21 up day with Nasdaq 216 new lows vs 53 new highs). Oct 15 was the only exhaustion‑shaped day (SOX −4.4% intraday low, closed −0.88%, CRWV 52‑week low $59.51 → +5.94% close) and it did not hold: new lows followed on Oct 16 and Oct 22. **One reversal day is not exhaustion; the tape needs a reversal day plus a session that does not take the low out, with the bounce leaders being the crowded longs rather than the most‑shorted names.**
4. **What a same‑day desk can actually use:** intraday universe internals (downside‑surge share, up‑volume share, % above VWAP, new‑20‑day‑low count per 15 min) as the **side selector and a gate on call entries**, not as a forecast of the low. These are computable tonight at zero cost from the desk's own surge lane and 1‑min bars (section 6), and must be tested against the desk's own B2 surge‑only baseline before anyone calls them edge (VERIFIED: that rule is in `docs/SCALING-STRATEGY-20261021.md`, line 251).

## 2. Metric by metric

Latency key: RT = real‑time intraday; EOD = after the close; W = weekly; M = monthly. Cost key: free / paid / PB = prime‑broker or sell‑side desk only.

### 2a. Daily breadth and capitulation statistics (NYSE/Nasdaq universe)

| Metric | What it measures (definition status) | Source, latency, cost | Same‑day predictive evidence | Recent reading |
|---|---|---|---|---|
| **Lowry 90% Downside / Upside Day** | Down volume ≥90% of (up+down) volume AND points lost ≥90% of (points gained+lost), Lowry's operating‑company‑only NYSE universe (UNVERIFIED, from memory). | Lowry Research (paid, EOD). Free approximation from WSJ Market Diary / StockCharts `$NYUPV` `$NYDNV` (EOD); real‑time only with a breadth data feed (`$VOLD` on Thinkorswim, free with account). | Desmond's 2002 Dow Award paper: lows form after a *series* of 90% down days and are confirmed by a 90% up day or two consecutive 80% up days; the first 90% down day in a decline is not the low (UNVERIFIED). I know of no evidence that the day after a 90% down day has a usable directional bias for a same‑day book. | **Not findable.** Oct 22 NYSE adv/dec 1.01:1 (EXTRACT) rules out a NYSE‑wide 90% day; SOX members 30/30 down (EXTRACT) is a 100% "down day" in the relevant universe. |
| **Zweig Breadth Thrust** | 10‑day EMA of NYSE advances/(advances+declines) moves from <0.40 to >0.615 within 10 sessions (UNVERIFIED). | StockCharts `$NYAD`‑based, EOD, free. | Horizon is months. Zero same‑day content; it cannot fire until ≥10 sessions after the low. | Not findable. Oct 19 advancers 945 / decliners 1,761 → single‑day ratio ≈0.35 (UNVERIFIED arithmetic on EXTRACT), so the oversold half of the setup is plausible; irrelevant intraday. |
| **TRIN / Arms Index** (`$TRIN`, Nasdaq `$TRINQ`) | (adv/dec) ÷ (adv vol/dec vol). >1 = volume concentrated in decliners (UNVERIFIED). | RT on Thinkorswim/TradingView (free with account; delayed free on StockCharts). | Closing TRIN >2–3 has a mild next‑day bounce bias in blog studies (Quantifiable Edges style; UNVERIFIED). Intraday TRIN is noisy; its useful same‑day use is *trajectory*: TRIN falling while the index is flat = selling pressure easing. For this episode `$TRINQ` is the relevant one. | Not findable. |
| **New 52‑week lows** (NYSE `$NYLOW`, Nasdaq `$NALOW`) | Count of issues at 52‑week lows. Expansion confirms the trend; a lower peak in new lows against a lower price low is the classic divergence (UNVERIFIED). | EOD free (WSJ Market Diary, StockCharts, Barchart); RT on TradingView/StockCharts subscriptions. | Divergence has multi‑day/week horizon; no same‑day evidence. | Oct 21 (an up day): Nasdaq 216 new lows vs 53 new highs (EXTRACT). Oct 22: not findable. Named 52‑week lows: CRWV $59.51 on Oct 15, NFLX on Oct 21 (EXTRACT). Note a sibling conflict: SOX "lowest since April 2026" (Oct 16) vs "lowest close since Jul 29" (Oct 22, at a lower level) cannot both be right; unresolved. |
| **% of S&P 500 above 50‑day / 20‑day MA** | Share of constituents above the MA. Rules of thumb: <20–25% washed out in corrections, <10% in panics (UNVERIFIED). | EOD free (Barchart, StockCharts `$SPXA50R`). The desk's Chart Bot already computes SMA50/EMA21 per name daily (VERIFIED `docs/API-INVENTORY.md`), so the universe version is one script. | Multi‑week horizon; no same‑day evidence. | Not findable. |
| **McClellan Oscillator / Summation** | 19‑day EMA minus 39‑day EMA of (ratio‑adjusted) net advances; below roughly −70 ratio‑adjusted / −100 raw = oversold (UNVERIFIED). | EOD free StockCharts `$NYMO`, `$NAMO`; mcoscillator.com (paid). | Multi‑day/week horizon; none same‑day. | Not findable. |
| **Up‑volume share / cumulative A‑D / NYSE TICK** | Intraday: `$ADD` (net advances), `$VOLD` (net up‑minus‑down volume), `$TICK` (upticks minus downticks across NYSE). TICK ≤ −1000 clusters = program selling; a first +1000 print after a run of −1000s is a common exhaustion tell (UNVERIFIED rules of thumb). | RT, free with a brokerage platform (Thinkorswim), Bloomberg/Reuters paid. | Tape‑reading heuristics, no controlled evidence I can cite. The one formally documented intraday pattern is cross‑sectional periodicity: a half‑hour's return predicts the same half‑hour on following days, consistent with institutional execution schedules (Heston, Korajczyk, Sadka, *JF* 2010; UNVERIFIED). | Not findable. |

### 2b. Closing auction

| Metric | What it measures | Source, latency, cost | How to read it in a de‑grossing | Reading |
|---|---|---|---|---|
| **Market‑on‑close imbalances** (NYSE closing auction imbalance, Nasdaq NOII) | Net buy/sell imbalance of MOC/LOC orders per name, published from ~3:50 pm ET until the 4:00 cross (UNVERIFIED time; confirm on nyse.com Trading Info and nasdaqtrader.com NOII). The closing auction is a large share of daily volume (UNVERIFIED, "roughly a quarter to a third"). | Direct feeds: NYSE Pillar imbalance feed, Nasdaq TotalView‑ITCH NOII messages; vendors resell them (Databento has an `imbalance` schema for XNAS/XNYS, UNVERIFIED; the desk lists Databento as "not connected", VERIFIED). Bloomberg `IMBAL` (paid). Aggregate "$X bn to sell" re‑posts on X (free, unreliable, UNVERIFIED). Robinhood (the desk's broker) does not expose it. | Forced de‑grossing shows as large **sell** imbalances concentrated in the names being cut (SMH/SOXX members), with price already below VWAP at 3:50. Exhaustion shows as (i) sell imbalances that are *absorbed* (price rises into the bell against a sell imbalance), or (ii) the flip to buy imbalances in the same names on a down day. Since the desk is flat by the close, this is next‑day context or a 3:50–3:59 scalp only. | **No published MOC figures found for any day Oct 14–22.** Consistent with sell‑MOC pressure: Oct 14 "declines of more than 2% late in the day", Oct 16 SOX closed near the lows, Oct 22 SOX closed −6.72% (EXTRACT). |

### 2c. Block prints, program trading, off‑exchange

| Metric | Status | Source, latency, cost | Use |
|---|---|---|---|
| NYSE program‑trading report | No longer published (UNVERIFIED on the discontinuation date). | n/a | n/a |
| Block prints (≥10k shares / ≥$200k) | RT via time‑and‑sales block filters (Bloomberg, Fidelity ATP, most pro platforms; paid). | Late‑day blocks printing at/below VWAP in the names being cut = liquidation; blocks lifting the offer above VWAP after a flush = absorption (UNVERIFIED heuristics). | Confirmation only. |
| Dark‑pool / off‑exchange prints | The desk already has Unusual Whales dark‑pool trades (`uw-oe` feed, VERIFIED `market-data/README.md`). FINRA ATS transparency data is free but weekly with a lag (UNVERIFIED on the exact lag). | Same reading as blocks; the UW feed gives it intraday for the universe at no new cost. | |

### 2d. Liquidity and depth

| Metric | What it measures | Source, latency, cost | Evidence | Reading |
|---|---|---|---|---|
| **E‑mini S&P / NQ top‑of‑book depth** | Dollar value resting at best bid/offer (and a few levels), usually shown as a rolling average. Thin books amplify flows; depth recovery is necessary, not sufficient, for selling to "slow". | CME Liquidity Tool (free with registration; historical, not live; UNVERIFIED). Sell‑side/PB desk charts (Goldman, JPM "Flows & Liquidity", Deutsche Bank) reach the public only through press quotes (PB/paid). Live DOM: CME Market Depth via Sierra Chart/Bookmap/Jigsaw with a CME L2 subscription (paid, modest). | Depth is a lagging function of realised vol; it tends to come back after vol falls, so it confirms rather than predicts (UNVERIFIED). | **Not findable** for Oct 2026. |
| **VIX intraday spike‑and‑fade** | VIX high‑of‑day vs close. Popular "capitulation" tell. | RT free (desk already pulls VIX via Robinhood `get_index_quotes`, VERIFIED). | See section 4: on CBOE daily data 1990–2026‑09 the *fade* adds little beyond ordinary vol mean reversion after a spike. | Oct 16: high 22.31, close 19.99; Oct 22: high 20.30, close 19.03 (+14%); VXN 27.1 on Oct 16 (EXTRACT). |

### 2e. Overnight vs intraday return decomposition

| | |
|---|---|
| What | Split each day into overnight (prior close → open) and intraday (open → close). |
| Source / cost | Computable from any OHLC; the desk's 1‑min archive gives it per name (VERIFIED the archive exists). Free. |
| Evidence | Lou, Polk, Skouras (*JFE* 2019): institutions trade intraday, retail overnight; momentum profits accrue overnight, reversals intraday (UNVERIFIED from memory). Bogousslavsky (*JFE* 2021) on cross‑sectional intraday/overnight returns and close‑of‑day institutional rebalancing (UNVERIFIED). |
| How to read it | De‑grossing is institutional, so it is an **intraday** phenomenon: "gap down and keep going." The first mechanical sign of exhaustion is the intraday leg turning flat or positive while overnight gaps are still negative (Asia‑led gaps, as this episode has: KOSPI −7.6% Oct 15, −3.52% Oct 22, EXTRACT). |
| Episode (UNVERIFIED arithmetic on EXTRACT levels) | Oct 14: SOX day high 12,022 vs prior close 12,208.8 → opened at least −1.5%, closed −4.30% → ≥2.8 points lost intraday after the gap. Oct 15: low −4.4% vs prior close, close −0.88% → +3.7% intraday recovery (the only positive intraday leg of the slide). Oct 22: NQ −1.7% at 7:50 ET pre‑market, Nasdaq closed −2.60% → roughly −0.9% further intraday. SOX closed −6.72% on Oct 22 with no open print findable, so the decomposition cannot be completed. |

### 2f. VWAP reclaim and first‑hour range

| | |
|---|---|
| What | Whether SMH/SOXX/QQQ and the % of universe names trade above session VWAP at fixed checkpoints (10:00, 10:30, 11:00 ET), and the first‑30/60‑minute range as a fraction of 20‑day ATR. |
| Source / cost | RT, free on every platform; universe version from the 1‑min archive. |
| Evidence | Opening‑range‑breakout studies on QQQ and on high‑relative‑volume stocks report positive results (Zarattini & Aziz 2023; Zarattini, Aziz & Barbon 2024, SSRN; UNVERIFIED, could not open). Gao et al.'s first‑half‑hour → last‑half‑hour momentum is the index‑level cousin, strongest on volatile days. The desk's own Setup F is an ORB (VERIFIED `SCALING-STRATEGY` §8). Widely quoted "the first hour contains the day's high or low X% of the time" figures: **I could not verify any number; compute it from the archive.** |
| How to read it | De‑grossing day: SMH never reclaims VWAP; universe % above VWAP stays <25% all day; late‑day range expansion downward. Exhaustion candidate: gap down, heavy first‑30‑min volume, VWAP reclaimed by ~11:00 ET and held through the European close (11:30 ET), afternoon range inside the first‑hour range. |

### 2g. Behaviour of the worst and most‑crowded names

| | |
|---|---|
| What | Whether the most‑crowded longs (Goldman "Hedge Fund VIP" list; GVIP ETF tracks it, daily NAV free) or the most‑shorted names (GS most‑shorted basket, PB/press only; S3 Partners short‑interest, paid) lead the bounce. |
| Rule of thumb (UNVERIFIED) | In a de‑grossing both sides are cut: longs sold, shorts covered. The *first* bounce is therefore led by the most‑shorted/high‑beta names (covering), while crowded longs lag because funds sell into strength. The durable turn is when crowded longs show relative strength on a down index day. Short sellers' +$32B paper gains over 7 sessions (S3 via Bloomberg Oct 16, EXTRACT) is the covering fuel. |
| Episode (EXTRACT) | Oct 15: CRWV printed a 52‑week low and closed +5.94% (worst name reversing at the low of the move). Oct 21: SMCI +9.55%, SPCX +7.79% (beaten high‑beta leading the relief), NFLX −5.3% to a 52‑week low. Oct 22: the Oct 21 bounce leaders were hit hardest again (AMD +3% Oct 21 → −8.1%; LRCX −11.76%; MRVL −8.7%; NVDA −4.4%; META −6.98%). Goldman PB: net leverage 48.6% = 1‑year low; tech still 23.5% of net book = 90th percentile of 5 years; Oct 15 de‑grossing "roughly half" of Oct 14 (EXTRACT, Bloomberg/Reuters Oct 16–19). |
| Reading | Crowded‑long leadership has not appeared on any day in the record; bounces have been high‑beta/short‑covering shaped and reversed. |

## 3. Time‑of‑day pattern of institutional deleveraging

**Mechanics (UNVERIFIED, standard market structure):** multi‑strategy and pod risk limits are marked at the close, so cuts decided overnight are worked the next session with VWAP/POV algos and finished in the closing auction; vol‑targeting and CTA rebalances are also close‑weighted; prime‑broker margin calls arrive in the morning. The expected footprint is "sell the open, sell the close," with the last hour and the 3:50 pm imbalance carrying the forced portion.

**Evidence from this episode (EXTRACT):** Oct 14 losses accelerated late ("declines of more than 2% late in the day"); Oct 16 SOX closed near its lows while VIX faded from 22.31 to 19.99 (vol sellers came in, equity sellers did not stop); Oct 19 and Oct 21 bounces faded intraday; Oct 22 closed at the lows across all 30 SOX members. Oct 15's intraday reversal is the exception. **Net: the selling in this episode has been close‑weighted, which is the forced‑selling signature, and no session yet shows the "flush early, bid by 10:30, positive close" shape holding for two consecutive days.**

**Research (all UNVERIFIED from memory, none could be opened):** Gao, Han, Li, Zhou, "Market intraday momentum," *JFE* 2018 (first half‑hour predicts last half‑hour; stronger on volatile, high‑volume and news days). Baltussen, Da, Lammers, Martens, "Hedging demand and market intraday momentum," *JFE* 2021 (the effect is driven by dealer/levered‑ETF gamma hedging into the close; stronger when dealers are short gamma, which the desk can proxy with the UW index GEX sign it already has). Heston, Korajczyk, Sadka, *JF* 2010 (half‑hour return periodicity at daily lags, consistent with institutional execution schedules). Lou, Polk, Skouras, *JFE* 2019 (overnight vs intraday). Practical implication for a same‑day book: on a day that opens down hard on semis, the last half‑hour is more likely to continue the first half‑hour's direction than to reverse it; fading the open into the close is the low‑probability side on these days.

## 4. VIX spike‑and‑fade base rates (VERIFIED data, UNVERIFIED inference)

Computed from `datasets/finance-vix` (CBOE mirror, 9,278 sessions, 1990‑01‑02 → 2026‑09‑22; file at `<local path>`, script `<local path>`). Forward figures are VIX changes only; the file has no SPX, so this says nothing about equity returns.

| Condition on day t | n | VIX down next day | 5‑day VIX change (median, % down) | Last hits |
|---|---|---|---|---|
| Base rate, all days | 9,213 | 53% | median −0.4% / — | — |
| A: high ≥ +10% vs prior close, close ≤ +2% vs prior close, high is a 60‑session high (spike that faded) | 25 | 60% | −9.4%, 76% | 2020‑03‑18, 2025‑10‑17, 2026‑03‑09 |
| B: high ≥ +10%, close ≥ +8% vs prior close, 60‑session high (spike that held) | 132 | 65% | −11.6%, 70% | 2025‑10‑10/14/16, 2026‑03‑03/06 |
| C: close ≥ 8% below own intraday high, any level | 1,217 | 57% | −2.2%, 56% | 2026‑09‑02, 2026‑09‑11 |
| D: C and high ≥ 20 | 643 | 59% | −4.5%, 61% | 2026‑06‑24/26, 2026‑07‑30 |

Reading: the "VIX faded off its high so the panic is over" tell adds almost nothing beyond ordinary mean reversion after any large spike (A ≈ B on 5‑day VIX, B is actually better next‑day). Spikes cluster for 1–2 weeks (the 2025‑10‑10/14/16 and 2026‑03‑03/06/09 runs). So Oct 16's fade from 22.31 to 19.99 was not evidence the semis liquidation was done, and the tape confirmed that on Oct 22. Demote VIX‑fade to context.

## 5. Recent readings that were findable (all EXTRACT; none verified)

| Date | Reading | Source as given by sibling |
|---|---|---|
| Fri Oct 16 | SOX −3.83%, 8th straight; VIX high 22.31 close 19.99; VXN 27.1; SPX/XSP option volumes 4th/5th highest on record; monthly opex | Bloomberg Oct 16 https://www.bloomberg.com/news/articles/2026-10-16/longest-chip-selloff-since-2006-mints-short-sellers-32-billion ; Chartmill https://www.chartmill.com/news/AA/Chartmill-56386-stock-market-today-chip-selloff-day-eight-nasdaq-worst-week-2026-10-16 |
| Mon Oct 19 | Nasdaq +1.11%, SOX +1.61% (SOXX +3.7% intraday, faded); NYSE decliners 1,761 vs advancers 945; RSP −0.32%; GS PB: tech net‑sold at fastest pace since 2016, net leverage 48.6% | CNBC https://www.cnbc.com/2026/10/18/stock-market-today-live-updates.html ; Bloomberg https://www.bloomberg.com/news/articles/2026-10-19/hedge-funds-cut-tech-at-fastest-pace-in-a-decade-goldman-says |
| Wed Oct 21 | Nasdaq +1.05%, SOX +1.97%; NYSE adv/dec 1.37:1; Nasdaq 216 new lows vs 53 new highs; SMCI +9.55%, SPCX +7.79%, NFLX −5.3% 52‑wk low | CNBC Oct 21 live blog (as cited by sibling) |
| Thu Oct 22 | Nasdaq −2.60% to 26,008.86; SPX −1.21%; SOX −6.72% to 10,731.98, all 30 members down; NYSE adv/dec 1.01:1; Nasdaq dec/adv 1.37:1; VIX high 20.30 close ~19.03; rotation into staples/utilities/health care; LRCX −11.76%, AMD −8.1%, META −6.98% | CNBC https://www.cnbc.com/2026/10/21/stock-market-today-live-updates.html ; Reuters/Yahoo as cited by sibling |

## 6. What the desk can compute tonight, at zero cost, from what it already has

All inputs below are VERIFIED to exist in the desk's stack: surge‑alert lane with `▲ day_high` / `▼ day_low` and rvol multiples; the "Market momentum" detector ("names making new 15‑min highs on ≥2x volume, last 5 min vs 45‑min peak", currently shadow and reading "detector 9h old"); a 16‑group sector strip with % change and rvol; UW market tide 15‑min net premium; Chart Bot daily SMA50/EMA21 per name; 1‑min SIP bars for the universe (`docs/strategy-2026-10-21/map-ui.md` line 15; `map-research.md` line 67; `docs/API-INVENTORY.md`). Each item is a hypothesis to register against B0/B1/B2 per the desk's own program rules, not an asserted edge.

| # | Metric (universe = 144 names, or SOX 30) | Computation | De‑grossing reading | Exhaustion‑candidate reading | Thresholds are guesses to test (UNVERIFIED) |
|---|---|---|---|---|---|
| 1 | **Downside‑surge share** | (# `▼ day_low` surges ≥3x) ÷ (all surges), rolling 30 min | >70% and rising through the afternoon | Peaks in the first 60–90 min, then collapses toward 50% while SMH holds above the first‑hour low | Gate: no call entries while share >70%; put entries favoured while >70% and SMH below VWAP |
| 2 | **Universe up‑volume share** | Σ volume of names up on day ÷ Σ volume, 5‑min refresh | <15% (a 90%‑style down day *in the right universe*) | Rises through 40% by 11:00 ET on a gap‑down day | Lowry analogue, intraday, free |
| 3 | **% of universe above session VWAP** at 10:00 / 10:30 / 11:00 / 15:30 ET | per‑name VWAP from 1‑min bars | <20% at every checkpoint | <20% at 10:00 → >50% by 11:00 and held at 15:30 | Second‑day confirmation required |
| 4 | **New 20‑day lows per 15 min** | count of names printing a new 20‑session low in the bar | Count makes a higher peak in the last hour than in the first | Last‑hour count < first‑hour count on a down close (intraday Hi‑Lo divergence) | |
| 5 | **Momentum‑detector mirror** | add "names making new 15‑min lows on ≥2x volume"; publish highs÷lows ratio | ratio <0.3 all day | ratio crosses 1 and stays above for 30 min | Fix the "9h old" detector first (already a listed item, `SCALING-STRATEGY` line 394) |
| 6 | **Universe cumulative A‑D vs SMH** | cumulative (adv − dec) per 5 min vs SMH price | both making lows into the close | A‑D holds above its 10:30 low while SMH tests it | |
| 7 | **Intraday leg sign** | (close − open)/open for SMH and the universe median | negative on ≥3 of last 4 sessions | first positive intraday leg on a gap‑down open, then a second day that holds the prior low | Section 2e logic |
| 8 | **Crowded‑long relative strength** | GVIP (free daily NAV) or an in‑house list of the universe's most‑discussed longs vs SPY/SMH; intraday from quotes | underperforms on up days (sold into strength) | outperforms on a down index day | PB baskets not available; this is the free proxy |
| 9 | **First‑hour range stats** | first‑30/60‑min range ÷ 20‑day ATR; whether the first‑hour low held as day low, conditioned on SOX gap ≤ −2% | compute the base rate instead of quoting one | | Direct input to Setup F |
| 10 | **3:50 pm behaviour (next‑day context)** | SMH/SOXX last‑10‑min return vs VWAP, from quotes; or buy the imbalance feed later (Databento `imbalance` schema, UNVERIFIED) | sells off into the bell on sell imbalances | rallies into the bell against a sell imbalance | Desk is flat by close, so this is for the next morning's bias |

**Honest edge statement.** Items 1–3 are the only ones with a plausible same‑day use for this book, and their use is as a **side selector and a gate** (which way the surge continuation is more likely to run, and when not to buy calls), not as a forecast that the de‑grossing has ended. The documented same‑day effects (intraday momentum on volatile days; overnight/intraday asymmetry) say the opposite of what a bottom‑picker wants: on a day that opens down hard on forced selling, continuation into the close is the base case. Multi‑day exhaustion calls belong to the EOD statistics, and in this episode those statistics are measuring the wrong universe.

## Sources

VERIFIED (read directly)
- Desk repository `/home/user/oid-trading-desk`: `README.md`; `dashboard/MARKET-TAPE.md`; `docs/API-INVENTORY.md`; `market-data/README.md`; `macro/README.md`; `docs/SCALING-STRATEGY-20261021.md` (lines 28–130, 251–253, 354–394); `docs/strategy-2026-10-21/map-research.md` (lines 56–120); `docs/strategy-2026-10-21/map-ui.md` (line 15); `docs/strategy-2026-10-21/verification-log.md` (line 323); `market-data/latest/macro-morning.json` (as of 2026‑10‑05).
- CBOE VIX daily history mirror: https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv (last row 2026‑09‑22; fetched 2026‑10‑22).

EXTRACT (from sibling briefs; not opened by me)
- https://www.bloomberg.com/news/articles/2026-10-16/longest-chip-selloff-since-2006-mints-short-sellers-32-billion
- https://www.bloomberg.com/news/articles/2026-10-19/hedge-funds-cut-tech-at-fastest-pace-in-a-decade-goldman-says
- https://www.cnbc.com/2026/10/18/stock-market-today-live-updates.html
- https://www.cnbc.com/2026/10/21/stock-market-today-live-updates.html
- https://www.chartmill.com/news/AA/Chartmill-56386-stock-market-today-chip-selloff-day-eight-nasdaq-worst-week-2026-10-16
- https://finance.yahoo.com/technology/ai/articles/chip-index-sox-posts-longest-123436535.html
- https://x.com/KobeissiLetter/status/2111185957781221387
- https://www.gate.com/news/detail/CRWV/semiconductor-stocks-hit-lowest-level-since-april-2026-on-eight-day-losing-25064993

UNVERIFIED (from memory; could not be opened this session)
- Desmond, P., "Identifying Bear Market Bottoms and New Bull Markets," Charles H. Dow Award 2002 (Lowry 90% days).
- Gao, Han, Li, Zhou, "Market intraday momentum," *Journal of Financial Economics* 2018.
- Baltussen, Da, Lammers, Martens, "Hedging demand and market intraday momentum," *JFE* 2021.
- Heston, Korajczyk, Sadka, "Intraday patterns in the cross‑section of stock returns," *Journal of Finance* 2010.
- Lou, Polk, Skouras, "A tug of war: Overnight versus intraday expected returns," *JFE* 2019.
- Bogousslavsky, "The cross‑section of intraday and overnight returns," *JFE* 2021.
- Zarattini & Aziz (2023) and Zarattini, Aziz & Barbon (2024), opening‑range‑breakout papers, SSRN.
- NYSE closing‑auction imbalance and Nasdaq NOII dissemination times; CME Liquidity Tool terms; Databento imbalance schema; FINRA ATS data lag.