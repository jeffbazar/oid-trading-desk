# Vendor bake-off: Unusual Whales vs Quant Data (quantdata.us)

**Desk:** Rose's Options Intelligence Desk (OID)  
**Date:** 2026-09-17 (PT)  
**Scope:** Research only — decide if Quant Data is worth **adding** for full options tape / net-premium drift / wall-break confirmation **beyond UW alerts**.  
**Not in scope:** Another GEX / walls vendor (FlashAlpha Growth already owns walls / GEX / DEX / VEX / CHEX).

---

## TLDR recommendation

**Stay UW-only for now.** Do **not** add Quant Data yet.

OID already pays for Unusual Whales MCP that covers soft-catalyst #2 (flow alerts + raw option trades), off-exchange soft color (dark pool / TRF), market tide, flow-per-strike/expiry, and minute greek flow. The bake-off gap (“full tape / net premium drift / wall-break beyond alerts”) is mostly **under-wiring of UW**, not a missing vendor:

| Gap | UW answer already available | QD equivalent |
|-----|----------------------------|---------------|
| Beyond alerts | MCP `get_option_trades` (filtered full tape) | `order-flow/consolidated` / unconsolidated |
| Net premium drift | REST `GET /api/stock/{t}/net-prem-ticks` (**not** in current UW MCP) + MCP `get_greek_flow_by_ticker` | MCP `qd_get_net_drift` / `qd_get_net_flow` |
| Wall-break color | MCP `get_flow_per_strike` + `get_dark_pool_volume_price_group` (+ REST option price levels) | net-drift + dark-pool levels + equity prints |
| GEX / walls | **Skip both** — use FlashAlpha Growth | QD exposure endpoints (redundant) |

**Revisit QD (~$150/mo API+MCP)** only if, after leaning harder on UW (below), Q5 still lacks reliable **MCP-native** per-name net-drift or consolidated comprising-trades tape and REST `net-prem-ticks` is impractical. QD is then a cheap additive tape/drift layer — **not** a GEX replacement.

**Ignore** `quantdata.uk` — unrelated product; keys/URLs are not interchangeable with `quantdata.us`.

---

## Desk context (fixed)

| Layer | Role today |
|-------|------------|
| FlashAlpha Growth | Walls / flip / GEX soft context (hard structure for soft #1) |
| Unusual Whales MCP (`user-unusual-whales`) | Soft #2 flow, OE/DP soft color, Form-4, tide, greek flow |
| Robinhood | Quotes / chains (≤120s, not delayed) |
| Q5 | 5-min qualifier; soft color only; never execution |

Universe V1.8a: **18** names (`SPY, QQQ, NVDA, TSLA, PLTR, GOOGL, NFLX, META, AMZN, AMD, CBRS, BE, NBIS, IREN, CRWV, SNDK, MU, SPCX`). Q5 deep-dives **near-wall / focused** names only — not all 18 every tick.

---

## 1. Unusual Whales — public API pricing + OID-relevant endpoints

### Published API pricing (2026-09-17 public pages)

Sources: [unusualwhales.com/public-api](https://unusualwhales.com/public-api), [unusualwhales.com/api_lander](https://unusualwhales.com/api_lander), [enterprise pricing](https://unusualwhales.com/pricing/enterprise).

| Tier | List / billed | Daily REST quota | History | MCP | Notes |
|------|---------------|------------------|---------|-----|-------|
| Free trial | 1 week free; lander also shows **$50/week** after trial | **30,000**/day | **90 days** | Yes (marketing) | Personal use |
| **API Basic** | **$125/mo** (list ~$150); **$1,500/yr** | **40,000**/day on lander; **80,000**/day on public-api page — **confirm at checkout** | **2 years** | Yes | Core flow / DP / tide / GEX / net premium |
| **API Advanced** | **$375/mo** or **~$315/mo** annual (**$3,780/yr**) | **Unlimited** REST | **2 years** | Yes | Adds **WebSocket** (personal), premium endpoints (forex/commodities/econ/etc.), CME futures tape |
| Startup (biz) | **$750/mo** | **160,000**/day | 2 years | — | Commercial use |
| Startup + Kafka | **$3,000/mo** | Startup + Kafka cluster | 2 years | — | Streaming option trades / equities / CME / etc. |
| Professional / Enterprise | **Contact sales / unpublished** | Custom | Custom | Custom | Redistribution, delayed-data discount, compliance |
| Historical full-tape add-on | **$250/mo** (full market); multi-year **contact** | — | — | — | Separate historical option trades download |

**Delayed data:** 15-minute delayed option available at reduced enterprise pricing — contact sales.

**Rate limit (personal API):** ~**120 requests/minute** (lander).

### OID soft #2 / wall-break — relevant UW endpoints

#### Already exposed on connected MCP `user-unusual-whales`

| MCP tool | Maps to / use for OID |
|----------|------------------------|
| `get_flow_alerts` | Soft #2 **unusual** rule hits (mandate language) |
| `get_option_trades` | **Tape-level** prints (sweeps/blocks/filters) — beyond alerts |
| `get_flow_per_strike` / `get_flow_per_expiry` | Premium/volume by strike or expiry — wall confluence |
| `get_dark_pool_trades` | OE/DP prints (mandate OE soft) |
| `get_dark_pool_volume_price_group` | Lit + DP **and** options call/put vol by price — wall-break soft |
| `get_market_tide` / `get_market_sector_tide` / `get_market_etf_tide` / `get_expiry_tide` | Net call/put premium / volume tide |
| `get_greek_flow_by_ticker` (+ expiry/group variants) | Minute delta/vega + call/put premium — **MCP-native drift proxy** |
| `get_gex_levels` / greek exposure tools | Available but **do not lean** — FA owns walls/GEX |
| Form-4 / insider tools | Soft color (separate cadence; not every Q5) |

#### Public REST relevant to OID but **not** found on current UW MCP tool list

| REST endpoint | Path | Why it matters |
|---------------|------|----------------|
| Net premium ticks | `GET /api/stock/{ticker}/net-prem-ticks` | True per-minute net call/put premium & volume (cumulate client-side) — closest UW match to QD net-drift |
| Option volume by price | `GET /api/stock/{ticker}/option/stock-price-levels` | Call/put volume per underlying price — wall-break |
| Off/lit stock volume levels | `GET /api/stock/{ticker}/stock-volume-price-levels` | Overlaps MCP `get_dark_pool_volume_price_group` |
| Full tape download | `GET` Full Tape (`OptionTradeController.full_tape`) | Day dump of all option transactions |
| Flow per strike intraday | `.../flow_per_strike_intraday` | 1-min non-aggregated flow |
| Option trades (raw) | `GET /api/option-trades` | Same family as MCP `get_option_trades` |

#### Requires higher UW plan / add-on (not needed for OID soft #2)

| Capability | Gate |
|------------|------|
| **WebSocket** channels (option_trades, flow_alerts, net_flow, market_tide, off_lit, etc.) | Personal use: **Advanced** only |
| CME futures tape / candles | Advanced or futures add-on |
| Premium fundamentals / forex / commodities / econ / top movers / IPO / intel analytics | **Advanced+** |
| Kafka full-market stream | **$3,000/mo** Startup+Kafka or Enterprise |
| Historical full-market option trades package | **+$250/mo** add-on |

**Implication:** Soft #2 + wall-break soft color do **not** require Advanced/WebSocket/Kafka if Q5 polls REST/MCP on a 5-min cadence. Advanced is only justified if OID wants push streaming.

---

## 2. Quant Data (quantdata.us) — pricing, MCP, endpoints

Sources: [quantdata.us/api](https://quantdata.us/api), [for-ai-agents](https://quantdata.us/for-ai-agents), [llms.txt](https://quantdata.us/llms.txt), endpoint docs.

### Pricing (published)

| Product | Price | Notes |
|---------|-------|-------|
| **API + MCP** (together) | **$149.99/mo** or **$1,499.99/yr** (~**$124.99/mo** annual) | Full **30+** endpoints; **240 req/min**; **no monthly quota**; 365+ day lookback; 99.99% uptime SLA marketed |
| Dashboard Standard | **$74.99/mo** / **$749.99/yr** | Separate; **not required** for OID API/MCP |
| Professional dashboard | Same surface as Standard for registered pros | Separate from API |
| Enterprise / redistribution | **Contact sales / unpublished** | Published API price is **personal use only** — not for external redistribution |
| OPRA | Signed OPRA market-data agreement required | Key format `qd_` + 32 alphanumerics |

### MCP

- Hosted MCP: `https://api.quantdata.us/mcp`
- Every REST endpoint mirrored as `qd_get_<snake_case>`
- Rate limit shared across REST + MCP: **240 / 60s sliding window**, burst **20/s**

### Endpoints relevant to bake-off goal (tape / drift / wall-break — not GEX)

| REST | MCP tool | OID use |
|------|----------|---------|
| `POST /v1/options/tool/order-flow/consolidated` | `qd_get_order_flow_consolidated` | Consolidated sweeps/blocks/splits + optional comprising trades — **full tape view** |
| `POST /v1/options/tool/order-flow/unconsolidated` | `qd_get_order_flow_unconsolidated` | Trade-by-trade legs |
| `POST /v1/options/tool/net-drift` | `qd_get_net_drift` | Bucketed net call/put premium + stockPrice — **wall-break drift** |
| `POST /v1/options/tool/net-flow` | `qd_get_net_flow` | `NET_PREMIUM` or `NET_VOLUME` aggregates |
| `POST /v1/equities/tool/equity-prints` | `qd_get_equity_prints` | Lit + dark equity prints |
| `POST /v1/equities/tool/dark-pool-levels` | (dark pool levels) | OE by price — **overlaps UW OE soft** |
| `POST /v1/equities/tool/dark-flow` | (dark flow) | OE notional time series |

**Do not wire for OID (GEX overlap with FA):** `exposure-by-strike`, `exposure-by-expiration`, `heat-map`, `interval-map`, max-pain family — out of bake-off scope.

Latency claim on marketing demos: ~**40–50 ms** response examples (not an SLA guarantee beyond uptime marketing).

---

## 3. Side-by-side for OID

| Dimension | Unusual Whales | Quant Data (us) | Winner for OID |
|-----------|----------------|-----------------|----------------|
| **Coverage — options tape** | Full market flow; MCP alerts + `get_option_trades`; REST full_tape | Consolidated + unconsolidated tape; comprising trades toggle | Tie / slight QD for consolidated UX |
| **Coverage — net premium drift** | REST `net-prem-ticks` (strong); MCP gap; greek_flow proxy | First-class MCP `net-drift` / `net-flow` | **QD MCP convenience**; UW REST parity |
| **Coverage — dark pool / TRF** | Already wired (`OFF-EXCHANGE-SOFT.md`) | equity-prints / dark-pool-levels | **UW** (already paid + mandate-cited) |
| **Coverage — GEX / walls** | Has Spot GEX etc. | Has exposure heat maps | **Neither** — use **FA Growth** |
| **Latency** | REST poll; WS only on Advanced | REST/MCP poll; ~40ms demos | Tie for Q5 poll model |
| **API / MCP fit** | MCP already connected; 100+ endpoints / 50+ tools | Clean agent docs + hosted MCP; 30 endpoints | **UW** (already live) |
| **Overlap with what we pay for** | High with FA on GEX; low on Form-4/congress/tide | High with FA on exposure; high with UW on DP/tape | QD adds **most** overlap |
| **Quota / Q5 cost** | Basic daily cap (40k–80k); 120/min | No monthly cap; 240/min | QD easier headroom; UW Basic still fine for Q5 |
| **Published $** | Basic **$125**; Advanced **$375** | API **$149.99** | QD cheaper than UW Advanced; **additive** to UW Basic |
| **Gaps each fills** | Form-4, congress, market tide proprietary, UW-labeled unusual alerts (mandate soft #2) | MCP-native net-drift + consolidated comprising trades without REST shim | See recommendation |

### Q5 cost model (calls × cadence)

Assumptions: ~**78** Q5 ticks/RTH day; deep work on ~**2–4 near-wall** names (not full universe every tick); soft color only.

| Stack | Calls per focused name per Q5 | 3 names × 20 focused ticks/day | Fit |
|-------|-------------------------------|--------------------------------|-----|
| **UW lean (stay)** | 1× `get_option_trades` + 1× `get_flow_per_strike` or `get_greek_flow_by_ticker` + optional 1× DP tools | ~**120–180**/day | Trivial vs Basic 40k–80k |
| **+ REST net-prem-ticks** | +1 per name | +~60–80 | Still trivial |
| **If add QD** | 1× `net-drift` + 1× `order-flow/consolidated` (+ optional equity-prints) | ~**120–240**/day | Fine vs 240/min, no monthly cap |
| **Anti-pattern** | Poll all 18 names × full tape every 5 min | Thousands/day | Wasteful; not mandated |

FA Growth (2500/day) remains the walls budget — unchanged by this bake-off.

---

## 4. Recommendation + wire lists

### Decision: **Stay UW-only**

Rationale in one paragraph: Soft #2 already names **Unusual Whales–labeled** unusual flow; OE soft already cites UW only; FA owns walls. QD’s published $150 API is attractive for MCP-native net-drift and consolidated tape, but it largely **duplicates** capabilities UW already sells (and partially exposes on MCP). Paying a third market-structure vendor before exhausting UW tape/drift tools fails the bake-off goal (“beyond UW **alerts**” ≠ “beyond UW entirely”).

### If we stay UW — lean harder on these (Q5 / near-wall)

**MCP (already connected):**

1. `get_flow_alerts` — keep for soft #2 “unusual” label  
2. `get_option_trades` — **primary beyond-alerts tape** (min_premium, report_flag sweep/floor, ask/bid tags, ticker)  
3. `get_flow_per_strike` — premium at FA wall strike  
4. `get_greek_flow_by_ticker` — minute call/put premium + delta flow (drift proxy while MCP lacks net-prem)  
5. `get_dark_pool_trades` + `get_dark_pool_volume_price_group` — wall-break OE soft (existing mandate)  
6. Optional context: `get_flow_per_expiry`, `get_market_tide` (index/ETF days)

**REST to add only if MCP remains blind (thin wrapper / future MCP ask):**

7. `GET /api/stock/{ticker}/net-prem-ticks` — true net premium drift  
8. `GET /api/stock/{ticker}/option/stock-price-levels` — option volume at wall price  

**Do not:** upgrade to UW Advanced solely for WebSocket unless Q5 moves to push streaming; do not use UW Spot GEX as walls primary (FA Growth).

### If we add QD later — exact Q5 shortlist

Wire **only** these (soft color; never execution; never replace FA walls):

| Priority | REST | MCP | When |
|----------|------|-----|------|
| P0 | `POST /v1/options/tool/net-drift` | `qd_get_net_drift` | Near-wall name; confirm call vs put premium drift with `stockPrice` vs FA wall |
| P0 | `POST /v1/options/tool/order-flow/consolidated` | `qd_get_order_flow_consolidated` | Near-wall / soft #2 reinforce; prefer vs alerts-only; optional `includeComprisingTrades` |
| P1 | `POST /v1/options/tool/net-flow` | `qd_get_net_flow` (`dataMode: NET_PREMIUM`) | Aggregate premium check |
| P2 | `POST /v1/equities/tool/equity-prints` | `qd_get_equity_prints` | Only if UW DP tools fail — else skip (overlap) |

**Explicitly do not wire from QD:** exposure / heat-map / GEX / max-pain (FA + optional UW already).

**Mandate note if QD added:** soft #2 language today is UW-labeled unusual flow — QD tape would be **additional soft color**, not a replacement for the UW unusual label unless mandate is amended.

---

## 5. Pricing table (quick ref)

| Vendor | Plan | Monthly | Annual | Quota | MCP | OID fit |
|--------|------|---------|--------|-------|-----|---------|
| Unusual Whales | API Basic | **$125** | **$1,500** | 40k–80k/day (confirm) | Yes | **Current path** |
| Unusual Whales | API Advanced | **$375** (~$315 ann.) | **$3,780** | Unlimited REST + WS | Yes | Only if need streaming |
| Unusual Whales | Startup / Kafka / Ent. | **$750** / **$3,000** / custom | — | Higher / stream | Biz | Overkill for OID |
| Quant Data | API + MCP | **$149.99** | **$1,499.99** | 240/min, no monthly | Yes | **Optional later** tape/drift |
| Quant Data | Dashboard Standard | **$74.99** | **$749.99** | — | No | Not needed for agents |
| Quant Data | Enterprise redistribute | **Contact sales / unpublished** | — | Custom | Custom | If commercial redistribution |

---

## Sources

- https://unusualwhales.com/public-api  
- https://unusualwhales.com/api_lander  
- https://unusualwhales.com/pricing/enterprise  
- https://api.unusualwhales.com/llms.txt (+ operation Markdown)  
- Connected MCP inventory: `user-unusual-whales`  
- https://quantdata.us/api  
- https://quantdata.us/for-ai-agents  
- https://quantdata.us/llms.txt  
- https://quantdata.us/api/docs/endpoints/net-drift  
- https://quantdata.us/api/docs/endpoints/net-flow  
- https://quantdata.us/api/docs/endpoints/order-flow-consolidated  
- OID: `MANDATE-V1.8.md`, `OFF-EXCHANGE-SOFT.md`, `FA-GROWTH-WIRE.md`

---

*Research snapshot 2026-09-17 PT. Prices and quotas can change; confirm on vendor checkout before purchase.*
