# Hal FlashAlpha reader notes

As of 2026-10-05. Research / paper only.

## Role
Hal is a **reader** of Rose-owned FlashAlpha wall files, not a second walls writer.

| Feed | Writer | Hal role |
|------|--------|----------|
| `fa-levels` | Rose (walls pulse + Q5 gated) | Read via `cache_io.read_fresh`; label FRESH vs STALE |
| `fa-flow-levels` | Rose (occasional / gated) | Soft color only; often sparse (e.g. NVDA one-off) |
| Shared FA daily hard limit | Desk-wide | Any Hal `get_levels` / option-quote burn logs on the shared pool |

## Rules
- Prefer FRESH levels (TTL ~600s / 10 min RTH). STALE = soft color only — never invent walls (`WALLS_DATA_INSUFFICIENT` if missing).
- Elevate / invalidate still needs **live RH ≤120s** option + equity quotes. Do not serve elevate gates from FA or `rh-quotes` cache.
- Minimize burns while flat: soft watches and Soft A screens may refresh one name's levels when needed; do not poll the whole Tech∪chip universe on FA.
- Path B LEAP / thru-CW seats need live thru CW on fresh map + second gate clearance.

## Not Hal's job
Primary FA walls writer, UW flow-alerts writer, Form-4 / EDGAR collectors (Rose / Peanut).
