# Real-time options aggressor (buy/sell × call/put) at 10–15 s: research note

2026-10-19, 11:15 AM PT. Research only. No code or config was changed on the box, mars, or the mini. No keys were read or printed (secret **file names** were listed, not their contents).

## TL;DR recommendation

**Phase 1 costs $0 extra: use the Alpaca OPRA feed we already pay for.** The mini's collector already holds the one allowed Alpaca options websocket (`wss://stream.data.alpaca.markets/v1beta1/opra`, channels `quotes`+`trades`, Algo Trader Plus). Extend that same connection (Alpaca allows only one) like this:
1. subscribe to **trades** for our ~20 core underlyings' contracts. A wildcard `*` trade subscription is probably allowed; Alpaca only forbids `*` for option *quotes*. That needs a one-off entitlement test after hours.
2. Keep **NBBO quotes** on up to **1,000 contracts** (the plan cap). Re-rank them every few minutes so the highest-volume contracts per name (from the trade stream) stay subscribed.
3. Classify each print with the **quote rule**: at or above ask is a buy, at or below bid is a sell. Inside the spread, use nearest-side, then a tick test at exact mid. Drop multi-leg and stock-tied conditions and stale NBBO.
4. Roll the prints into **1 s buckets → rolling 15 s / 60 s** buy-call, sell-call, buy-put and sell-put volume and premium per underlying. Serve that from a new collector endpoint. livepage.py polls it every 2–3 s and draws a chip on each tile, with a **coverage %**.

Expected end-to-end latency is about 1–3 s from print to tile, set by the poll interval. CPU and bandwidth on the mini are small. Accuracy: the quote rule is right about **83%** of the time on the trades it can classify. With Lee-Ready mid handling it is about **80%** over all trades (Savickas & Wilson 2003). Treat the chip as a directional lean, not ground truth.

**Phase 2, only if Phase 1 coverage or noise disappoints: Unusual Whales API Advanced, about +$250/mo** ($375/mo vs our $125 Basic). Its websocket `option_trades:TICKER` gives every print with UW's own side tag (`ask_side`/`bid_side`/`mid_side`/`no_side`), and `net_flow:TICKER` gives running ask-minus-bid call/put premium and volume. That covers every contract with no 1,000-quote cap, and UW already separates multi-leg volume. It's the same vendor and the same side logic as the existing 15m chip, just pushed instead of polled every 4 min.

Other options I looked at and why they're not first choice: **ThetaData Options Pro (about $160/mo)** has a full OPRA trade stream that sends the last NBBO before each trade. It's the cheapest full-coverage raw path, but it needs the Java Theta Terminal running on the mini. **Databento OPRA Standard ($199/mo + $1.25 OPRA fee)** has a TCBBO schema (trade plus the NBBO just before it) across the whole chain. It's the cleanest raw data, but costs more to build. **Massive (formerly Polygon) Options Advanced ($199/mo)** also caps quotes at 1,000 contracts, the same limit Alpaca has, so it adds nothing. **Intrinio, Cboe LiveVol and DataShop** are enterprise-priced. **Tradier** needs a funded brokerage account.

---

## 1. What the mini actually has (verified over SSH from mars → `jake@Jakes-Mac-mini.local`)

| item | finding |
| --- | --- |
| Plan | Algo Trader Plus. The collector config and README say so; SIP stocks and `opra` options both authenticate (an unentitled feed errors at auth). |
| Collector | `~/oid-quote/app`, version **0.5.0**, listening on :8787, status `ok` |
| Stocks socket | `wss://stream.data.alpaca.markets/v2/sip`, 61 symbols, channels quotes/trades/bars/updatedBars, connected |
| Options socket | `wss://stream.data.alpaca.markets/v1beta1/opra`, msgpack, channels **quotes + trades**, connected since 10/18 6:37 PM PT |
| Option subs right now | **`~/oid-quote/options-subs.json` = `[]`, `desired_count 0`, `subscribed_count 0`**. The last option data arrived at **8:48 AM PT today**, so the OPRA socket is open but streaming nothing. (Side issue: option marks are probably on the RH fallback right now. The box's `option_marks.py push` should repopulate the list; that's for someone else to fix.) |
| Caps in code | `option_cap` 1000 (hard max in `config.py`). README says "**Wildcards are never sent**". |
| Trade fields stored | `cache.apply_trade` keeps `x` (exchange) and `c` (**trade conditions**). Quotes keep `c`. `feeds.py` handles `t`/`q` and `x`/`c` cancel/correction messages, which today feed live volume only. |
| REST | `data.alpaca.markets` (`/v2/stocks/snapshots`, `/v1beta1/options/snapshots?feed=opra`) |
| Other ws in the desk | None. The UW key is used over REST/MCP only (Basic plan, $125/mo per `VENDOR-BAKEOFF-UW-vs-QuantData.md`). |
| Live page | `/Users/jake/oid-live-page/livepage.py`, CLT Python 3.9, listening on 127.0.0.1:8791 |
| Mini HW / load | Mac16,10 (M4 mini), 10 cores, 16 GB. At 11:05 AM PT: load average about 2.0, CPU about 77% idle, **memory about 15 GB used / 337 MB free** (keep any new state small) |
| Secrets dir | `~/oid-quote/secrets`: `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `UW_API_KEY`, … (names only) |

## 2. Alpaca options websocket: capability check

Source: Alpaca docs, [Real-time Option Data](https://docs.alpaca.markets/docs/real-time-option-data), [About Market Data API](https://docs.alpaca.markets/docs/about-market-data-api), [WebSocket Stream](https://docs.alpaca.markets/us/v1.4.2/docs/streaming-market-data).

- **Trades and quotes, both yes.** Trade messages carry `S, t (ns), p, s, x, c` (c is the **trade condition**). Quote messages carry `bp, bs, bx, ap, as, ax, c`, which is the consolidated OPRA BBO.
- **Quote subscription cap: 1,000 contracts on Algo Trader Plus** (200 on Basic). `*` is **not allowed for option quotes** (error 413).
- **Wildcard trades:** the docs only forbid `*` for *quotes*, and the SDK documents `"*"` for `subscribe_trades`. So `trades:["*"]` is most likely allowed and would deliver the whole OPRA tape (UW puts it at **6–10M prints/day**). **This is not verified.** Testing it means a brief run of our own collector (the only process allowed to connect: 1 connection per endpoint, error 406). Do it after hours or in a maintenance window.
- **Latency:** Alpaca publishes no number. The stream is event-driven websocket. The collector already logs `source_observed_at` against receive time, so we can measure it ourselves on a few hundred prints. Expect well under 1 s exchange-to-mini (an estimate, not a measurement).
- **Connection limit 1 per endpoint.** Any aggressor logic **must live inside the existing collector**, not in a second process.

### Can we infer aggressor side? Yes, with care

Rule per print, using the latest NBBO for that contract at the time the print is received:
- `p ≥ ask` → **BUY** (customer lifted the offer). `p ≤ bid` → **SELL**.
- `bid < p < ask`: nearer side wins (EMO-style). At exact mid, use a **tick test** against the last different print price for that contract, or mark it **MID/unclassified** and report it separately (cleaner).
- Premium = `p × s × 100`. Bucket by underlying (root parsed from the OCC symbol) × {call, put} × {buy, sell, mid}.

**Pitfalls and filters**
1. **Multi-leg and complex prints.** OPRA conditions such as `MLET`, `MLAT`, `MLCT`, `MLFT`, `MESL` (multi-leg) and `TLET`/`TLAT`/`TLCT`/`TLFT`/`TESL`/`TASL`/`TFSL` (stock-tied) are priced against a package net, so leg-vs-NBBO says nothing about direction ([QuoteMedia OPRA trade indicators](https://support.quotemedia.com/support/solutions/articles/13000100515-trade-indicators-for-options-opra-); [OPRA Pillar spec](https://cdn.opraplan.com/documents/OPRA_Pillar_Output_Specification.pdf)). **Exclude** them from buy/sell and show a separate "complex %". Alpaca passes the code through as a single character in `c`, so we need to build the mapping from the Pillar spec and test it against live prints.
2. **Stale or locked NBBO.** Skip classification if the quote is older than about 2 s, the spread is crossed or locked, or the spread is more than about 50% of mid (illiquid wings). Count those as unclassified.
3. **Quote/trade ordering.** Trades and quotes arrive on one socket, but the quote that moved *because of* the trade can arrive first. Use the quote state just before the trade's timestamp: keep the last 2 quotes and pick the one with `t_quote ≤ t_trade`.
4. **Auctions and price improvement (PIP/CUBE/PRISM).** These print inside the spread, often at mid. Expect a meaningful share of contracts to land unclassified or mid. Show it, don't hide it.
5. **Cancels and corrections.** Apply them if Alpaca sends them on the options stream (the collector already handles `x`/`c` for stocks). It's not confirmed that the option feed sends them. Late or out-of-sequence condition codes should be excluded.
6. **Which contracts.** 1,000 quotes over ~20 core names is about 50 contracts per name. Pick **dynamically**: with wildcard trades on, rank each name's contracts by the last 15–30 min of premium and keep the top N quoted. Re-rank every 2–5 min and apply the changes as subscribe/unsubscribe diffs (the collector already does this without reconnecting). Without wildcard trades, fall back to near-term expiries × ATM ±N strikes. Either way, publish **coverage = classified premium / total premium seen** per name. Prints on unquoted contracts can only use the tick rule (about 59% accurate). Show those as "tick-only" or drop them.
7. **Buy/sell isn't open/close.** "Sell-put" can be a closing long put. Same caveat as UW's Ask Put chip.

## 3. Alternatives and current public pricing

| vendor / plan | monthly | real-time options stream | side field? | quote cap / coverage | notes |
| --- | --- | --- | --- | --- | --- |
| **Alpaca Algo Trader Plus** (have) | **$99, already paid** ([alpaca.markets/data](https://alpaca.markets/data)) | OPRA trades + quotes, msgpack ws | No. Infer with the quote rule | 1,000 quote subs; `*` trades probably OK | 1 connection per endpoint |
| **Unusual Whales API Advanced** | **$375** (have Basic at $125) ([UW public-api](https://unusualwhales.com/public-api); repo bakeoff) | `option_trades[:T]`, `net_flow:T`, `flow-alerts`, `interval_flow` … ([UW websocket docs](https://api.unusualwhales.com/docs/websocket.md)) | **Yes.** `tags` ask_side/bid_side/mid_side/no_side, plus NBBO at trade and multi-leg volume split ([option_trades](https://api.unusualwhales.com/docs/websocket/option-trades.md)). `net_flow` = cumulative ask−bid call/put prem/vol ([net_flow](https://api.unusualwhales.com/docs/websocket/net-flow.md)) | Full tape | The docs say "WebSocket … requires the Advanced tier" for personal use (the marketing page lists ws under Basic too; the docs win, confirm with UW). One machine per token. No replay. |
| **ThetaData Options Pro** | about **$160** (Value $40, Standard $80) ([pricing](https://www.thetadata.net/pricing); [tiers](https://docs.thetadata.us/Articles/Getting-Started/Subscriptions.html); price cross-check [FlashAlpha article](https://flashalpha.com/articles/flashalpha-vs-thetadata-options-greeks-iv-api)) | **Full trade stream**: the last NBBO is sent before each trade, plus 2 quotes after ([Full Trade Stream](https://www.thetadata.net/docs/Streaming/US-Options/Full-Trade-Stream.html)) | No, but NBBO comes attached to each print, so the quote rule covers 100% of prints | Standard: 10k quote / 15k trade streams; Pro: full trade stream | Needs the **Java Theta Terminal** on the mini (more RAM on an already-tight 16 GB box). Personal use only. |
| **Databento OPRA Standard** | **$199** + OPRA non-pro $1.25 (+2.9% card fee on pass-through) ([blog](https://databento.com/blog/introducing-new-opra-pricing-plans); [calculator](https://stockmarketstack.com/calculators/options-data-cost)) | `trades`, `cmbp-1`, `tcbbo` (NBBO just before each trade), `cbbo-1s` ([OPRA spec](https://databento.com/docs/venues-and-datasets/opra-pillar)) | No. "OPRA does not disseminate the side … side always N". Use TCBBO + quote rule | Parent-symbol subs (`NVDA.OPT`), whole chain | Cleanest raw data. Binary DBN via Python client. |
| **Massive (Polygon) Options Advanced** | **$199** ($160 annual) ([pricing summary](https://aifinhub.io/articles/polygon-io-options-data-pricing-2026/); [ws overview](https://massive.com/docs/websocket/options/overview)) | `T` trades + conditions, `Q` quotes | No | **1,000 quote contracts per connection** ([quotes doc](https://massive.com/docs/websocket/options/quotes)) | Same cap as Alpaca, so no gain |
| **Intrinio real-time OPRA** | about **$20,400/yr** + OPRA fees (enterprise) ([Intrinio realtime options](https://intrinio.com/realtime-options)) | ws trades, quotes, unusual activity | Has unusual-activity events | Full | Out of budget |
| **Tradier** | Brokerage account; real-time needs a **funded** account ([market data](https://docs.tradier.com/docs/market-data)) | ws `timesale` carries **bid/ask at print** ([streaming](https://docs.tradier.com/docs/streaming)) | No, but bid/ask comes with each print | Per-symbol subs | Needs a new brokerage relationship |
| **Cboe LiveVol / DataShop API** | All Access Tier 3 **$2,499+** plus your own OPRA pro fee ([calculator](https://stockmarketstack.com/calculators/options-data-cost)) | Yes | LiveVol has trade-side analytics | Full | Out of budget |

## 4. Recommended build (Phase 1, Alpaca, $0 incremental)

```
Alpaca OPRA ws (existing, 1 conn)
  ├─ trades:  ["*"]  (or per-contract list if * refused)
  └─ quotes:  ≤1000 dynamic contracts (top premium per core name, re-ranked every 2–5 min)
        │
collector v0.6  ~/oid-quote/app/oid_quote/aggressor.py   (hook on t/q/x/c like livevol.py)
  - per contract: last 2 NBBO (t, bid, ask) + last print price (tick test)
  - per print: drop complex/stock-tied/late conditions, stale/crossed NBBO
              → side ∈ {BUY, SELL, MID, UNQ}; prem = p*s*100
  - per underlying: ring of 1 s buckets × {C,P} × {BUY,SELL,MID,UNQ} × {vol,prem}  (~300 buckets kept)
  - GET /v1/aggressor?symbols=NVDA,AMD&window=15|60   (Bearer, same token)
        → {sym, window_s, buy_call_prem, sell_call_prem, buy_put_prem, sell_put_prem,
           vols…, mid_prem, unq_prem, complex_prem, coverage_pct, quoted_contracts, as_of}
        │
livepage.py (:8791)  poll /v1/aggressor every 2–3 s (or SSE /events push)
        │
tile chip "15s  BC 58% · SC 14% · BP 9% · SP 19%   cov 71%"  (grey "—" if as_of > 10 s or cov < 30%)
```

- **Ratios to show.** Bull share = (buy-call + sell-put) / classified premium. Bear share = (buy-put + sell-call) / classified premium. Also show call B/S = buy-call / sell-call and put B/S. Add a 60 s companion window so 15 s spikes have context.
- **Load estimate.** Full OPRA tape averages about 300–450 prints/s over RTH (6–10M/day ÷ 23,400 s), with bursts of several thousand per second. At roughly 60–100 B per msgpack print that's tens of KB/s average and a few MB/s at peak. Filtering to about 20 roots before any per-print work keeps CPU to a fraction of a core. 1,000 option quote streams add the bigger message rate (ATM quotes update many times a second). The collector already ingests 61 SIP names at about 50M messages/day without trouble. Memory for buckets is under 20 MB.
- **Rollout.** (a) After hours: test `trades:["*"]` entitlement and measure the message rate. (b) Run shadow mode for one session: log the classifications and compare per-name 5 min net premium against UW `net-prem-ticks` for the same windows. Ship the chip only if the signs agree on most windows. (c) Then put the chip on core tiles.
- **Fix the empty subs first.** `options-subs.json` is `[]` today. The marks pipeline and the new ranker have to share the 1,000-contract budget, with seat contracts pinned.

## 5. Honest accuracy expectations

- Savickas & Wilson, "On Inferring the Direction of Option Trades," *JFQA* 38(4), 2003 ([RePEc](https://ideas.repec.org/a/cup/jfinqa/v38y2003i04p881-902_00.html), [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=295024)): quote rule **83%** (classifiable trades only), Lee-Ready **80%**, EMO **77%**, tick rule **59%**. Accuracy is worse for prints inside the spread, multi-leg prints and large trades.
- Today's tape has more auction and price-improvement prints than the 1990s sample did. Expect the effective all-trades accuracy to sit at the **low end of 75–85%**, with a visible MID/unclassified slice. A 15 s window on a single name can hold only a handful of prints, so show print count and coverage, and grey out thin windows.
- UW's side tags use the same NBBO-at-trade logic, so Phase 2 improves **coverage and convenience**, not the underlying accuracy ceiling.

## Not done / open items
- Wildcard option trades on Alpaca: not tested (it needs the collector's single connection).
- Alpaca options cancel/correction messages and the exact `c` code alphabet: confirm on live data.
- UW Basic vs Advanced websocket entitlement: the docs say Advanced; confirm with UW before paying.
- Alpaca stream latency: measure with the collector's existing timestamps.
