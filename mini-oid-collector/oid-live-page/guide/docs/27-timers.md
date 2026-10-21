# 27 · Timers: how often every live-page metric updates

> Reference for every number on the private live page and the mini jobs behind it. Values are read from the mini's launchd jobs (`~/Library/LaunchAgents/com.oid.*`) and the code on **Tue 10/20/2026, 4:15 PM PT** (light score rows added). All times PT. "Market hours" = 6:30 AM–1:00 PM PT weekdays. Items marked **live from 10/21** are being built on 10/20.

## Prices and volume

| Metric | Refresh | Source | Job |
|---|---|---|---|
| **score_features snapshots** (score learning) | Every **15 s** per ticker while each score runs | the core, light and full scores' own inputs | inside `com.oid.desk.score`, `com.oid.desk.score-wide`, `com.oid.desk.score-widefull` |
| **score_labels + Parquet** | Weekdays **1:40 PM PT** | 5 s / 1-min bars after each snapshot | `com.oid.desk.score-labels` |
| **Weekly model scorecard** | Saturdays **11:00 AM PT** | score_labels Parquet + experiments log | `com.oid.desk.score-model-weekly` |
| **Chart Bot scenario status** (chart lines, shadow) | Every **30 min**, :01 and :31 past the hour, 7:01 AM–1:31 PM PT weekdays | Chart Bot latest.json (box push) + mini 1-min bars rolled to 30 min | `com.oid.desk.chart-scn-status` |
| **Quotes** (bid/ask, last trade) | Streamed; quote cache written every **2 s** | Alpaca SIP stocks + OPRA options websockets | `com.oid.quote-collector` (always on) |
| **Live volume** (1 s / 10 s / 30 s / 60 s volume, rvol_1m, 10 s pace) | Every **1 s** from each trade print | Alpaca SIP trade prints vs 20-session same-minute norms | `com.oid.quote-collector` |
| **5-second bars** (price + volume, all 61 tickers) | One bar every **5 s**, written 3 s after the bar ends | Alpaca SIP trade prints | `com.oid.quote-collector` (`volume_5s`) |
| **1-minute bars** | Every **1 min** (each closed minute; the forming minute updates live) | Alpaca SIP websocket bars, trade prints as fallback | `com.oid.quote-collector` |
| **5-min / 15-min bars** (desk) | Every **60 s** in market hours, 5 min when closed | Robinhood 5-minute bars | `com.oid.desk.bars` (always on) |
| **Held option marks** | Every **60 s** in market hours, 5 min outside | Option quotes | `com.oid.desk.marks` |
| **VIX tile** | Every **120 s** in market hours | FlashAlpha index quote | `com.oid.desk.vix-live` (every 120 s) |
| **WTI / Brent tiles** | Job every **60 s**, alternating, so each about every **2 min** in market hours (30 min other CME hours) | FlashAlpha futures quote | `com.oid.desk.futures-live` (every 60 s) |

## Options flow

| Metric | Refresh | Source | Job |
|---|---|---|---|
| **15s C/P and 1m C/P chips** (call-buy ÷ put-buy premium, live aggressor) | Recomputed every **1 s** over rolling 15 s and 60 s windows; greyed after 30 s with no trade | Alpaca OPRA option prints | `com.oid.desk.optflow` (always on) |
| **C/P momentum on the chips** (page 22) | Sampled every **15 s**, slope over the last 45 s | Same OPRA flow | `com.oid.desk.optflow` |
| **UW flow** (net premium, 5m / 15m lean chips, C/P chip) | Pulled every **240 s** in market hours, plus one closing pull; live page re-reads every 45 s; 5m chip blank if the newest pull is over 10 min old | Unusual Whales REST | `com.oid.desk.uw-refresh` (always on) |
| **UW market tide** | Every **240 s** in market hours | Unusual Whales REST | `com.oid.desk.uw-refresh` |
| **Whale flow** (sweeps / blocks, desk Evidence tab) | Polled every **60 s** in market hours, desk republish at most every 5 min | Unusual Whales flow alerts | `com.oid.desk.whale-flow` (always on) |

## Walls and levels

| Metric | Refresh | Source | Job |
|---|---|---|---|
| **Call wall, put wall, gamma flip** (tile marks, page 23) | Job every **10 min**, 6:30 AM–1:00 PM PT: core names every **10 min**, the rest rotated so each refreshes every **40 min**. Marked STALE after 20 min in market hours, hidden after 4 days. | FlashAlpha | `com.oid.desk.fa-walls` (every 600 s) |
| **Focus watch** (spot vs wall) | Every **5 s** when active, 30 s idle; reads saved levels, makes no FlashAlpha calls | Saved FlashAlpha levels + quotes | `com.oid.desk.fa-focus` (always on) |
| **Open interest and volume at the wall strikes** (wall mark weight) | Volume every **5 min** in market hours | Alpaca option data (read-only) | live page (`com.oid.desk.livepage`) |

## Signals and scores

| Metric | Refresh | Source | Job |
|---|---|---|---|
| **vol_surge** (surge strip, event log) | Every **~2 s** in market hours | Live volume (rvol_1m) | `com.oid.desk.volsurge` (always on) |
| **Trigger engine** | Every **60 s** | Mini data files | `com.oid.desk.triggers` (every 60 s) |
| **Momentum detector** (ACCEL / DECEL / RESUME chip, market gauge, page 25) | Every **15 s**, 6:31 AM–1:00 PM PT; a flag older than 10 min shows quiet | 1-minute SIP bars + last trade | `com.oid.desk.momentum` (always on) |
| **Mover alerts** (3% runs, wall crosses) | Every **15 s** in market hours; one alert per ticker per direction per 30 min | Live page state, 1-minute bars, FlashAlpha walls | `com.oid.desk.mover-alert` (always on) |
| **Direction score badge** (page 24) | Recomputed about every **60 s** in market hours (job checks every 5 s); not saved | Mini data files only | `com.oid.desk.score` (always on) |
| **Direction score saved rows** | 8 anchor times + every **15 min** 6:45 AM–12:45 PM PT + each vol_surge | Same | `com.oid.desk.score` |
| **Score changes saved as they happen** | Every change, with start and stop time (**live from 10/21**) | Same, plus C/P, surge, wall room, momentum and tape context | `com.oid.desk.score` |
| **Score grading** | Every **15 min** (old fixed windows, through 10/20); holds graded start to stop (**live from 10/21**) | Saved rows + 5-second bars | `com.oid.desk.score-grade` (every 900 s) |
| **Daily scorecard** | Once a weekday at about **1:10 PM PT**; results to Jeffrey in chat about **1:20 PM PT** (**live from 10/21**) | Graded holds | mini |
| **Light score** (Sector watch, 144 names, page 24 §9: trend + volume + market only) | Re-scored every **5 s** in market hours; 1-minute bars re-read every **20 s**; every change saved as it happens (**live from 10/21**) | Wide collector tier (SIP trades + 1-minute bars), core market input | `com.oid.desk.score-wide` (always on, Nice 10) |
| **Light score chip** (L±n on Sector watch rows) | Feed rewritten every **5 s**; page section refreshed every **5 s**; faded after 30 s, hidden after 15 min | `latest-wide.json` | `com.oid.desk.score-wide` + `com.oid.desk.livepage` |
| **Light scorecard** (`scorecard-wide-YYYYMMDD`) | Same job, once a weekday at about **1:10 PM PT** (**live from 10/21**) | Light holds + wide 5-second bars | `com.oid.desk.score-scorecard` |
| **Position trigger** | Every **30 s** | Held positions + quotes | `com.oid.desk.position-trigger` (every 30 s) |

## News

| Metric | Refresh | Source | Job |
|---|---|---|---|
| **Headlines and sentiment** (news panel, tile badge, page 26) | Real-time websocket (seconds); REST safety-net and X archive read every **60 s**; live page re-reads every **20 s** | Alpaca news (Benzinga), x-on-surge X archive, FinBERT | `com.oid.desk.news` (always on) |
| **News in the score** | **Off** | — | — |

## The live page itself

| What | Refresh |
|---|---|
| Server rebuilds the page data | Every **1 s** (`com.oid.desk.livepage`, always on) |
| Push to your browser | Every **1 s** over a live stream; a full payload (with sparklines) every 10 ticks, small updates in between |
| Browser redraw | Every **5 s** |
| Sector groups reload | Every **5 min** |
| News panel reload | Every **20 s** |
| Mini health jobs (status, self-heal, alerts) | `com.oid.desk.status`, `com.oid.desk.selfheal`, `com.oid.desk.alerts` each every **60 s** |

## Slower background jobs

| Job | Timer |
|---|---|
| `com.oid.desk.macro-public` | Every 15 min |
| `com.oid.desk.edgar` (Form 4) | Hourly, when due |
| `com.oid.desk.short-borrow` | Hourly, when due |
| `com.oid.archive.main` / `.post` | Weekdays 2:00 PM and 5:15 PM PT |
| `com.oid.archive.weekly` | Saturday 10:00 AM PT |

## Direction arrows and Sector watch (added 10/20)

| Metric | Refresh | Source | Job |
|---|---|---|---|
| **Volume direction ▲/▼** (last 15 s vs prior 60 s share rate; ▲ ≥1.3×, ▼ ≤0.7×, floor 500 shares) | Computed every **1 s** in market hours; page redraw at least every **5 s** | Alpaca SIP trade prints (per-second buckets) | `com.oid.quote-collector` + `com.oid.desk.livepage` |
| **C/P direction ▲/▼ / STRONG** (15s and 1m C/P now vs ~60 s ago; STRONG = doubled/halved or moved >0.5; floor 8 prints + $15K for 15s, 20 prints + $40K for 1m) | Computed every **1 s** in market hours; page redraw at least every **5 s** | Alpaca OPRA aggressor flow | `com.oid.desk.optflow` + `com.oid.desk.livepage` |
| **Sector watch** (144 sector names, now sections of the **Table** view; the one-line Sector watch bar under the heatmap shows status and alerts: price, % change, 1-min rvol, SURGE ≥3×, MOVE ≥3% vs prior close) | Collector live every **1 s**; rows refreshed every **5 s** | Alpaca SIP **trades + 1-minute bars only** (no quotes, no options flow) | `com.oid.quote-collector` (wide tier) + `com.oid.desk.livepage` |
| **Sector watch alerts** | Page only, **batched per sector** over the last 15 min; no chat alerts | Same | `com.oid.desk.livepage` |
| **Sector watch walls** | Only after a SURGE/MOVE: up to **3 names per 10-min run**, **30 per day**, each name at most hourly, and only while FlashAlpha remaining is **≥ 800** | FlashAlpha | `com.oid.desk.fa-walls` |
| **Sector watch raw archive** (5-second bars + 1-minute bars) | Written live; kept **21 days** (core stays 90) | Alpaca SIP | `com.oid.quote-collector` |

## Exit watch (added 10/20)

| Metric | Refresh | Source | Job |
|---|---|---|---|
| **Hal exit watcher** (option stop and target, +20% half, stock stop and target, 5-min structure break, time stop, 12:40 PM PT warning for 8 or fewer days to expiry; page 28) | Every **3 s** in market hours and for **15 min** after the close; status every 30 s otherwise. Price rules must hold 2 checks; each alert repeats at most every **2 min**, **3** times a day | Alpaca SIP stock trades and quotes, Alpaca OPRA option quotes, Alpaca SIP 5-minute bars (one fetch per name about 8 s after each 5-minute bar ends) | `com.oid.desk.hal-exit-watch` (always on, Nice 10; dry run until Hal's webhook is saved) |
| **Hal's exit rules file** (box → mini) | Sent within about **15 s** of a change in market hours, 60 s otherwise | Box mirror poller (`/v1/desk-state`) | box `quotes/mirror_poller.py` |

## Host health (added 10/20)

| Metric | Refresh | Source | Job |
|---|---|---|---|
| **Mac mini resources** (load 1/5/15, total CPU %, memory free %, swap, disk free, network in/out, top 8 processes) | Every **15 s** weekdays 6:00 AM–1:30 PM PT, every **5 min** otherwise | macOS kernel counters, `memory_pressure`, `netstat -ib`, `ps` | `com.oid.desk.host-monitor` (always on, Nice 10, about 0.24% of one core at 15 s) |
| **Daily host summary** (peak and p95 CPU and load, lowest memory free, top processes at the CPU peak) | Weekdays **1:15 PM PT** | `~/oid-data/host/host-YYYYMMDD.jsonl` | `com.oid.desk.host-summary` → `~/oid-data/host/summary-YYYYMMDD.txt` |

<!-- LEARN-1021 -->
