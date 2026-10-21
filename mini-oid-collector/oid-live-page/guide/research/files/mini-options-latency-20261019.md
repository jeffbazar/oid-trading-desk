# Mini live dashboard: options vs Robinhood latency study (Mon 2026-10-19, 11:00–11:16 AM PT)

Research only. Nothing on the mini was changed: no config edits, restarts or subscriptions. The only things written were temporary sampler scripts in the mini's `/tmp`, removed afterwards. The raw samples are kept at `/tmp/oid-lat-samples-20261019.jsonl` on the mini.
Access: `ssh jake@Jakes-Mac-mini.local` from mars.local, with loopback `curl` on the mini, plus the Robinhood connector (read-only) for comparison. No keys were printed.
Clocks: mars and the mini are each within about 40 ms of time.apple.com (`sntp`), and the gap between them is about 10 ms, so the cross-machine numbers below can be trusted.
Note: livepage.py was redeployed twice by the parallel dashboard work while I was measuring (11:05:40 for the 5m chip and sectors, and 11:13:13). The intervals below are from the **deployed** copy after 11:05.

## TL;DR
* **The biggest gap is the options table. It isn't slow: it's frozen.** The mini's Alpaca OPRA websocket is connected, but it has **0 subscribed contracts** and has had none since **08:48:11 AM PT**. `options-subs.json` is `[]`, `desired_count=0`, and `last_option_received_at 08:48:11`. The 3 option rows on the page are left over from that time:
  | contract | mini day vol (last print) | Robinhood vol @ 11:06:45 AM PT | behind by |
  |---|---|---|---|
  | QQQ 10/23 720C | 6,254 (08:48:03 AM PT) | 10,778 | 2 h 18 m, −42% |
  | NVDA 10/23 220C | 1,610 (06:32:08 AM PT) | 33,562 | 4 h 34 m, −95% |
  | META 10/23 705P | 493 (07:17:37 AM PT) | — | about 3 h 50 m |
  Cause: the subscription set is built only from open seats and legs (`trades.json`/`paper-open.json`), live RH option positions (`cache/rh-live-option-positions.json`, last written 7:20 AM PT with `positions: []`), and `config/option-watch-contracts.json`, which **doesn't exist**. Once the desk went flat, the list emptied. Hal's live GOOG 340C is not in that set either, so its mark on the page comes from the ledger, not OPRA.
* **The UW chips (C/P, 15m lean, Ask lean, the new 5m chip) are limited by the source refresh, not by the mini.** Typical data age is about 3.3 min and the worst is about 7 min. Most of that is the uw-refresh poll cycle of about 264 s. The page's 45 s re-read adds 0–45 s on top.
* **Stocks are fine.** Stock volume reaches the browser on mars in about 1.2 s median and about 2 s worst. The mini's last trade time matched Robinhood's venue trade time to within about 1 s.
* The mini's own processing is negligible. A state build plus SSE publish takes ≤0.2 s, `state.json` is served in 11 ms, and Tailscale RTT is 9 ms.

## (a) Stock volume path, measured
| Stage | Mechanism (deployed) | Measured | n |
|---|---|---|---|
| SIP print → collector receive | Alpaca SIP websocket (trades, quotes, bars, updatedBars) | 84% ≤50 ms, 95% ≤100 ms. Mean 3.9 s is skewed by 0.4% of prints >5 s (reconnects/overnight feed). Max 901 s. | 49.4 M (collector lag histogram) |
| Mini vs Robinhood last trade | mini `last_pt` 11:07:04/05 vs RH venue trade time 11:07:06.1/06.5 (RH read ~1 s later) | ≈0–1 s | 2 symbols × 2 reads |
| 5-second bar close → archive write (`volume_5s`) | written at bucket_end + 3 s GRACE (by design) | median 3.6 s, range 3.1–4.2 s | 26 |
| *The page does **not** read the 5 s archive.* It gets rolling `vol_1s/10s/60s`, `cur_bar` and `last_closed_bar` from the collector's in-memory `/v1/live-volume`. | | | |
| Collector → livepage | livepage polls `/v1/live-volume` every 1 s | 0–1 s wait (mean 0.5 s) | — |
| New 1-min bar visible in livepage `state.json` | `cur_bar`/`last_closed_bar` merged each tick; today's jsonl re-read every 5 s; history/norms on change or every 30 ticks | 0.26–0.66 s after the minute boundary (sampled every 0.25 s) | 3 |
| livepage → mars over Tailscale SSE | `/stream`, one event per tick (full payload every 10th tick or when the sparkline changes) | publish→arrival median 0.18 s, p90 0.20 s, max 0.61 s. Event gap median 1.10 s, p90 1.15 s. Payload ~38 KB median, 79 KB full. | 57 events / 60 s |
| Tailscale | ping / HTTPS `/healthz` | RTT 9.3 ms avg. HTTPS total 41–148 ms. | 5 |
| Browser render | `es.onmessage → onData → render()` right away. A separate `setInterval(render, 5000)` only re-ages labels. | Not instrumented. Estimated <50 ms (one innerHTML pass for about 60 tiles). | — |
| **End-to-end stock (print → pixels on mars)** | | **median ≈ 1.2 s, worst ≈ 2 s** (feed outliers excluded) | |

## (b) Options chips (Unusual Whales) path, measured
| Stage | Mechanism | Measured (3 cycles in the sampler, plus the log for 10:00–11:15) |
|---|---|---|
| UW internal: tape minute → API response | `net-prem-ticks` 1-min ticks, market-tide 5-min bars | `as_of − last_tape_time` = 35 s, 51 s, 17 s. Market-tide bar = the current 5-min bar. |
| UW pull cycle (33 calls: tide + 3 sectors + 24 net-prem + flow-alert chunks) | `quotes/uw_refresh.py`, 0.25 s request spacing | 11 s, 11 s, 30 s for net-prem (log: 10.1–33.9 s, median ≈ 11.5 s) |
| **Refresh interval** | `interval_s 240`, counted from the end of the previous cycle; the main loop also checks the schedule only every 30 s (15 × 2 s sleeps) | file rewrites every **238–286 s, median ≈ 264 s** (10:00:09 → 11:14:56 log) |
| File write → livepage re-read | `OID_LIVEPAGE_UW_REFRESH_S=45`: stat the 3 files at most every 45 s, re-parse when an mtime changes | observed 17 s and 21 s (10 s sampler). By design 0–45 s, mean ≈ 22 s. |
| livepage → browser | same SSE path as stocks | ≤1.2 s |
| **Displayed chip data age** | | **best ≈ 30 s, median ≈ 200 s (≈3.3 min), worst ≈ 415 s (≈7 min)** |
| 15m lean | sum of the last 15 one-minute ticks | also smoothed over 15 min by design |
| 5m CALL/PUT chip (deployed 11:05:40) | difference between two UW snapshots 180–600 s apart (target 300 s), dash when stale >600 s | first value appeared after the 11:14:56 write: NVDA CALL +$0.12M and QQQ CALL +$0.56M over **4.4 min**, `lean5_age_s 90` at 11:16:12 AM PT. It updates only once per UW cycle, so it is never fresher than the 15m chip. |
| Calls budget | `daily_call_cap 6000` | 2,045 calls by 11:02 AM PT; about 33 × 89 ≈ 2.9k for a full RTH day at 240 s |

## (c) Alpaca OPRA options collector
* It is a **stream**, not a poll: `wss://stream.data.alpaca.markets/v1beta1/opra`, `quotes` and `trades` channels, `option_cap 1000`, subs file polled every 5 s.
* When it had contracts, it was fast: 87% of option messages arrived ≤50 ms after the event and 99.3% ≤1 s (mean 1.04 s, skewed by stale-seed outliers).
* Right now it carries **nothing** (see the TL;DR). Options volume on the page is therefore hours old and can't match Robinhood. Robinhood's `updated_at` was about 1 s old.
* The box/mini 5 s poller (`quotes/mini_poller.py`, `OID_MINI_POLL_S=5`) and `refresh_marks.py` both depend on the same empty set (`mini-option-marks.json`: `mini_opra: []`, 4 expired 10/02 contracts listed under `none`).

## (d) Deployed livepage.py cadences (mini copy, 11:05+ build)
| Panel | Source | Rate |
|---|---|---|
| Volume tiles, heat, RVOL, Hot, pace | collector `/v1/live-volume` | every 1 s (loop `sleep(max(0.05, 1 − build))`) |
| Today's 1-min bars / sparkline | `cache/bars/store/live/{SYM}-1m-YYYYMMDD.jsonl` plus `last_closed_bar` from live-volume | file re-read every 5 s (only if the mtime changed); the newest bar comes from live-volume each second |
| Prior-session bars + norms | `{SYM}-1m.json`, `live-norms-1m.json` | on norms mtime change; check every 30 ticks |
| Held-option marks | collector options (OPRA mid) | every 5 s (only if there are open OCCs) |
| Live trades / seats | `paper-trades/trades.json` | every 30 s |
| UW chips (C/P, 15m, 5m, Ask lean, tide) | `market-data/latest/uw-*.json` | stat at most every 45 s; the files themselves change about every 264 s |
| Options table | collector `/v1/live-volume` options block | every 1 s (but the source is frozen) |
| Sectors | `/sectors.json` → `loadSectors()` | browser `setInterval` 300 s |
| SSE | `/stream` | one event per state tick (~1.1 s), `: ping` after 15 s idle, full payload every 10 ticks |
| Browser | `onmessage → render()`, plus `setInterval(render, 5000)` | — |

## (e) Event-driven push: feasibility
| Option | Feasible on the current stack? | Build effort | Lag removed |
|---|---|---|---|
| Collector SSE/websocket (`/v1/live-volume/stream` on the existing aiohttp server, pushing per second or on bar close), with livepage switched from polling to a stream reader thread | Yes. aiohttp supports `StreamResponse`/websockets natively, and livepage is stdlib, so it needs a small SSE reader. | about 4–6 h with tests and auth | Stocks: mean ≈0.5 s, worst ≈1 s. **Low value**, because stocks are already ≈1 s. |
| livepage watches the UW files with `select.kqueue` (stdlib, works on macOS `/usr/bin/python3` 3.9). Watch the **directory** (`KQ_NOTE_WRITE`), because the files are atomically replaced (rename). | Yes | about 1–2 h | UW chips: mean ≈22 s, worst ≈45 s |
| Cheaper equivalent: `OID_LIVEPAGE_UW_REFRESH_S=2` in the livepage plist (stat 3 files every 2 s; it already skips re-parsing when the mtimes haven't changed) | Yes | about 10 min plus a restart | same ≈22 s mean / 45 s worst |
| Faster UW source: split uw-refresh into a 60 s fast lane (market-tide + flow-alerts + net-prem for the tile names) and keep the 240 s slow lane for sectors and the long tail. Tighten the 30 s schedule check to 2 s. | Yes, but check the UW plan's per-minute/day limits first. At 60 s for all 33 calls it's about 12.9k calls/day, more than the configured 6,000 cap. | about 2–3 h | UW chips: median age about 200 s → 60 s, worst about 415 s → 120 s |
| UW websocket (flow/net-flow channels, if the plan includes them) | Depends on the plan; this is covered by the parallel aggressor-ratio research | — | UW chips: down to seconds |

**Recommendation:** don't build collector push for stocks; it saves at most about 1 s. Spend the effort on the options sources:
1. **Fix 1: re-populate OPRA subscriptions (largest visible gain).** Add a standing near-ATM watch set for the core names, either by creating `config/option-watch-contracts.json` or by auto-seeding ATM ±N strikes for the nearest weekly. Keep it within `option_cap 1000`. Expected result: the options table goes from **2–4.5 h stale** to **≈1 s** (stream), matching Robinhood volume within about a second. This is a config/data change, so it needs Jeffrey's OK.
2. **Fix 2: UW freshness.** Set the livepage UW re-read to 2 s (or use kqueue), and move uw-refresh to a 60 s fast lane within the UW limits. Expected result: the UW chip age drops from a median of about 3.3 min / worst about 7 min to a median of about 1 min / worst about 2 min. The new 5m chip then becomes a true about-5-min window refreshed every minute, instead of one value per 4.4 min.

## Overlap with the Alpaca options websocket / 15 s aggressor-ratio work
It is the same feed. The mini **already holds** the OPRA websocket (`v1beta1/opra`, quotes and trades) open, with zero subscriptions. Every trade arrives with the latest NBBO quote in the collector cache, so Lee-Ready/quote-rule tagging (ask = buy, bid = sell) and a rolling 15 s buy-call/buy-put vs sell-call/sell-put ratio can be computed inside `livevol.py` with no new vendor. **Fix 1's subscription set is the shared prerequisite.** Coverage is limited by `option_cap` (1000 contracts), not by money. Still to verify: whether Alpaca's options stream allows wildcard trade subscriptions, and the plan's contract limit.
