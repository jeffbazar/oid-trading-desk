# 26 · News panel, sentiment chips and tile news badge

> **Research only.** Built 10/20/2026. The feed job `com.oid.desk.news` runs on the Mac mini at no extra cost (Alpaca Algo Trader Plus already includes Benzinga news). It never trades and has no chat path of its own.

## Where the headlines come from

| Source | How | Delay |
|---|---|---|
| **Alpaca news (Benzinga)** | Real-time websocket `v1beta1/news`, subscribed to everything and filtered to the names on this page. Today's headlines are backfilled from REST on startup, and REST is polled every 60 s as a safety net. | Seconds |
| **X posts** | Read from the x-on-surge archive (posts fetched when a ticker surges). Only posts that passed the spam filter are shown, deduped by cluster and text, most-engaged first. | When a fetch ran |

"Followed" means the tickers in `sectors.json` plus SPY and QQQ, minus WDC, STX, SNDK and the VIX/WTI/BRENT tiles.

## The panel (under the header)

- **Followed / All market / X posts** tabs. Followed is the default. All market shows every headline today, including names that are not on the page.
- Each row shows the time (PT), the **sentiment chip**, ticker chips, the headline (click to open the source), and the source. Blue time = in the last 30 minutes.
- Click a **ticker chip** to filter to that name; click it again (✕) to clear. **hide** collapses the panel and the page remembers that choice.

## Sentiment chip (−2 … +2)

| Chip | Meaning |
|---|---|
| <span style="background:#1a7f37;color:#fff;padding:0 4px;border-radius:3px;font-weight:800">+2</span> | Clearly bullish |
| <span style="background:#dafbe1;color:#1a7f37;padding:0 4px;border-radius:3px;font-weight:800">+1</span> | Leaning bullish |
| <span style="background:#f6f8fa;color:#59636e;padding:0 4px;border-radius:3px;font-weight:800">0</span> | Neutral |
| <span style="background:#ffebe9;color:#cf222e;padding:0 4px;border-radius:3px;font-weight:800">−1</span> | Leaning bearish |
| <span style="background:#cf222e;color:#fff;padding:0 4px;border-radius:3px;font-weight:800">−2</span> | Clearly bearish |

- **Method:** FinBERT (`ProsusAI/finbert`), running locally on the mini's CPU at about 0.08 s per headline. Score = P(positive) − P(negative); ≥0.6 → +2, ≥0.2 → +1, ≤−0.2 → −1, ≤−0.6 → −2. If FinBERT cannot load, a finance keyword list is used instead, and the panel header says which method is active.
- **Analyst actions** ("Maintains Overweight … Raises Price Target", "Downgrades …") use a small rule set on top: upgrade/downgrade ±1.5, PT raise/cut ±0.8, rating ±0.6, rounded.
- **Per ticker:** every ticker on an item gets the same score. FinBERT reads the whole headline and does not split it by company.
- Every scored item is logged with its timestamp in `~/oid-desk/state/news/sentiment-YYYYMMDD.jsonl`.

## Tile badge

<span style="font-size:9px;font-weight:800;padding:0 3px;border-radius:3px;border:1px solid #1a7f37;background:#dafbe1;color:#1a7f37">N+3</span> next to the ticker = **60-minute net news sentiment**: the sum of headline scores, plus X posts at half weight.

- **Solid badge:** a headline came out in the last 30 minutes.
- **Dashed and faded:** there is news in the last 60 minutes, but no headline in the last 30.
- **Color:** green when net ≥ +1, red when net ≤ −1, blue otherwise. Hover to see the latest headline; click to filter the panel to that ticker.

## Mover alerts

Each mover alert now carries the latest 1–2 headlines for that ticker from the last 60 minutes, with their sentiment, plus the 60-minute net. With no headline it says `no headline found (60m)`, and adds an X post if one exists.

## Direction score

A `news` input is defined in `~/oid-data/config/score-config.json` and is **off** (`enabled: false`). It is there to test against the logged sentiment later.

## Files

`~/oid-desk/news/` (code) · `~/oid-desk/state/news/latest.json`, `news-YYYYMMDD.jsonl`, `sentiment-YYYYMMDD.jsonl` · log `~/oid-desk/logs/news.log` · page endpoint `/news.json`.
