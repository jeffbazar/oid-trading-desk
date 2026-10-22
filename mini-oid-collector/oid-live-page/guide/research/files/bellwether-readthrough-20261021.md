# Bellwether earnings read-through and category betas (10/21/2026)

**Status:** research only. No trading changes. In-sample. Raw returns (not market-adjusted).
**Data:** Alpaca SIP daily bars (split/dividend-adjusted) from 1/1/2023 to 10/20/2026 for 205 symbols; first 30-minute RTH bar on 176 reaction days; extended-hours snapshot at about 4:59 PM PT on 10/21. Earnings dates come from Unusual Whales `get_earnings_history` (15 bellwethers, 15–16 events each, 227 events; GOOG uses GOOGL dates). Scripts: `~/oid-score/research/{rt_fetch,readthrough,catbeta}.py`. Outputs: `~/oid-data/patterns/{readthrough,catbeta}-20261021.json`.

## 1. Category beta table (the short version)

How many times the category basket moves for each 1.0 move in the driver. Equal-weight baskets; R² and n in brackets.

| Category (basket) | vs QQQ 1y | vs QQQ 60d | vs SMH 1y | vs SMH 60d | Overnight-only vs QQQ, 1y | On LRCX/AMAT/KLAC/ASML prints (close→open) | On META/MSFT/GOOG/AMZN capex prints (close→open) |
|---|---|---|---|---|---|---|---|
| Chip equipment (LRCX, AMAT, KLAC, ASML) | **2.1×** (.59, 252) | 2.0× (.53, 60) | **1.25×** (.83) | 1.24× (.80) | **2.6×** (.71) | **0.33×** (.66, 61) | 0.02× (.00, 60) |
| Memory (MU, SKHY, DRAM, SNDK) | **3.1×** (.46) | 2.8× (.48) | **1.8×** (.62) | 1.6× (.65) | **3.5×** (.62) | 0.14× (.09); close→close 0.38× (.32) | 0.08× (.05) |
| GPU/logic (NVDA, AMD, AVGO, MRVL, INTC, ARM) | **2.2×** (.74) | 2.4× (.77) | **1.2×** (.86) | 1.3× (.90) | **2.3×** (.76) | 0.16× (.30) | 0.08× (.06) |
| Neoclouds/AI builders (NBIS, CRWV, IREN, WULF, CIFR, APLD, CORZ) | **2.7×** (.40) | 3.6× (.52) | **1.45×** (.45) | 2.0× (.60) | **3.0×** (.70) | 0.14× (.09) | 0.12× (.07) |
| Neoclouds, heavy debt (CRWV, APLD, CORZ, WULF, CIFR) | **2.6×** (.39) | 3.4× (.49) | **1.4×** (.44) | 1.85× (.57) | **2.95×** (.69) | 0.14× (.08) | 0.12× (.06) |

Event-night betas leave the reporting company out of its own basket. "Overnight-only" means the basket's close→next-open return regressed on QQQ's close→next-open return.

**Watch only (WDC, STX).** Overnight beta vs QQQ is 3.1×; beta on LRCX-type prints is 0.17×. Per name, vs QQQ 1y: WDC 2.45× (R² .36), STX 2.05× (.29). No trading in WDC, STX or SNDK; research only.

**How the heavy-debt group was tagged.** Latest-quarter balance sheet from Unusual Whales. Debt includes leases. Net debt = debt − cash. EV = market cap + net debt. A name is heavy-debt if net debt / EV ≥ 25%.

| Ticker | Debt $B | Cash $B | Mkt cap $B | Debt/mkt cap | Net debt/EV | Heavy? |
|---|---|---|---|---|---|---|
| CRWV | 51.6 | 6.4 | 34.1 | 1.52 | 0.57 | yes |
| APLD | 6.48 | 2.95 | 6.1 | 1.06 | 0.37 | yes |
| CORZ | 4.30 | 1.77 | 4.6 | 0.93 | 0.35 | yes (negative equity) |
| WULF | 5.24 | 2.62 | 6.2 | 0.85 | 0.30 | yes |
| CIFR | 5.59 | 4.02 | 3.7 | 1.50 | 0.30 | yes |
| IREN | 7.84 | 5.90 | 10.1 | 0.78 | 0.16 | no (large cash pile) |
| NBIS | 10.06 | 8.04 | 48.1 | 0.21 | 0.04 | no |

Under the looser rule (debt / market cap ≥ 25%), IREN also counts. The heavy-debt basket behaves almost the same as the whole neocloud basket, so on these betas leverage adds no separate effect.

### Per-name betas (R², n)

| Name | QQQ 1y | QQQ 60d | SMH 1y | Overnight vs QQQ 1y | Equipment prints (co) | Capex prints (co) |
|---|---|---|---|---|---|---|
| LRCX | 2.48 (.58) | 2.60 | 1.45 | 3.11 | 0.36 (.54, 46) | −0.03 |
| AMAT | 2.16 (.51) | 2.21 | 1.29 | 2.68 | 0.43 (.79, 46) | 0.00 |
| KLAC | 2.17 (.51) | 1.89 | 1.30 | 2.54 | 0.36 (.70, 46) | 0.05 |
| ASML | 1.63 (.49) | 1.22 | 0.97 | 2.10 | 0.21 (.46, 45) | 0.05 |
| MU | 2.84 (.48) | 2.56 | 1.64 | 3.34 | 0.16 (.17, 61) | 0.07 |
| SKHY | 3.23 (.36, n 72) | 2.59 | 1.99 | 3.54 | 0.24 (n 5) | 0.07 (n 4) |
| DRAM | 3.20 (.62, n 139) | 2.69 | 1.70 | 4.16 | 0.21 (n 9) | 0.08 (n 8) |
| SNDK | 3.34 (.34) | 3.25 | 1.93 | 3.49 | 0.14 (.03, 26) | 0.11 |
| NVDA | 1.29 (.47) | 1.28 | 0.65 | 1.30 | 0.09 (.09) | 0.11 (.15) |
| AMD | 2.54 (.55) | 2.49 | 1.38 | 2.59 | 0.19 (.23) | 0.09 |
| AVGO | 1.58 (.47) | 1.49 | 0.80 | 1.65 | 0.12 (.20) | 0.01 |
| MRVL | 2.55 (.40) | 2.82 | 1.44 | 2.71 | 0.21 (.32) | 0.11 |
| INTC | 2.53 (.42) | 2.78 | 1.45 | 2.71 | 0.07 (.03) | 0.09 |
| ARM | 2.59 (.42) | 3.46 | 1.37 | 2.87 | 0.30 (.28, 49) | 0.05 |
| NBIS | 2.92 (.28) | 4.18 | 1.55 | 3.34 | 0.18 (.13) | 0.07 |
| CRWV | 2.53 (.27) | 3.86 | 1.31 | 2.93 | 0.21 (.10, 25) | 0.32 (.18, 24) |
| IREN | 3.02 (.31) | 4.04 | 1.58 | 3.04 | 0.12 (.06) | 0.17 (.14) |
| WULF | 2.52 (.29) | 3.15 | 1.34 | 2.92 | 0.13 (.08) | −0.07 |
| CIFR | 2.93 (.27) | 3.26 | 1.61 | 3.34 | 0.18 (.08) | 0.19 (.10) |
| APLD | 3.02 (.34) | 3.66 | 1.58 | 3.19 | 0.05 (.01) | 0.24 (.11) |
| CORZ | 2.13 (.34) | 3.02 | 1.16 | 2.37 | 0.16 (.13) | 0.09 |

## 2. Tonight's attribution (snapshot about 4:59 PM PT on 10/21)

Drivers after hours: QQQ −0.79%, LRCX −7.41%, META +2.17%, SMH −1.69%.

| Category | Actual after hours | QQQ-implied (resid) | LRCX-implied (resid) | META-implied (resid) | Best fit |
|---|---|---|---|---|---|
| Chip equipment (AMAT −3.88, KLAC −2.96, ASML −1.71) | −2.85% | −1.93% (−0.91) | −2.37% (−0.48) | +0.09% (−2.94) | **LRCX** |
| Memory (MU −1.68, SKHY −1.77, SNDK −2.05; DRAM had no after-hours print) | −1.83% | −2.78% (+0.94) | −1.04% (−0.79) | +0.17% (−2.00) | LRCX (only just) |
| GPU/logic (NVDA −1.22, AMD −2.25, AVGO −1.30, MRVL −2.54, INTC −2.17, ARM −2.08) | −1.93% | −1.82% (−0.11) | −1.19% (−0.74) | +0.17% (−2.10) | **QQQ** |
| Neoclouds (NBIS −3.25, CRWV −3.43, IREN −2.55, WULF −2.19, CIFR −1.97, APLD −1.67, CORZ −1.65) | −2.39% | −2.39% (+0.01) | −1.04% (−1.35) | +0.26% (−2.65) | **QQQ** |
| Neoclouds, heavy debt | −2.18% | −2.34% (+0.16) | −1.04% (−1.14) | +0.26% (−2.44) | **QQQ** |
| Watch only: WDC −1.19, STX −1.49 | −1.34% | −2.47% (+1.13) | −1.26% (−0.08) | +0.20% (−1.54) | LRCX |

**In plain words.**
- LRCX's drop explains chip equipment, with about −0.5 pt of extra weakness left over.
- GPU/logic and the neoclouds moved like a normal high-beta night: their QQQ beta times the QQQ move matches almost exactly.
- Memory fell less than its QQQ beta implies (+0.9 pt held up).
- META's beat explains nothing. Capex-print betas are about 0.1× with R² ≤ .18 in every category, and every group fell while META rose.

**Caveat.** QQQ's after-hours move is not independent. It already contains LRCX, semis, TSLA (−3.3%) and META, so "QQQ explains it" partly means "the whole AI/semis complex sold off together". TSLA, TXN and META also reported tonight.

The Research Bot timing check (1:05 PM, during the calls, or the 5:38 PM Saudi order) had not arrived by the time this was written, so it is not included.

## 3. Read-through map (per bellwether, top linked peers)

Slope = peer move per 1.0 bellwether move. co = close→next open; cc = close→next close; hit = share of events where the peer moved the same way. The full map is in the JSON; heatmaps are below.

| Bellwether (events) | Peer | cc slope | cc r | cc hit | co slope | co r | co hit | n |
|---|---|---|---|---|---|---|---|---|
| LRCX (15) | AMAT | 0.74 | .96 | .87 | 0.44 | .95 | .80 | 15 |
| | MU | 0.79 | .93 | .93 | 0.28 | .82 | .73 | 15 |
| | KLAC | 0.53 | .89 | .93 | 0.38 | .90 | .80 | 15 |
| | ASML | 0.39 | .88 | .93 | 0.23 | .75 | .80 | 15 |
| | SMH | 0.37 | .84 | .87 | 0.17 | .82 | .67 | 15 |
| | AMD | 0.51 | .82 | .80 | 0.17 | .66 | .60 | 15 |
| | ALAB | 0.81 | .81 | .70 | 0.37 | .77 | .60 | 10 |
| ASML (16) | AMAT | 0.58 | .86 | .94 | 0.56 | .90 | .94 | 16 |
| | KLAC | 0.56 | .80 | .88 | 0.52 | .86 | .94 | 16 |
| | LRCX | 0.56 | .75 | .94 | 0.61 | .86 | .94 | 16 |
| | SMH | 0.30 | .71 | .75 | 0.29 | .71 | .75 | 16 |
| | AVGO | 0.30 | .69 | .62 | 0.28 | .64 | .75 | 16 |
| | TSM | 0.30 | .65 | .62 | 0.34 | .66 | .75 | 16 |
| TSM (16) | LRCX | 0.59 | .78 | .88 | 0.73 | .79 | .88 | 16 |
| | ASML | 0.54 | .72 | .81 | 0.54 | .68 | .88 | 16 |
| | AMAT | 0.56 | .71 | .81 | 0.74 | .81 | .88 | 16 |
| | KLAC | 0.56 | .70 | .69 | 0.58 | .76 | .81 | 16 |
| | SMH | 0.38 | .70 | .81 | 0.50 | .88 | .88 | 16 |
| NVDA (15) | SMH | 0.38 | .92 | .80 | 0.27 | .93 | .87 | 15 |
| | TSM | 0.37 | .86 | .80 | 0.30 | .95 | .93 | 15 |
| | AVGO | 0.33 | .84 | .87 | 0.14 | .61 | .80 | 15 |
| | VRT | 0.46 | .83 | .67 | 0.37 | .86 | .73 | 15 |
| | SMCI | 1.02 | .77 | .73 | 0.68 | .78 | .80 | 15 |
| | AMAT | 0.33 | .78 | .53 | 0.15 | .73 | .80 | 15 |
| META (15) | SHOP | 0.29 | .79 | .80 | 0.20 | .91 | .87 | 15 |
| | AMZN | 0.23 | .72 | .67 | 0.16 | .63 | .80 | 15 |
| | PLTR | 0.18 | .56 | .53 | 0.12 | .75 | .87 | 15 |
| | RDDT | 0.23 | .51 | .50 | 0.34 | .89 | .80 | 10 |
| | SNAP | 0.21 | .50 | .47 | 0.20 | .90 | .93 | 15 |

**Spurious matches.** Ranking about 200 peers on about 15 events throws up chance correlations with no business link, such as LRCX→MRNA/TEM, TSM→BA/UAL/DKNG/AAL/DAL and META→F/GM. They are left out above. META's read-through goes to ad/consumer-internet names (SHOP, SNAP, RDDT, PLTR), not to semis.

![Read-through heatmap, close→next open](/guide/research/files/readthrough-heatmap-co-20261021.png)
![Read-through heatmap, close→next close](/guide/research/files/readthrough-heatmap-cc-20261021.png)

## 4. Is it tradeable? (in-sample)

"Linked peers" are each bellwether's top 10 core (AI/semis list) peers by cc correlation, n ≥ 8. Observations within one event are correlated, so the effective n is closer to the number of events.

- **Gaps neither hold nor fade.** Linked peers gapping ≥1% (n 1,192 observations): open→30m +4.0 bp in the gap direction (holds 49.0%); open→close +16.1 bp (52.5%); next day +21.3 bp (52.2%). That is about a coin flip.
- **Peers under-react at the open.** The median gap is 0.75× the leave-one-out beta-implied move (n 2,235).
  - Under-reacters (gap in the implied direction but under 75% of the implied move, where the implied move is at least 1%; n 302) drift +50.8 bp toward the implied move open→close, +28.7 bp of it in the first 30 minutes, then −0.5 bp the next day.
  - Over-reacters (gap above 125% of the implied move, n 284) do not fade. They extend another +13.5 bp open→close, then another +39.7 bp the next day, in the gap direction.
  - The linear fit is weak: corr 0.03.
- **When the bellwether moves ±4% or more** (131 events, 1,295 linked-peer observations): the peer gaps +161 bp in the bellwether's direction, then open→30m +17.9 bp, open→close +50.2 bp (same direction 55.0%), next day −32.2 bp (46.3%).
  - **Down ≥4%** (58 events, 576 observations): gap −93.5 bp, 30m −17.0, open→close −69.8 bp (keeps falling), next day **+46.0 bp bounce**.
  - **Up ≥4%** (73 events, 719 observations): gap +215.9, 30m +18.6, open→close +34.6, next day −21.2.
  - Control, all peers (25,404 observations): gap +45.6 bp, open→close −5.9, next day −14.5.
- **Bellwethers' own follow-through after their gap** (open→close, signed, about 15 events each):
  - Continuation: AVGO +171 bp, SMCI +169, ASML +105, AMD +87, KLAC +74.
  - Fade: AMAT −101, GOOG −82, MU −64, NVDA −58, META −54.

**Tonight.** LRCX at −7.4% is a "down ≥4%" case. Historically, linked peers kept falling open→close (−70 bp) and bounced the next day (+46 bp). This is in-sample, the observations are clustered, and it is not a signal.

## 5. Tonight's peers vs the LRCX-implied move

Leave-one-out co beta × LRCX −7.41%, against each peer's actual after-hours move. z = residual / historical residual SD. Peers whose last print equalled the close (no real extended-hours trade) are dropped.

- **Held up more than implied:**
  - ARM: implied −7.07%, actual −2.08%, z +2.07. The slope comes from only 12 events and looks inflated.
  - ON: implied −1.36%, actual +1.96%, z +1.21.
- **Fell more than implied:**
  - NVDA: implied +0.60%, actual −1.22%, z −1.58. Its LRCX correlation is only .08.
  - AMD: implied −0.52%, actual −2.25%, z −1.09.
  - DELL: implied −0.64%, actual −1.96%, z −1.15.
  - VRT: implied +0.34%, actual −1.92%, z −1.15.
  - PLTR: implied +0.64%, actual −1.01%, z −1.00.
  - AAPL: implied +0.74%, actual −0.06%, z −1.45.
- **In line:**
  - Equipment: AMAT (implied −3.24%, actual −3.88%), KLAC (−2.50 / −2.96), ASML (−1.06 / −1.71).
  - Memory: MU (−1.97 / −1.68).
  - Semis ETFs: SMH (−0.73 / −1.69, z −0.99), SOXX (−1.12 / −1.57).
  - Others: NBIS (−2.45 / −3.25), MRVL (−1.40 / −2.54), ALAB (−2.20 / −2.78).

The pattern: equipment and memory trade in line with LRCX. The AI-hardware complex (NVDA, AMD, VRT, DELL) fell more than LRCX explains, consistent with the broader QQQ / high-beta selloff in section 2.

## 6. Caveats

- About 15 events per bellwether, and everything is in-sample. With roughly 200 candidate peers, expect some correlations of .6–.8 by chance.
- Raw returns. On big market days, part of every move is beta to the market.
- When an earnings timing label was missing, the reaction day was taken as the candidate day with the larger bellwether gap.
- Data guards: single-day returns above 60% in absolute size are dropped (for example, the CORZ relisting on 1/24/2024 showed +7,290%). A last print equal to the close counts as no extended-hours print.
- QQQ after hours stands in for NQ futures. The snapshot time is about 4:59 PM PT, not the final 5:00 PM print.
- SKHY (n 72 days), DRAM (n 139) and CRWV (about 25 events) have short histories.
- Debt figures are latest-quarter values from UW, including leases. Market caps use the 10/21 close.
