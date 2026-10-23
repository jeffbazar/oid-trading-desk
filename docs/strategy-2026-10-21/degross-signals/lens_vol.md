# Volatility and options lens: de-grossing episode 2026-10-14 → 2026-10-22

## 0. Access and labelling (read first)

- **No external page could be read in this session.** WebSearch returned "web search budget is used up (200 calls per turn, shared by every agent)" on the first query, so zero searches ran. WebFetch failed with DNS errors (`getaddrinfo ENOTFOUND`) on fred.stlouisfed.org and www.cboe.com. `curl` through the sandbox proxy returned `CONNECT tunnel failed, response 403` for fred.stlouisfed.org and cdn.cboe.com (proxy status at `http://127.0.0.1:37523/__agentproxy/status` shows policy denials). I did not route around any of this. If the desk wants the missing readings pulled, send a follow-up message after this reply (or raise `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`).
- Consequently **nothing below is VERIFIED.** Labels used:
  - **EXTRACT** = a number that appears in the two sibling briefs supplied in the task (themselves search-snippet extracts of Reuters/CNBC/Bloomberg/Cboe). URL given where the brief gave one.
  - **LOCAL** = read from the desk's own files under `/home/user/oid-trading-desk` (path given). These are the desk's data, not independent verification.
  - **UNVERIFIED** = my own arithmetic on EXTRACT numbers, my recollection of published research (paper named so the desk can check), or a practitioner rule of thumb.
- **Date caveat (same as the sibling brief):** the harness says "before the open Thu 2026-10-22", but the sibling brief already carries an Oct 22 close (Nasdaq −2.60% to 26,008.86; SOX −6.72% to 10,731.98) and the proxy log is stamped 2026-10-22T22:56Z. I treat Oct 22 as closed and the checklist in §6 as applying to Fri 2026-10-23 (and any later session in the same regime).

---

## 1. Readings I could assemble for the episode (all EXTRACT unless marked)

| Date | VIX close | VIX intraday range | Other vol readings | Index tape (for non-confirmation checks) |
|---|---|---|---|---|
| Fri Oct 2 | 15.31 (−6.6%) | — | Oct VIX futures ~17.7–18.5 at Oct 5 pack (contango). **LOCAL** `market-data/latest/macro-morning.json` (`metric_scores[3]`); snapshot shows VIX 15.60 quote at 1:02 PM PT Oct 2 **LOCAL** `data/snapshot.json` (`macro.metrics`) | SPY 769.84, QQQ 749.77 (LOCAL, Oct 2 AH) |
| Mon Oct 12 | 15.21 | — | — | SOX −2.67% (12,236.8) |
| Tue Oct 13 | 15.27 | 15.17–15.61 | — | SOX −2.8% intraday, closed −0.23% |
| Wed Oct 14 | 16.87 | 14.98–17.45 | — | NDX −2.02%, SOX −4.30% closed near lows; hot CPI; GS: heaviest de-grossing day |
| Thu Oct 15 | 16.46 | 16.34–18.01 | — | SOX intraday −4.4% then closed −0.88% (big reversal); KOSPI −7.6%; GS: de-grossing "roughly half" of Oct 14 |
| Fri Oct 16 (OPEX) | **19.99 (+21.45%)** | 15.72–**22.31** (first >22 in 4 months, faded into close) | **VXN 27.1**; SPX/XSP option volumes 4th/5th highest on record; ~$1T notional OPEX | SOX −3.83% (11,137.29), 8th straight; NDX week −5.49% |
| Mon Oct 19 | 18.44 (−7.75%) | — | — | Nasdaq +1.11%; breadth negative (RSP −0.32%, NYSE decliners 1,761 vs 945) |
| Tue Oct 20 | 17.31 (−6%) | — | — | Dow-led; Nasdaq −0.02% |
| Wed Oct 21 (**VIX Oct futures/options expiry, see note**) | 16.68 (−3.6%) | — | **VIX3M 18.72 → VIX/VIX3M = 0.891** (UNVERIFIED arithmetic) | Nasdaq +1.05%; Nasdaq new lows 216 vs 53 new highs on an up day |
| Thu Oct 22 | **~19.03 (+14%)** | high **20.30** | 10Y below 5% first time since Sep 23 | Nasdaq −2.60% (26,008.86; lower low vs Oct 16's 26,140.03 by −0.5%); **SPX −1.21% to 7,663.43 (NOT a lower low; Oct 16 close 7,659.44)**; **SOX −6.72% to 10,731.98 (−3.6% below Oct 16 low; 30/30 members down; broke ~11,000)**; NYSE adv/dec 1.01:1 |

Sources for the EXTRACT rows: sibling briefs quoting Reuters/CNBC/Bloomberg/Investing.com (https://www.cnbc.com/2026/10/21/stock-market-today-live-updates.html ; https://www.cnbc.com/2026/10/18/stock-market-today-live-updates.html ; https://www.bloomberg.com/news/articles/2026-10-16/longest-chip-selloff-since-2006-mints-short-sellers-32-billion ; https://x.com/KobeissiLetter/status/2111185957781221387). None read directly.

**Derived observations (UNVERIFIED arithmetic on the EXTRACT numbers):**
1. **VIX made a lower high (20.30 on Oct 22 vs 22.31 on Oct 16) while SOX made a decisively lower low (−3.6%) and Nasdaq a marginally lower low; SPX merely retested its Oct 16 close.** In SPX-vol terms this is a textbook "retest on lower vol" non-confirmation. In sector terms it is not: VIX is an SPX index, and this episode is concentrated. Oct 22's SPX move (−1.21%) was ≈1.15 daily sigma at the prior-close VIX (16.68/√252 ≈ 1.05%/day); SOX −6.72% is the extreme. **The index-vol complex is the wrong thermometer for a semis de-grossing; VXN, SMH/SOXX ATM IV, single-name IV and implied correlation are the right ones, and I have none of those for Oct 19–22.**
2. VXN/VIX on Oct 16 = 27.1/19.99 = 1.36. A normal VXN/VIX ratio is roughly 1.15–1.25 (UNVERIFIED rule of thumb); 1.36 says Nasdaq-specific vol was being paid up for well beyond the index.
3. **The Oct 21 VIX/VIX3M = 0.891 should be discounted.** By the standard CFE rule (VIX expiry = Wednesday 30 days before the third Friday of the next month; Nov 20, 2026 is the third Friday), **Wed Oct 21 was the October VIX settlement day.** VIX readings on settlement day are routinely distorted by the SOQ and the roll of the VIX strip to the next expiries (UNVERIFIED rule of thumb; date arithmetic mine). The 16.68 print and the "contango restored" look on Oct 21 were followed by +14% on Oct 22.
4. VIX rose ~31% in the week to Oct 16 (EXTRACT, derived by sibling) — large, but the high was 22.31, i.e. this never reached the 30s. Hedge-fund de-grossing showed up as *single-name/sector* vol and *dispersion*, not index tail-vol. That is consistent with "funds cutting both sides of a concentrated book" (GS Prime via Reuters, EXTRACT) rather than a macro-beta hedge wave.

**Not found in this session (say so explicitly):** VIX9D, VIX6M, VVIX, SKEW, VX1/VX2 futures, Cboe total/equity/index put-call ratios, SpotGamma/MenthorQ gamma-flip levels, Nomura/Goldman gamma estimates, single-name IV/skew for NVDA/AMD/MU/LRCX/AVGO, Cboe implied correlation (COR1M/COR3M), SMH/SOXX IV, MOVE — for every day Oct 12–22. The desk's own files contain no vol-surface data later than Oct 5 (`market-data/latest/*.json` are stamped 2026-10-05; `docs/strategy-2026-10-21/map-research.md` line 60 notes "no 10Y/VIX/DXY/futures history" is archived).

---

## 2. Metric-by-metric: what it measures, where it comes from, when, what it costs, and the honest evidence

Legend for "Evidence": **1D** = one-session-ahead directional edge; **1W** = one-week-ahead; **RV** = forecasts next-day *realized range* (not direction). All research citations are UNVERIFIED (from memory; paper names given for checking).

### 2a. VIX level and term structure

| Metric | What it measures | Source / latency / cost | 1D / 1W evidence | How to read it in a de-grossing |
|---|---|---|---|---|
| **VIX spot** | 30-day SPX implied vol (variance-swap-like strip). Also published during GTH 3:15–9:15 ET. | Cboe disseminates every 15 s in RTH; free delayed on cboe.com; real-time via broker/feeds (desk already pulls it via Robinhood `get_index_quotes`, **LOCAL** `dashboard/refresh_market_tape.py` lines 588–602). Daily history free: Cboe `VIX_History.csv`, FRED `VIXCLS`. | **1D direction: essentially none** in the academic literature; VIX level is a risk-premium/regime variable. **RV: strong** — implied vol is a good (upward-biased) forecast of next-day realized vol (Christensen & Prabhala 1998; Blair, Poon & Taylor 2001). **1W: weak**; the variance-risk-premium return predictability (Bollerslev, Tauchen & Zhou, RFS 2009) peaks at 3–6 months, R² ~ low single digits at 1 month, nil at 1 day. | Use for expected daily move (VIX/√252) and option-pricing richness, not for direction. VIX 19 ⇒ ~1.2% SPX daily σ. |
| **VIX9D / VIX ratio** | 9-day vs 30-day SPX IV. >1 = near-term stress/event premium; normal 0.85–0.95. | Cboe VIX9D real-time in RTH; free delayed; daily history free from Cboe. | No peer-reviewed 1D study I can cite. Practitioner use: the *roll back under 1.0* (front end un-inverting) coincides with the end of forced-hedging phases; it is a coincident/lagging confirm, not a lead. | **Slowing:** VIX9D falls below VIX on a day when stocks are still red (hedgers done). **Still deleveraging:** VIX9D > VIX and rising on each down day. |
| **VIX / VIX3M (and VIX3M/VIX6M)** | 1M vs 3M (6M) SPX IV. >1 = inverted/backwardated term structure = stress. | Cboe VIX3M, VIX6M, VIX1Y real-time in RTH; free delayed; FRED `VXVCLS` (VIX3M) daily. | Johnson (JFQA 2017, "Risk premia and the VIX term structure") — slope predicts *VIX futures/variance* returns, not equity returns. Practitioner base rates I recall (e.g. from sell-side and vol-blog studies): after VIX/VIX3M > 1, 1-month forward SPX returns are on average positive and above unconditional, with much wider dispersion; I **cannot verify the numbers this session**, so no figures. **1D: no documented edge.** | **Only one reading available (Oct 21: 0.891, settlement-day distorted).** On Oct 16 (VIX 19.99, VXN 27.1) the structure was very likely inverted at the front (UNVERIFIED). **Slowing:** ratio drops back below ~0.95 and stays there through a red day. |
| **VIX futures curve (VX1/VX2, VX1–spot basis)** | Market's expected VIX path; backwardation (VX1 > VX2) = stress; basis sign. | CFE real-time (paid feed or broker); free delayed curve at vixcentral.com; Cboe CFE settlement files free EOD. | Simon & Campasano (JAI 2014) — basis predicts *VIX futures* returns (roll-down), not equities. Backwardation has historically coincided with the worst week-ahead equity dispersion; **1D direction: none.** | **Slowing:** VX1 drops back below VX2 (contango restored) and VX1–spot basis turns positive. Note Oct VX expired Oct 21; VX1 is now Nov (settles Nov 18, UNVERIFIED date arithmetic). |

### 2b. Vol-of-vol, skew, correlation

| Metric | What it measures | Source / latency / cost | Evidence | Reading |
|---|---|---|---|---|
| **VVIX** | 30-day implied vol of VIX options = demand for VIX calls (crash insurance on insurance). Calm ~80–100; stress >110; extreme >130 (Aug 5 2024 printed well above 150) — UNVERIFIED rule of thumb. | Cboe real-time in RTH; free delayed; daily history free. | Huang, Schlag, Shaliastovich & Thimme (JFQA 2019, "Volatility-of-volatility risk") — VVIX is a priced risk factor, i.e. a premium, not a timing signal. VVIX spikes mean-revert faster than VIX. **1D: none documented.** | **Slowing:** VVIX falls while VIX is flat/up (VIX-call buyers stop chasing); VVIX/VIX ratio falling. **Still deleveraging:** VVIX rising faster than VIX. |
| **Cboe SKEW** | Price of 30-day SPX OTM puts vs calls (tail-risk pricing), 100–150. | Cboe (RTH dissemination, UNVERIFIED frequency); free delayed; daily history free. | Widely found to have **little/no forward predictive power for crashes or returns** (SKEW is typically *high* in calm, well-hedged markets and *falls* in selloffs as ATM vol catches up). Treat as a hedging-intensity gauge only. **1D: none.** | A sharp *drop* in SKEW during the selloff = puts already monetised/sold = hedges coming off; a rebuild of SKEW after the low = re-hedging. Low value for this desk. |
| **Cboe implied correlation (COR1M / COR3M)** | Implied correlation among SPX top-50 names: high = index/basket liquidation; low = dispersion/single-name selling. | Cboe disseminates intraday (UNVERIFIED frequency); free delayed; daily history free. | Driessen, Maenhout & Vilkov (JF 2009) — correlation risk premium; no 1D equity edge. Practically, *falling* implied correlation on a red day is the cleanest "this is stock-picking, not de-grossing" signal. | **Highly relevant to this episode.** Oct 19–22 tape (average stock up, semis crushed, breadth ~1:1) is a *dispersion* signature. Watch COR1M: a renewed spike = basket/program liquidation (still deleveraging); drifting lower = de-grossing migrating to idiosyncratic. |
| **VXN (and VXN−VIX, VXN/VIX)** | 30-day NDX implied vol. | Cboe real-time; free delayed; FRED `VXNCLS` daily. | Same as VIX. | **The right index-vol gauge for a tech de-grossing.** 27.1 on Oct 16 (EXTRACT). A VXN lower-high on an NDX lower-low is the non-confirmation to look for on Oct 23+. |

### 2c. Realized vs implied, and the variance risk premium (VRP)

| Metric | What it measures | Source / latency / cost | Evidence | Reading |
|---|---|---|---|---|
| **VRP = IV² − RV²** (VIX² − 5/10/21-day realized SPX variance) | Whether the market is paying above fair for protection. Normally positive (IV > RV). Turns **negative in liquidation phases** (realized exceeds implied: moves bigger than priced). | Computable free from daily closes; intraday RV from the desk's own 1-min bars (√(Σr²) · √(252·390/n) annualises a partial session). FlashAlpha tags VRP history as Alpha-tier only (**LOCAL** `docs/strategy-2026-10-21/vendor-facts.md` §6). | Bollerslev-Tauchen-Zhou 2009; Bekaert & Hoerova 2014 — VRP predicts returns at 1–6 months, **not at one day.** Negative VRP episodes are short and cluster at lows (coincident). | **Slowing:** 5-day RV rolls over below 10-day RV and back under VIX; intraday RV for 12:00–16:00 ET below 9:30–12:00 ET on the same day. **Still deleveraging:** RV > IV (negative VRP) and widening; late-session RV > morning RV. For SOX use SMH/SOXX ATM IV vs SMH realized (VIX is irrelevant). |
| **Single-name IV, IV rank, 25Δ risk reversal, 1M/3M IV term** in NVDA, AMD, MU, LRCX, AVGO, MRVL, SMCI, CRWV, META | Idiosyncratic fear and hedging; crowded-long names show IV spikes + steep put skew + inverted term during de-grossing. | Broker chains (free, real-time but one name at a time); ORATS, IVolatility, Market Chameleon (paid/freemium, daily surfaces); Unusual Whales API (desk has; Basic $150/Advanced $375 per **LOCAL** vendor-facts §5, UNVERIFIED-S there). | Single-name IV spikes mean-revert; buying calls at IV rank >80 has negative expectancy after the vol crush (the desk's own filter: "IV rank below 80 against the trailing 60 sessions", **LOCAL** `docs/SCALING-STRATEGY-20261021.md` line 383). Skew-as-predictor literature (Xing, Zhang & Zhao 2010) finds steep put skew predicts *underperformance over weeks*, not a day. | **Slowing:** IV rank plateaus, 25Δ put skew flattens from its peak, 1M IV drops back under 3M IV on a red day. **Still deleveraging:** IV and skew making new highs on each down day; term inverted and steepening. |

### 2d. Flow and positioning

| Metric | What it measures | Source / latency / cost | Evidence | Reading |
|---|---|---|---|---|
| **Cboe put/call ratios** (total, equity-only, index-only; 10-day MA) | Volume ratio. Equity-only ~0.5–0.7 normal, >0.9–1.0 extreme; index ratio normally >1 (hedging). UNVERIFIED rules of thumb. | Cboe daily market statistics after the close (free); intraday snapshots on cboe.com during the day (free, UNVERIFIED cadence). | Pan & Poteshman (RFS 2006): **buy-to-open** put/call from non-market-makers (private Cboe data) predicts next-day returns; the **public volume ratios have little or no next-day power.** 0DTE and spread volume further pollute them. **1D: weak/none.** | Use only as a contrarian extreme flag: equity P/C 10-day MA at a local high then turning down = exhaustion. Oct 16's record SPX/XSP volume (EXTRACT) was OPEX-inflated. |
| **Dealer gamma (SPX/SPY/QQQ net GEX, gamma flip, call/put walls)** | Sign of dealers' hedging: **negative gamma** → dealers sell weakness/buy strength → wider ranges, trend days, late-day acceleration, MOC follow-through; **positive gamma** → mean reversion/pinning. | SpotGamma, MenthorQ (paid retail subscriptions; prices not verifiable this session); Nomura (McElligott) and Goldman (Rubner) estimates are sell-side/PB-only, reach the public 0–1 day late via press/X; **FlashAlpha** (desk has Growth, $299/mo, 2,500 req/day, VIX-state Growth+, **LOCAL** vendor-facts §6 and `verification-log.md` §12) gives walls/flip/0DTE magnet. Free: compute from OCC/broker OI (desk plan: Alpaca OI walls). | **Index-level:** Baltussen, Da, Lammers & Martens (JFE 2021) — hedging demand predicts *last-half-hour* momentum; Barbon & Buraschi ("Gamma Fragility") — gamma imbalance predicts intraday reversal/momentum regimes and vol; Gao, Han, Li & Zhou (JFE 2018) — first-30-min return predicts last-30-min return, stronger on high-vol/high-volume days. These are **same-day, index-level, small-magnitude (bps) effects**. **Single-name walls: the desk's own 82,190-ticker-minute study found no information (46.9% vs 44.9% chance; put wall 9.2% vs 9.9%), and 1-min rvol ≥3× is the only conditioner that survived** (**LOCAL** `docs/strategy-2026-10-21/map-research.md` line 98; `verification-log.md` line 339). | **Slowing:** SPX/QQQ reclaim and hold the gamma flip (positive gamma) → ranges compress, afternoon reversals become likelier, late-day selling fades. **Still deleveraging:** spot below flip, flip migrating down, big post-OPEX gamma drop-off (Oct 16 OPEX removed a lot of pinning — UNVERIFIED rule of thumb). For this desk, gamma sign is a **regime/sizing/hold-time switch**, not a signal. |
| **0DTE share and flow** | SPX 0DTE ~50–60% of SPX volume (Cboe figures via Schwab, **LOCAL** vendor-facts §9, UNVERIFIED-3P). Intraday 0DTE call/put sweeps are *magnet/pin* mechanics. | Cboe publishes share stats (free, lagged); real-time 0DTE flow only via paid vendors (SpotGamma HIRO, Unusual Whales, CheddarFlow; the desk's Hal X-scan allowlist includes spotgamma, MenthorQpro, GammaEdges, SqueezeMetrics — **LOCAL** `hal/HAL-X-ALLOWLIST.md`). | Beckmeyer, Branger & Gayda (SSRN 2023/24) — retail 0DTE loses in aggregate; Dim, Eraker & Vilkov (SSRN 2024) — 0DTE gamma propagates intraday vol; Brogaard, Han & Won (2023) — mixed on vol effects. **No next-day predictive content; same-day pin/magnet content is real but index-level.** | Watch the 0DTE put-wall vs spot at 10:00–10:30 ET and 14:30–15:30 ET on SPX/QQQ: a flush *through* the 0DTE put wall that is bought back above it by 11:00 = absorption; a slow grind below it into 15:00 = dealers still selling. |
| **Prime-broker de-grossing prints** (GS Prime, MS PB) | % of book net-sold/de-grossed, gross/net leverage, long-selling vs short-covering ratio. | PB-only daily notes; public only via Bloomberg/Reuters/CNBC quotes with a 1–3 day lag (Oct 14 pace → published Oct 16; Oct 19 weekly). Free via press, impossible real-time. | GS gave the only quantitative "pace" datum: **Oct 15 global de-grossing ≈ half of Oct 14** (EXTRACT, Reuters). No PB note I saw gives "typically lasts N days." | By the time it is public it is 2+ sessions stale; useful only to confirm the *character* (both sides cut, Asia epicentre). Not a trading input. |

---

## 3. What separates "slowing" from "still deleveraging" — the vol-market signature

De-grossing has a specific options footprint (UNVERIFIED synthesis of the above):

| Phase | Index vol (VIX/VXN) | Term structure | VVIX | Implied correlation | Single-name IV/skew | Realized vs implied | Dealer gamma | Tape |
|---|---|---|---|---|---|---|---|---|
| **Active de-grossing** | Rising, closes near highs | VIX9D > VIX > VIX3M; VX1 > VX2 | Rising faster than VIX | Rising (basket liquidation) *or* flat while sector IV explodes (concentrated book) | New IV highs daily; put skew steepening; 1M > 3M | RV > IV (negative VRP) | Negative, flip migrating lower, late-day acceleration | Both longs and shorts move against funds (shorts squeezed up on red days); all-members-down days |
| **Exhaustion / slowing** | Lower high on a lower low in the index being sold (**for this episode: VXN or SMH IV vs SOX, not VIX vs SPX**) | VIX9D back under VIX; VIX/VIX3M back under ~0.95 on a red day | Falls while VIX flat/up | Falls on a red day (dispersion returns) | IV rank plateaus, skew flattens, term un-inverts | RV rolling over; afternoon RV < morning RV; IV back above RV | Spot reclaims flip, ranges compress, late-day selling fails | Intraday reversals (Oct 13, Oct 15 SOX pattern); fewer new lows on down days |
| **Relief bounce that is NOT the end** (what Oct 19–21 looked like) | VIX down but holds above pre-episode level (18.4 → 16.7 vs 15.2 before) | Normalising, but distorted by VIX expiry (Oct 21) | n/a (not found) | n/a (not found) | n/a | n/a | n/a | Narrow breadth (RSP down on an up day Oct 19; Nasdaq new lows 216 vs 53 highs on an up day Oct 21 — EXTRACT) |

Where Oct 22 sits (UNVERIFIED): mixed. SPX-level vol says "retest on lower vol" (slowing); sector-level tape says "new leg" (30/30 SOX members down, LRCX −11.8%, META −7% with CDS at highs, −$900B chip cap in a day — EXTRACT). The missing VXN/SMH-IV/implied-correlation readings are exactly the ones that would resolve this; I could not get them.

---

## 4. Is there genuine one-day predictive edge for a same-day single-leg options desk? Honest answer

1. **Direction: no.** Every metric above with peer-reviewed support predicts returns at weeks-to-months horizons (VRP, term structure, correlation premium) or predicts *realized volatility* (VIX, single-name IV). Public put/call ratios, SKEW and VVIX have no documented next-day directional power. The one same-day directional effect with real support — intraday momentum (first 30 min → last 30 min) amplified under negative dealer gamma and high volume (Gao et al. 2018; Baltussen et al. 2021) — is an index-level, few-bps effect that is below single-leg option bid-ask costs for most names (retail options flow pays ~12.6% effective spread per Bryzgalova, Pavlova & Sikorskaya, JF 2023 — **LOCAL** vendor-facts §9, UNVERIFIED-S).
2. **Range and regime: yes, and that is what this desk can monetise.** The desk takes +10–20% on single legs held seconds-to-hours. Whether that target is reachable before theta/spread eat it is a function of *realized intraday range*, which IV forecasts well. So the vol complex should drive: (a) **position size** (higher IV → fewer contracts), (b) **IV-rank gate** (do not buy calls into an IV spike; desk's <80 rule), (c) **hold-time and time-of-day policy** (negative gamma → favour late-day continuation setups and fade the 10:00–11:00 counter-trend; positive gamma → take profits faster, expect pinning), (d) **delta choice** (in high-IV regimes 0.40–0.50Δ keeps gamma-per-dollar; desk already specifies this).
3. **The desk's own evidence agrees:** walls carry ~2 points over chance at the single-name level; the 1-min rvol ≥3× surge is the only robust conditioner (8.7% → 26.7% 15-min breakout odds; ±2 with surge held 2 min 61.5%, n=26; light ±3 with surge held 5 min 67.5%, n=40 — wide binomial intervals, one or two correlated sessions) (**LOCAL** `docs/strategy-2026-10-21/synthesis-draft.md` lines 8, 45, 47). Vol metrics belong as *features/gates* beside rvol, not as a replacement signal.
4. **What would actually be new information intraday** (free, real-time): VXN vs NDX non-confirmation at the morning low; SMH/SOXX ATM IV vs SMH realized; COR1M direction on a red day; SPX/QQQ spot vs gamma flip at 14:30 ET. None of these is proven as a signal; all are at least *logically* tied to the de-grossing mechanism, unlike VIX/SPX which barely registered the episode.

---

## 5. Availability and cost summary

| Metric | Real-time intraday | Daily after close | Weekly / lagged | Cost |
|---|---|---|---|---|
| VIX, VIX9D, VIX3M, VIX6M, VVIX, SKEW, VXN, COR1M/COR3M | Yes, Cboe-disseminated in RTH (VIX also GTH) | Cboe CSVs; FRED (`VIXCLS`, `VXVCLS`, `VXNCLS` — series IDs from memory, UNVERIFIED) | — | Free delayed; real-time via broker feed (desk already has VIX via Robinhood index quotes, **LOCAL**) |
| VIX futures curve | CFE real-time (paid or broker) | CFE settlements free | — | Free delayed (vixcentral.com) |
| Realized vol / VRP | Desk computes from own 1-min bars | Free from closes | — | Free |
| Cboe put/call | Intraday snapshots (cadence UNVERIFIED) | Free after close | — | Free |
| Single-name IV/skew/term | Broker chain (free), UW API (desk has) | ORATS/IVolatility surfaces | — | Free–$375/mo |
| Dealer gamma / walls / 0DTE flow | FlashAlpha (desk, Growth $299/mo, 2,500 req/day — **LOCAL**), SpotGamma, MenthorQ, UW (paid) | SpotGamma/MenthorQ EOD notes | — | ~$79–$1,499/mo tiers (FlashAlpha, **LOCAL**); SpotGamma/MenthorQ prices not verified |
| Nomura / Goldman gamma and flow estimates | No | Via press/X same or next day | — | Sell-side/PB-only; free second-hand |
| GS/MS prime-broker de-grossing | No | No | 1–3 day lag via Reuters/Bloomberg/CNBC | PB-client-only; free second-hand |

---

## 6. Checklist for the next session (Fri 2026-10-23, or any session in this regime) — thresholds are UNVERIFIED rules of thumb

**Pre-open (free, 5 minutes):**
1. VIX9D/VIX and VIX/VIX3M at 9:15 ET (GTH VIX available): both < 1.0 and falling vs Oct 22 close = front-end stress fading; either > 1.0 = still paying for the next two weeks.
2. VX1 (Nov) vs VX2 (Dec): backwardation = still deleveraging.
3. VVIX vs Oct 22: lower while VIX ~19 = VIX-call demand gone.
4. VXN − VIX spread and SMH/SOXX 30-day ATM IV vs 10-day SMH realized: the sector thermometer. IV < RV = market still underpricing the moves (dangerous for premium buyers on the wrong side, fine for momentum longs of puts/calls with tight holds).
5. COR1M vs Oct 22: up = basket liquidation resumed; down = dispersion.
6. Cboe equity-only P/C for Oct 22 (published after close): >0.9 and a 10-day MA at a local high = extreme; still rising = not yet.
7. FlashAlpha / SpotGamma SPX and QQQ gamma flip vs ES/NQ pre-market: below flip = negative-gamma day (expect trend/late acceleration; favour ACCEL-state continuation, avoid fading); above = pin/mean-revert day (take +10% fast).
8. Single-name IV rank in NVDA/AMD/MU/LRCX/AVGO/MRVL: >80 = no call buying into the spike (desk rule); watch for the first day IV rank *falls* on a red close (vol sellers returning = exhaustion marker).

**Intraday:**
9. 10:00–10:30 ET: if SOX/SMH prints a new low and VXN (and SMH IV) prints a lower high than the prior day's high → non-confirmation; if VXN makes a new high with it → still deleveraging.
10. Intraday RV (sum of squared 1-min returns, annualised) for the afternoon vs the morning on SMH/QQQ: falling = selling exhausting; rising into 15:00 = continuation, and in negative gamma the last 30 min will likely extend the day's direction (Baltussen; Gao).
11. 0DTE put wall on SPX/QQQ: a flush through it that recovers above within ~30 min = absorption; a grind below into the close = dealers still selling.
12. Breadth confirmation (desk already has RSP−SPY): a down day where average stock is up (Oct 22: NYSE 1.01:1) is sector de-grossing, not market stress — VIX-based gauges will keep under-reading it.

**What this cannot do:** none of the above tells you Friday's direction with any documented reliability. It tells you the *regime* (range, pinning vs trending, late-day behaviour, premium richness), which is where a seconds-to-hours single-leg book makes or loses money.

---

## 7. Sources

**EXTRACT (via sibling briefs; not read directly):**
- CNBC live blogs Oct 21/22 and Oct 18/19: https://www.cnbc.com/2026/10/21/stock-market-today-live-updates.html ; https://www.cnbc.com/2026/10/18/stock-market-today-live-updates.html
- Bloomberg Oct 16 (VIX intraday >22, SOX streak, S3 short gains): https://www.bloomberg.com/news/articles/2026-10-16/longest-chip-selloff-since-2006-mints-short-sellers-32-billion
- Bloomberg Oct 19 (GS Prime de-grossing): https://www.bloomberg.com/news/articles/2026-10-19/hedge-funds-cut-tech-at-fastest-pace-in-a-decade-goldman-says
- Kobeissi Letter (NDX worst week since Apr 2025): https://x.com/KobeissiLetter/status/2111185957781221387
- Chartmill Oct 16 close report: https://www.chartmill.com/news/AA/Chartmill-56386-stock-market-today-chip-selloff-day-eight-nasdaq-worst-week-2026-10-16
- Reuters Oct 16 (GS Prime: Oct 15 de-grossing ≈ half of Oct 14; VXN 27.1; record SPX/XSP volumes) — URL not supplied by the sibling brief.

**LOCAL (desk files, read directly):**
- `/home/user/oid-trading-desk/market-data/latest/macro-morning.json` — VIX 15.31 Fri Oct 2 close; Oct VIX futures ~17.7–18.5 on Oct 5.
- `/home/user/oid-trading-desk/data/snapshot.json` (`macro.metrics`) — VIX 15.60 at 1:02 PM PT Oct 2 via Robinhood index quotes.
- `/home/user/oid-trading-desk/docs/strategy-2026-10-21/vendor-facts.md` — FlashAlpha tiers/VRP/VIX-state, UW API pricing, research citations (§5, §6, §9; status UNVERIFIED-S/3P in that file).
- `/home/user/oid-trading-desk/docs/strategy-2026-10-21/map-research.md` (line 60, 98), `synthesis-draft.md` (lines 8, 45, 47), `verification-log.md` (line 339, §12) — wall-magnet null, rvol ≥3× result, FA quota.
- `/home/user/oid-trading-desk/docs/SCALING-STRATEGY-20261021.md` (lines 18, 383) — IV-rank <80 filter, 0.40–0.50Δ.
- `/home/user/oid-trading-desk/hal/HAL-X-ALLOWLIST.md` — positioning accounts the desk already scans.
- `/home/user/oid-trading-desk/dashboard/refresh_market_tape.py` (lines 588–602) — VIX pulled via Robinhood index quotes.

**UNVERIFIED (from memory; check before relying):** Bollerslev, Tauchen & Zhou (RFS 2009); Bekaert & Hoerova (J. Econometrics 2014); Johnson (JFQA 2017); Simon & Campasano (JAI 2014); Huang, Schlag, Shaliastovich & Thimme (JFQA 2019); Driessen, Maenhout & Vilkov (JF 2009); Pan & Poteshman (RFS 2006); Xing, Zhang & Zhao (JFQA 2010); Christensen & Prabhala (JFE 1998); Blair, Poon & Taylor (J. Econometrics 2001); Gao, Han, Li & Zhou (JFE 2018); Baltussen, Da, Lammers & Martens (JFE 2021); Barbon & Buraschi (SSRN 2021); Dim, Eraker & Vilkov (SSRN 2024); Beckmeyer, Branger & Gayda (SSRN 2023/24); Bryzgalova, Pavlova & Sikorskaya (JF 2023). CFE VIX expiry rule and the Oct 21, 2026 settlement date are my calendar arithmetic. All threshold levels (VVIX 110/130, P/C 0.9–1.0, VXN/VIX 1.15–1.25, VIX9D/VIX normal 0.85–0.95) are practitioner rules of thumb, not measured base rates.