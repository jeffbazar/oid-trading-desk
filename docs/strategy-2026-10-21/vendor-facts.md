# Vendor and broker fact sheet (workflow output, 2026-10-21)

> **Read the corrections first.** This sheet was written by a research agent whose web access was limited to search-engine extracts (the sandbox proxy blocked most vendor hosts). A second pass of adversarial fact-checkers then re-tested twelve claims drawn from it. Three were wrong as written; the corrected statements are in `verification-log.md` and in the main report (`../SCALING-STRATEGY-20261021.md`, section 14). The most important corrections:
>
> 1. **Robinhood Agentic Trading supports single-leg options orders** (rollout from 2026-06-12, all US customers by 2026-07-06) and the Customer Agreement revised 2026-10-01 expressly authorizes AI-agent orders in a dedicated Agentic account (sections 4.13 and 29.8). "Zero orders" is OID's own policy, not a Robinhood restriction. Multi-leg orders are not supported through agents.
> 2. **Alpaca retired the pattern-day-trader rule on 2026-06-04** and runs FINRA's intraday-margin framework; the PDT API fields were removed 2026-07-06. There is no $25,000 minimum or 4-in-5 lockout at Alpaca.
> 3. **FlashAlpha Basic is 250 requests/day** on the vendor's current pages (100/day is a stale figure). The conclusion (stay on Growth) is unchanged.

# Vendor & Broker Fact Sheet (checked 2026-10-21)

**Access caveat (read first).** The session's egress proxy refused CONNECT (HTTP 403) to every vendor/regulator host I tried: docs.alpaca.markets, alpaca.markets, finra.org, investor.gov, databento.com, massive.com, flashalpha.com. Only github.com was fetchable. WebSearch worked and returned extracts attributed to official URLs, but I could not open those pages myself. Status key:
- **VERIFIED** = I read the official page (GitHub repos only).
- **UNVERIFIED-S** = search-engine extract quoting an official page I could not open (treat as likely-true, confirm before acting).
- **UNVERIFIED-3P** = only third-party/press sources, or my own prior knowledge.

Budget: ~47 web calls (14 fetch attempts, 7 of which failed on blocked hosts; 26 searches).

---

## 1. Alpaca (Trading API + Algo Trader Plus)

| Fact | Source | Status |
|---|---|---|
| Options levels: L0 disabled; L1 covered calls + cash-secured puts; L2 adds long calls/puts; L3 adds call/put spreads (multi-leg). No uncovered short options at any level. | https://docs.alpaca.markets/docs/options-trading ; https://alpaca.markets/support/are-there-any-level-3-options-strategies-that-are-not-supported | UNVERIFIED-S |
| Multi-leg (order_class `mleg`, `legs[]` with symbol/side/ratio_qty/position_intent, limit price + TIF at order level) live in Trading API + dashboard since 2025-02-26; covers verticals, calendars, straddles, strangles, iron condors/butterflies. | https://docs.alpaca.markets/changelog/multi-leg-level-3-options-are-now-available-in-trading-api-and-dashboard ; https://docs.alpaca.markets/docs/options-level-3-trading | UNVERIFIED-S |
| Options order types: `market`, `limit`, `stop`, `stop_limit` only (no `trailing_stop`). Order classes for options: `simple` and `mleg` only; **bracket / OCO / OTO are equities-only** (no native bracket for options). | https://alpaca.markets/sdks/python/api_reference/trading/enums.html | UNVERIFIED-S |
| Options TIF: SDK enum page says `day` only, but changelog 2026-08-28 says docs were corrected to list `day` **and** `gtc` for options (gtc was already accepted by the API). | https://docs.alpaca.markets/us/changelog/2026-08-28-options-gtc-15a3de4 | UNVERIFIED-S (two official pages conflict; newer says GTC works) |
| Paper trading: all paper accounts get Level 3 automatically; options level application is needed only for live. | https://docs.alpaca.markets/us/v1.1/changelog/multi-leg-level-3-options-trading-in-paper ; https://alpaca.markets/learn/how-to-trade-options-with-alpaca | UNVERIFIED-S |
| PDT at Alpaca: all Alpaca accounts are margin accounts; 4 day trades in 5 business days = PDT; if equity closes < $25,000 the account is blocked from new day trades next day; after a lift, one more day trade => liquidation-only for 90 days. PDT buying power 4x prior-day excess maintenance margin. Whether options day trades count is not stated on the pages found (FINRA definition counts options). These pages predate the June 2026 FINRA change (item 4); Alpaca's transition status not found. | https://docs.alpaca.markets/docs/user-protection ; https://forum.alpaca.markets/t/1x-margin-and-pdt/14500 | UNVERIFIED-S |
| Algo Trader Plus: $99/mo; options = OPRA consolidated BBO feed real-time (Basic/free tier = "indicative" feed, trades delayed 15 min). | https://alpaca.markets/data ; https://docs.alpaca.markets/docs/about-market-data-api | UNVERIFIED-S |
| Historical option data available **from February 2024 onward only** (bars, trades). Historical option **quotes**: not confirmed; a 2025 forum thread reports 404s on historical quote requests with no official answer. | https://docs.alpaca.markets/docs/historical-option-data ; https://forum.alpaca.markets/t/historical-options-request/19218 | UNVERIFIED-S |
| ~1,000 option-contract websocket subscription cap (desk's own figure). | Not found in search; from task context | UNVERIFIED-3P |

## 2. Robinhood

| Fact | Source | Status |
|---|---|---|
| Robinhood has **no public REST trading API for equities/options**. The only documented API is the **Crypto Trading API**. | https://robinhood.com/us/en/support/articles/crypto-api | UNVERIFIED-S |
| **Agentic Trading (beta) launched 2026-05-27**: an official MCP service (reported endpoint agent.robinhood.com/mcp/trading) that AI agents (Claude, ChatGPT) connect to; trades execute in a **separate dedicated "Agentic" account**; push notifications per trade; user can pause; some trades require preview/approval; Robinhood does not audit third-party agents. **At launch: stocks only; options, crypto, futures, event contracts "coming soon."** This is almost certainly the "Robinhood MCP connector" the desk uses. | https://techcrunch.com/2026/05/27/robinhood-now-lets-your-ai-agents-trade-stocks/ ; https://finance.yahoo.com/markets/stocks/articles/robinhood-now-lets-ai-agents-123000016.html ; https://walnutinvest.com/help/robinhood-mcp-server | UNVERIFIED-3P (press, consistent across 5+ outlets; Robinhood newsroom not reachable). **Confirm whether options orders are enabled on the MCP as of Oct 2026 before any bot-execution plan assumes Robinhood.** |
| Unofficial libraries (robin_stocks etc.) rely on reverse-engineered private endpoints; third parties say Robinhood's customer agreement prohibits "automated systems, bots, or scrapers" for equities/options. Not read in Robinhood's own terms. | https://blog.traderspost.io/article/does-robinhood-allow-trading-bots ; https://algotrading101.com/learn/?p=4550 | UNVERIFIED-3P |
| Options approval: Level 2 (long calls/puts, covered calls, cash-secured puts) and Level 3 (spreads; **margin account required; cash accounts cannot get Level 3**); level shown in-app, based on investor profile. | https://robinhood.com/us/en/support/articles/360001214663 ; https://www.finder.com/how-to-trade-options-on-robinhood | UNVERIFIED-S |

## 3. Alternative execution venues (short)

| Broker | Facts | Source | Status |
|---|---|---|---|
| Interactive Brokers | Two APIs: **TWS API** (socket via TWS/IB Gateway; full order-type set incl. bracket via parentId and OCO via ocaGroup; options fully supported) and **Web API** (REST, formerly Client Portal API; WebSocket for orders/P&L; historically fewer features/less documentation than TWS API). Paper-trading accounts available. Options commissions: IBKR Lite $0.65/contract; IBKR Pro $0.65 fixed, tiered lower (Tradier's March-2026 comparison lists IB Lite at $0.65). Python: ib_async (item 8) or official ibapi. | https://www.interactivebrokers.co.uk/de/trading/ib-api.php ; https://trade.tradier.com/tradierpro/ ; https://wealth-lab.com/Discussion/Interactive-Brokers-client-API-portal-vs-TWS-IBGateway-12267 | UNVERIFIED-S/3P |
| Tradier | REST brokerage API; sandbox at sandbox.tradier.com (15-min delayed data, no streaming, no account activity); order classes `oto`, `oco`, `otoco` with option legs (`buy_to_open` etc.); only first OTOCO leg may be market. Pricing (Tradier page, rates as of March 2026): **Pro plan $10/mo flat for unlimited equity/ETF options** + exchange/clearing/regulatory fees. | https://docs.tradier.com/reference/brokerage-api-trading-place-otoco-order ; https://documentation.tradier.com/brokerage-api/trading/place-oto-order ; https://trade.tradier.com/tradierpro/ | UNVERIFIED-S |
| tastytrade | Open API at developer.tastytrade.com (public docs, SDKs, and an official MCP server + "Agent Quickstart"); sandbox host api.cert.tastyworks.com (separate credentials, resets every 24 h, quotes 15-min delayed or absent per conflicting pages); complex orders OTO/OCO/OTOCO with dry-run endpoints. Commissions: $1.00/contract to open, $0 to close (per Tradier comparison; cap $10/leg from memory). No paper trading in the retail app; sandbox is the test path. | https://developer.tastytrade.com/open-api-spec/orders/ ; https://developer.tastytrade.com/sandbox ; https://developer.tastytrade.com/docs/sdks-and-tools/mcp-server/ | UNVERIFIED-S |

PDT handling: all three are margin-capable brokers subject to FINRA 4210; each may still apply legacy PDT during the transition window (item 4). Not individually verified.

## 4. FINRA pattern day trader rule (2025-2026 change)

| Fact | Source | Status |
|---|---|---|
| Legacy rule: PDT = 4+ day trades in 5 business days where day trades > 6% of total trades in a **margin** account; $25,000 minimum equity; day trades include options (a round trip in the same option contract). | https://www.finra.org/investors/investing/investment-products/stocks/day-trading ; https://www.investor.gov/introduction-investing/investing-basics/glossary/pattern-day-trader | UNVERIFIED-S (blocked hosts; the 6% carve-out is standard rule text) |
| **Rule replaced.** FINRA filed SR-FINRA-2025-017 amending Rule 4210; SEC granted accelerated approval ~April 14-15, 2026. Amendments **eliminate the PDT designation, the 4-in-5 test, the $25k minimum and day-trading buying power**, replacing them with an **"intraday margin" standard** measured on maximum intraday exposure. **Effective June 4, 2026, with a firm-level transition period until October 20, 2027** - a broker may keep legacy PDT rules or move early. | https://www.finra.org/sites/default/files/2026-01/SR_FINRA-2025-017-91-FR-1580.pdf ; https://www.investor.gov/introduction-investing/investing-basics/glossary/pattern-day-trader ; https://www.kslaw.com/insights/articles/finra-adopts-sweeping-changes-to-margin-requirements-for-day-trading ; https://www.jdsupra.com/legalnews/finra-adopts-sweeping-changes-to-margin-8807068/ | UNVERIFIED-S (multiple law-firm + investor.gov extracts agree; one blog (Option Alpha) still describes the old rule - stale). **Action: ask Alpaca/IBKR/Tradier/tastytrade which regime they apply today.** |
| Cash accounts: PDT never applied (margin only); constraint is **settled funds** - equities and options settle **T+1**; buying with unsettled proceeds and selling before settlement = good-faith violation (brokers typically restrict after 3-5 GFVs in 12 months). Cash accounts cannot hold Level 3 at Robinhood. | https://www.tradingsim.com/blog/margin-account-vs-cash-account-which-is-better-for-traders ; https://ig.com/uk/help-and-support/us-options-and-futures-cf57eec3/faqs-d3eab104/z-good-faith-violations-us-options-futures-e951c4ab | UNVERIFIED-3P |

## 5. Options data vendors

| Vendor | Facts | Source | Status |
|---|---|---|---|
| Databento OPRA | **Standard OPRA plan $199/mo** (launched June 2025, live + historical, no exchange license fees); former Enterprise plans renamed **Plus** and **Unlimited** (prices not found; one extract mentions a $1,500/mo license-fee tier adding external distribution). **Usage-based live OPRA discontinued 2025-06-03**; usage-based historical still available (metered by uncompressed binary size). History from **2013-04-01** for trades, OHLCV, statistics, definition, **cbbo-1m**; **cmbp-1** (NBBO + trades) full feed = several TB/day; **tcbbo** = NBBO snapshot just before each trade. June 22, 2026 price update touched CME/US equities/ICE only, "all other plans unaffected." | https://databento.com/blog/introducing-new-opra-pricing-plans ; https://databento.com/catalog/opra/OPRA.PILLAR ; https://databento.com/blog/opra-migration ; https://databento.com/blog/updates-to-subscription-pricing | UNVERIFIED-S |
| Massive (ex-Polygon, rebranded Oct 2025) | Individual US-stock plans: Basic $0, Starter $29, Developer $79, Advanced $199/mo. **Options is a separately priced asset-class subscription**; individual plans are personal/non-professional use only (Business plans custom-priced, required for commercial use/redistribution). Options plan prices not confirmed. | https://qveris.ai/guides/polygon-pricing-optimized/ ; https://apicostcalc.com/de/blog/polygon-massive-rebrand-api-pricing.html | UNVERIFIED-3P |
| ThetaData | Options (individual): **Value $40, Standard $80, Pro $160 /mo**; ~8 years history; real-time; Pro = tick-level + larger streaming contract caps (one docs version: Standard 1,000 / Pro 2,000 quote streams; another puts tick-level in Pro only). Commercial use priced separately. | https://thetadata.net/pricing ; https://thetadata.net/subscribe ; https://docs.thetadata.us/Articles/Getting-Started/Subscriptions.html | UNVERIFIED-S (vendor pages conflict on tier contents) |
| Cboe DataShop | Products (via LiveVol): EOD and intraday option quote/trade files, Market Data API, Time & Sales API; **no pricing found**. | https://datashopcert.livevol.com/options | UNVERIFIED-3P |
| Unusual Whales API | Since 2025-05-27: trial $50/week, **Basic $150/mo, Advanced $375/mo** (grandfathered older rates). Per-minute rate limits and 2026 prices not found; desk's "50 EOD rows/contract" historic-chain cap is from desk context. | https://unusualwhales.substack.com/p/unusual-whales-api-prices-increasing | UNVERIFIED-S (vendor newsletter) |

## 6. FlashAlpha

| Fact | Source | Status |
|---|---|---|
| Plans: Starter free (5 req/day, 15-min freshness, single-expiry GEX, call/put wall, gamma flip); **Basic $79/mo** ($63 annual; 100 req/day, 15-s freshness); **Growth $299/mo** ($239 annual; full-chain GEX, exposure summary, dealer-positioning narrative; **2,500 req/day** per vendor article); **Alpha $1,499/mo** ($1,199 annual; "unlimited" per vendor article). | https://flashalpha.com/pricing ; https://flashalpha.com/use-cases/dealer-positioning-trading ; https://flashalpha.com/articles/flashalpha-vs-polygon-options-data-raw-vs-computed | UNVERIFIED-S |
| **Historical walls/GEX API exists**: mirrors live endpoints, minute resolution, SPY from 2018-04-16, **Alpha tier only**. SDK (NuGet FlashAlpha 1.2.1) tags VRP history as Alpha-only, VIX-state as Growth+. | https://flashalpha.com/articles/historical-gex-api-backtesting-gamma-exposure-strategies ; https://www.nuget.org/packages/FlashAlpha/1.2.1 | UNVERIFIED-S |

## 7. Free/cheap sources

| Source | Facts | URL | Status |
|---|---|---|---|
| Kalshi API | Public trade API v2; historical trades endpoint reported to need no auth; Kalshi's own docs not reached. Third-party (Oddpool) offers orderbook+trade history from 2026-03-19 on free tier. | https://zuplo.com/learning-center/kalshi-api.md ; https://docs.oddpool.com/kalshi/overview.md | UNVERIFIED-3P |
| Korea customs 10-day exports | KCS publishes 1-10 / 1-20 day export figures monthly (around the 11th/21st). data.go.kr free REST API "Export/Import performance by item" (XML; base http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList; dev quota 50,000 calls); whether the 10-day series is in that endpoint is not confirmed. CEIC carries the series (paid). | https://www.data.go.kr/en/data/15100475/openapi.do ; https://www.ceicdata.com/en/korea/trade-statistics-first-10-days | UNVERIFIED-S |
| FINRA short interest | Official API: POST https://api.finra.org/data/group/otcMarket/name/EquityShortInterest (CSV or JSON); covers NYSE/Nasdaq/AMEX/ARCA/BZX/OTC; 5 rolling years online; bi-monthly settlement cycle. API-key requirement not confirmed. | https://www.finra.org/sites/default/files/Equity_Short_Interest_Data_File_Download_API.pdf ; https://www.finra.org/finra-data/browse-catalog/equity-short-interest | UNVERIFIED-S |
| Silicon Data GPU index | SDH100RT H100 rental index launched May 2025; published once per business day (USD/GPU-hour); portal, direct API, Bloomberg, Kaiko. No public API pricing/free tier found. | https://www.silicondata.com/products/silicon-index/h100 | UNVERIFIED-S |
| SEC EDGAR | Full-text search JSON endpoint https://efts.sec.gov/LATEST/search-index?q=... (no auth; filings since 2001; indexed within minutes; 10,000 hits/query); SEC fair-access limit 10 req/s with User-Agent header. Acceptance timestamps: `acceptanceDateTime` field in https://data.sec.gov/submissions/CIK##########.json (from prior knowledge). | https://apify.com/andrew_avina/edgar-fulltext-mcp.md (3P) | UNVERIFIED-3P |
| FRED/ALFRED | FRED API (free key): `series/observations` accepts `realtime_start`/`realtime_end` for vintage-as-of data; `series/vintagedates` lists vintages. Search returned nothing; prior knowledge. | https://fred.stlouisfed.org/docs/api/fred/ | UNVERIFIED-3P |

## 8. Open-source stacks

| Project | Facts | URL | Status |
|---|---|---|---|
| karpathy/autoresearch | "AI agents running research on single-GPU nanochat training automatically." Agent edits **only `train.py`**, runs fixed 5-minute training, keeps/discards by `val_bpb`; `prepare.py` fixed; **`program.md` is the human-edited agent instruction file**. MIT, 98.3k stars, 36 commits. It is an LLM-training experiment loop, not a trading tool; the desk borrowed its loop/`program.md` pattern. | https://github.com/karpathy/autoresearch | VERIFIED |
| NautilusTrader | Rust core, Python control plane; backtest + live same code; adapters incl. **Interactive Brokers, Databento, Kalshi, Polymarket**, Betfair, major crypto venues; **no Alpaca/Tradier/Polygon adapter** listed; options mentioned generically. LGPL-3.0; 30.4k stars; stable 1.x on PyPI, 2.0.0rc line in progress. | https://github.com/nautechsystems/nautilus_trader | VERIFIED |
| QuantConnect Lean | C# engine with first-class Python; Apache-2.0; 22.1k stars; local via `pip install lean` (Docker); README does not list brokerages (IB/Tradier/Alpaca/tastytrade/Schwab plugins exist per QuantConnect docs - UNVERIFIED-3P). | https://github.com/QuantConnect/Lean | VERIFIED |
| vectorbt (free) | Vectorized pandas/NumPy/Numba backtester; fair-code (Apache 2.0 + Commons Clause); 9.5k stars; **no options support**; limit orders/leverage are PRO-only (paid vectorbtpro). | https://github.com/polakowo/vectorbt | VERIFIED |
| hummingbot | Crypto CEX/DEX market-making only; **no equity/options brokers**; Apache-2.0; 20.6k stars. Not relevant. | https://github.com/hummingbot/hummingbot | VERIFIED |
| alpaca-py | Official SDK, Apache-2.0, Python 3.10+, 1.6k stars; `OptionHistoricalDataClient`, `OptionDataStream`, multi-leg examples folder. | https://github.com/alpacahq/alpaca-py | VERIFIED |
| ib_async | Successor to ib_insync (renamed after original author's death early 2024; maintainers lost access to old repo); maintained by Matt Stancliff; BSD-2; Python 3.10+; 1.8k stars; implements IB protocol natively (no `ibapi` needed). | https://github.com/ib-api-reloaded/ib_async | VERIFIED |

## 9. Evidence on short-horizon retail options edge, 0DTE flow, dealer gamma

| Finding | Citation | Status |
|---|---|---|
| Retail 0DTE traders lose: ~$125M aggregate, ~$350k/day since weekday SPX expirations; 0DTEs "not a lucrative vehicle for retail." | Beckmeyer, Branger & Gayda, "Retail Traders Love 0DTE Options... But Should They?" (SSRN 2023/24); summarized at https://neudata.co/literature-reviews/zero-day-to-expiry-options-a-losing-bet-for-retail-traders | UNVERIFIED-S |
| Retail options flow (wholesaler-flagged) favors cheap weeklies, pays ~12.6% effective bid-ask spread, loses on average. | Bryzgalova, Pavlova & Sikorskaya, "Retail Trading in Options and the Rise of the Big Three Wholesalers," Journal of Finance 2023; abstract at https://econ.au.dk/research/finance/seminars/vis/artikel/accounting-and-finance-seminar-svetlana-bryzgalova-london-business-school | UNVERIFIED-S |
| 0DTE = ~60% of SPX option volume in 2025; ~1.5M 0DTE contracts/day; mixed evidence on whether they raise underlying volatility. | Cboe figures via Schwab https://workplace.schwab.com/story/zeroing-on-0dte-options-learn-basics ; Brogaard, Han & Won (2023) "How does 0DTE trading affect volatility" (SSRN) | UNVERIFIED-3P |
| 0DTE mispricing test via volatility-arbitrage Sharpe ratios (2026). | HKUST summary https://bm.hkust.edu.hk/bizinsight/2026/04/are-0dte-options-mispriced | UNVERIFIED-S |
| Dealer gamma: aggregate hedging demand predicts intraday momentum (last-half-hour), and dealer gamma imbalance predicts intraday reversal/momentum regimes and volatility; 0DTE gamma propagates volatility. | Baltussen, Da, Lammers & Martens, "Hedging demand and market intraday momentum," JFE 2021; Barbon & Buraschi, "Gamma Fragility" (SSRN 2021); Dim, Eraker & Vilkov, "0DTEs: Trading, Gamma Risk and Volatility Propagation" (SSRN 2024); Gao, Han, Li & Zhou, "Market intraday momentum," JFE 2018 | UNVERIFIED-3P (prior knowledge; SSRN not reachable) |
| Practitioner: BMLL/SpiderRock white paper argues dealer short-gamma in large-cap tech amplifies intraday momentum. | https://www.bmlltech.com/files/documents/BMLL-Spiderrock-White-Paper.pdf | UNVERIFIED-S |
| **No peer-reviewed evidence found that single-name "call/put wall" levels predict touches/breaks** beyond volume effects; the academic gamma results are index-level (SPX/SPY) and regime-level, consistent with the desk's own wall-magnet null (46.9% vs 44.9%) and "volume is the real switch." | - | Assessment |

## Could not verify at all
- Alpaca: whether options historical **quotes** exist; options websocket cap; Alpaca's post-June-2026 PDT regime.
- Robinhood: whether the Agentic MCP now supports options orders (stocks-only at May 2026 launch); exact customer-agreement text on bots.
- IBKR 2026 commission schedule and Web API order-type matrix; Massive options-plan prices; Databento Plus/Unlimited OPRA prices; Cboe DataShop prices; Unusual Whales rate limits/2026 prices; FlashAlpha Growth/Alpha quotas from the pricing page itself (only vendor articles).
- Kalshi official docs; data.go.kr 10-day series endpoint; FRED/ALFRED and SEC EDGAR official pages (blocked); all SSRN papers in item 9.