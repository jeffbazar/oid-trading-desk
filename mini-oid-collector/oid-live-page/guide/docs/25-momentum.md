# 25 · Momentum chip, market gauge and recent flags

> **Shadow mode, research and logging only.** The momentum detector (`com.oid.desk.momentum`, every 15 s, 6:31 AM–1:00 PM PT) never sends alerts or places orders. Built 10/20/2026 from Jeffrey's CRWV and NVDA call trades that morning.

## The chip on each ticker

| Chip | Meaning |
|---|---|
| <span style="background:#1a7f37;color:#fff;padding:0 4px;border-radius:3px;font-weight:800">▲ ACCEL 42s</span> | Speed picked up and the stock closed above its 15-minute high. |
| <span style="background:#dafbe1;color:#1a7f37;padding:0 4px;border-radius:3px;font-weight:800">▲ RESUME</span> | After a slowdown, speed picked up again and the stock closed above its last high. |
| <span style="background:#fff1c2;color:#9a6700;padding:0 4px;border-radius:3px;font-weight:800">DECEL</span> | The move slowed (the take-profit moment in the replay). |
| <span style="background:#f6f8fa;color:#8c959f;padding:0 4px;border-radius:3px">quiet</span> | No active flag, or the last flag is more than 10 minutes old. |

- **Number after the label:** time since the flag (seconds, then minutes).
- **Dashed border:** the minute that is still forming already meets the test. This is provisional until the minute closes.
- **¼ 9¢ · $1 59¢:** distance from the last price up to the next $0.25 level and the next whole dollar. In the replay, exits often came a few cents under these levels.
- **Hover:** shows the time of the flag, the held level and the exact levels.
- **Table view:** has a sortable Momentum column.

## Rules (one-minute SIP bars)

- **Speed** is a stock's one-minute price change compared with its usual one-minute move over the prior 30 minutes, so CRWV and NVDA are measured on the same scale.
- **Accelerate:** speed at least 1.25× normal and a close above the 15-minute high.
- **Decelerate:** the latest minute gains no more than 35% of the best minute in the prior three, and is barely moving (at most 0.5× normal).
- **Resume:** after a decelerate, speed at least 1.25× again and a close above the last high.
- A decelerate ends quietly if the stock closes under its 15-minute low.

## The market gauge (top of the page)

- **Count:** stocks making new 15-minute highs on at least 2× normal volume, added up over the last 5 minutes (ETFs left out). The bar shows that count against its peak over the last 45 minutes; the tick marks the warning line.
- **BROAD (green):** breadth is healthy. *No surge yet* means the 45-minute peak is under 25, so the gauge isn't armed.
- **WARN (amber):** the 5-minute count has dropped to 35% of its peak or lower.
- **RECEDE CONFIRMED (red):** WARN has held for 10 minutes in a row. On 10/20 the warning came at 7:36 and the confirm at 7:45 AM PT, one minute before Jeffrey's last exit at 7:46.

## Recent flags strip

- The last 20 flags, newest first: time (PT), ticker, then accelerate / decelerate / resume or market recede.
- **pause→resume:** a decelerate followed by a resume on the same name within 2 minutes is shown as one flag.
- **Dashed:** a provisional flag from the forming minute. It disappears once the closed minute confirms it.

## 10/20 replay scorecard

- **Matches:** 13 of 14 fills, within 90 s before to 75 s after the fill.
- **Exits:** median lag about +10 s (range −36 s to +51 s).
- **Entries:** median lag about +17 s (range −24 s to +73 s).
- **Missed:** the 6:44 CRWV buy, which was a bounce, not a break of the 15-minute high.
- **Extra flags:** about 14 while he was trading, roughly half of them one-to-two-minute pauses he held through.

## Data and limits

- **Source files:** `~/oid-desk/state/momentum/current.json` and `events-YYYYMMDD.jsonl`; the page refreshes them with its normal live updates.
- **State archive (new 10/20, 6:26 PM PT):** every change of the state shown on the page is logged to `~/oid-data/archive/momentum_state/` (90 days JSONL, Parquet forever; columns on [29](29-how-data-is-saved.md)). The [chart](30-chart.md) draws it as a ribbon under the score lane; 10/20 regular hours are derived from the engine's bar-close events.
- **Lag:** the history is only one-minute bars, so the bar-close lag is up to about 60 s.
- **Provisional flags:** these aren't tested yet. The job stores 15-second price samples (`ticks-YYYYMMDD.jsonl`) so they can be tested later.
