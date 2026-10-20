# FA walls fetch — Growth operating notes

Agents should pull walls via MCP (**prefer `user-flashalpha-keyed`**). There is no curl key in workspace scripts — keep the key only under agent secrets.

## Preferred call order (Growth, remaining > 0)

1. **Hard gates:** `get_levels` (settled OI walls/flip) — always for mandate table.
2. **Live RTH upgrade:** `get_flow_levels` — live call/put wall, gamma flip, max pain (simulation-aware). Prefer for intraday pulses when quota allows.
3. **Soft context (optional, do not gate elevate alone):**
   - `get_exposure_summary` — net GEX/DEX/VEX/CHEX, regime, hedging estimates
   - `get_dex` / `get_vex` / `get_chex` — greek exposure by strike
   - `get_oi_diff` — day-over-day OI deltas
   - `get_expected_move` — straddle-implied move
   - `post_screener` — cross-sectional (Growth top-10)

## Quota discipline (Growth = 2500/day)

- Full-universe walls tables on FH / Open / PM / Close / Walls Pulse: FRESH refresh is the default.
- Q5 (5-min): still throttle — refresh on :00/:15/:30/:45, near-wall, or ≥1% move — but **prefer FRESH**, not STALE-by-default.
- STALE carry **only** when `remaining ≈ 0`. Never invent walls. Never print API key.

## Snapshot path

Save under `/workspace/options-intelligence-desk/tmp/fa-walls-YYYYMMDD-<pass>.json` with `as_of`, per-symbol levels, and `freshness: FRESH|STALE`.
