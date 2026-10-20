# Glossary
[← Index](README.md)

| Term | Plain meaning |
|---|---|
| **rvol** | Relative volume: volume now ÷ the normal amount for this minute of the day (20-session average) |
| **Day rvol / Day vs norm** | Volume so far today ÷ the normal amount by this time of day |
| **10s pace** | Last 10 s of volume, scaled to a minute, ÷ normal. An early warning. |
| **Hot / pulsing** | rvol ≥ 3× or a vol_surge in the last 5 min |
| **vol_surge** | Trigger-engine event: rvol ≥ 3× **and** a price-level break within 60 s |
| **VS tag** | That ticker had a vol_surge in the last 5 min |
| **dry run / test** | Logged only. Nothing armed. |
| **C/P** | Today's call contracts ÷ put contracts |
| **15m lean** | Net call premium − net put premium over the last 15 min. ±$50K deadband = FLAT. |
| **5m lean** | Change in UW day net (call − put premium) between the newest snapshot and one ~5 min older. ±$25K = FLAT; "—" when stale (>10 min) or missing. |
| **Sector group** | Fixed bucket from `sectors.json` (Semis, Neoclouds, …) used for section headers and the sector strip. |
| **ask lean** | Calls vs puts by premium paid at the ask (aggressive buyers) |
| **Tide** | Market-wide net call − put premium (Unusual Whales) |
| **Wall (ladder)** | Unusually large resting order in the Robinhood book (≥3× typical size, ≥500 shares) |
| **Call wall / put wall** | FlashAlpha: the strike with the biggest dealer call (put) gamma. Tends to cap (floor) price or pin it. Green (red) dot on the tile edge. |
| **Gamma flip** | FlashAlpha: the price where dealer gamma changes sign. Amber dot; hollow when FlashAlpha flags it low-confidence. |
| **OI (open interest)** | Contracts still open at a strike (from the previous close); part of the edge-mark weight |
| **Edge-mark weight** | OI + today's option volume at the level's strike (expiries ≤ 45 days), scaled within the ticker |
| **15s / 1m C/P** | Live OPRA aggressor call-buy premium ÷ put-buy premium over the last 15 s / 60 s |
| **Aggressor** | The side that crossed the spread: a print at or above the ask is a buy, at or below the bid is a sell |
| **Source tile** | VIX, IWM, WTI, Brent: tiles fed from desk files, not the SIP stream (no bars or chips) |
| **CLOSED / STALE** | Source tiles: CLOSED = that market is shut (CME break or weekend); STALE = open but the value is too old |
| **Thin** | Few shares resting on the side price is moving into (ratio ≤ 0.6) |
| **mfe / mae** | Max favorable / max adverse excursion: best and worst move after entry |
| **SIP** | The consolidated US stock tape (all exchanges) |
| **OPRA** | The consolidated US options tape |
| **core-20 + focus** | The desk's main ticker list, the only names that get Unusual Whales chips (the live 15s/1m chips cover all 57 optionable names) |
| **Soft** | Context only. Never a trade trigger by itself. |
