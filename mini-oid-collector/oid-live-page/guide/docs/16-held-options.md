# 16 · Held option contracts: traded volume
[← Index](README.md)

Volume printing on the exact option contracts we hold or are watching (OPRA prints via the mini collector).

| Column | Meaning |
|---|---|
| Contract | OCC symbol. `QQQ261023C00720000` = QQQ, 2026-10-23, **C**all, strike 720.000 |
| Vol 60s / Vol 5m | Contracts traded in the last 60 s / 5 min |
| Day vol | Contracts today |
| Trades | Number of prints today |
| Last print | Time of the latest trade (PT) |

**Why it matters:** if the contract you hold has 0 volume for 5 minutes, its mark is stale and you'll have a harder time getting a clean exit. A burst here when the stock isn't moving can mean someone is positioning in your strike.

How to read the OCC symbol:
```
QQQ   26 10 23   C   00720 000
root  YY MM DD  C/P  strike ×1000
```
