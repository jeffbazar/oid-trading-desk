# 12 · Sort dropdown (heatmap)
[← Index](README.md)

Sits at the top-left of the heatmap. Your choice is remembered on that device.

| Option | Orders tiles by | Use it to |
|---|---|---|
| **Name (A→Z)** *(default)* | Ticker | Keep tiles from jumping around. Good for a glance. |
| **Volume heat (1-min rvol)** | rvol, highest first | See what's busiest **right now** |
| **Day rvol** | Day volume vs 20-day norm | See which names have been in play all day |
| **% change** | Biggest gainers first | Leaders and laggards |
| **Last price** | Highest price first | Rarely needed |
| **Surges first** | Hot (pulsing) names first, then A→Z | Busy-tape days |

Names with no data sort to the end. Ties fall back to A→Z.

**No auto-float.** Tiles only move when *you* pick a sort. Nothing reorders itself when a name gets hot: a surge shows up as the pulsing border, the surge strip and the flow lean strip, not by jumping the tile to the top. Pick **Volume heat** or **Surges first** if you want the busy names first; with the default **Name** sort, positions never change.

Sector-name tiles (the 16 sector sections) follow the same dropdown; names with no live value (e.g. 1-min rvol after hours) fall to the end of their section.

With **Group by sector** on (default), the sort applies **inside each group**; groups themselves stay in a fixed order and tiles never change group. See [Sector groups](19-sectors.md).
