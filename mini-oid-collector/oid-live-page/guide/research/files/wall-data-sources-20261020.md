# Options-wall data: where to get more (research only, 2026-10-20)
Nothing was bought, subscribed to or changed. Prices were read from vendor sites on 10/20/2026.

## Where today's FlashAlpha calls went
The quota day runs from 5 PM PT to 5 PM PT, because it resets at 00:00 UTC. These counts are rebuilt from the mini logs and the `X-RateLimit-Remaining` value after each call. About 2,122 of 2,500 calls were used by 4:32 PM PT.

| Caller | Calls | Notes |
|---|---|---|
| vix-live (`/stockquote/VIX`) | ~700 (33%) | Runs every 120 s, around the clock (the `overnight` session is not treated as "closed"). Only ~195 of those are during RTH. |
| futures-live (CL/BZ `/stockquote`) | 450 (21%) | Once a minute 6:30 AM–1 PM PT (~390), plus 4 an hour overnight. |
| fa-walls (mini core + rotation) | 325 (15%) | Started only at 11:20 AM today. A **full day is ~37 runs × ~29 ≈ 1,050**. |
| Agent routines / MCP (FH, WP-1..4, OPEN, Q5, marks) | ~650 (31%) | Mostly 6–9 AM PT (~220 in the 7 AM hour). |

**Correction:** walls were not what used ~2,000 calls. VIX and the oil futures used ~1,150, more than half.

**Risk for tomorrow:** with fa-walls running the full day, the total comes to ~700 + 450 + 1,050 + 650 ≈ 2,850. That is over 2,500, so the 380 floor guard will pause walls before the close.

**Wall churn:** walls barely move during the day. On 10/20, 48 of 59 names never changed call or put wall from the open to the close.

## Free savings, about 1,300–1,500 calls a day
1. **VIX:** call only during RTH (or every 10 min outside it). Saves ~450–500.
2. **Futures:** call every 5 min in RTH instead of every minute. Saves ~300.
3. **Core walls:** refresh every 30 min, and every 10 min only when price is within 0.5 ATR of a wall or volume is surging. Saves ~500–600 of the full-day 1,050.
4. **Agent routines:** read the mini's `fa-walls-pulse.json` mirror instead of pulling FlashAlpha again through the MCP. Saves ~200–400.

Together that is enough to pull walls for all 144 sector names hourly (~940) without a new plan.

## Vendors
| Option | Price | What you get | Freshness | Fit |
|---|---|---|---|---|
| FlashAlpha Alpha | $1,499/mo ($1,199/mo yearly) | Unlimited calls, same `/v1/flow/levels` | ~1 s cache (Growth is 15 s) | Drop-in, but expensive |
| Unusual Whales (already paid) | $0 extra; UW API plan is $375/mo, 120 req/min, no daily cap | `get_gex_levels` (call_wall, put_wall, gamma_flip, magnet; `oi` or intraday `vol` basis) and `get_greek_exposure_by_strike` | Snapshot at the 4 PM ET close; `vol` updates intraday | Tested on NVDA and OXY and both work. Gaps: different method (NVDA OI call wall 230 at UW vs 220 at FA); Mandate V1.8 says FA walls are primary and UW GEX is secondary; the mini has no UW key (it's MCP only) |
| Alpaca, DIY (already paid) | $0 | Chain snapshots with greeks and IV (data API, 10,000 req/min), plus OI from `/v2/options/contracts` (200 req/min) | OI is 2 trading days old (10/16 on 10/20); greeks on ~40% of contracts | Free OI walls for 144 names in ~300 calls a day; needs our own gamma math |
| Massive (Polygon) Options Starter | $29/mo | Chain snapshot with OI, greeks and IV, unlimited calls | 15-min delay; OI from the prior day | Cheapest fix for fresher OI, DIY walls |
| Massive Options Advanced | $199/mo | Same, real-time, plus quotes | Real-time | Non-professional use only |
| ORATS Live Data API | $299/mo (100k req/mo ≈ 4,500 a trading day) | Live strikes with call/put OI, gamma and IV | Under 10 s | Good DIY source; Delayed is $199, Live Intraday $599 |
| ThetaData | Value $40 (OI, no greeks) / Standard $80 (greeks, IV) / Pro $160 | OI, greeks, chain snapshots | Real-time on Standard | Needs the local Theta Terminal running |
| Tradier | Free with a brokerage account | Chains with greeks and OI, 120 req/min | Greeks ~hourly | Needs a Tradier account opened |
| Cboe All Access (LiveVol) | Free up to 500 points/day; $599/mo for 150k points | Per-strike OI and greeks | Live (OPRA fee extra) | Expensive for this use |
| GEXBoard API / TickStream | $89–169/mo / $29–69/mo | Ready-made walls and per-strike GEX | Intraday | Small vendors; unknown coverage of the 144 names |
| SpotGamma | $99 / $299 a month | No public API (dashboard and CSV export only) | – | Not usable |
