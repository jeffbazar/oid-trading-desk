# 28 · Hal exit watcher (fast stop and target alerts)

> Added **Tue 10/20/2026**. Job `com.oid.desk.hal-exit-watch` on the Mac mini. All times PT. **It never places orders.** It only wakes Hal; Hal still decides and sends the close himself.

## Why it exists

Hal's live trader routine runs every 5–10 minutes, and some gaps were 34–46 minutes. A stop that broke between runs was only seen at the next run, which led to fills well past the stops (Hal's audit, `paper-trades/HAL-LIVE-VS-PAPER-AUDIT-20261020.md`). The watcher checks every open seat **every 3 seconds** and wakes Hal the moment an exit rule is hit.

## How a seat gets watched

1. At every entry and exit, Hal rewrites one file on the box: `paper-trades/hal-live/active-exit-rules.json`. It lists every open seat (live 8444 and paper) with its exit levels.
2. The box mirror poller sends that file to the mini whenever it changes, within about **15 seconds** in market hours (60 seconds outside them). It travels on the same private link that already carries `paper-open.json` and `trades.json`.
3. The watcher re-reads the file on every check. A seat Hal removes stops being watched right away.
4. Each seat's option contract is added to the mini's live options feed automatically, so its price is real-time.

## What it checks every 3 seconds

| Rule | Trips when | Which part tripped |
|---|---|---|
| `option_stop` | Option **mid price** is at or below the option stop. The bid is shown too. | option |
| `stock_stop` | The stock's **last trade** is through the stock stop (below it for calls, above it for puts). | stock |
| `target_option` | Option mid is at or above the option target. | option |
| `target_stock` | The stock's last trade reaches the stock target. | stock |
| `take_half` | Option mid is up **+20%** (or the seat's own %) from the entry price. Stays quiet once Hal marks the half as sold. | option |
| `structure_break` | A **5-minute bar closes** through the structure level (for example the wall or flip). Checked about 8 s after each 5-minute bar ends. | structure |
| `time_stop` | The clock passes the seat's time stop. | time |
| `preclose_dte` | At **12:40 PM PT**, a warning for any seat with **8 or fewer days** to expiry. | time |
| `quotes_stale` | The stock or option price has been more than 30 s old for a full minute, so silence is never mistaken for "nothing tripped". | data |

**The option can trip on its own.** Time decay or falling volatility can push an option through its stop while the stock is still above its stop (that's what happened to MU). Every option-stop alert says which case it is: "stock moved through its stop too" or "option mark only".

## How often it alerts

- Price rules must hold for **2 checks in a row** (about 3–6 seconds), so one odd print doesn't fire. Time rules fire on the first check.
- Each seat and rule fires **once**. If it's still tripped **2 minutes** later it fires again, at most **3 times** a day for that seat and rule.

## What Hal receives

The watcher sends a webhook (JSON) to Hal's routine "Hal live exit wake". The fields are seat_id, account, underlying, occ_symbol, rule, leg (option, stock, structure, time or data), observed (stock last, bid, ask and age; option mid, bid, ask and age; the level), quote_age_s, fire_n, first_tripped_at, ts, a plain-text detail line and `never_trades: true`.

## Dry run and live

The watcher runs in **dry run** (it logs every trip and sends nothing) until Hal's webhook address and key are saved on the mini. Jeffrey saves them on the mini himself with `~/oid-desk/bin/hal-exit-keys.sh`. The input is hidden, and the files are private (600) in `~/oid-quote/secrets`. The watcher notices them within 3 seconds and switches to live without a restart. To force dry run, run `touch ~/oid-desk/flags/hal-exit-watch.dry`.

## When it runs

Every **3 seconds** during market hours (6:30 AM–1:00 PM PT on trading days) and for **15 minutes after the close**. Outside those hours it only updates its status every 30 s.

## Files

| What | Where (mini) |
|---|---|
| Code | `~/oid-desk/app/oid_desk/hal_exit_watch.py` |
| Rules file (from the box) | `~/oid-desk/desk/paper-trades/hal-live/active-exit-rules.json` |
| Schema and example | `~/oid-desk/app/docs/hal-exit-watch/` |
| Every check and every trip | `~/oid-data/hal-exit/YYYYMMDD.jsonl` |
| Status (heartbeat) | `~/oid-desk/desk/cache/hal-exit-watch.json` |
| Log | `~/oid-desk/logs/hal-exit-watch.log` |
| Webhook secret files | `~/oid-quote/secrets/HAL_EXIT_WEBHOOK_URL`, `HAL_EXIT_WEBHOOK_KEY` (600; never printed) |

Prices come from the mini's own feeds: Alpaca SIP stock trades and quotes, Alpaca OPRA option quotes and Alpaca SIP 5-minute bars. It makes **no paid data calls** beyond those.
