# 22 · C/P momentum on the 15s / 1m chips (built 10/19 11:42 AM PT)
[← Index](README.md) · user view: [21](21-live-aggressor-chips.md)

**Status:** BUILT and live Mon 10/19/2026 at 11:42 AM PT (optflow v0.3.0 + livepage OPTMOM patch). Originally a spec only. Jeffrey approved writing this spec on Mon 10/19/2026 at 11:31 AM PT.
**Scope:** add a momentum cue to the live aggressor chips (`15s C/P`, `1m C/P`, see [21](21-live-aggressor-chips.md)) so you can see whether call buying or put buying is climbing or fading.
**Builds on:** `mini/optflow/optflow.py` (v0.2.0, `com.oid.desk.optflow`, :8792, writes `optflow.json` every 1 s), `mini/optflow/patch_livepage.py` (the OPTFLOW patch), `mini/live-page/livepage.py` + `index.html`.

---

## TL;DR

| Item | Decision |
|---|---|
| Where history lives | **In optflow memory.** One `deque(maxlen=6)` per underlying per window (15s, 60s), sampled on wall-clock 15 s boundaries (:00/:15/:30/:45). |
| Thin, stale or disconnected reading | A slot is still written, holding `null` plus a reason. Gaps stay time-aligned and are never skipped. |
| Disk | Optional JSONL with one line per boundary for all tickers, RTH only. `~/oid-optflow/data/cp-history/YYYY-MM-DD.jsonl`, roughly 7 MB/day raw. Earlier days are gzipped (~1 MB) and deleted after 365 days. |
| Math | Smoothed **log-ratio** `L = ln((cb+k)/(pb+k))`, clamped to ±ln 10. Momentum = least-squares slope of L over the last 4 slots (45 s span), per minute. Needs ≥3 valid readings **including the latest**. Deadband with hysteresis decides "flat". |
| UI | **Arrow, not sparkline.** One 7-px glyph after the number (`15s C/P 2.3▲`), with the 6-reading history in the tooltip. |
| Arrow color | By **direction**: ▲ green = moving toward calls, ▼ red = moving toward puts, `–` muted grey = flat. No arrow when there aren't enough readings. The chip body keeps its current band color (green ≥1.25, red ≤0.80, amber between, grey thin/stale). |
| Exposure | New `mom` block in `optflow.json`, passed through inside the existing `af15`/`af60` row fields, so **LIGHT_KEYS doesn't change**. Adds about 6–7 KB raw per SSE event across 57 names (~1.5 KB gzipped). Optional `/v1/history?sym=` on :8792. |
| Build | About **3–4 h** including tests and docs, plus a deadband re-tune after 1–2 sessions of JSONL. |
| RTH risk | Low. Restarting optflow greys or hides only the 15s/1m chips for about 30–90 s while it re-selects and re-subscribes. Arrows come back about 45 s after that, and everything else on the page is untouched. Behind a flag (`OID_OPTFLOW_MOMENTUM=0`) with patch-marker rollback. Safe mid-session, but deploy between setups and not while an open seat is near a trigger. |

---

## 1. Where the history lives

### Recommendation: optflow, not livepage
* optflow already has the raw ingredients: call-buy premium `cb`, put-buy premium `pb`, print count `n` and thin flag per window, plus the websocket state and the reselection time. The log-ratio needs `cb`/`pb`, not just the rounded `cp_buy`.
* livepage gets restarted on almost every UI deploy, and each restart would wipe the history. optflow is restarted rarely.
* This also follows the rule that the mini owns data collection and the page only reads.
* *Alternative (livepage-only):* livepage samples `af15`/`af60` from `optflow.json` on 15 s boundaries. This avoids restarting optflow at deploy time, but history is lost on every page deploy and the log-ratio would need `cb_k`/`pb_k`, which livepage already has to 0.1 K. It's acceptable as a fallback if an optflow restart during RTH is unwanted. The UI is identical.

### Data structure (optflow.py)
```python
HIST_N = int(os.environ.get("OID_OPTFLOW_HIST_N", "6"))     # 6 slots = 90 s
SAMPLE_S = 15

class Slot(NamedTuple):
    t: float            # boundary epoch (multiple of 15)
    cp: float|None      # cp_buy as displayed (None when invalid)
    L: float|None       # smoothed, clamped log-ratio (None when invalid)
    cb: int; pb: int    # $ premium in the window (kept for study/debug)
    n: int              # prints in window
    why: str|None       # None = valid; else "thin" | "stale" | "nobuy" | "ws" | "rerank" | "warmup" | "missed"

State.hist: dict[str, dict[str, deque[Slot]]]   # und -> {"15s": deque(maxlen=HIST_N), "60s": deque(...)}
State.last_boundary: float | None
```
Memory: 57 names × 2 windows × 6 slots × ~120 B ≈ **80 KB**. Negligible.

### Sampling
* Run it inside the existing 1 s `writer()` loop, right after `ST.compute()`, so there's no new task and no new lock. Let `b = floor(now / 15) * 15`. If `b > last_boundary`, append one Slot per underlying per window using the summaries `compute()` just produced, then set `last_boundary = b`. Jitter is ≤1 s, which is fine for 15 s slots, and `Slot.t = b` keeps the slots aligned across tickers.
* **Missed boundaries:** if `b - last_boundary > 15` (event-loop stall or laptop-style sleep), append `why="missed"` null slots for each skipped boundary, up to `HIST_N`, so slot spacing always means 15 s.
* **Overlap note:** the 15s window sampled every 15 s gives back-to-back, non-overlapping readings. The 60s window sampled every 15 s overlaps 75% between neighbours, so its slope is naturally smoother and lags by about 30 s. That is intended: the 1m arrow is the "trend" and the 15s arrow is the "now".

### When a reading is invalid (store null, keep the slot)
| Condition at the boundary | `why` |
|---|---|
| `n < THIN_PRINTS` (5) in the window | `thin` |
| no print for this underlying for > 30 s during RTH (same rule as the grey chip) | `stale` |
| `cb + pb == 0` (the chip shows `—`) | `nobuy` |
| websocket not `subscribed_ready`, **or** the window start is before `ws_connected_at` (the window overlaps a reconnect gap) | `ws` |
| window start is before this name's last reselection, *and* contract overlap < 70% (see §6) | `rerank` |
| before 6:30:15 AM PT, or the first slot after a (re)start | `warmup` |

Nulls count toward the 6 slots, so a thin patch ages out naturally. The arrow simply disappears while there are fewer than 3 valid readings.

### Optional on-disk log (for later study and calibration)
* Path `~/oid-optflow/data/cp-history/YYYY-MM-DD.jsonl` (ET trading date). There is **one line per boundary** holding all tickers, which keeps writes to one per 15 s:
  ```json
  {"t":1792431015,"pt":"11:30:15","sel":"11:15:02","u":{"NVDA":{"15":[2.31,0.84,184000,79600,23,null],"60":[1.62,0.48,612000,377000,88,null]},"MU":{"15":[null,null,0,0,2,"thin"],"60":[0.71,-0.34,...]}}}
  ```
  Tuple order: `[cp, L, cb, pb, n, why]`. The computed momentum is **not** logged (it can be recomputed). The deadband used is logged once per file in a header line.
* Size: about 4–5 KB per line × 1,560 RTH boundaries ≈ **7 MB/day**.
* Writes only during RTH (6:30–1:00 PM PT, plus early-close awareness). Append through `run_in_executor` so disk I/O never blocks the websocket. Wrapped in try/except so a log failure never stops the chips.
* **Rotation:** a new file per ET date. On startup and at the first boundary of a new day, gzip any non-today `.jsonl` files and delete `.jsonl.gz` files older than **365 days** (env `OID_OPTFLOW_HIST_KEEP_D`). Steady state is about 250 MB (~252 trading days × ~1 MB gz).
* **Restart warm-start:** on startup, read the last 6 lines of today's file and refill the deques (marking slots older than 90 s as dropped). A mid-session optflow restart then keeps its arrows. This is cheap: about 30 KB read.
* Flag `OID_OPTFLOW_HIST_LOG=1` (default on). Turning it off leaves the in-memory history and the arrows unaffected.

## 2. How it's exposed

### optflow.json / `GET :8792/v1/optflow`
Add a `mom` block per underlying, next to the existing `15s`/`60s`/`day`:
```json
"NVDA": {
  "15s": {...existing...}, "60s": {...existing...}, "day": {...},
  "mom": {
    "15s": {"d": 1, "s": 0.62, "nv": 4, "h": [1.1, null, 1.4, 1.9, 2.0, 2.31]},
    "60s": {"d": 0, "s": 0.08, "nv": 6, "h": [1.5, 1.55, 1.58, 1.6, 1.61, 1.62]}
  }
}
```
* `d`: −1 / 0 / +1, or `null` when there are too few readings. `s`: slope in log-units per minute, 2 dp. `nv`: valid slots out of the last 4. `h`: displayed `cp` for the 6 slots, oldest first, `null` for invalid slots. The 99 value (∞) is sent as 99, as today.
* Snapshot `version` goes to `0.3.0`, and the `method` string gets a momentum sentence.
* Optional new endpoint `GET :8792/v1/history?sym=NVDA` returns the full Slot deques, including `cb`/`pb`/`n`/`why`, for debugging. It is loopback only, same as the others.

### livepage.py (via `patch_livepage.py`, new marker `OPTMOM`)
* In `_c(w)`, also copy `a["mom"][w]` into the chip dict as `d`, `s`, `h`. `af15`/`af60` are already in `LIGHT_KEYS` and nest as dicts, so **LIGHT_KEYS needs no change** and light events carry the arrow automatically.
* If `mom` is missing (older optflow, or flag off), the fields are absent and the UI shows no arrow. That gives backward compatibility in both directions, so the two pieces can be deployed in either order.

### Payload size (57 optionable names)
| Piece | Bytes |
|---|---|
| `d` + `s` + `nv` per window | ~30 |
| `h` (6 values) per window | ~35–45 |
| × 2 windows × 57 names | **≈ 6–7 KB raw per SSE event** |
| gzipped / Tailscale-compressed | ~1.5 KB |

Events are sent at 1 Hz. If that's too heavy, `h` can go in full events only (it changes only every 15 s) while `d`/`s` ride in light events. The UI doesn't need `h` except in the tooltip.

## 3. Momentum math

### Why a log-ratio
The ratio is asymmetric: 0.5→1.0 is the same swing as 1.0→2.0, but the raw difference says +0.5 vs +1.0. On a log scale both are ±0.69. A raw ratio also explodes to ∞ when there are no put buys. So the math works on:

```
k  = max(2_000, 0.05 * (cb + pb))          # $ pseudo-premium: smooths tiny windows, kills inf
L  = clamp( ln((cb + k) / (pb + k)), -ln(10), +ln(10) )   # ±2.30 ≈ ratio 0.1 … 10
```
* `k` scales with the window, so a $2M SPY window barely moves while a $3K thin-name window is pulled toward 1.0. That's exactly the skepticism thin windows deserve.
* Band thresholds in log space: 1.25 → +0.223, 0.80 → −0.223. They're symmetric, which is a nice property of the existing bands.

### Slope
Use the last **4** slots (t−45 s … t). Over the valid ones, compute an ordinary least-squares slope of `L` vs time, ×60, giving **log-units per minute**.
* Require **≥3 valid slots, and the latest slot must be valid**. Otherwise `d = null`, meaning no arrow. An arrow must never point based on data that has since gone thin.
* Why OLS over 4 rather than "latest vs mean of prior N": on non-overlapping 15 s windows a single noisy reading dominates latest-vs-mean. OLS on 3–4 points is equally cheap and less jumpy. *Latest-vs-mean-of-prior-3* is the documented fallback (one line to switch) if the slope turns out too sluggish in the JSONL replay.
* Slots 5–6 (older) are for the tooltip history and the warm-start, not for the arrow.

### Deadband ("flat") with hysteresis
| Window | Enter ▲/▼ when \|s\| ≥ | Drop back to flat when \|s\| < |
|---|---|---|
| 15s | 0.35 /min (≈ ratio ×1.4 per minute) | 0.20 |
| 1m | 0.20 /min (≈ ratio ×1.22 per minute) | 0.10 |

* Hysteresis keeps the arrow from flickering between ▲ and – every second. It's kept as per-ticker state (`last_d`) in optflow.
* A direction flip (▲→▼) must pass through the enter threshold on the other side. There's no direct flip on a tiny move.
* These are starting values from reasoning, not data. They're all env-tunable (`OID_OPTFLOW_DB15_IN/OUT`, `OID_OPTFLOW_DB60_IN/OUT`). **Calibration:** after 1–2 sessions of JSONL, pick the thresholds so ▲/▼ shows about 25–35% of the time on liquid names (SPY/QQQ/NVDA/TSLA) and the rest is flat.
* Optional later "steep" cue: |s| ≥ 2× enter shows a bolder arrow. It's left out of v1 to keep the chip quiet.

## 4. UI: arrow vs sparkline

**Recommendation: the arrow on the chip, and the history in the tooltip.**

| | Arrow `▲ ▼ –` | 3-bar sparkline |
|---|---|---|
| Width at 9 px chip font | ~7 px (one glyph) | ~12–14 px (3 bars × 3 px + gaps + padding) |
| Fits a ~106 px landscape tile | Yes. The chip row already holds 15s, 1m, day C/P, 15m and 5m chips and wraps on narrow tiles; one glyph per chip adds at most a few px. | Two sparklines add ~28 px and push one more chip to a second row on most tiles, adding tile height for every name. |
| Readable at a glance across 57 tiles | Yes: up/down/flat is a single shape the eye pre-attentively picks out. | Three 22-px-tall bars at chip height (≈11 px) are 3–4 px tall each, and the differences are hard to read from across the desk. |
| Says "how much / how steady" | No, so the tooltip carries it. | A little, but with only 3 points it's still mostly direction. |
| Handles null slots | Just absent or grey. | Needs a gap glyph, which adds clutter. |

**Chip format (v1):** `15s C/P 2.3▲`<sup>98%</sup>, with the glyph between the number and the coverage %. The glyph is 8 px, and flat shows a muted `–` so the chip width stays stable instead of jumping as arrows come and go. Fewer than 3 valid readings shows nothing.

**Tooltip (title) addition:** `momentum: ▲ rising toward calls (+0.62/min) · last 90s: 1.1 · — · 1.4 · 1.9 · 2.0 · 2.3`, with `—` marking thin or stale slots.

A sparkline can still go where there is room. The ladder card (`.lc`, 300 px wide) or a future tile-expand view could show the full 6-slot sparkline with each bar colored by its band. That's optional and not in the v1 estimate.

## 5. Colors (consistent with existing bands)
* **Chip body:** unchanged. Green ≥1.25, red ≤0.80, amber between, grey/dim when thin or stale (`.chip.dim`, opacity .4).
* **Arrow:** colored by **direction**, independent of the band:
  * ▲ `var(--green)` #1a7f37 means the ratio is rising, toward call buying.
  * ▼ `var(--red)` #cf222e means the ratio is falling, toward put buying.
  * `–` `var(--mut)` #59636e means flat.
  * No arrow means fewer than 3 valid readings or a thin/stale latest reading. When the chip is dim, the arrow is always hidden, so there's no colored arrow on a grey chip.
* Reading the combos aloud: a green chip with ▲ is call buying still building. A green chip with ▼ is calls still leading but fading. A red chip with ▲ is put buying easing off. A red chip with ▼ is put buying accelerating. An amber chip with an arrow means it's leaving balance in that direction.
* If a sparkline is added later (ladder card): each bar is colored by **its own reading's band** (green/red/amber), thin/stale slots are a light grey stub `#d0d7de`, and the height is |L| on a fixed ±ln 10 scale so tiles compare.
* CSS: `.tile .chip .mo{font-size:8px;margin-left:1px}.mo.u{color:var(--green)}.mo.d{color:var(--red)}.mo.f{color:var(--mut)}`.
* Legend line gets: `▲/▼ = 15s-slot trend of that C/P over ~45s (green toward calls, red toward puts, – flat)`.

## 6. Edge cases
| Case | Handling |
|---|---|
| **Market open (6:30 AM PT)** | Before then there are no option prints in our set (no SPX/GTH contracts), so the slots are `warmup` or `nobuy`. The first valid 15s slot is ~6:30:15, so the earliest arrow is ~6:31:00 (3 valid slots). The 1m window isn't full until 6:31:30 and its arrow appears ~6:32. The opening rotation is noisy, so the deadband is enough and no extra suppression is planned. Re-check this in the JSONL. |
| **Day rollover / pre-market** | Clear `hist` and `last_d` when `day_date` changes (same place `day.clear()` already runs). |
| **Websocket reconnect** | Slots whose window overlaps the disconnected period become `ws` nulls. The 15s window recovers after one slot and the 1m after four, so the arrow returns about 45 s after the 3rd clean slot. No fake momentum comes from a half-empty window after reconnect. |
| **optflow process restart** | Warm-start from today's JSONL (§1). Without the log, arrows return about 45 s after the stream is subscribed again. |
| **livepage restart** | No effect on history, which lives in optflow. The page re-reads on its next 1 s tick. |
| **Contract re-rank every 15 min** | Most top-premium contracts survive a re-rank, so the ratio is continuous. For each name, compute `overlap = |old ∩ new| / |old|`. If it's ≥70%, keep the history. If it's below, mark the slots whose window starts before the re-rank as `rerank` (excluded from the slope), and add `· contracts re-ranked` to the tooltip. This stops a coverage jump from showing up as fake call/put momentum. |
| **Ratio ∞ (zero put buys) / 0 (zero call buys)** | The display keeps today's `∞`/0.0. The math uses smoothed, clamped L, so there's no infinity. A run of `∞` readings gives L near +2.3 and slope ≈ 0, which shows flat. That's correct: calls dominating steadily isn't momentum. |
| **No buys at all (`—`)** | `nobuy` null. |
| **Thin names** (25–60% coverage, often <5 prints/15 s) | The 15s arrow will mostly be absent on these names. That is by design. The 1m arrow will show more often. A quiet 15s arrow on thin names isn't a bug. |
| **Underlying halt / LULD** | No prints means `stale` nulls and the arrow disappears. |
| **optflow.json > 10 s old** | Chips and arrows are hidden, as today. |
| **Clock/loop stall** | `missed` slots (§1) keep the spacing honest. |
| **Early-close days** | The RTH flag already comes from the collector session. The JSONL stops when RTH ends. |

## 7. Build time & live-RTH risk

| Step | Est. |
|---|---|
| optflow: Slot/hist, boundary sampler, L + OLS + hysteresis, `mom` in snapshot, `/v1/history`, flags | 1.25 h |
| optflow: JSONL writer + rotation/gzip/365-day trim + warm-start | 0.75 h |
| `patch_livepage.py` `OPTMOM` block: `_c()` passthrough, arrow glyph + CSS + tooltip + legend | 0.75 h |
| Tests on the box: unit tests for the L/slope/deadband/hysteresis/null rules on synthetic series; replay one session of `/v1/recent` prints or a captured optflow.json series; payload size check | 0.75 h |
| Doc update (21 → add momentum section, glossary) and deploy with backups | 0.5 h |
| **Total** | **≈ 3–4 h** (+ ~30 min deadband re-tune after 1–2 sessions of JSONL) |

**Can it go in mid-session?** Yes, with care:
* **livepage restart:** a few seconds of SSE reconnect. Same as the many UI deploys already done today.
* **optflow restart:** only the 15s/1m chips are affected. At startup, contract selection runs over REST before the subscribe; the estimate (not measured) is about **30–90 s** of grey or hidden chips. Arrows then take about 45 s, or come back immediately with the warm-start, which can't apply on the very first deploy. The main collector (:8787), its websocket, stock tiles, held-option marks, the day C/P and the UW chips are all **untouched**, and nothing places orders.
* **Order:** deploy optflow first (old livepage ignores `mom`), check that `/v1/optflow` shows `mom` and that the JSONL is appending, then deploy livepage. Each half is backward compatible.
* **Kill switch:** `OID_OPTFLOW_MOMENTUM=0` (no `mom` block, no arrows) or `OID_OPTFLOW_HIST_LOG=0` (no disk). Rollback is restoring the `.bak` copies, as with the OPTFLOW patch.
* **Timing:** avoid the 6:30–6:45 AM PT open and any moment an open seat is near a trigger. Mid-morning or lunch is ideal. CPU cost is trivial: 57×2 slope fits every 15 s plus one 5 KB append.
