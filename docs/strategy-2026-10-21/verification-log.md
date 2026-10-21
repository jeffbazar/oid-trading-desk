# Verification log (adversarial fact-check, 2026-10-21)

Each claim below was drawn from the synthesized plan and handed to two independent fact-checkers instructed to refute it. `refuted=true` from both means the claim as written was wrong; the correction column gives what is actually true. Sources are what the checkers cited (web pages were reached through search extracts where the sandbox proxy blocked direct access).

## 1. CONFIRMED: Alpaca's options trading API supports only the `simple` and `mleg` order classes for options (no bracket/OCO/OTO) and only `market`, `limit`, `stop`, `stop_limit` order types (no `trailing_stop`), so option brackets must be emulated client-side.

*Why it matters:* The entire Bracket Manager design (resting TP + software stop + time stop) and the Tradier fallback decision rest on this; if Alpaca has native option OCO the synthetic bracket and its reconnect risk are unnecessary.

**Checker 1** (refuted=False, confidence 0.9).

Evidence: Alpaca's official alpaca-py SDK source (alpaca/trading/enums.py, master branch, fetched 2026-10-21) states verbatim in the OrderClass docstring: "Equity trading: simple (or ""), oco, oto, bracket. - Options trading: simple (or ""), mleg (required for multi-leg complex options strategies). - Crypto trading: simple (or "")." And in the OrderType docstring: "Equity trading: market, limit, stop, stop_limit, trailing_stop. - Options trading: market, limit, stop, stop_limit. - Crypto trading: market, limit, stop_limit." The SDK's requests.py adds that mleg orders take 2-4 legs and that limit_price is required for simple/bracket/oto/mleg, with no options-specific bracket path. Corroborating secondary sources: an Alpaca forum thread ("Bracket Order for Option | Error - complex orders not supported for options trading") where Alpaca staff replied that bracket, OTO and OCO are supported for equity orders but not option orders; a July 2026 forum reply by Alpaca staff (Dan Whitnable) that trailing stops on multi-leg orders are not on the roadmap; and a TradersPost broker comparison (~Sept 2026) reporting that Alpaca returns an API error for trailing stops on options and for bracket orders on options/crypto. An extended search for any 2025-2026 announcement adding options bracket/OCO/trailing-stop support found none. Caveats: docs.alpaca.markets, alpaca.markets and forum.alpaca.markets did not resolve through this session's proxy, so the REST reference page itself could not be read directly; the SDK docstring is the primary artifact used, and the commit date of enums.py could not be confirmed via gh (repo not attached). The local repos (/home/user/oid-trading-desk, /home/user/oid-research) contain no Alpaca order-class material either way; the desk's mandate there is research/paper only with zero brokerage execution.

Correction: No correction needed. The claim stands as stated: on Alpaca, option orders are limited to order_class simple or mleg and type market/limit/stop/stop_limit; bracket/OCO/OTO and trailing_stop are equity-only, so a take-profit + stop pair on a single option contract must be managed client-side (resting limit plus a software-monitored stop, or two separate orders with the client cancelling the other on fill). One nuance worth noting for the design: Alpaca does accept native `stop` and `stop_limit` types on options, so the protective leg can be a resting broker-side stop rather than a purely software stop; what is missing is the OCO linkage, not the stop order itself.

Sources:
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/trading/enums.py
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/trading/requests.py
- https://alpaca.markets/sdks/python/api_reference/trading/enums.html
- https://forum.alpaca.markets/t/bracket-order-for-option-error-complex-orders-not-supported-for-options-trading/14241
- https://forum.alpaca.markets/t/trailing-stop-orders-as-part-of-advanced-orders/10146/7
- https://blog.traderspost.io/article/traderspost-broker-comparison
- https://docs.alpaca.markets/docs/options-trading-overview
- /home/user/oid-trading-desk/prompts/01-rose-trader-prompt.txt
- /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md

**Checker 2** (refuted=False, confidence 0.8).

Evidence: Primary source: Alpaca's official Python SDK (alpacahq/alpaca-py, master branch; enums.py last modified Oct 16, 2026, and explicitly realigned to "the current Trading and Broker OpenAPI specs" in PR #789 merged Sep 28, 2026). Its OrderClass docstring reads verbatim: "Equity trading: simple (or ""), oco, oto, bracket. / Options trading: simple (or ""), mleg (required for multi-leg complex options strategies). / Crypto trading: simple (or "")." Its OrderType docstring reads: "Equity trading: market, limit, stop, stop_limit, trailing_stop. / Options trading: market, limit, stop, stop_limit. / Crypto trading: market, limit, stop_limit." The same text appears on Alpaca's hosted SDK reference (alpaca.markets/sdks/python/api_reference/trading/enums.html). alpaca-py's request validators also state "mleg order class only supports market and limit orders." Corroboration: Alpaca staff replied on the Alpaca forum ("Bracket Order for Option | Error - complex orders not supported for options trading", thread 14241, and thread 14076 for OTO/OCO) that bracket, OTO and OCO "are not yet supported for options trading"; a newer forum thread "No exit bracket OCO for Options" (18856, activity dated May 2026) shows a user still asking for OCO on options with no resolution found; TradersPost's Alpaca connection docs state Alpaca "does not support complex orders (OCO, OTO, bracket) for the Crypto or Options asset class." PR #815 (Oct 15, 2026) added group_id/group_role parsing for bracket/OTO/OCO groups with no mention of options. The local repos (/home/user/oid-trading-desk, /home/user/oid-research) contain no Alpaca order-class or bracket/Tradier material, so this is purely a vendor claim. Caveats: (1) I could not reach docs.alpaca.markets, forum.alpaca.markets, or web.archive.org directly from this sandbox (DNS/proxy 403), so verification rests on Alpaca's GitHub SDK source and search-engine excerpts of the docs/forum; (2) one third-party blog (TradersPost, "How to Use Trailing Stops on Options", fact-checked Dec 2025) claims Alpaca options now include trailing stop orders, but this is contradicted by Alpaca's own SDK enums aligned to the OpenAPI spec nine months later, and I found no Alpaca changelog or announcement supporting it; recommend a paper-account probe (POST /v2/orders with type=trailing_stop on an option symbol) before relying on either. Not part of the claim but relevant: an Alpaca changelog entry dated 2026-08-28 says the TimeInForce schema now lists gtc alongside day for options orders.

Correction: No correction needed as stated. Minor precision: alpaca-py validators also restrict mleg orders to market and limit types only (stop/stop_limit apply to single-leg options), and the one dissenting third-party source (TradersPost, Dec 2025) claiming options trailing stops is unverified against Alpaca's own current spec-aligned SDK; a single paper-trading probe would settle the trailing_stop point definitively.

Sources:
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/trading/enums.py
- https://github.com/alpacahq/alpaca-py/blob/master/alpaca/trading/enums.py
- https://github.com/alpacahq/alpaca-py/commits/master/alpaca/trading/enums.py
- https://github.com/alpacahq/alpaca-py/pull/789
- https://github.com/alpacahq/alpaca-py/pull/815
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/trading/requests.py
- https://alpaca.markets/sdks/python/api_reference/trading/enums.html
- https://forum.alpaca.markets/t/bracket-order-for-option-error-complex-orders-not-supported-for-options-trading/14241
- https://forum.alpaca.markets/t/i-cant-submit-oto-order-or-oco-order-with-option-symbol/14076
- https://forum.alpaca.markets/t/no-exit-bracket-oco-for-options/18856
- https://docs.traderspost.io/docs/all-supported-connections/alpaca
- https://blog.traderspost.io/article/how-to-use-trailing-stops-on-options
- https://docs.alpaca.markets/docs/options-level-3-trading
- https://docs.alpaca.markets/eu/changelog/2026-08-28-options-gtc-15a3de4
- /home/user/oid-research/program.md
- /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md

## 2. CONFIRMED: Alpaca accepts GTC time-in-force on options orders (per the 2026-08-28 changelog), so a resting take-profit limit can be left in place across the session.

*Why it matters:* If only `day` TIF is honored, the resting TP must be re-posted and the stop logic must handle a missing resting order; the two Alpaca docs pages conflict.

**Checker 1** (refuted=False, confidence 0.85).

Evidence: Alpaca's changelog entry dated 2026-08-28 ("GTC time-in-force documented for options orders") states the TimeInForce schema now lists gtc alongside day for options and that the change is documentation-only because the gtc enum value was already accepted (wire contract unchanged); the EU changelog files the same item under "Fixed", noting the earlier docs listed only day, which did not match accepted values. The current Options Trading doc says "time_in_force must be day or gtc", and the Create an Order reference lists "Options trading: day, gtc". Alpaca's Learn article "How to Use GTC Orders for Options with Alpaca" says "Alpaca now supports Good 'Til Cancelled (GTC) orders for options" (GTC supported only for limit orders, which covers a resting take-profit limit). Independent corroboration: QuantConnect Lean.Brokerages.Alpaca PR #84 (2026-09-28) removed its guard that forced option GTC orders to day and now sends gtc, citing those Alpaca docs; alpacahq/alpaca-mcp-server PR #126 (2026-09-25) updated its place_option_order tool from "day only" to support gtc per the September 2026 OpenAPI spec. The conflicting "day only" text comes from stale sources: the Options Trading Overview page and the alpaca-py TimeInForce docstring (alpaca/trading/enums.py line 351: "Options trading: day."), both predating the August correction. Note: I could not fetch docs.alpaca.markets or alpaca.markets directly (proxy 403/DNS); their content was obtained via web-search excerpts and quotations inside the GitHub PRs, while the alpaca-py source was fetched directly from GitHub.

Correction: Claim stands. Caveats for the desk: (1) GTC on options is documented for limit orders (Alpaca Learn: "GTC is currently supported only for Limit orders"), so use a plain GTC limit for the resting TP, not a market/stop GTC; (2) the stale "day only" statements in the Options Trading Overview page and alpaca-py docstring are the source of the apparent doc conflict and should be ignored; (3) Alpaca still does not support bracket/OCO orders on options, so the TP limit and any stop logic remain separate orders and the stop logic must still cancel/replace the resting TP on exit; (4) verify once in paper trading that a gtc option limit order is accepted rather than returning 422 "invalid option time_in_force".

Sources:
- https://docs.alpaca.markets/us/changelog/2026-08-28-options-gtc-15a3de4
- https://docs.alpaca.markets/eu/changelog/2026-08-28-options-gtc-15a3de4
- https://docs.alpaca.markets/us/docs/options-trading
- https://docs.alpaca.markets/us/reference/postorder
- https://alpaca.markets/learn/how-to-trade-good-til-canceled-options-trading-with-python-and-alpaca
- https://github.com/QuantConnect/Lean.Brokerages.Alpaca/pull/84
- https://github.com/alpacahq/alpaca-mcp-server/pull/126
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/trading/enums.py (saved at (session scratch file, not retained) TimeInForce docstring line 351 shows the stale day-only text)
- https://docs.alpaca.markets/us/docs/options-trading-overview (stale day-only listing)

**Checker 2** (refuted=False, confidence 0.85).

Evidence: Primary sources support the claim. (1) Alpaca docs changelog dated 2026-08-28 ("GTC time-in-force documented for options orders", https://docs.alpaca.markets/us/changelog/2026-08-28-options-gtc-15a3de4): the TimeInForce schema now lists gtc alongside day for options orders; it states "the gtc enum value was already accepted; only the per-security-type documentation changed", i.e. no wire-contract change. (2) Alpaca Options Trading docs page: "time_in_force must be day or gtc" (https://docs.alpaca.markets/us/docs/options-trading). (3) Alpaca blog "Alpaca Adds Good 'Til Cancelled (GTC) Orders for Options via Trading API": "Good 'Til Cancelled (GTC) orders for options are now available through Alpaca's Trading API." (4) Alpaca learn guide: "Placing a GTC order is similar to a Day order. You just need to change the time_in_force parameter to GTC" and "GTC is currently supported only for Limit orders" (https://alpaca.markets/learn/how-to-trade-good-til-canceled-options-trading-with-python-and-alpaca). (5) Third-party corroboration: QuantConnect Lean.Brokerages.Alpaca PR #84 (merged 2026-09-28) "A GoodTilCanceled option order is now sent to Alpaca as gtc, the same as for equities", citing the same Alpaca docs. The "two docs pages conflict" referenced in the claim's context is real but resolved: the Create Order reference / alpaca-py enums page previously listed options as day-only; the 2026-08-28 changelog is precisely the fix that brought the per-security-type docs in line with the already-accepted behavior. Note: docs.alpaca.markets and alpaca.markets could not be fetched directly from this sandbox (DNS/proxy 403); evidence comes from search-engine snippets of those pages plus a direct fetch of the GitHub PR. Local repos (/home/user/oid-trading-desk, /home/user/oid-research) contain no mention of Alpaca GTC/TIF, so no desk-side evidence either way.

Correction: Not refuted, but two caveats narrow the claim: (a) Alpaca's own GTC-options guide says GTC is currently supported only for LIMIT options orders, which covers a resting take-profit limit but means a GTC stop/stop-limit on the option is unconfirmed (a forum question on stop+gtc for single-leg options has no official answer); the stop/invalidate leg should still be handled by the bot, not by a resting GTC stop. (b) Alpaca's aged-order policy auto-cancels GTC orders 90 days after creation (irrelevant for same-day holds). The stale alpaca-py enums page listing options TIF as "day" only is outdated per the 2026-08-28 changelog; the bot should still handle a missing resting order defensively (cancel/reject/expiry), but not because GTC is unsupported.

Sources:
- https://docs.alpaca.markets/us/changelog/2026-08-28-options-gtc-15a3de4
- https://docs.alpaca.markets/us/docs/options-trading
- https://docs.alpaca.markets/us/reference/postorder
- https://alpaca.markets/blog/alpaca-launches-gtc-orders-for-options-on-the-trading-api/
- https://alpaca.markets/learn/how-to-trade-good-til-canceled-options-trading-with-python-and-alpaca
- https://github.com/QuantConnect/Lean.Brokerages.Alpaca/pull/84
- https://alpaca.markets/sdks/python/api_reference/trading/enums.html
- https://forum.alpaca.markets/t/proper-options-json-kata/19041
- https://docs.alpaca.markets/us/docs/orders-at-alpaca

## 3. CONFIRMED: Alpaca paper accounts receive options Level 3 automatically, so multi-leg and long calls/puts can be paper-traded without an application.

*Why it matters:* Stage 1 and Stage 2 paper gates assume paper execution is available immediately; if an application is required the day-8 OMS milestone slips.

**Checker 1** (refuted=False, confidence 0.8).

Evidence: Could not refute. Alpaca's own documentation and launch materials state the claim nearly verbatim. (1) docs.alpaca.markets "Options Trading" page: "In the Paper environment, options trading capability will be enabled by default - there's nothing you need to do!" (quoted consistently by the search index and by three independent GitHub repos that cite the page). (2) Alpaca blog "Multi-Leg (Level 3) Options Trading Now Available with Alpaca's Trading API" (2025-02-25) and the changelog entry "Multi-leg (Level 3) Options Trading in Paper" (Jan/Feb 2025): "All paper trading accounts will automatically have access to Level 3 strategies. You only need to apply for your desired level if you are looking to live trade options." (3) Alpaca Learn article "How To Trade Options with Alpaca's Dashboard and Trading API" repeats the same sentence. (4) Alpaca's level definitions: Level 2 = long calls/puts, Level 3 = spreads/multi-leg (order_class "mleg", 2-4 legs), so Level 3 in paper covers both the desk's long calls/puts and multi-leg. Limitation: the proxy in this session blocks alpaca.markets, docs.alpaca.markets, web.archive.org and mirror fetchers (403 CONNECT / ENOTFOUND), so I could not read the primary pages first-hand; the quotes come from search-engine extracts of those pages plus independent third-party repos quoting them identically (Abhiram-0910/alpaca-options-agent docs/RESEARCH.md, Auirsblade/ashercarlow-api tasks/todo/alpaca-api-discovery.md, vishnu-0011/conviction-spread-agent docs/research/alpaca-platform-research.md, tyleree/jevbot docs/research/02-critique-and-corrections.md). No local file under /home/user/oid-trading-desk or /home/user/oid-research mentions Alpaca options levels, so the desk has not verified this on its own paper account.

Correction: Claim stands as stated, with two caveats worth a 5-minute check before the day-8 OMS milestone: (a) one third-party report says a fresh paper account can show a restrictive options_trading_level until max_options_trading_level is set via PATCH /v2/account/configurations (options_trading_level is always <= options_approved_level and can be lowered in Dashboard > Account > Configure), so the OMS should assert at boot that GET /v2/account returns options_approved_level >= 3 and options_trading_level >= 2 (or 3 for mleg) rather than assume it; (b) the automatic Level 3 applies to PAPER only; a LIVE account requires the options application/suitability questionnaire in the dashboard, and the approved live level may be lower than what was tested in paper. Paper execution requires an Alpaca trading account with paper API keys (paper-api.alpaca.markets), which is separate from the Algo Trader Plus data subscription already in use.

Sources:
- https://docs.alpaca.markets/docs/options-trading
- https://docs.alpaca.markets/changelog/multi-leg-level-3-options-trading-in-paper
- https://alpaca.markets/blog/level-3-options-trading-now-available-with-alpacas-trading-api/
- https://alpaca.markets/learn/how-to-trade-options-with-alpaca
- https://docs.alpaca.markets/docs/options-level-3-trading
- https://docs.alpaca.markets/us/docs/options-trading-overview
- https://github.com/Auirsblade/ashercarlow-api/blob/cb8f876b7b58c741aa3e5d7c69601e026e76203d/tasks/todo/alpaca-api-discovery.md
- https://github.com/Abhiram-0910/alpaca-options-agent/blob/e3509f80fd5b1435bed24a8f7e7da8a633e1eb92/docs/RESEARCH.md
- https://github.com/vishnu-0011/conviction-spread-agent/blob/bd06dd42343eb5c4b0fab78f7fc6cadd4c615a70/docs/research/alpaca-platform-research.md
- https://github.com/tyleree/jevbot/blob/9dd505192dff821b00ae2a8880bd9d4b2b5bf655/docs/research/02-critique-and-corrections.md

**Checker 2** (refuted=False, confidence 0.8).

Evidence: Alpaca's own pages, as surfaced in search snippets (direct fetches of docs.alpaca.markets and alpaca.markets are blocked by this session's proxy, so I could not read the full page bodies), consistently support the claim: (1) Alpaca's options tutorial/learn page states "all paper trading accounts will automatically have access to Level 3 strategies" and "You only need to apply for your desired level if you are looking to live trade options." (2) The Options Trading docs state options trading is "enabled by default in the Paper environment," requiring no user action; the level table there lists Level 2 = buying calls and puts, Level 3 = spreads. (3) The docs changelog entry "Multi-leg (Level 3) Options Trading in Paper" and Alpaca's X post of 21 Jan 2025 announce mleg (order_class="mleg" with a legs array via POST /v2/orders) available in the Trading API and dashboard in paper. (4) The launch blog says paper accounts automatically get Level 3 access while live trading requires an application, and the alpaca.markets/options page says single- and multi-leg options are supported for both paper and live. Caveats: I could not independently verify the exact options_approved_level/options_trading_level values returned by GET /v2/account for a fresh paper account (the docs note trading level can be set <= approved level via the account configuration endpoint), and nothing in /home/user/oid-trading-desk or /home/user/oid-research documents a paper options order ever being placed (desk policy is zero brokerage orders; Alpaca is used there only as the Algo Trader Plus data feed). The day-8 OMS milestone should still include a 5-minute smoke test: GET /v2/account on the paper key and confirm options_approved_level==3 and options_trading_level==3 before assuming no setup is needed.

Correction: No correction needed to the claim as stated. Nuance: Level 3 is automatic in the PAPER environment only; a live account requires an options application (Level 3 requires financial info and a suitability attestation), so any later paper-to-live transition does need lead time. Also verify on the actual paper key that options_trading_level has not been lowered via the account-configuration endpoint, and note the desk's Alpaca usage to date is data-only (no evidence in local repos of any paper options order having been submitted).

Sources:
- https://alpaca.markets/learn/how-to-trade-options-with-alpaca
- https://docs.alpaca.markets/docs/options-trading
- https://docs.alpaca.markets/docs/options-trading-overview
- https://docs.alpaca.markets/docs/options-level-3-trading
- https://docs.alpaca.markets/changelog/multi-leg-level-3-options-trading-in-paper
- https://alpaca.markets/blog/level-3-options-trading-now-available-with-alpacas-trading-api/
- https://x.com/AlpacaHQ/status/1881703433209627125
- https://alpaca.markets/options
- /home/user/oid-trading-desk/README.md
- /home/user/oid-research/docs/DATA_SOURCES_EDGE_REVIEW.md

## 4. CONFIRMED: Alpaca's options websocket stream allows roughly 1,000 concurrent contract subscriptions on the Algo Trader Plus plan.

*Why it matters:* The R2 design (260 fixed + up to ~300 dynamic contracts) and the option-leg label pipeline assume this headroom; a lower cap forces a smaller fixed set and fewer labeled names.

**Checker 1** (refuted=False, confidence 0.7).

Evidence: Alpaca's "About Market Data API" docs page (both the current /us/docs version and the older /us/v1.1 version, as surfaced by three independent web searches) lists an Options plan-comparison table in which websocket subscriptions are "200 quotes" on Basic and "1000 quotes" on Algo Trader Plus, with OPRA as the real-time feed on Algo Trader Plus (Basic gets only the indicative feed). The same docs also state most plans, Algo Trader Plus included, allow one connection per endpoint (406 "connection limit exceeded") and that a subscribe request exceeding the package limit returns a 405 "symbol limit exceeded" error, leaving existing subscriptions unchanged. The desk's own docs are consistent: /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md line 31 and docs/mini/MINI_SUFFICIENCY.md line 9 cite the collector README's 1,000-OCC-subscription cap, and docs/mini/FEEDS_CURRENT.md line 29 and docs/mini/RESEARCH_FEED_ADDITIONS.md lines 38 and 51 describe the collector as capped at 1,000 subs. Caveats: (1) I could not fetch docs.alpaca.markets directly (the session proxy refuses that host, as well as web.archive.org), so the "1000 quotes" wording comes from search-engine extractions of the page rather than my own read; (2) one search summarized the alpaca.markets/data marketing page as showing options websocket symbols as "unlimited" on Algo Trader Plus, which conflicts with the docs table; the docs table is the more specific source and matches the desk collector's observed cap. (3) The documented limit is phrased as 1,000 quote subscriptions, not contracts per se; trade subscriptions may be counted separately. Design headroom for 260 fixed + ~300 dynamic contracts (~560) fits under 1,000 quote subscriptions with a single connection.

Correction: No correction needed; the claim as stated is supported. Precision note: Alpaca's docs express the Algo Trader Plus options limit as "1000 quotes" websocket subscriptions (Basic: 200), on a single allowed connection per endpoint; verify against the live docs page before relying on it, since direct fetch was blocked here and the marketing page uses a looser "unlimited" wording.

Sources:
- https://docs.alpaca.markets/us/docs/about-market-data-api
- https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api
- https://docs.alpaca.markets/docs/streaming-market-data
- https://alpaca.markets/data
- /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md
- /home/user/oid-research/docs/mini/MINI_SUFFICIENCY.md
- /home/user/oid-research/docs/mini/FEEDS_CURRENT.md
- /home/user/oid-research/docs/mini/RESEARCH_FEED_ADDITIONS.md

**Checker 2** (refuted=False, confidence 0.85).

Evidence: Alpaca's official docs support the claim. The "Real-time Option Data" page (docs.alpaca.markets/docs/real-time-option-data) has a feed table listing: OPRA | wss://stream.data.alpaca.markets/v1beta1/opra | quote subscription limit 1000 | requires Algo Trader Plus; the Indicative Pricing feed (free/Basic) is capped at 200. The "About Market Data API" page (docs.alpaca.markets/docs/about-market-data-api) likewise lists Options websocket subscriptions as 1000 quotes for Algo Trader Plus vs 200 on Basic, with OPRA as the Algo Trader Plus feed. The desk's own docs are consistent: /home/user/oid-research/docs/mini/RESEARCH_FEED_ADDITIONS.md (R2: "cap 1,000 contracts per collector README"; R15: "OPRA subscription count against the 1,000 cap"), /home/user/oid-research/docs/mini/FEEDS_CURRENT.md ("Alpaca OPRA (collector, ≤1,000 subs)"), /home/user/oid-research/docs/mini/MINI_SUFFICIENCY.md, and /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md ("Collector supports up to 1,000 OCC subscriptions (collector/README.md)"). Caveats, not refutations: (a) the docs phrase it as a quote-subscription limit of exactly 1000, not "roughly"; (b) Alpaca also limits connections to 1 per endpoint on Algo Trader Plus (a second connection returns 406 "connection limit exceeded"), so the 1,000 must be shared by every consumer on the desk through a single collector; (c) OPRA access additionally requires signing the OPRA agreement; (d) the docs note the host part of the URL may change. I could not fetch docs.alpaca.markets directly (proxy 403 / DNS blocked), so the figures come from search-engine excerpts of the official docs pages plus the desk's own docs that cite the collector README; the collector README itself is not present in the local checkout.

Correction: No correction needed. Precise statement: Alpaca documents a hard limit of 1,000 option quote subscriptions on the OPRA websocket feed for Algo Trader Plus (200 on the indicative feed), with only 1 websocket connection per endpoint, so the R2 design's 260 fixed + ~300 dynamic contracts (~560) fits within the cap only if all desk consumers share the single collector connection.

Sources:
- https://docs.alpaca.markets/docs/real-time-option-data
- https://docs.alpaca.markets/us/docs/real-time-option-data
- https://docs.alpaca.markets/docs/about-market-data-api
- https://docs.alpaca.markets/docs/streaming-market-data
- /home/user/oid-research/docs/mini/RESEARCH_FEED_ADDITIONS.md
- /home/user/oid-research/docs/mini/FEEDS_CURRENT.md
- /home/user/oid-research/docs/mini/MINI_SUFFICIENCY.md
- /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md

## 5. REFUTED: The Robinhood Agentic Trading MCP (launched 2026-05-27) executes stocks only, with options not yet enabled as of October 2026, and Robinhood's customer agreement prohibits automated trading on equities/options.

*Why it matters:* The plan removes Robinhood from the bot order path entirely; if options are now supported and permitted, Jeffrey may reasonably want his existing venue evaluated.

**Checker 1** (refuted=True, confidence 0.85).

Evidence: Only the launch date survives. (1) Launch: Robinhood's newsroom post "Robinhood is Now Open to Agents" (2026-05-27) says Agentic Trading launched in beta "with support for equities only" -- true at launch, not in October. (2) Options: Robinhood's official X account posted on 2026-06-12 "Options are now rolling out for agentic trading. Discover chains, pull quotes with full Greeks, check positions, and place or cancel orders. All through the Robinhood Trading MCP server," and on 2026-07-06 "Agentic options trading is now available to all US customers." Robinhood's support article "Trading with your agent" states a connected agent can place long equity, options, and crypto orders in the dedicated agentic account, with the limitation that agents cannot place multi-leg options orders (single-leg only). Crypto followed on 2026-08-17; at the Sept 2026 HOOD Summit Robinhood said >150,000 agentic accounts had been opened. A third-party setup guide dated 2026-10-07 (vorplabs) still lists the server at agent.robinhood.com/mcp/trading with options in scope. (3) Customer agreement: no primary text was found that prohibits automated trading on equities/options. The opposite is documented: Robinhood's newsroom says opening an Agentic Account authorizes third-party agents to view account data and place trades; the support pages say trade approvals are OFF by default for external MCP agents (agents trade without per-order confirmation), that the customer assumes all risk for agent-executed trades, and that Robinhood "does not control, supervise, monitor, recommend, or audit agents." The only "automated trading" language found in the Customer Agreement (2018 RHF version indexed) concerns Robinhood's own Automated Systems for order entry, not a customer prohibition. Locally, the "policy-prohibited" order tools are the desk's own rule, not Robinhood's: /home/user/oid-trading-desk/docs/API-INVENTORY.md line 48 "No order tools. Zero RH orders. Alerts / research / paper only," and /home/user/oid-trading-desk/hal/README.md line 3 "Never place ... Robinhood orders unless Jeffrey separately names a live Agentic ticket" -- i.e., the desk itself anticipates a sanctioned Agentic order path. Caveat: robinhood.com and x.com could not be fetched directly from this sandbox (proxy 403/DNS), so the primary-page wording comes via search-engine snippets of those pages; secondary coverage (StockBrokers.com, NexusTrade 2026-07-08 review, Genfinity 2026-07-21) independently confirms single-leg options via the MCP.

Correction: As of October 2026 the Robinhood Trading MCP supports single-leg options orders (chains, quotes with Greeks, positions, place/cancel) in addition to long equities and crypto; options rolled out 2026-06-12 and reached all US customers 2026-07-06; multi-leg/spread orders are not supported. Robinhood does not contractually prohibit automated trading on equities/options -- it explicitly authorizes third-party agents to place trades in a dedicated Agentic Account (approvals off by default for MCP agents, customer bears all risk). What remains outside Robinhood's terms is unofficial/reverse-engineered API access to the primary account. The desk's "zero orders" rule is an internal OID policy, not a Robinhood restriction, so Robinhood's agentic account is a legitimate venue to evaluate for the bot order path (with the single-leg-only and dedicated-account-funding constraints noted).

Sources:
- https://robinhood.com/newsroom/robinhood-is-now-open-to-agents/
- https://x.com/RobinhoodApp/status/2065441614659482094
- https://x.com/RobinhoodApp/status/2074206140557037865
- https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- https://robinhood.com/us/en/support/articles/setting-up-an-agent/
- https://robinhood.com/us/en/agentic-trading/
- https://vorplabs.com/agent-tools/robinhood-cli
- https://nexustrade.io/blog/robinhood-agentic-trading-mcp-review-20260708
- https://genfinity.io/2026/07/21/robinhood-agentic-trading-crypto-ai-agents/
- https://www.coindesk.com/markets/2026/09/30/robinhood-is-giving-customers-an-ai-agent-that-trades-for-them-plus-10x-crypto-bets
- https://www.stockbrokers.com/guides/ai-agent-brokers
- https://brokerage-static.s3.amazonaws.com/assets/robinhood/legal/RHF%20Customer%20Agreement.pdf
- /home/user/oid-trading-desk/docs/API-INVENTORY.md
- /home/user/oid-trading-desk/hal/README.md

**Checker 2** (refuted=True, confidence 0.88).

Evidence: (1) Launch date and stocks-only-at-launch are correct: Robinhood newsroom "Robinhood is Now Open to Agents" (May 27, 2026) says Agentic Trading "is launching in beta with support for equities only out of the gate" and that "support for options, crypto, event contracts, futures, and more are coming soon as we move out of beta." (2) But options were enabled within weeks, not still pending in October: Robinhood's July 1, 2026 newsroom release refers to having launched "Agentic Trading for equities and options in the US last month"; Robinhood's X account posted on Jun 12, 2026 that options were "now rolling out" for agentic trading, followed by a post that "Agentic options trading is now available to all US customers"; crypto was added July 20, 2026. Robinhood's current help-center article "Trading with your agent" (updated within the last ~2-3 weeks of 2026-10-21) states you "can currently use a built-in or external agent to place long equities, options, and crypto orders," with the caveat that "agents cannot place multi-leg options orders" (those must be placed manually). (3) The Customer Agreement does not prohibit automated/agent trading: the Robinhood Customer Agreement (Revised October 1, 2026) Section 29.8 expressly governs orders placed by AI agents ("any instruction submitted to Robinhood from an authenticated session of your AI agent shall be final and binding upon you upon receipt by Robinhood"; you are "solely responsible for your investment decisions and for any orders placed in your Account pursuant to such instructions"), and Section 4.13 carves AI agents out of the Third Party Authorized Representative restriction ("an AI agent is not a Third Party Authorized Representative for purposes of this Section"). The agreement also addresses margin debits created by agent orders and requires the customer to ensure the agent complies with anti-manipulation rules, i.e. it regulates rather than bans automation. Robinhood's separate Friday/Agents agreement explicitly describes automations that run on a schedule "as frequently as every minute" and place trades. The only source asserting a ban is a TradersPost vendor blog that does not quote the agreement. (4) Locally, the "policy-prohibited order tools / zero orders" statement is desk-internal policy, not a Robinhood term: /home/user/oid-research/docs/CAPABILITY_REPORT.md line 58 says "Robinhood connector instructions grant live-order authority to Rose only, with per-order explicit approval," and /home/user/oid-trading-desk/automations/oid-support-levels-watch-prompt.md line 32 restricts bots to read-only RH quote tools by desk rule. Caveat: robinhood.com and cdn.robinhood.com were unreachable from this sandbox (proxy 403 / DNS), so the primary-page quotations above come from search-engine extracts of those pages rather than a direct fetch.

Correction: Robinhood's Agentic Trading beta did launch May 27, 2026 with equities only, but Robinhood enabled agentic options trading in June 2026 (rolling out from ~Jun 12, announced as available to all US customers by early July; Robinhood's July 1 release describes "Agentic Trading for equities and options") and added crypto on July 20, 2026. As of October 2026 Robinhood's help center says external (MCP) agents can place long equities, options, and crypto orders; multi-leg options orders are not supported via agent. Robinhood's Customer Agreement (revised Oct 1, 2026) does not prohibit automated/agent trading; it explicitly authorizes and binds orders submitted by an authenticated AI agent in a dedicated Agentic/MCP account (Sections 4.13 and 29.8), with the customer responsible for the agent's compliance. Constraints that remain: orders only from the separate funded agentic/MCP account (other accounts read-only), single-leg options only, trade approvals OFF by default for MCP accounts, futures/event contracts still not supported. The "zero orders / order tools prohibited" status on the desk is OID's own operating policy (Rose-only, per-order approval), not a Robinhood contractual bar, so Robinhood can legitimately be evaluated as a bot order venue for long single-leg calls/puts.

Sources:
- https://robinhood.com/newsroom/robinhood-is-now-open-to-agents/
- https://robinhood.com/newsroom/robinhood-accelerates-global-expansion-robinhood-chain-mainnet-stock-tokens-agentic-trading/
- https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- https://robinhood.com/us/en/support/articles/agentic-trading-overview/
- https://x.com/RobinhoodApp/status/2074206140557037865
- https://cdn.robinhood.com/assets/robinhood/legal/Robinhood-Customer-Agreement.pdf
- https://cdn.robinhood.com/assets/robinhood/legal/friday_agent_agreement.md
- https://genfinity.io/2026/07/21/robinhood-agentic-trading-crypto-ai-agents/
- https://www.finder.com/stock-trading/robinhood-agentic-accounts
- https://blog.traderspost.io/article/does-robinhood-allow-trading-bots
- /home/user/oid-research/docs/CAPABILITY_REPORT.md
- /home/user/oid-trading-desk/automations/oid-support-levels-watch-prompt.md
- /home/user/oid-trading-desk/docs/API-INVENTORY.md

## 6. REFUTED: FINRA's amended Rule 4210 eliminated the pattern-day-trader designation effective 2026-06-04 with a firm-level transition period until 2027-10-20, and Alpaca's current regime (legacy PDT vs intraday margin) is undetermined.

*Why it matters:* A seconds-to-hours options book is 100% day trades; under legacy PDT an account under $25k equity is locked out after four day trades in five sessions, which caps Stage 2 throughput and sizing.

**Checker 1** (refuted=True, confidence 0.85).

Evidence: PART 1 (regulatory) is SUPPORTED. FINRA Regulatory Notice 26-10 (published 2026-04-20, after SEC approval of SR-FINRA-2025-017 on 2026-04-14): "The effective date of the amendments is June 4, 2026, 45 days from publication of this Notice"; "Members that need more time to implement the rule change will be permitted to phase in their implementation over a period of 18 months, until October 20, 2027"; the amendments "eliminate paragraph (f)(8)(B)" (the PDT definition / four-day-trades-in-five-days test) and the $25,000 minimum equity, replacing them with new Rule 4210(d)(2) "intraday margin deficit" standards. The phase-in is at the member-firm level (firms may apply legacy or new rules per account or firm-wide during the transition). Companion Notice 26-11 deletes the old day-trading interpretations. I could not fetch finra.org/sec.gov directly (proxy returned 403 on CONNECT; WebFetch DNS failed), so these quotes come via search-engine excerpts of the Notice and consistent law-firm/compliance summaries (WilmerHale, ACA Group, WSGR, KRP).

PART 2 (Alpaca undetermined) is REFUTED. Alpaca is NOT undetermined; it adopted the intraday margin regime on day one: (a) AlpacaHQ on X, status 2049111388581191772: "FINRA's Pattern Day Trader (PDT) rule is officially being retired, and Alpaca is implementing the new Intraday Margin Framework on June 4, 2026." (b) AlpacaHQ on X, status 2062566639325917446: "The day has come! FINRA's Pattern Day Trader (PDT) rule has been retired and we've implemented our new Intraday Margin Framework." (c) Alpaca blog "FINRA Retires the PDT Rule: Introducing Alpaca's New Intraday Margin Framework": "We have officially lifted the Pattern Day Trader rule and replaced it with the new intraday margin framework in production for both Trading API users and Broker API partners"; PDT designations and the $25,000 minimum are gone, previously PDT-restricted accounts were unrestricted; "Intraday Buying Power replaces Day Trade Buying Power"; and specifically for options: "the expiration of a long option is explicitly classified as an IML-reducing transaction." (d) Alpaca docs changelog 2026-06-03 "Pattern day trading and DTBP fields and endpoints are deprecated": pattern_day_trader, daytrade_count, daytrading_buying_power, bod_dtbp, last_daytrade_count, last_daytrading_buying_power deprecated, removed 2026-07-06. (e) Alpaca docs pages "The Intraday Margin Rule" and "Understanding FINRA's New Intraday Margin Rule and the End of PDT" state the Intraday Margin Rule replaces the legacy PDT system; FAQ: "Is the $25,000 minimum equity requirement still in effect? No." Local repos (/home/user/oid-trading-desk, /home/user/oid-research) contain no Rule 4210/PDT material; the "undetermined" statement exists only in the research-page context (Section 10), which predates or ignores Alpaca's June 4 switch.

Correction: The FINRA facts are correct (PDT designation and $25k minimum eliminated effective 2026-06-04; member-firm phase-in permitted until 2027-10-20). But Alpaca's regime is determined, not undetermined: Alpaca implemented FINRA's intraday margin framework in production on 2026-06-04 for Trading API and Broker API accounts, removed PDT designations and the $25,000 minimum, deprecated the pattern_day_trader/daytrade_count/daytrading_buying_power API fields (removed 2026-07-06; use buying_power / intraday buying power), and explicitly covers options (long-option expiration is an IML-reducing transaction). Consequently, as of 2026-10-21 an Alpaca account under $25k equity is NOT locked out after four day trades in five sessions; the binding constraint for a seconds-to-hours options book at Alpaca is intraday buying power and intraday margin calls, not a day-trade count. (Separate caveat for the desk: the Alpaca subscription described is a data plan, and order routing is currently via Robinhood, so the relevant PDT regime for live sizing is whichever broker actually executes; secondary reports say Robinhood also adopted the new rules at or shortly after June 4, but that was not verified against a Robinhood primary source here.)

Sources:
- https://www.finra.org/rules-guidance/notices/26-10
- https://www.finra.org/sites/default/files/2026-04/Regulatory-Notice-26-10.pdf
- https://www.finra.org/rules-guidance/notices/26-11
- https://www.federalregister.gov/documents/2026/01/14/2026-00519/self-regulatory-organizations-financial-industry-regulatory-authority-inc-notice-of-filing-of-a
- https://www.sec.gov/files/rules/sro/finra/2026/34-104572.pdf
- https://www.wilmerhale.com/en/insights/client-alerts/20260423-sec-approves-amendments-to-finra-rule-4210-replacing-day-trading-margin-requirements-with-a-modernized-intraday-margin-standard
- https://www.acaglobal.com/industry-insights/finra-ends-the-pattern-day-trader-rule/
- https://alpaca.markets/blog/finra-retires-the-pdt-rule-introducing-alpacas-new-intraday-margin-framework/
- https://docs.alpaca.markets/us/changelog/2026-06-03-pdt-651df23
- https://docs.alpaca.markets/us/docs/the-intraday-margin-rule
- https://docs.alpaca.markets/us/docs/understanding-finras-new-intraday-margin-rule-and-the-end-of-pdt
- https://forum.alpaca.markets/t/pdt-change-approved-when-will-changes-take-effect/18701
- https://x.com/AlpacaHQ/status/2049111388581191772
- https://x.com/AlpacaHQ/status/2062566639325917446
- /home/user/oid-trading-desk (grep for 4210/PDT/intraday margin: no matches)
- /home/user/oid-research (grep for 4210/PDT/intraday margin: no matches)

**Checker 2** (refuted=True, confidence 0.9).

Evidence: Regulatory half is CONFIRMED by primary sources: SEC Release 34-105226 (File No. SR-FINRA-2025-017, 2026-04-14) granted accelerated approval of FINRA's amendments to Rule 4210 replacing the PDT designation, day-trading buying power and the $25,000 minimum with intraday margin standards; FINRA Regulatory Notice 26-10 (published 2026-04-20) sets the effective date at June 4, 2026 and allows firms that need more time an 18-month phase-in ending October 20, 2027. The Alpaca half is REFUTED: Alpaca is not undetermined. Alpaca's own blog ("FINRA Retires the PDT Rule: Introducing Alpaca's New Intraday Margin Framework") and docs page "Understanding FINRA's New Intraday Margin Rule and the End of PDT" state Alpaca implemented the intraday margin framework on June 4, 2026 (not using the phase-in); AlpacaHQ on X announced ahead of time it would implement on June 4, 2026 and then posted "The day has come! FINRA's PDT rule has been retired and we've implemented our new Intraday Margin Framework"; Alpaca's changelog entry 2026-06-03 deprecated pattern_day_trader, daytrade_count, daytrading_buying_power, last_daytrade_count, bod_dtbp and the PDT status/removal endpoints, with removal from API responses on 2026-07-06 (alpaca-py models also mark daytrade_count/dtbp_check/pdt_check as removed 2026-07-06). Alpaca docs now describe Intraday Buying Power replacing DTBP, Intraday Margin Deficit calls replacing day-trade margin calls (cure within 2 business days; 90-day freeze if unmet by the 5th business day; de minimis threshold of the lower of $1,000 or 5% of equity), accounts previously PDT-restricted were unrestricted, and 4x intraday buying power available at >= $2,000 equity. Local repos (/home/user/oid-trading-desk, /home/user/oid-research) contain no PDT/4210 content (grep for 4210, pattern day, PDT, intraday margin, 25,000 returned only timezone strings), so the "undetermined" status is not grounded in any desk document either. Note: direct fetch of finra.org/alpaca.markets/sec.gov was blocked by the sandbox proxy (403 CONNECT), so evidence comes from search-engine excerpts of those primary pages rather than full-page reads.

Correction: The regulatory facts are right (SEC approval 2026-04-14, effective 2026-06-04, optional 18-month firm phase-in to 2027-10-20), but Alpaca's regime is determined: Alpaca adopted the new intraday margin framework on the June 4, 2026 effective date, retired PDT designation/day-trade counting/$25k minimum, lifted existing PDT restrictions, and removed the PDT/DTBP API fields on 2026-07-06 (use buying_power / intraday margin instead). For the desk this means a sub-$25k Alpaca account is no longer locked out after four day trades in five sessions; the binding constraint on a long-options book is now cash/options buying power (premium must be fully covered) plus the intraday-margin-deficit regime (orders creating a deficit are rejected pre-trade; repeated unmet deficits trigger a 90-day freeze). Whether the 4x intraday multiplier applies to options buying power is not stated in the sources found and should be verified with Alpaca; a GET /v2/account on the desk's own account would confirm the live field set.

Sources:
- https://www.sec.gov/files/rules/sro/finra/2026/34-105226.pdf
- https://www.sec.gov/rule-release/34-105226
- https://www.finra.org/rules-guidance/notices/26-10
- https://www.finra.org/sites/default/files/2026-04/Regulatory-Notice-26-10.pdf
- https://www.finra.org/investors/insights/intraday-margin-requirements
- https://alpaca.markets/blog/finra-retires-the-pdt-rule-introducing-alpacas-new-intraday-margin-framework/
- https://docs.alpaca.markets/us/docs/understanding-finras-new-intraday-margin-rule-and-the-end-of-pdt
- https://docs.alpaca.markets/us/changelog/2026-06-03-pdt-651df23
- https://docs.alpaca.markets/us/docs/the-intraday-margin-rule
- https://docs.alpaca.markets/us/docs/account-plans
- https://alpaca.markets/sdks/python/api_reference/trading/models.html
- https://x.com/AlpacaHQ/status/2049111388581191772
- https://x.com/AlpacaHQ/status/2062566639325917446
- https://forum.alpaca.markets/t/pdt-change-approved-when-will-changes-take-effect/18701
- /home/user/oid-trading-desk (grep: no PDT/4210 content)
- /home/user/oid-research (grep: no PDT/4210 content)

## 7. CONFIRMED: Tradier's sandbox provides 15-minute delayed data with no streaming, so a Tradier gateway cannot be paper-tested at seconds scale, while its live Pro plan offers native OTOCO option-leg orders for $10/month flat.

*Why it matters:* This is the decisive reason the plan does not run a two-gateway paper trial and keeps Tradier as a fallback only; if the sandbox streams real-time data the venue decision should be revisited.

**Checker 1** (refuted=False, confidence 0.8).

Evidence: Core assertions are supported by Tradier's own documentation (quoted via search snippets; direct fetches of tradier.com/docs.tradier.com were blocked by the session proxy with DNS/403 errors, so I could not read the raw pages). (1) Sandbox delay: Tradier FAQ (docs.tradier.com/docs/faq): "We delay our market data the industry standard 15-minutes for all sandbox data. In the production environment index data is also subject to the 15-minute delay." The Market Data page lists sandbox equities/options as delayed, sandbox indices as not available, and Greeks unavailable in sandbox. (2) No sandbox market-data streaming: FAQ: "Presently, we do not offer a delayed streaming endpoint for paper trading." The WebSocket market-data reference lists only the production host (wss://ws.tradier.com/v1/markets/events) with no sandbox host; QuantConnect's Tradier docs say streaming is unavailable in the demo environment "due to exchange restrictions related to delayed data"; TradersPost docs say paper accounts are 15-minute delayed "and there is no way to change this." Nuance: an ACCOUNT-event WebSocket does have a sandbox host (wss://sandbox-ws.tradier.com), so order-status streaming can be paper-tested, just not market data. (3) OTOCO with option legs: Tradier advanced-orders reference (docs.tradier.com/reference/advanced-orders, place-otoco-order): POST /v1/accounts/{id}/orders with class=otoco; "for option orders, [the second and third orders] must share an option_symbol"; option sides buy_to_open/sell_to_close etc.; only the first leg may be market; valid classes are equity, option, multileg, combo, oto, oco, otoco. Tradier's MCP tool list also exposes a dedicated OTOCO tool. (4) Pro price: tradier.com/individuals/pricing and trade.tradier.com/tradierpro list Pro at $10/month with $0 commissions on stock and equity/ETF options. No local file under /home/user/oid-trading-desk or /home/user/oid-research mentions Tradier or OTOCO (grep hits were only "trader"/"protocol" substrings), so there is no desk-side evidence to contradict the claim.

Correction: Claim stands with two precision caveats. (a) "$10/month flat" is overstated: Pro's $0 commission covers stock and equity/ETF options only; single-listed index options (SPX/VIX-style) carry a $0.35/contract commission on Pro ($0.10 on Pro Plus at $35/mo), exchange/OCC/regulatory/clearing pass-through fees still apply per contract, and assignment/exercise is $9 on Lite/Pro. (b) OTOCO is an API feature available on any plan with API access (the pricing table lists API access under the Lite tier), not something the Pro plan specifically "offers"; Pro only removes the per-contract commission. Also, the venue decision logic in WHY IT MATTERS holds: the sandbox has no market-data stream (only an account-event sandbox WebSocket), so seconds-scale paper testing of signal timing is not possible on Tradier sandbox; order-workflow/bracket mechanics can still be paper-tested there.

Sources:
- https://docs.tradier.com/docs/faq
- https://docs.tradier.com/docs/market-data
- https://docs.tradier.com/docs/endpoints
- https://docs.tradier.com/reference/websocket-market-data-streaming
- https://docs.tradier.com/reference/websocket-account-data-streaming
- https://docs.tradier.com/reference/advanced-orders
- https://docs.tradier.com/reference/brokerage-api-trading-place-otoco-order
- https://docs.tradier.com/docs/trading
- https://docs.tradier.com/docs/tradier-mcp
- https://tradier.com/individuals/pricing
- https://trade.tradier.com/tradierpro/
- https://trade.tradier.com/options
- https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/tradier
- https://docs.traderspost.io/docs/all-supported-connections/tradier
- https://tradersunion.com/brokers/fond/view/tradier/
- /home/user/oid-trading-desk (grep: no Tradier/OTOCO mentions)
- /home/user/oid-research (grep: no Tradier/OTOCO mentions)

**Checker 2** (refuted=False, confidence 0.8).

Evidence: Supported on every material point. (1) Sandbox data: Tradier's own FAQ (docs.tradier.com/docs/faq; documentation.tradier.com/brokerage-api/overview/faq) states market data is delayed "the industry standard 15 minutes" for sandbox data and that Tradier "does not presently offer a delayed streaming endpoint for paper trading"; the Market Data page lists sandbox Equities/Options as Delayed, Indices and Greeks Not Available. QuantConnect's Tradier integration page independently says streaming Tradier market data is unavailable in the paper environment due to exchange restrictions on delayed data, and TradersPost's docs say sandbox paper accounts are 15-minute delayed with no way to change it (quotes and fills based on delayed data). The only sandbox websocket is the beta account-events stream (wss://sandbox-ws.tradier.com), which is order/account events, not market data, so the conclusion that seconds-scale paper testing of quotes is impossible on the sandbox holds. (2) OTOCO: Tradier's trading docs have a native POST /v1/accounts/{account_id}/orders with class=otoco (docs.tradier.com/reference/brokerage-api-trading-place-otoco-order; documentation.tradier.com/brokerage-api/trading/advanced-orders) and the validations explicitly cover all-option-leg orders (when all legs are options the 2nd and 3rd legs must share the same option_symbol; only the first leg may be market; 2nd/3rd legs need different order types). (3) Pricing: Tradier's pricing pages (tradier.com/individuals/pricing; trade.tradier.com/options-traders) describe Tradier Pro as $10/month with unlimited commission-free stock, ETF and equity/ETF options trades; Lite is free with $0.35/contract, Pro Plus is $35/mo. Local repos (/home/user/oid-trading-desk, /home/user/oid-research) contain no Tradier references, so the claim rests solely on vendor documentation. Caveat on verification: the agent proxy blocks tradier.com, documentation.tradier.com, docs.tradier.com, quantconnect.com and traderspost.io (CONNECT 403 / ENOTFOUND), so the primary pages were confirmed via search-engine excerpts of those official pages rather than direct fetches. Nuances that do not refute the claim but should be noted: "$10/month flat" is the subscription only; exchange, clearing/OCC and regulatory pass-through fees still apply, and single-listed index options (SPX/VIX-style) carry $0.35/contract on Pro ($0.10 on Pro Plus). Also the OTOCO endpoint is not Pro-exclusive: the API is available on the free Lite tier at $0.35/contract, so Pro is a cost choice, not a prerequisite for native OTOCO.

Correction: No correction needed; the claim is accurate as stated. Minor precision: $10/month is the Pro subscription fee, with exchange/clearing/regulatory pass-through fees and $0.35/contract on single-listed index options still charged; the sandbox does expose a beta account-events websocket (sandbox-ws.tradier.com) but no market-data stream; and native OTOCO is available on all API tiers including free Lite, not only Pro.

Sources:
- https://docs.tradier.com/docs/faq
- https://documentation.tradier.com/brokerage-api/overview/faq
- https://docs.tradier.com/docs/market-data
- https://documentation.tradier.com/brokerage-api/overview/market-data
- https://docs.tradier.com/reference/websocket-account-data-streaming
- https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/tradier
- https://docs.traderspost.io/docs/all-supported-connections/tradier
- https://docs.tradier.com/reference/brokerage-api-trading-place-otoco-order
- https://documentation.tradier.com/brokerage-api/trading/advanced-orders
- https://tradier.com/individuals/pricing
- https://trade.tradier.com/options-traders/
- https://trade.tradier.com/tradierpro/
- https://in.tradingview.com/broker/Tradier_Brokerage
- /home/user/oid-trading-desk (no Tradier references found)
- /home/user/oid-research (no Tradier references found)

## 8. SPLIT: Removing the 15 s/1 m C/P flow input raised the core ±2 right-after-5-min rate from 50.3% to 55.8% (n 1,552 → 1,034) on the 10/20 replay, and 1-min rvol ≥ 3× raised 15-min breakout odds away from walls from 8.7% to 26.7% over 82,190 ticker-minutes.

*Why it matters:* These two numbers are the evidentiary basis for the surge-only B2 baseline, setup A, and running the drop-C/P variant as a shadow challenger; they come from page-local scripts not in either repo.

**Checker 1** (refuted=True, confidence 0.7).

Evidence: None of the claimed figures (50.3%, 55.8%, 1,552, 1,034, 8.7%, 26.7%, 82,190) appear anywhere in either accessible repository: a grep across /home/user/oid-trading-desk and /home/user/oid-research returns only unrelated hits (a FlashAlpha flip level 1034.80, a -26.7% MAE cell in the Rose ledger, and a sklearn wheel hash). No file mentions "right-after", "ticker-minute", "drop C/P", "shadow challenger", "surge-only", or a 10/20 replay. The GitHub heads match the local clones exactly (jeffbazar/oid-trading-desk @ 3f9399a8, 2026-10-05; jeffbazar/oid-research @ b29a1bc0, 2026-10-11), so no newer commit contains the replay scripts or results. The only breakout-related study in the repos, /home/user/oid-research/studies/S1-rose-breakout-quality.md, is "DRAFT, v0.3.0 ... Verdict: none", and /home/user/oid-research/README.md states "No study is registered or authorized. No experiment has been run, and no results exist." The claim's only possible source is the live page's Research tab on oid-mini.tail3d8d4d.ts.net (Tailscale, unreachable from here) and page-local scripts that are not in either repo; the context excerpt supplied to this checker was truncated before the Research rows, so the figures could not be confirmed even against the page transcript. No primary source supporting the two numbers as stated was found after a real attempt.

Correction: What is verifiable: the two experiments and their figures are not reproducible from any artifact in the oid-trading-desk or oid-research repositories; they exist only as unverified text on the live page's Research tab (rows 6 and 12 per the task note), backed by scripts that live solely on the data mini. The repos' own research program says no experiment has been run and no results exist (DRAFT_ONLY), and the S1 breakout study has no verdict. Until the page-local replay scripts, the 10/20 input data and the output tables are committed (or at least archived with hashes) and re-run by the sealed-holdout evaluator, these numbers should be treated as unaudited page claims, not as an evidentiary basis for the surge-only B2 baseline, setup A, or the drop-C/P shadow challenger.

Sources:
- /home/user/oid-research/README.md
- /home/user/oid-research/studies/S1-rose-breakout-quality.md
- /home/user/oid-research/program.md
- /home/user/oid-trading-desk/data/raw/index.html
- https://github.com/jeffbazar/oid-trading-desk/commit/3f9399a8f2cb816b75668db0ff28ad3b92e4e78e
- https://github.com/jeffbazar/oid-research/commit/b29a1bc04af82c9c798290a5495353d4176b26fe

**Checker 2** (refuted=False, confidence 0.85).

Evidence: The live-page Research tab screenshot (image 3, dated 10/20/2026) contains both figures verbatim. Row 12, "Drop-one test: core score without C/P flow (10/20)", method "score_replay_changes.py 10/20 (5 s steps) baseline vs --drop flow; every change to a non-zero score checked 1 m and 5 m later on 5 s closes", headline: "Score changes 8,108 -> 5,578. ±2 changes right after 5 m: 50.3% -> 55.8% (1,552 -> 1,034 changes). ±3: 54.3% -> 42.9% (46 -> 14). All non-zero: 47.6% -> 49.2%." Verdict: "done. One day only: logged, no settings change. Repeat over 10+ live days." Row 6, "Wall magnet: is price pulled to the call or put wall?", method "82,190 ticker-minutes over 325 ticker-days (9/25-10/20), FlashAlpha walls harvested from 1,045 stored snapshots (latest earlier the same day, no look-ahead), 1-minute SIP bars, compared with a no-magnet chance rate", headline: "...A 1-minute rvol of 3x or more roughly triples breakout odds everywhere: away from walls, 15-minute breakouts go from 8.7% to 26.7%." Verdict: "Not supported. Mostly not supported. Volume is the real switch." Grep of /home/user/oid-trading-desk and /home/user/oid-research for 55.8, 50.3, 1,552, 1,034, 82,190, 26.7, 8.7% and for score_replay_changes.py found no relevant hits (only unrelated snapshot.json strings such as 'flip 1034.80' and '-26.7% 8:55a'), confirming the underlying scripts and 'full file' outputs are not in either repo; the only primary evidence available here is the page screenshot.

Correction: No correction to the numbers; the claim transcribes the live page accurately. Caveats a reader should carry: (1) the drop-C/P result is a single replay day (10/20) with the page's own verdict 'done ... Repeat over 10+ live days', and the ±3 bucket moved the other way (54.3% -> 42.9%, n 46 -> 14), so it is not yet evidence of a stable improvement; (2) 82,190 ticker-minutes is the whole wall-magnet sample (325 ticker-days, 9/25-10/20); the 8.7% -> 26.7% figure is the away-from-walls subset of it, whose n is not shown; (3) the wall-magnet row's overall verdict is 'Not supported' (for the magnet hypothesis), while the rvol finding is a side result; (4) the linked 'full file' outputs and score_replay_changes.py could not be independently inspected because they are not in jeffbazar/oid-trading-desk or jeffbazar/oid-research and the live site is unreachable.

Sources:
- (session scratch file, not retained) (live-page Research tab screenshot, rows 6 and 12)
- (session scratch file, not retained)
- (session scratch file, not retained)
- /home/user/oid-trading-desk (grep: no score_replay_changes.py, no matching figures)
- /home/user/oid-research/studies (S1-S5, C2-S6: no matching figures)

## 9. CONFIRMED: The paper ledger's top three Rose tickets (AMD 550C +$4,917.50, META 670C +$4,550, LRCX 310C +$1,975) equal 89% of her +$12,844 net, and 43 of 57 closes were batch administrative events on eight timestamps.

*Why it matters:* These facts justify the top-3-share gate, the administrative-close category, and the refusal to use the ledger as a sizing baseline; if the ledger is less concentrated the gates could be loosened.

**Checker 1** (refuted=False, confidence 0.8).

Evidence: Parsed the closed-ticket table in /home/user/oid-trading-desk/data/raw/index.html (lines 1477-2452): 57 rows (Rose 31, Hal 26; closed 49, invalidated 6, expired 2). Rose net across all 31 rows = +$12,844.00. Top three Rose tickets: AMD 2026-09-25 550C +$4,917.50 (out 2026-09-21 9:23 AM PT), META 2026-09-25 670C +$4,550.00 (same timestamp), LRCX 2026-10-16 310C +$1,975.00 (out 2026-10-02 6:26 PM PT) = $11,442.50 = 89.1% of net. Exactly as claimed. Close clustering: 20 distinct Out timestamps; 8 shared timestamps hold 45 rows (10 @ 2026-10-02 6:26 PM, 7 @ 09-22 9:15 PM, 7 @ 09-22 1:09 PM, 7 @ 09-21 9:23 AM, 6 @ 09-24 12:08 PM, 3 @ 09-23 7:18 AM, 3 @ 09-17 8:38 AM, 2 @ 09-18 1:00 PM). The 43 count arises only if the two 09-18 1:00 PM expirations (status expired, tag time_decay) are excluded, which leaves 7 timestamps. /home/user/oid-research/docs/DATA_GAP_REPORT.md line 22 corroborates admin/owner close reasons mixed into the ledger (USER_REQUESTED_FLAT 10, user_ordered_book_tp_harvest 7, jeffrey_clear_seats_fresh_book 6, Hormuz owner-confirmed trim 3) and says these need the §18 'administrative close' category; it also notes the later (10-09) ledger has 64 tickets (Rose 36). The concentration finding stands and the batch-clustering is, if anything, slightly understated, so the gates are not loosened by the correction.

Correction: Concentration figures are exact (89.1%, +$12,844, 57 rows). The batch figure is off by one batch: the snapshot shows 45 of 57 rows closing on eight shared timestamps, or 43 of 57 on seven timestamps if the two 2026-09-18 1:00 PM expirations are excluded; '43 on eight' mixes the two counts. Also, only 26 of those carry explicit owner/administrative close reasons in the ledger (USER_REQUESTED_FLAT 10, user_ordered_book_tp_harvest 7, jeffrey_clear_seats_fresh_book 6, Hormuz trim 3); the 09-22 1:09 PM, 09-22 9:15 PM and 09-17 8:38 AM batches are tagged win_exit/loss_exit, so 'administrative' for the full 43/45 is an inference from same-timestamp batching rather than a ledger label. The 57/12,844 figures are from the 2026-10-05 review snapshot; the research repo's 10-09 ledger has 64 tickets (Rose 36), so a refreshed ledger will move the totals.

Sources:
- /home/user/oid-trading-desk/data/raw/index.html
- /home/user/oid-trading-desk/data/snapshot.json
- /home/user/oid-research/docs/DATA_GAP_REPORT.md
- /home/user/oid-research/program.md

**Checker 2** (refuted=False, confidence 0.75).

Evidence: Parsed the 57-row "Recently closed / invalidated" ledger table in /home/user/oid-trading-desk/data/raw/index.html (byte-identical to the reference snapshot). Rose: 31 rows (23 closed, 6 invalidated, 2 expired), summed P&L exactly +$12,844.00. Top three: AMD 2026-09-25 550C +$4,917.50, META 2026-09-25 670C +$4,550.00, LRCX 2026-10-16 310C +$1,975.00 = $11,442.50 = 89.1% of net (84.0% if only status=closed rows, net $13,627). Close-timestamp clustering across all 57 rows (Rose 31 + Hal 26): 2026-10-02 6:26 PM x10 (tag 'other', after-hours), 2026-09-22 9:15 PM x7 (Hal, after-hours, includes 3 jeffrey_hormuz_trim), 2026-09-22 1:09 PM x7 (Rose 'User-ordered Wed-reset harvest'), 2026-09-21 9:23 AM x7 (Rose 'BOOK_TP harvest / user-ordered paper close'), 2026-09-24 12:08 PM x6 (jeffrey_clear_rotate), 2026-09-23 7:18 AM x3 (Hal, jeffrey_hormuz_trim), 2026-09-17 8:38 AM x3 (Hal win_exit, no administrative label), 2026-09-18 1:00 PM x2 (Rose expired/time_decay). Timestamps with >=3 closes: 7 timestamps, 43 rows; timestamps with >=2 closes: 8 timestamps, 45 rows. The repo's own DATA_GAP_REPORT.md (row J) independently documents that owner/administrative closes are mixed into the ledger (USER_REQUESTED_FLAT 10, user_ordered_book_tp_harvest 7, jeffrey_clear_seats_fresh_book 6, jeffrey_clear_rotate 6, Hormuz owner-confirmed trim 3) on the fuller 64-ticket trades.json, and program.md requires administrative closes be separated from strategy exits.

Correction: Substantively supported, with two precision caveats: (1) the 43-row figure corresponds to SEVEN timestamps (those carrying >=3 closes); eight timestamps (>=2 closes) cover 45 rows, so '43 on eight' is an inconsistent pairing; (2) '57 closes' is the full table including 6 invalidated and 2 expired rows (49 status=closed), and one 3-row cluster (Hal 2026-09-17 8:38 AM, win_exit) carries no administrative/owner-ordered label, so ~40 of 57 are clearly owner-ordered or after-hours batch events. The 89% top-3 concentration and +$12,844 net are exact. None of this loosens the gates: concentration and batching are at least as severe as claimed.

Sources:
- /home/user/oid-trading-desk/data/raw/index.html
- /home/user/oid-trading-desk/data/reference-snapshots/72b155a6448703b5112c889507c663e2682688574b19c9c41ced6951cd4fca2a/index.html
- /home/user/oid-trading-desk/data/snapshot.json
- /home/user/oid-research/docs/DATA_GAP_REPORT.md
- /home/user/oid-research/program.md
- (session scratch file, not retained)
- (session scratch file, not retained)

## 10. CONFIRMED: Databento OPRA pay-as-you-go historical pricing is approximately $2/GB for `cbbo-1m` and $5/GB for `definition`, with full history from 2013-04-01, so a targeted pull around ~325 surge ticker-days costs under $300.

*Why it matters:* The only new spend in the plan is capped at $300 on this basis; if per-GB rates or minimums are higher the backfill may not be affordable and the option-leg label would rely solely on forward R2 capture.

**Checker 1** (refuted=False, confidence 0.6).

Evidence: Not refuted, but only partly verified from primary sources because databento.com, api.databento.com, docs.databento.com, Substack and web.archive.org are all blocked at this session's proxy (DNS/CONNECT 403); only WebSearch snippets were reachable. What holds up: (1) The $2.00/GB cbbo-1m and $5.00/GB definition figures come from the desk's own 2026-10-10 pull of Databento's public catalog endpoint api.databento.com/v0/dataset/service/catalog, recorded in /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md Section 3 (also cmbp-1 $0.16/GB, cbbo-1s $2.00/GB, trades $280/GB, tcbbo $210/GB). I could not re-fetch the catalog to confirm, and no search snippet exposes per-schema rates (the pricing page is JS-rendered; Databento's public 'from $0.04/GB' headline for OPRA is consistent with the catalog's mbp-1 floor). (2) Indirect corroboration: a Sept-2026 Concretum Group comparison (concretumgroup.substack.com/p/spx-options-database-databento-vs) reports Databento quoted $423 for 12 months of cbbo-1m across both SPX chains on usage pricing; SPX is tens of thousands of contracts, so that total implies a low single-digit $/GB rate, consistent with ~$2/GB and inconsistent with a materially higher rate. (3) Coverage: Databento's blog 'OPRA improvements coming soon' (2025-05-14) states that from 2025-05-21 OPRA.PILLAR includes history from April 1, 2013 for trades, OHLCV, statistics, definitions and CBBO-1m, and the OPRA.PILLAR dataset page lists 2013-04-01 as the start. (4) Billing basis/minimums: Databento's usage-pricing FAQ (via search) says historical data is billed per uncompressed GB in DBN with no monthly fee, no license is required for historical OPRA on usage rates (license pass-through applies to live), and new accounts get $125 in free credits (expire in 6 months); no source mentions a minimum purchase. (5) Arithmetic at the claimed rates (80-byte CbboMsg records, 390 minutes/day, 325 ticker-days): C=1,500 contracts/underlying at full fill = 15 GB -> ~$30; even C=5,000 (TSLA/NVDA-sized chains) at every-minute fill = 51 GB -> ~$101, plus definition at ~$1-4. Under $300 holds with roughly 3x headroom even in the worst case, before the $125 credit. Cross-check from the desk doc's own Section 4 table: 41 underlyings x 675 sessions x C=500 at f=0.5 was ~$432, i.e. ~$0.016 per ticker-day, which scales to ~$5 for 325 ticker-days.

Correction: Claim stands with caveats: (a) the per-GB rates are sourced only from the desk's 2026-10-10 catalog snapshot (not re-verified today); the exact price must come from metadata.get_cost with the real symbol/date filter (needs an API key). (b) 'Full history from 2013-04-01' is accurate for cbbo-1m/definition/trades, but per Databento's OPRA.PILLAR docs the pre-2023-03-28 portion is reconstructed from subsampled data (ts_recv = event time, F_BAD_TS_RECV flag), not packet capture; tick-level cmbp-1/tcbbo/cbbo-1s start 2023-03-28. This does not affect recent surge-day pulls. (c) Databento's Standard OPRA plan ($199/mo) includes the last 12 months of top-of-book history, so if the 325 days fall within 12 months, a one-month subscription is an alternative to usage billing; the $125 new-account credit would also cover most or all of a sub-$300 pull.

Sources:
- /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md (Sections 1, 3, 4, 5, 7; catalog pulled 2026-10-10)
- https://api.databento.com/v0/dataset/service/catalog (cited by the local doc; unreachable from this session)
- https://databento.com/blog/opra-improvements-coming-soon
- https://databento.com/datasets/OPRA.PILLAR
- https://databento.com/docs/venues-and-datasets/opra-pillar
- https://databento.com/docs/faqs/usage-pricing-and-data-credits
- https://databento.com/blog/introducing-new-opra-pricing-plans
- https://databento.com/docs/quickstart/set-up ($125 credit)
- https://concretumgroup.substack.com/p/spx-options-database-databento-vs ($423 for 12 months SPX cbbo-1m)
- https://www.quantvps.com/blog/download-historical-options-data
- /home/user/oid-research/docs/FIRST_TESTS_ONE_PAGER.md (get_cost as owner step)

**Checker 2** (refuted=False, confidence 0.6).

Evidence: Not refuted, but the per-GB rates could not be re-verified against Databento today because databento.com, hist.databento.com, api.databento.com, docs.databento.com and archive mirrors are all blocked from this sandbox (proxy 403 / DNS). What I could establish: (1) The desk's own vendor check /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md (fetched 2026-10-10 from Databento's public catalog API api.databento.com/v0/dataset/service/catalog, which feeds databento.com/pricing) lists OPRA.PILLAR pay-as-you-go rates cbbo-1m $2.00/GB, cbbo-1s $2.00/GB, cmbp-1 $0.16/GB, definition $5.00/GB, trades $280/GB, and history_from 2013-04-01; FIRST_TESTS_ONE_PAGER.md repeats $2/GB and $5/GB. (2) Databento's own blog posts (opra-improvements-coming-soon, introducing-new-opra-pricing-plans, June 2025) confirm cbbo-1m, definition, trades, OHLCV and statistics history 'from April 1, 2013, onwards' and that 'usage-based historical data is not being removed' after live usage-based OPRA ended 2025-06-03; the May 2026 'Updates to subscription pricing' post lists CME/US Equities/ICE plans, not OPRA. (3) Databento docs/FAQ: historical data is metered per uncompressed binary GB, symbol filtering reduces billable size, metadata.get_cost is free, new users get $125 free credits (6-month expiry), and no minimum purchase was found in any source. (4) Independent size datapoints make the <$300 arithmetic robust: GitHub issue AlgoGators/data-ngin#123 reports an OPRA.PILLAR cbbo-1m pull for 48 underlyings x 317 trading days restricted to a 2-minute window (15:59-16:01 ET) = 2.9 GB, and definition for the same universe = 1.9 GB. Scaling the 2-minute window to a full 390-minute session gives roughly 37 MB per ticker-day of full-chain cbbo-1m, so ~325 ticker-days is ~12 GB (~$24 at $2/GB) plus ~125 KB/ticker-day of definition (~$0.20 at $5/GB). The dbn source (github.com/databento/dbn, rust/dbn/src/record.rs) confirms CbboMsg is 80 bytes (size_of assertion), matching the desk's own formula. Even if the cbbo-1m rate were 5-10x higher than $2/GB, the pull would stay under $300. A third-party datapoint (Concretum Group substack: 12 months of SPX+SPXW cbbo-1m via get_cost = $423) is consistent with a low single-digit $/GB rate on a very large chain.

Correction: Claim stands, with caveats to carry into the plan: (a) the $2/GB and $5/GB rates come from the desk's 2026-10-10 catalog pull and were not re-read from Databento today; run metadata.get_cost (free, needs an API key) before purchase as VENDOR_OPTIONS_HISTORY.md already says. (b) cbbo-1m history before 2023-03-28 is subsampled (not packet-capture) with F_BAD_TS_RECV set, so 'full history from 2013' is lower quality before that date. (c) Standard plan ($199/mo) already includes the last 12 months of top-of-book history; pay-as-you-go is only needed for older data or if no plan is bought. (d) OPRA license approval/questionnaire and a possible small OPRA fee ('starting at $1.25/mo' per the desk's note, UNVERIFIED) are separate from the per-GB spend. (e) Usage-based live OPRA was discontinued 2025-06-03, so this pricing applies to historical pulls only.

Sources:
- /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md
- /home/user/oid-research/docs/FIRST_TESTS_ONE_PAGER.md
- https://databento.com/blog/opra-improvements-coming-soon
- https://databento.com/blog/introducing-new-opra-pricing-plans
- https://databento.com/blog/updates-to-subscription-pricing
- https://databento.com/docs/faqs/usage-pricing-and-data-credits
- https://databento.com/docs/knowledge-base/new-users/usage-based-pricing-and-data-credits
- https://databento.com/options
- https://github.com/AlgoGators/data-ngin/issues/123
- https://github.com/databento/dbn/blob/main/rust/dbn/src/record.rs
- https://concretumgroup.substack.com/p/spx-options-database-databento-vs
- https://www.quantvps.com/blog/download-historical-options-data

## 11. CONFIRMED: Alpaca provides historical option bars and trades from February 2024 onward but no historical option quotes, so a $0 lower-fidelity option-leg backfill is possible but bid/ask-based labels are not.

*Why it matters:* Determines whether E4 can start before R2 matures and whether the backfilled labels are usable for anything beyond a coarse mark-based proxy.

**Checker 1** (refuted=False, confidence 0.8).

Evidence: Could not reach docs.alpaca.markets or forum.alpaca.markets directly (egress proxy rejects the hosts), so I verified via Alpaca's own SDK source on GitHub, search snippets of the docs/forum, and the desk's own doc fetches dated 2026-10-10. (1) Start date: Alpaca docs page "Historical Option Data" states "Currently we only offer historical option data since February 2024" (search snippet; same text recorded in /home/user/oid-research/docs/CAPABILITY_REPORT.md and COST_COMPUTE_ESTIMATE.md from a 2026-10-10 fetch). (2) Bars/trades exist, historical quotes do not: official alpaca-py OptionHistoricalDataClient exposes get_option_bars (/options/bars), get_option_trades (/options/trades), get_option_latest_quote (/options/quotes/latest), get_option_latest_trade, get_option_snapshot, get_option_chain, get_option_exchange_codes, and no /options/quotes historical method. Official Go SDK marketdata/options.go likewise has GetOptionTrades (/v1beta1/options/trades), GetOptionBars (/v1beta1/options/bars), GetLatestOptionQuote(s) (/v1beta1/options/quotes/latest), snapshots and chain, with no GetOptionQuotes with start/end. (3) Server-side confirmation: Alpaca forum thread "Historical Options Request" (19218) reports an Algo Trader Plus user whose historical option trades and bars calls work but historical option quote requests return HTTP 404 for both expired and recent contracts, with no answer in the thread. (4) Nuance: the community C# SDK (alpaca-trade-api-csharp) declares IAlpacaOptionsDataClient : IHistoricalQuotesClient<HistoricalOptionQuotesRequest> with LastPathSegment "quotes", i.e. it would call v1beta1/options/quotes, but the forum 404 indicates the server does not serve it under the desk's plan; this is consistent with the claim rather than against it. (5) $0: the desk already pays Algo Trader Plus (~$99/mo, OPRA entitled); docs say the OPRA historical feed is available to subscribed users, so incremental cost is $0, though the desk's own docs flag this as unprobed (CAPABILITY_REPORT.md: "Historical REST not probed"). Local docs agree with the claim: /home/user/oid-research/docs/mini/RESEARCH_FEED_ADDITIONS.md R4 ("Only latest quotes are documented, with no historical quote (bid/ask) endpoint found"), /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md line 118 ("No historical quotes documented (bars + trades only) | Feb 2024").

Correction: No correction needed; claim stands as stated. Caveats: (a) the primary docs page could not be fetched live from this sandbox, so the Feb-2024 start date rests on search snippets plus the desk's 2026-10-10 fetch; (b) a C# SDK class for historical option quotes exists, so the desk's planned one-contract probe of /v1beta1/options/quotes (R4) is still worth running before treating the absence as final, though a forum user on the same plan got 404; (c) the alpaca-py get_option_trades docstring oddly says "up to 7 days ago", which should be checked during the R4 probe in case trade history lookback is shorter than bars.

Sources:
- https://docs.alpaca.markets/docs/historical-option-data
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/data/historical/option.py
- https://raw.githubusercontent.com/alpacahq/alpaca-trade-api-go/master/marketdata/options.go
- https://raw.githubusercontent.com/alpacahq/alpaca-trade-api-csharp/master/Alpaca.Markets/Interfaces/IAlpacaOptionsDataClient.cs
- https://raw.githubusercontent.com/alpacahq/alpaca-trade-api-csharp/master/Alpaca.Markets/Parameters/HistoricalOptionQuotesRequest.cs
- https://forum.alpaca.markets/t/historical-options-request/19218
- https://alpaca.markets/sdks/python/api_reference/data/option/historical.html
- /home/user/oid-research/docs/mini/RESEARCH_FEED_ADDITIONS.md
- /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md
- /home/user/oid-research/docs/CAPABILITY_REPORT.md
- /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md
- /home/user/oid-research/docs/DATA_GAP_REPORT.md

**Checker 2** (refuted=False, confidence 0.8).

Evidence: Attempted refutation found supporting evidence, not contradicting evidence. (1) Alpaca's Historical Option Data docs page states "Currently we only offer historical option data since February 2024" (text confirmed via search snippets of docs.alpaca.markets/docs/historical-option-data and the v1.1/v1.4.2 copies; the docs host itself is blocked by this sandbox's proxy, so the page was not fetched directly). (2) Alpaca's official Python SDK source (alpaca-py master, alpaca/data/historical/option.py) exposes exactly these OptionHistoricalDataClient methods and paths: get_option_bars -> /options/bars, get_option_trades -> /options/trades, get_option_latest_quote -> /options/quotes/latest, get_option_latest_trade -> /options/trades/latest, get_option_snapshot -> /options/snapshots, get_option_chain -> /options/snapshots/{underlying}, get_option_exchange_codes -> /options/meta/exchanges. There is no date-range option quotes method, and requests.py defines OptionBarsRequest, OptionTradesRequest and OptionLatestQuoteRequest but no OptionQuotesRequest (StockQuotesRequest and CryptoQuoteRequest exist, so the omission is specific to options). The SDK's docs/api_reference/data/option/historical.rst lists the same seven methods. (3) The Alpaca .NET SDK interface IAlpacaOptionsDataClient implements IHistoricalTradesClient and IHistoricalBarsClient but not IHistoricalQuotesClient; it only has ListLatestQuotesAsync. (4) The official Go SDK marketdata/rest.go has no options endpoints at all. (5) A forum thread (Historical Options Request, 19218) reports an Algo Trader Plus user getting HTTP 404 on historical option quote requests while bars and trades worked; no staff answer found. (6) The desk's own docs reach the same reading: oid-research/docs/mini/RESEARCH_FEED_ADDITIONS.md R4 ("historical option bars and trades (OPRA) since Feb 2024... no historical quote (bid/ask) endpoint found"), docs/VENDOR_OPTIONS_HISTORY.md line 118 ("No historical quotes documented (bars + trades only) | Feb 2024"), and CAPABILITY_REPORT.md / DATA_GAP_REPORT.md mark historical NBBO as UNVERIFIED pending a probe. Caveats: the $0 cost is an inference (the existing Algo Trader Plus plan covers OPRA; the desk notes incremental cost is unverified and historical REST was never probed from the mini); one Alpaca tutorial page summary claims "historical bars, trades, and quotes for stocks, crypto, and options" but no primary endpoint or SDK method for historical option quotes exists, so that wording appears loose; the 'backfill' is trade-derived (bars/VWAP/prints), not even mid-quote marks, and thinly traded contracts will have sparse bars.

Correction: No correction needed; claim stands as stated. Minor precision: the backfill proxy is trade-print/bar based (OHLC, VWAP, volume), not quote-mid based, and the "$0" assumes the existing Algo Trader Plus subscription entitles historical OPRA REST pulls, which the desk has not yet probed (R4 P1 verify step).

Sources:
- https://docs.alpaca.markets/docs/historical-option-data
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/data/historical/option.py
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/data/requests.py
- https://raw.githubusercontent.com/alpacahq/alpaca-py/master/docs/api_reference/data/option/historical.rst
- https://raw.githubusercontent.com/OlegRa/Alpaca.Markets/master/Alpaca.Markets/Interfaces/IAlpacaOptionsDataClient.cs
- https://raw.githubusercontent.com/alpacahq/alpaca-trade-api-go/master/marketdata/rest.go
- https://forum.alpaca.markets/t/historical-options-request/19218
- https://forum.alpaca.markets/t/does-historical-options-data-starts-from-2024-or-my-script-is-wrong/13976
- /home/user/oid-research/docs/mini/RESEARCH_FEED_ADDITIONS.md
- /home/user/oid-research/docs/VENDOR_OPTIONS_HISTORY.md
- /home/user/oid-research/docs/CAPABILITY_REPORT.md
- /home/user/oid-research/docs/DATA_GAP_REPORT.md
- /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md
- /home/user/oid-research/program.md

## 12. REFUTED: FlashAlpha Growth is capped at 2,500 requests/day and the Basic tier at 100/day, and the desk's observed burn was 2,122 by 4:32 PM PT with VIX ~700, oil 450, walls 325 and agents ~650, projecting ~2,850 on a full wall day.

*Why it matters:* Justifies staying on Growth (not Alpha, not Basic), the Quota Steward, and the VIX/oil cadence cut; if the Basic cap is higher a downgrade could save $220/month.

**Checker 1** (refuted=True, confidence 0.6).

Evidence: PART A (Growth 2,500/day) is SUPPORTED. Local: /home/user/oid-trading-desk/docs/API-INVENTORY.md line 10 ("Growth plan, one shared hard daily limit (2,500/day per last get_account, verified 2026-10-01)"); /home/user/oid-research/docs/mini/FEEDS_CURRENT.md line 26 ("FlashAlpha Growth (2,500/day)"); /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md line 28 (Growth $299/mo monthly, Alpha $1,499/mo or $1,199/mo annual, unlimited requests; pricing page fetched 2026-10-10). Vendor web pages (via search snippets; flashalpha.com was not directly fetchable from this sandbox, DNS/proxy blocked) consistently say Growth = 2,500 req/day, $299/mo monthly or $239/mo annual.

PART B (Basic 100/day) is CONTESTED by the vendor's own material. FlashAlpha's current comparison articles and use-case pages (best-options-data-apis-2026, flashalpha-vs-polygon, best-gex-api-2026, earnings-volatility-trading use case) list Basic at 250 requests/day ($79/mo monthly, $63/mo annual). The 100/day figure appears in FlashAlpha's downloads/agents.md (Free 5, Basic 100, Growth 2,500, Alpha uncapped) and on third-party listings (GetApp, SaaSWorthy) and one search-engine rendering of flashalpha.com/pricing. So the vendor publishes both 100 and 250 for Basic; "100/day" cannot be stated as fact without checking the live pricing page or get_account on a Basic key. The $220/mo saving ($299-$79) is arithmetically consistent with the Basic price.

PART C (burn 2,122 by 4:32 PM PT; VIX ~700, oil 450, walls 325, agents ~650; ~2,850 projection) has NO primary source available. These numbers do not appear anywhere in /home/user/oid-trading-desk or /home/user/oid-research (grep for 2,122 / 2,850 / 4:32 / "Quota Steward" returns nothing); api-quotas.json is absent from /home/user/oid-trading-desk/market-data/latest/. They exist only on the unreachable live Research page (Section 6/9). The component arithmetic is internally consistent (700+450+325+650 = 2,125). However, the breakdown conflicts with the repo's own FA policy as of 2026-10-05: API-INVENTORY.md says FA is Rose-only (walls), Macro bot gets "none", and non-Rose callers get a working budget of about 5 calls/day; FEEDS_CURRENT.md budgets focus walls at <=900/day and the mini fa-focus shadow at a 250/day cap. A VIX ~700 + oil 450 FA burn (1,150/day for macro series) is not reflected in any repo document, so it is either a post-10/05 change or a figure that cannot be reconciled with the written desk policy.

Correction: What is verifiable: FlashAlpha Growth = 2,500 requests/day, $299/mo monthly ($239/mo annual), hard shared desk-wide limit (confirmed by the desk's own get_account on 2026-10-01). Basic = $79/mo monthly ($63/mo annual) but its daily cap is published inconsistently by the vendor: 250/day on FlashAlpha's current comparison and use-case pages, 100/day in FlashAlpha's agents.md and third-party listings; treat it as "100-250/day, verify on flashalpha.com/pricing" rather than a flat 100. Alpha = $1,499/mo monthly ($1,199/mo annual), unlimited. The observed-burn figures (2,122 by 4:32 PM PT; VIX ~700 / oil 450 / walls 325 / agents ~650; ~2,850 full-wall-day projection) are unverified: they come only from the live Research page, are not in either repo, and the VIX/oil component contradicts the repo's 10/05 policy that Macro makes no FA calls and non-Rose callers get ~5/day. The strategic conclusion nonetheless survives either Basic figure: whether Basic is 100 or 250/day, it is an order of magnitude below any plausible desk burn (even the repo's conservative <=900/day walls budget), so a Basic downgrade is not viable and the $220/mo saving is illusory; but the claim should cite an api-quotas.json or get_account log for the 2,122 figure before it is used as a number.

Sources:
- /home/user/oid-trading-desk/docs/API-INVENTORY.md
- /home/user/oid-research/docs/mini/FEEDS_CURRENT.md
- /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md
- /home/user/oid-trading-desk/docs/SETUP-VS-PRODUCTION.md
- /home/user/oid-trading-desk/automations/oid-support-levels-watch-prompt.md
- https://flashalpha.com/pricing
- https://flashalpha.com/downloads/agents.md
- https://flashalpha.com/articles/best-options-data-apis-2026
- https://flashalpha.com/articles/flashalpha-vs-polygon-options-data-raw-vs-computed
- https://flashalpha.com/articles/best-gex-api-2026-flashalpha-vs-spotgamma-vs-unusual-whales
- https://flashalpha.com/use-cases/earnings-volatility-trading
- https://flashalpha.com/articles/flashalpha-vs-intrinio-institutional-options-api
- https://www.getapp.com/all-software/a/flashalpha/
- https://www.saasworthy.com/product/flashalpha/pricing

**Checker 2** (refuted=True, confidence 0.6).

Evidence: PART SUPPORTED: Growth = 2,500/day is corroborated by a primary desk source (/home/user/oid-trading-desk/docs/API-INVENTORY.md line 10: "Growth plan, one shared hard daily limit (2,500/day per last get_account, verified 2026-10-01)"; /home/user/oid-research/docs/mini/FEEDS_CURRENT.md line 26: "FlashAlpha Growth (2,500/day)") and by FlashAlpha's own pricing/comparison pages found via search (tier table "Daily API requests | 5 | 250 | 2,500 | Unlimited" for Free/Basic/Growth/Alpha; Growth $299/mo monthly, $239/mo annual). PART REFUTED: Basic = 100/day is contradicted by FlashAlpha's current pages. flashalpha.com/pricing, /docs/lab-api-overview and multiple 2026 FlashAlpha articles (best-options-data-apis-2026, best-gex-api-2026, build-volatility-scanner-python-free-api, free-options-data-api-get-started FAQ) all state Basic = 250 requests/day ($79/mo monthly, $63/mo annual). The 100/day figure appears only on the older flashalpha.com/docs/api page (~7 months stale) and third-party listings (SaaSworthy, GetApp). Direct fetch of flashalpha.com was blocked from this sandbox (DNS/proxy 403), so this rests on search-indexed page text rather than a live page read. PART UNVERIFIABLE: the burn breakdown (2,122 by 4:32 PM PT; VIX ~700, oil 450, walls 325, agents ~650; ~2,850 projection) appears in no file under /home/user/oid-trading-desk or /home/user/oid-research (grep for 2,122 / 2,850 / 4:32 / "Quota Steward" returns nothing; market-data/latest/api-quotas.json, which API-INVENTORY.md names as the quota source of record, is absent from the snapshot). The only documented FA cadence (FEEDS_CURRENT.md line 26) is "Focus every 5 min (<=900/day)" over a 20-symbol fa-levels universe, with no FlashAlpha VIX or oil pull described anywhere, so the VIX ~700 / oil 450 components have no primary-source backing available here. No evidence contradicts them either; they exist only on the live research page (Section 9), which is unreachable.

Correction: Growth is 2,500 requests/day (confirmed by the desk's own get_account on 2026-10-01 and by the vendor). Basic is 250 requests/day per FlashAlpha's current pricing and docs pages, not 100 (100 is a stale figure from the old /docs/api page and third-party listings). Either way, Basic is far below a ~2,100+/day burn, so the conclusion "stay on Growth, do not downgrade to Basic" still holds; the ~$220/month saving (299 - 79) is arithmetically right but the downgrade would cut capacity to 250/day, about 12% of observed use. Alpha is unlimited at $1,499/mo monthly ($1,199 annual). Reset is at midnight UTC (5 PM PDT), so a 4:32 PM PT reading is effectively an end-of-cycle count. The 2,122 observed burn and the VIX/oil/walls/agents breakdown should be treated as UNVERIFIED until the live research page's linked file or api-quotas.json is produced; the repos contain no record of FlashAlpha being polled for VIX or oil at all.

Sources:
- /home/user/oid-trading-desk/docs/API-INVENTORY.md
- /home/user/oid-research/docs/mini/FEEDS_CURRENT.md
- /home/user/oid-research/docs/COST_COMPUTE_ESTIMATE.md
- /home/user/oid-trading-desk/docs/QUERY-ARCHITECTURE.md
- https://flashalpha.com/pricing
- https://flashalpha.com/docs/api
- https://flashalpha.com/docs/lab-api-overview
- https://flashalpha.com/articles/best-options-data-apis-2026
- https://flashalpha.com/articles/best-gex-api-2026-flashalpha-vs-spotgamma-vs-unusual-whales
- https://flashalpha.com/articles/free-options-data-api-get-started
- https://flashalpha.com/articles/build-volatility-scanner-python-free-api
- https://www.saasworthy.com/product/flashalpha/pricing
- https://www.getapp.com/all-software/a/flashalpha/
