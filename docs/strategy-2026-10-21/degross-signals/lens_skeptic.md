# De-grossing episode, 2026-10-14 → 10-22: real edge vs. hindsight narrative for a same-day single-leg options desk

## 0. Access statement (read first; it governs every label below)

- **No web research was possible in this session.** The shared per-turn WebSearch budget (200 calls across all agents) was already exhausted before my first query, and the egress proxy returned `403 connect_rejected` (policy denial) for every host I tried: fred.stlouisfed.org, api.stlouisfed.org, cboe.com, papers.ssrn.com, nber.org, quantifiableedges.com, sentimentrader.com, arxiv.org, wikipedia.org (status endpoint shows the same denials for ssrn.com, aqr.com, cmtassociation.org, repec.org, semanticscholar.org from sibling agents). Per the proxy README, policy denials must not be retried or routed around.
- Consequently **nothing below is VERIFIED** in the strict sense. Labels used:
  - **EXTRACT** = taken from the two sibling briefs (themselves search-snippet extracts of Reuters/Bloomberg/CNBC/GS-via-press).
  - **UNVERIFIED-memory** = from training data (cutoff June 2026); bibliographic identifiers and numbers are recalled, not re-read. Treat every number so tagged as "approximate, do not quote without checking."
  - **MODEL** = my own arithmetic (Black–Scholes script, run locally; file `<local path>`). Not a market fact.
  - **LOCAL** = read directly from the desk's own repository at `/home/user/oid-trading-desk` (these are checkable by the owner in seconds).
- Date note: the harness says "before the open on Thu 2026-10-22", but the sibling brief found closing data for the Oct 22 session (SOX −6.72%, Nasdaq −2.60%). The framework below applies to whichever session is next.

---

## 1. What the literature says about deleveraging episodes, and whether the end is predictable

| Paper (UNVERIFIED-memory for all identifiers) | What it found | What it says about **predicting the end** |
|---|---|---|
| **Khandani & Lo (2007)**, "What Happened to the Quants in August 2007?", J. Investment Management 5(4); SSRN 1015987. Follow-up with transactions data: NBER w14465 (2008), J. Financial Markets (2011) | A simulated short-term contrarian (reversal) L/S strategy lost money on three consecutive days, Aug 7–9 2007, with Aug 9 the worst, then **recovered most of it in one day, Aug 10**. Order of magnitude (memory, approximate): unlevered daily losses of roughly −1%, −3%, −6%, then roughly +6% on Aug 10; at typical quant leverage these were multi-sigma. The unwind was **invisible at the index level** (S&P barely moved on the worst factor day). Their "unwind hypothesis": forced liquidation of one or more large multi-strategy/quant books, propagated through crowded factor positions; crowding had built because strategy returns had decayed since 1998 and funds levered up to compensate. | **The authors explicitly could not identify the cause from public data in real time, and the reversal was abrupt.** The signal that the unwind had ended was the reversal day itself. Duration: 3 down days + 1 reversal day. n = 1. |
| **Ben-David, Franzoni & Moussawi (2012)**, "Hedge Fund Stock Trading in the Financial Crisis of 2007–2009", RFS 25(1):1–54, doi 10.1093/rfs/hhr077 | Hedge funds cut equity holdings by roughly 6% in Q3 2008 and roughly 15% in Q4 2008 (memory), far more than mutual funds; the selling was driven by **investor redemptions and prime-broker funding (margin) pressure**, not fundamentals; funds with lock-ups/gates sold less. Stocks heavily sold by hedge funds suffered price pressure that **reversed over subsequent quarters**. | Data are quarterly 13F. Zero intraday content. The useful lesson: de-grossing is a *funding* phenomenon; it stops when the funding constraint stops binding (redemption dates, VaR/margin resets), which is not visible in price data. |
| **Daniel & Moskowitz (2016)**, "Momentum Crashes", JFE 122(2):221–247, doi 10.1016/j.jfineco.2015.12.002; NBER w20439 (2014) | Momentum (winners-minus-losers) crashes occur in "panic" states: **after a market decline, when ex-ante market volatility is high, and specifically when the market rebounds sharply**. The loser (short) side behaves like a **written call option on the market**. Magnitudes (memory): WML ≈ −91% over Jul–Aug 1932; ≈ −73% over Mar–May 2009; the past-loser decile rose on the order of +160% in Mar–May 2009. Crashes are **partially forecastable** using a bear-market indicator × ex-ante variance; a dynamically-weighted strategy roughly doubles the Sharpe ratio. | Forecastability is at the *monthly* horizon and is about *conditional variance of the payoff*, not timing. Relevance: when a de-gross ends, the rip is concentrated in the most-shorted / most-beaten names (short covering), and that payoff is option-like. It tells you *where* the violence will be, not *when*. |
| **Brunnermeier & Pedersen (2009)**, "Market Liquidity and Funding Liquidity", RFS 22(6):2201–2238, doi 10.1093/rfs/hhn098 | Two spirals: the **loss spiral** (losses → less capital → forced sales → lower prices) and the **margin spiral** (higher vol/illiquidity → higher margins/VaR limits → forced sales → higher vol). Liquidity has **commonality** across assets; there is **flight to quality** (high-margin assets get hit hardest); the system is **fragile** when speculator capital is low (small shocks, large effects). | The model gives **no duration**. Spirals end when (a) speculator capital is replenished, or (b) margins stop rising (i.e., implied vol stops rising). Both are observable **concurrently**, not in advance. The one testable implication: if the spiral is spreading (credit, FX carry, other asset classes), it is a funding-liquidity event and lasts longer; if it stays inside one sector while credit/breadth are calm, it is a positioning event and ends faster. |
| Supporting (UNVERIFIED-memory): **Nagel (2012)** "Evaporating Liquidity", RFS 25(7); **Coval & Stafford (2007)** "Asset Fire Sales (and Purchases) in Equity Markets", JFE 86(2); **Pedersen (2009)** "When Everyone Runs for the Exit", IJCB 5(4); **Adrian & Shin (2010)** "Liquidity and Leverage", JFI 19(3); **Greenwood & Thesmar (2011)** "Stock Price Fragility", JFE 102(3); **Lou & Polk (2022)** "Comomentum", RFS | Nagel: returns to short-term reversal (liquidity provision) **rise sharply with VIX** — fading extreme moves pays more when vol is high, as a *premium for bearing crash risk*, not as a forecast. Coval–Stafford: fund fire sales depress prices and reverse over **quarters**. Adrian–Shin: leverage is pro-cyclical and VaR-driven. Greenwood–Thesmar: stocks held by fragile, correlated owners have higher vol. Lou–Polk: crowding (return co-movement among momentum stocks) predicts momentum crashes **at a monthly horizon**. | All consistent: crowding predicts *fragility* (higher conditional variance), not timing. None provides a daily "x% done" estimator. |

**Base-rate problem (UNVERIFIED-memory).** Clean, well-documented US equity de-grossing episodes in ~20 years: Aug 2007 (quant quake, ~3 days + 1 reversal), Feb 2018 (Volmageddon, ~2 days; VIX close roughly 17 → 37 on Feb 5), Mar 2020 (weeks, exogenous + policy), Jan 2021 (GME short-squeeze de-gross of L/S books, ~1 week), Nov 2021–Jan 2022 (software/unprofitable-tech unwind, ~2 months, slow), Aug 2024 (yen-carry unwind; VIX intraday ~65 on Aug 5, back under 16 within ~2 weeks), Apr 2025 (tariff shock), plus the three 2026 same-day-correlated-loss events GS cites (Feb 4, Jul 28, Oct 15: EXTRACT). That is roughly 8–10 episodes with wildly different durations (2 days to 2 months). **Any "conditional statistic on de-grossing episodes" has n < 10 and is not a statistic.** Statistics on *daily extremes* (VIX inversions, 90% days, breadth washouts) have n in the dozens-to-hundreds but are clustered in 2008/2020/2022 and are not independent draws.

**What the literature does support (UNVERIFIED synthesis):** (1) the end is marked, not forecast — a reversal day that closes near its high on record sector volume with the most-shorted names leading; (2) the margin/vol loop is the mechanism, so implied vol *stopping its rise* is a necessary condition and is observable intraday; (3) breadth and credit tell you whether it is a sector positioning event (fast) or a funding-liquidity event (slow).

---

## 2. Conditional one-day return statistics after extreme readings: what exists, what I could not verify

I could not open any of the sources that publish these tables (Quantifiable Edges, SentimenTrader, Lowry Research, CBOE, Hulbert). I will not fabricate hit rates. What I can state:

| Indicator | Definition (UNVERIFIED-memory) | What the practitioner literature generally reports (UNVERIFIED-memory; no numbers quoted) | Availability / cost |
|---|---|---|---|
| **Lowry 90% Downside Day** | NYSE downside volume ≥ 90% of (up+down volume) **and** points lost ≥ 90% of (points gained+lost). Source: Paul Desmond, "Identifying Bear Market Bottoms and New Bull Markets", Charles H. Dow Award 2002 (CMT Association) | A single 90% down day is **not** a bottom signal; it is typically followed by a 2–7 day reflex rally that fails. Durable bottoms came after a *series* of 90% down days followed closely by a **90% Upside Day** (or two consecutive 80% up days). The confirmation is the up day, i.e., concurrent. | Free intraday on most platforms ($UVOL/$DVOL, $ADD). Daily after close in Lowry's (paid). |
| **VIX term-structure inversion (VIX > VIX3M; VIX9D > VIX)** | Spot above 3-month index; 9-day above 30-day | First inversion after a long contango is, in the blog literature, followed by positive 1–3 month index returns in a majority of cases, but **next-day is roughly a coin flip**, and in persistent bear phases (2008, 2020, 2022) inversion lasted weeks. The *un-inversion* (VIX falling back below VIX3M) is a reasonable concurrent marker that the acute phase ended. | VIX, VIX3M, VIX9D, VVIX are free from CBOE (real-time on CBOE's site; 15-min delayed on most retail feeds). Oct 21 close: VIX 16.68 **below** VIX3M 18.72 (EXTRACT) — i.e., the term structure was *not* inverted going into Oct 22 even though SOX then fell 6.7%; VIX intraday high Oct 22 was 20.30 vs 22.31 on Oct 16 (EXTRACT). |
| **Extreme put/call (CBOE total or equity-only, 1-day or 10-day MA)** | e.g., total P/C above ~1.2 or 10-day MA at a 1-year high | Contrarian; multi-week forward returns above baseline; 1-day edge weak and unstable; the series' level has drifted structurally with 0DTE and index-hedging volume so fixed thresholds are unreliable. | Free daily after close (CBOE); intraday from some vendors. |
| **Oversold breadth** (% of S&P 500 / Nasdaq-100 above 20-day MA < 10%; NYSE McClellan Oscillator extreme; net new lows) | Various | Multi-week forward returns above baseline with high hit rates in the blog literature; **1-day forward is close to unconditional**; "oversold gets more oversold" in liquidation regimes. Note Oct 21 showed 216 Nasdaq new lows vs 53 new highs *on an up day* and Oct 22 NYSE adv/dec ≈ 1.01 while SOX fell 6.7% with all 30 members down (EXTRACT): by Lowry's definition **Oct 22 was not a market-wide 90% down day**; it was a concentrated sector liquidation. | Free daily; intraday approximations free. |
| **Short-term index mean reversion** (Connors RSI(2) < 5 on SPY; 3-day down streaks) | | Positive 1–5 day expectancy in 1993–2008 samples; materially weaker after ~2010. | Free. |
| **Market intraday momentum** — **this is the one peer-reviewed intraday effect relevant to a flat-by-close desk** (UNVERIFIED-memory): Gao, Han, Li & Zhou (2018), "Market Intraday Momentum", JFE 129(2):394–414; Baltussen, Da, Lammers & Martens (2021), "Hedging Demand and Market Intraday Momentum", JFE 142(1) | The **first half-hour return of SPY/index futures predicts the last half-hour return with the same sign**; the effect is **stronger on high-volatility days and on major-news days** (Gao et al.) and is **driven by hedging demand — leveraged-ETF rebalancing and option dealers' gamma hedging — and is strongest when dealer gamma is negative** (Baltussen et al.). R² is small (low single-digit %), the effect is at the *index* level, and it is concentrated in the final 30 minutes. | Free: you need only the index's first-30-min return and a gamma-sign estimate (the desk already pays Unusual Whales for SPY/QQQ GEX — LOCAL, `docs/SCALING-STRATEGY-20261021.md` line 381). |
| **Overnight vs intraday drift** (Lou, Polk & Skouras 2019, "A Tug of War", JFE 134(1); Bogousslavsky 2021 JFE) | | Average *intraday* returns for high-beta, high-momentum, retail-favored stocks are near zero to negative; the equity premium accrues *overnight*. A desk that is always flat by the close is structurally on the wrong side of this drift and must earn it back from selection/timing. Check on your own 1-minute archive. | Free. |

**Honest summary of §2:** the conditional 1-day index edge after extreme readings, where it exists at all, is on the order of a few percentage points of hit rate and a few tenths of a percent of expected return against a conditional daily standard deviation of 1.5–3% in these regimes (UNVERIFIED rule of thumb). That is a t-stat near zero for a single day. Multi-week edges are more robust but irrelevant to a same-day book.

---

## 3. Hazards specific to a single-leg options buyer in this regime

### 3a. Variance risk premium and the asymmetry of long premium (UNVERIFIED-memory)
- Index options are on average overpriced relative to realized: Coval & Shumway (2001, JF 56(3)) found zero-beta SPX straddles lose on the order of 3% per week; Bakshi & Kapadia (2003, RFS 16(2)) found delta-hedged option gains are negative on average; Israelov & Nielsen (2015, "Still Not Cheap: Portfolio Protection in Calm Markets", J. Portfolio Mgmt 41(4)) found long SPX puts lost money in both calm and volatile regimes. Driessen, Maenhout & Vilkov (2009, JF 64(3)) show the index premium is larger than single-name premia (a correlation-risk premium), so single-name options are *less* overpriced than index options but have far worse spreads.
- The regime you are in — **realized vol high and probably past its peak** — is exactly when long premium is worst: you pay for vol that is about to stop materializing.

### 3b. IV crush on a relief rally (MODEL; Black–Scholes, r = 4%, ATM call, 2 trading days to expiry, position held 2 hours)

| Entry IV → exit IV | Option P&L if spot +2% in 2h | Option P&L if spot flat in 2h | Spot move needed in 2h for your +15% target |
|---|---|---|---|
| 80% → 80% (no crush) | **+32%** | −8% | +1.20% |
| 80% → 65% | +16% | −25% | — |
| 80% → 55% | **+5%** | **−37%** | — |
| 80% → 60% | — | — | **+2.19%** |
| 60% → 60% | +47% | −8% | +0.90% |
| 60% → 45% | +26% | −31% | +1.65% |
| 45% → 45% | +68% | −8% | +0.68% |
| 45% → 35% | +51% | −28% | +1.19% |

Reading: the desk's own working thesis is that a 0.3–0.8% underlying move becomes +10–20% on premium (LOCAL, `docs/SCALING-STRATEGY-20261021.md` line 32). That arithmetic holds when IV is **stable**. On the first relief day of a de-gross, single-name IV in semis can fall 15–25 vol points intraday (UNVERIFIED rule of thumb; it is the mirror of the spike on the way down), and the table shows a 2% rally can net a call buyer **+5%** instead of +32%. The desk's existing filter "IV rank below 80 against the trailing 60 sessions, do not buy a surge that is also an IV spike" (LOCAL, line 383) is the correct defense; in this regime it will exclude most of the universe, which is the point.

### 3c. Theta is IV-independent in percentage terms (MODEL)
A 0DTE ATM call bought at 10:00 ET loses **−9.6% per hour** if spot is unchanged, at 45%, 60%, or 80% IV alike (ATM price ∝ σ√T, so percentage decay depends only on time remaining). A 45-minute time stop on a 0DTE costs ~7% of premium in pure decay before any direction is wrong.

### 3d. Spreads
In stress, single-name option spreads widen to 5–15% of mid on 2–5 DTE contracts in second-tier semis (UNVERIFIED rule of thumb). A 10% round-trip spread makes a +10% target a break-even trade. The desk's "reject any contract whose spread-implied underlying move to re[cover]..." filter (LOCAL, line 383) is the right tool; log the spread-at-entry distribution by session and look at it for Oct 14–22 before anything else.

### 3e. Gap and open risk
Flat-by-close removes overnight gap risk, but the overnight repricing then prints in the opening auction and first 5–15 minutes, where spreads are widest and 1-minute rvol norms are least meaningful. META −7%, LRCX −11.8%, AMD −8% on Oct 22 (EXTRACT) were largely gap-driven from after-close prints and Asia. The desk's setup F (opening-range break, 6:35–7:15 PT; LOCAL line 379) should be evaluated separately in this regime; it is where IV crush and spread cost are both maximal.

### 3f. Correlation goes to one
In a de-gross, the 144-name universe behaves as one factor (all 30 SOX members down Oct 22: EXTRACT). Single-name selection edge collapses toward index direction, but you pay single-name spreads and single-name IV. The sector-sympathy setup C (LOCAL line 376) is mechanically more frequent in this regime and also more crowded.

### 3g. Realized-vol regime and bracket geometry
With 1-day 1-σ moves of 3.8% at 60% IV and 5.0% at 80% IV (MODEL, scenario D), a +12 / −20 / 45-minute bracket on premium is hit far faster in both directions; the per-ticket win rate may not change but the P&L variance and sequencing risk (several same-direction losses in minutes) rise. The desk's own ledger already shows exits as the failure mode (45 of 57 closes on eight shared timestamps: LOCAL, line 19).

---

## 4. Which "signals" are mostly narrative, and why

| Signal | Why it is not a predictive input |
|---|---|
| **Prime-broker "pace of de-grossing" commentary** (GS: Oct 15 de-grossing "roughly half of Wednesday"; "largest % of book net-sold since 2016"; net leverage 48.6% = 1-yr low; EXTRACT) | (a) T+1 at best, usually T+2 by the time press quotes it; (b) covers one broker's book, a sample whose share of total HF gross is undisclosed; (c) **descriptive, not a forecast** — no PB publishes an out-of-sample test of "flow deceleration → next-day return"; (d) the same phrase ("funds sold the most since X") is printed at bottoms *and* mid-decline, and only the bottoms get remembered; (e) the sibling brief confirms **no note gives an "X% done" or "typically lasts N days" figure.** The honest use: it tells you the *mechanism* (both sides of book cut, Asia epicenter), which matters for §5 proxies. |
| **"Selling nearing its limit" / "prepare to buy"** (JPM Panigirtzoglou Oct 21; Wilson Oct 19: EXTRACT) | Judgment calls from weekly positioning proxies (futures positioning, CTA signal models, beta of fund returns). Published weekly; Oct 21's "limit" note preceded a −6.7% SOX day. No track record is published. |
| **CTA / systematic-flow estimates** (GS, JPM, Nomura, UBS models) | Conditional, model-based ("if SPX closes below X, CTAs sell $Y over N days"); the houses' estimates differ by tens of billions; the flows are a small fraction of daily volume. Useful only as a map of *levels* where mechanical selling could accelerate; unverifiable; circulated through X screenshots. |
| **"Record" framing** | The sibling brief showed the only literal record was GS's own since-2016 series; the SOX streak **tied** 2008 (record is 9 days); weekly NDX decline was the worst since April 2025. "First VIX > 22 in four months" statistics are generated after every selloff and have no documented hit rate. |
| **Anonymous or branded X positioning accounts** | Survivorship (losers stop posting), no auditable track record, after-the-fact deletion, incentive to maximize engagement by calling turns. Treat as a *news-first-seen* input only (the desk already scores news this way), never as a probability. |
| **CDS prints on CoreWeave / Meta "at all-time highs"** (EXTRACT) | Illiquid single-name CDS; not free; concurrent with equity; reported with a lag. Regime color, not timing. |
| **Option walls** | The desk's own study: walls are noise at the single-name level (46.9% vs 44.9%; LOCAL line 18). Do not promote them in a crisis. |

---

## 5. What a same-day desk can actually measure in real time, free or cheap, with at least some documented conditional edge

Ordered roughly from "has a mechanism and a paper" to "rule of thumb." Thresholds are **UNVERIFIED** unless noted; the desk should backtest each against its own 1-minute archive (209 names + SPY, QQQ, SMH, SOXX, IWM, DIA; LOCAL line 285) using the stratified hit-rate tables with Wilson intervals the Research tab already produces (LOCAL line 255).

| # | Metric | When available | Cost | What it measures in a de-gross | Documented edge | Honest size |
|---|---|---|---|---|---|---|
| 1 | **First-30-min return of NQ/QQQ and SMH, sign and magnitude** | Real-time, 10:00 ET | Free | Direction of the day's hedging-demand flow | Gao et al. 2018; Baltussen et al. 2021 (UNVERIFIED-memory): predicts last-30-min sign, stronger on high-vol/news days and under negative dealer gamma | Index-level; R² low single digits; hit rate modestly above 50%. Concrete use: bias the **last-hour** tickets to the morning's direction; do not fade into the close in negative-gamma regimes. |
| 2 | **SPY/QQQ dealer gamma sign** (Unusual Whales GEX, already paid) | Real-time (vendor estimate) | Paid (already have) | Whether dealer hedging amplifies (negative) or dampens (positive) intraday moves | Same two papers for the mechanism; vendor GEX is an approximation (assumes customers are long calls / long puts) | Use as the regime conditioner the plan already specifies (LOCAL line 381): setup A (continuation) under negative gamma, setup D (fade) under positive gamma. |
| 3 | **VIX vs VIX3M and VIX9D; VVIX; VIX intraday high vs prior-episode high (22.31 on Oct 16: EXTRACT)** | Real-time (CBOE site), 15-min delayed elsewhere | Free | Margin-spiral state (Brunnermeier–Pedersen): rising IV = rising VaR margins = more forced selling | Inversion/un-inversion widely studied in practitioner blogs (UNVERIFIED); next-day edge small | Treat **un-inversion + VIX lower high on a lower SOX low** as a *necessary* condition for "slowing," not sufficient. Oct 22 already showed VIX 20.30 < 22.31 with SOX at a new low (EXTRACT) — consistent with a sector event, not an index liquidity spiral; also consistent with simple index narrowness, so do not over-read. |
| 4 | **Nasdaq and NYSE up-volume share and adv/dec, intraday (90% day forming?)** | Real-time | Free | Breadth of forced selling vs. sector concentration | Lowry (Desmond 2002, UNVERIFIED-memory): series of 90% down days then a 90% up day marks durable lows; one down day = reflex rally | Oct 22: NYSE adv/dec 1.01 with SOX −6.7% (EXTRACT) says the market-wide 90% condition was **not** met; this is a sector de-gross. A **Nasdaq 80–90% up-volume day with SMH rvol above norm closing in the top 20% of range** is the concurrent "it ended" print. |
| 5 | **Most-shorted and most-crowded proxies vs SOX** (hand-built basket of the 20 highest-short-interest names in the 144 universe from FINRA biweekly short interest; ARKK; EWY and the overnight KOSPI print, since GS named Asia the epicenter: EXTRACT) | Real-time (basket), overnight (KOSPI) | Free | Short covering vs. long liquidation; whether the Asia leg is still forcing US sales | Daniel–Moskowitz (UNVERIFIED-memory): rebound payoff concentrates in losers; option-like | A day when the high-SI basket outperforms SOX by >2% on rvol ≥ 2x is short covering = de-gross flipping sign. Concurrent, not predictive, but it is *where* your call tickets should be on that day, with the IV-crush caveat in §3b. |
| 6 | **1-minute rvol ≥ 3x on SMH/SOXX and on the group leader** — the desk's own conditioner | Real-time | Free (already built) | Surge events | **LOCAL, the only edge the desk has measured itself:** 15-min breakout odds 8.7% → 26.7% after rvol ≥ 3x away from walls (line 18, 53) | Unknown whether it holds in this regime: surges are more frequent and spreads wider. **Stratify the existing event table by (VIX > VIX3M), (SOX day% quintile), (GEX sign), (time of day) before trusting it this week.** |
| 7 | **Credit, intraday: HYG and LQD day moves, HYG vs SPY, HYG premium/discount to NAV** | Real-time | Free | Whether the spiral has left equities (Brunnermeier–Pedersen commonality) | Rule of thumb only (UNVERIFIED) | If HYG is flat to up while SOX −5%, it is a positioning event, which the historical episodes (Aug 2007, Feb 2018) suggest ends in days, not weeks (n ≈ 2). If HYG gaps lower and HY OAS Q4 percentile widens day over day, expect a longer event. |
| 8 | **FRED HY OAS / IG OAS with 10-yr percentiles** (the desk's credit page) | **Daily, published next business day** (T+1 lag) | Free | Regime (funding-liquidity vs positioning) | Fidelity-3 framing is a *1-year* forward-return heuristic (LOCAL, `dashboard/MARKET-TAPE.md`); no intraday content | Keep it as regime color. It cannot tell you about today. |
| 9 | **USDJPY, DXY, 10Y, WTI/Brent, NQ vs ES** (already on the desk) | Real-time | Free | Cross-asset spiral spread (carry unwind, rates shock, oil shock) | Aug 2024 analogue (UNVERIFIED-memory): USDJPY was the leading variable for the equity de-gross | 10Y falling below 5% on Oct 22 while tech crashed (EXTRACT) is a flight-to-quality print (B&P), i.e., the spiral was still active in equities but not in rates funding. Watch USDJPY for a carry leg. |
| 10 | **CBOE put/call, SPX 0DTE put share, FINRA daily short-volume ratio** | Daily after close (P/C intraday from some vendors) | Free | Hedging demand and short-sale pressure | Weak 1-day edge (UNVERIFIED) | Color only. |
| 11 | **Prime-broker flow (GS, MS, JPM)** | T+1 to T+2, clients only | Prime-broker-only | Mechanism | None published | Read for mechanism; never for timing. |
| 12 | **CFTC COT, 13F** | Weekly (Fri, Tue data) / quarterly | Free | Positioning | Academic (Ben-David et al.) at quarterly horizon | Irrelevant intraday. |

### 5a. Putting it together for the next session (UNVERIFIED synthesis; a checklist, not a forecast)

1. **Pre-open:** KOSPI/Nikkei closes and EWY pre-market (Asia leg still forcing?), USDJPY direction, HYG pre-market vs SPY pre-market, VIX futures front vs second month, VIX9D/VIX. Note any scheduled prints from your econ calendar; no entries inside the 15-minute windows around them (LOCAL line 383).
2. **09:30–10:00:** do not trade the open in this regime unless setup F has been separately validated on Oct 14–22 data. Record spread-at-entry on every candidate.
3. **10:00:** read the first-30-min NQ and SMH return sign and the GEX sign. This is the one input with a peer-reviewed intraday effect, and it is a *late-day* effect: it tells you which way to lean in the last hour, not what to do at 10:05.
4. **10:00–15:00:** trade only the desk's own measured conditioner (rvol ≥ 3x at day high/low, bar close in top/bottom 30%, not ACCEL ≥ 60 s), with IV-rank and spread filters enforced; prefer names in the high-SI basket on days when that basket leads SOX (short covering).
5. **"Slowing" scorecard, all concurrent:** (a) VIX intraday high below the prior episode high and VIX < VIX3M at 11:00 and at 15:00; (b) Nasdaq up-volume share ≥ 80% by 14:00; (c) SMH closing in top 20% of range on rvol ≥ 1.5x; (d) high-SI basket outperforming SOX; (e) HYG not making a new low. Four of five has, in the historical episodes listed in §1, been what the reversal day *looked like*; nobody has shown it predicts the *next* day beyond the intraday-momentum effect in item 3.
6. **Do not** convert any sell-side "% through the de-gross" quote, X positioning post, or "first in N months" statistic into a probability.

### 5b. The honest size of the edge
- **Index direction over the day:** a few percentage points of hit rate from items 1–3, at the index level, mostly realized in the last 30 minutes.
- **Single-name 15-minute outcomes:** the desk's own 8.7% → 26.7% (LOCAL) is the only measured number, and its validity in this regime is untested; its cost side (spread + IV crush, §3b–3d) is larger in this regime than the extra gross edge any macro indicator contributes.
- **Everything about the de-gross "ending":** recognizable the day it happens, from breadth, vol and short-covering prints; not forecastable the day before, per every paper in §1 and the n < 10 base rate.

---

## Sources

No URL below was opened in this session (proxy policy denial). Identifiers are from training memory and should be checked before citation.

**Literature (UNVERIFIED-memory):**
- Khandani & Lo (2007), "What Happened to the Quants in August 2007?", J. Investment Management 5(4) — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1015987 ; transactions-data follow-up NBER w14465 (2008) — https://www.nber.org/papers/w14465
- Ben-David, Franzoni & Moussawi (2012), RFS 25(1):1–54 — https://doi.org/10.1093/rfs/hhr077
- Daniel & Moskowitz (2016), "Momentum Crashes", JFE 122(2):221–247 — https://doi.org/10.1016/j.jfineco.2015.12.002 ; NBER w20439 — https://www.nber.org/papers/w20439
- Brunnermeier & Pedersen (2009), RFS 22(6):2201–2238 — https://doi.org/10.1093/rfs/hhn098
- Nagel (2012), "Evaporating Liquidity", RFS 25(7):2005–2039 — https://doi.org/10.1093/rfs/hhs066
- Coval & Stafford (2007), JFE 86(2):479–512; Pedersen (2009), IJCB 5(4); Adrian & Shin (2010), JFI 19(3):418–437; Greenwood & Thesmar (2011), JFE 102(3):471–490; Lou & Polk (2022), "Comomentum", RFS
- Gao, Han, Li & Zhou (2018), "Market Intraday Momentum", JFE 129(2):394–414 — https://doi.org/10.1016/j.jfineco.2018.05.009
- Baltussen, Da, Lammers & Martens (2021), "Hedging Demand and Market Intraday Momentum", JFE 142(1):377–403 — https://doi.org/10.1016/j.jfineco.2021.04.029
- Lou, Polk & Skouras (2019), "A Tug of War: Overnight versus Intraday Expected Returns", JFE 134(1):192–213; Bogousslavsky (2021), JFE
- Coval & Shumway (2001), "Expected Option Returns", JF 56(3):983–1009; Bakshi & Kapadia (2003), RFS 16(2):527–566; Israelov & Nielsen (2015), "Still Not Cheap", J. Portfolio Mgmt 41(4); Driessen, Maenhout & Vilkov (2009), JF 64(3):1377–1406
- Desmond (2002), "Identifying Bear Market Bottoms and New Bull Markets", Charles H. Dow Award, CMT Association — https://cmtassociation.org (blocked)

**Data pages (blocked this session; for the desk's own use):** CBOE VIX/VIX3M/VIX9D/VVIX historical — https://www.cboe.com/tradable_products/vix/vix_historical_data/ ; FRED VIXCLS — https://fred.stlouisfed.org/series/VIXCLS ; FRED BAMLH0A0HYM2 / BAMLC0A0CM (T+1 publication); FINRA short interest and daily short-volume files (free).

**EXTRACT items** are from the two sibling briefs quoted in the task (Reuters/Bloomberg/CNBC/GS-via-press snippets, Oct 16–22 2026); their URLs are listed there and were not opened here.

**LOCAL items** (read directly): `/home/user/oid-trading-desk/docs/SCALING-STRATEGY-20261021.md` (lines 18–19, 32, 53, 57, 255, 285, 376–383), `/home/user/oid-trading-desk/dashboard/MARKET-TAPE.md`, `/home/user/oid-trading-desk/macro/README.md`, `/home/user/oid-trading-desk/market-data/latest/macro-morning.json` (stale: as-of 2026-10-05).

**MODEL:** `<local path>` (Black–Scholes, output reproduced in §3b–3c).