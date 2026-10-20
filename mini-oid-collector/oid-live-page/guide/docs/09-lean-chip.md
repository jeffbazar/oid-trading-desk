# 9 · 15m lean chip (net premium)
[← Index](README.md)

`15m CALL` / `15m PUT` / `15m FLAT` = over the **last 15 minutes**, was more net premium (dollars) spent on calls or on puts?

```
net = net call premium − net put premium   (last 15 min)
net > +$50K  → CALL (green)
net < −$50K  → PUT  (red)
otherwise    → FLAT (amber)
```

A shorter-window companion, the [5m chip](20-lean5-chip.md), sits right after this one.

The **flow lean strip** shows the dollar figure (for example `15m net +1.57M CALL`).

### C/P vs 15m lean: why both?
| | C/P chip | 15m lean |
|---|---|---|
| Window | whole day | last 15 min |
| Units | contracts | dollars |
| Answers | "What has the day looked like?" | "What is money doing *right now*?" |

When they **disagree**, the 15m lean is the fresher read. For example `C/P 1.9` with `15m PUT` means a call-heavy day where the last 15 minutes flipped to puts (see the NVDA tile below).

![Lean chips](img/lean-chips.png)

The chip is drawn in *italics* because it is the slow read: the desk refreshes the Unusual Whales files about every 4 minutes and the page re-reads them every ~45 s, so the data is typically 3–7 minutes old. No extra API calls. For the live read use the [15s / 1m C/P chips](21-live-aggressor-chips.md). **Soft color only.**
