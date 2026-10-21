# Ladder-scalp dry run (started for Mon 10/19/2026 open)

**Research only. Nothing here places, cancels or modifies orders.** Robinhood stays off the Mac mini.
Book data is private (Robinhood L2); never put it on the public blotter.

## The idea (Jeffrey, 10/18)
A 1-minute volume surge on a stock (mini `vol_surge` / `/v1/live-volume` rvol) **plus** a thin order book on the
side price is moving into → price runs ~$0.50–$2 to the next larger resting wall → exit into that wall.
The dry run checks whether "thin" surges reach the wall more often than "not thin" surges.

## Data sources
| What | Where | How |
|---|---|---|
| Order book (L2) | Robinhood `get_equity_price_book` (connector `user-robinhood-trading`), ≤4 symbols/call | **MCP only**: an agent calls it, saves raw output to `raw/`, then runs `ingest`. Box Python cannot call it. |
| Surge context | mini `/v1/live-volume` | `quotes/live_volume_pull.py` (Tailscale proxy, token file, never printed) |
| Outcomes | mini `/v1/bars?timeframe=1Min` (Alpaca SIP) | `quotes/mini_bars.fetch_mini_bars` |

Book shape (observed 10/18, market closed): `{"data":{"books":[{"symbol","updated_at","asks":[{price,quantity}],"bids":[...]}]}}`,
asks best-first, bids best-first, `quantity` = resting shares. Closed market → empty `asks`/`bids` (stamp is request time).
Depth, tick step, and whether levels are aggregated get measured from the first RTH snapshots (`n_asks`, `tick`, `ask_span`).

## Workflow
```bash
cd /workspace/oid-trading-desk/research/ladder-dryrun
# 1. agent pulls get_equity_price_book for the surging ticker(s); save raw text:
#    raw/YYYYMMDD-HHMMSS-<SYMS>.txt
python3 ladder_dryrun.py ingest raw/<file>.txt --event '<webhook payload JSON>'   # direction/rvol/price/test from the mini payload
python3 ladder_dryrun.py ingest raw/<file>.txt --trigger vol_surge     # no payload: dir auto from /v1/live-volume surge event
python3 ladder_dryrun.py ingest raw/<file>.txt --dir up --note "manual"
# 2. after 16+ min (or end of day):
python3 ladder_dryrun.py score
python3 ladder_dryrun.py report --date 2026-10-19
```

## Logged per snapshot (`data/snapshots.jsonl`)
- `symbol`, `book_ts` (RH stamp), `logged_epoch`, `trigger`, `dir` (up/down), `rvol_1m`, `mini` (rvol, 10s pace, last, surge event)
- `book`: `ask0/bid0/mid/spread/tick`, `ask_depthN/bid_depthN` (N=3,5,10 levels), `thin_ratio5` = move-side depth(5) / opposite depth(5),
  `thin` (≤0.6), `wall_ahead` = first move-side level with qty ≥ 3× median of the side's first 10 levels and ≥500 sh
  (`price`, `qty`, `level`, `dist_usd`, `shares_before`), `entry_ref` (ask for up, bid for down)
- `outcome` (from `score`): `mfe5/mfe15` (max favorable $ from entry), `mae5/mae15` (max adverse $),
  `wall_hit_min`, `stop_hit_min` ($0.50 adverse), `result` = WIN_wall / LOSS_stop / AMBIG_same_bar / FLAT, `run_050_5/15`

Tunables at the top of the script: `WALL_MULT`, `WALL_MIN_SHARES`, `THIN_RATIO`, `STOP_USD`, `HORIZONS`.

## Limits to keep in mind
- 1-minute bars: the first bar includes ticks before the snapshot, and wall-vs-stop in the same minute is `AMBIG`.
- Robinhood's book is one snapshot per LLM call (seconds, not ticks); walls can be pulled (spoofing) or hidden (icebergs).
- Results are stock-move only; options spreads would eat part of a $0.50–$2 move.

## Upgrade path
True tick-by-tick depth = Nasdaq TotalView (e.g. Databento `XNAS.ITCH`) streamed into the mini. See the parent report for pricing/licensing.

## Mini wake payload (v0.4.2)
The mini's vol_surge loop POSTs dry-run surges (cap 20/day, 5-min per-ticker dedupe) with flat fields
`ticker, direction, rvol, price, time_pt, test, tag, trade_action:"none"`. `--event` reads those (falls back to `details.dir/rvol_1m/last`).
Payloads with `test:true` are logged with `test:true`, shown as `[TEST]`, and left out of the thin vs not-thin stats.

## Private live page panel ("Last ladder", 10/18)
`ingest` and `score` push the rows they write to the mini's private live page (tailnet only), where the
**Last ladder** panel shows the newest snapshot per ticker: book bars (top 10 levels/side, parsed from `raw/`),
thin ratio + THIN badge, wall ahead, and the scored outcome. `[TEST]` rows are flagged.
- Transport: `POST http://<mini tailnet IP>:8791/ingest/ladder` via the box Tailscale proxy (`localhost:1056`),
  `Authorization: Bearer` = dedicated token `/home/box/tailscale/secrets/OID_LADDER_PUSH_TOKEN` (chmod 600; mini copy
  `~/oid-live-page/secrets/LADDER_PUSH_TOKEN`, chmod 600). Never printed or logged.
- The mini accepts only JSON `{"snapshots":[...]}` (1-20 rows, <=64 KB, whitelisted fields, numeric ranges,
  120 posts/hour) and keeps the last 300 in `~/oid-live-page/data/ladder.jsonl` (chmod 600).
- Push failures never break ingest/score; see `data/push.log`. Re-send: `python3 ladder_dryrun.py push --last 10`.
- Off: `LADDER_PUSH=0` (env) or `ingest --no-push`. Override target: `LADDER_PUSH_URL`, `LADDER_PUSH_PROXY`.
