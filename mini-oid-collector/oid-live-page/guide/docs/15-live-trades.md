# 15 · Live trades
[← Index](README.md)

> **Retired: the Live trades panel is no longer on the live page** (checked Tue 10/20/2026, 6:55 PM PT). This page is kept for reference only. The ladder dry run itself is listed on the [Research tab](32-research-tab.md).

The traders' real option seats (Rose, Hal), read from the trade ledger every 30 s. Option marks refresh every 5 s while a trade is open.

| Column | Meaning |
|---|---|
| Trader | Rose / Hal |
| Contract | e.g. `META 2026-10-23 705 put` |
| Qty | Contracts |
| Entry | Fill price, with time below |
| Mark | Current option price, with source (live quote or ledger) and time below |
| P&L $ / P&L % | (mark − entry) × qty × 100. Green if positive, red if negative. |
| Status | open / closed |
| Exits | The written stop and target, e.g. `Stop: META 5m close > 715.67 OR option <= 15.11` |

The section header shows how many seats are open. "No live trades" means everyone is flat.
