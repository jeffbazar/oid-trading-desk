#!/usr/bin/env python3
"""Build paper-trades/scorecard.json + SCORECARD.md from trades.json."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from outcome_helper import ensure_outcome_fields, format_pt, entry_ref

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "trades.json"
OUT_JSON = ROOT / "scorecard.json"
OUT_MD = ROOT / "SCORECARD.md"

CLOSED_STATUSES = {"closed", "stopped", "expired", "invalidated"}
OPEN_STATUSES = {"open", "watching", "paper", "live"}


def realized_usd(t):
    """Realized P&L of a closed ticket: pnlUsd, falling back to realizedPnlUsd."""
    for k in ("pnlUsd", "realizedPnlUsd"):
        v = t.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def pnl_result(t) -> str:
    """Win/loss rule (Jeffrey 2026-10-09): sign of realized P&L. >0 win, <0 loss,
    0 (or no realized number) = scratch, excluded from the win rate. Ledger tags are ignored."""
    v = realized_usd(t)
    if v is None or v == 0:
        return "scratch"
    return "win" if v > 0 else "loss"


def catalyst_bucket(soft) -> str:
    if isinstance(soft, (list, tuple)):
        soft = " ".join(str(x) for x in soft if x)
    s = (soft or "unknown").lower()
    if "fomc" in s:
        return "FOMC / Fed calendar"
    if "ex-div" in s or "exdiv" in s:
        return "ex-div / calendar"
    if "wall" in s or "thesis" in s:
        return "wall+thesis"
    if "flow" in s or "uw" in s:
        return "UW flow"
    return soft or "unknown"


def main():
    ledger = json.loads(LEDGER.read_text())
    trades = ledger.get("trades", [])
    for t in trades:
        ensure_outcome_fields(t)

    closed = [t for t in trades if (t.get("status") or "").lower() in CLOSED_STATUSES]
    open_t = [t for t in trades if (t.get("status") or "").lower() in OPEN_STATUSES]

    wins = [t for t in closed if pnl_result(t) == "win"]
    losses = [t for t in closed if pnl_result(t) == "loss"]
    scratches = [t for t in closed if pnl_result(t) == "scratch"]
    decided = len(wins) + len(losses)
    win_rate = (len(wins) / decided * 100.0) if decided else None

    def avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    win_pcts = [float(t["pnlPct"]) for t in wins if isinstance(t.get("pnlPct"), (int, float))]
    loss_pcts = [float(t["pnlPct"]) for t in losses if isinstance(t.get("pnlPct"), (int, float))]
    closed_usd = [float(t["pnlUsd"]) for t in closed if isinstance(t.get("pnlUsd"), (int, float))]
    expectancy = avg(closed_usd)

    open_unreal_usd = sum(
        float(t.get("unrealizedPnlUsd") or t.get("pnlUsd") or 0)
        for t in open_t
        if isinstance(t.get("unrealizedPnlUsd") or t.get("pnlUsd"), (int, float))
        or True
    )
    # recompute cleanly
    open_unreal_usd = 0.0
    open_unreal_pct_w = []
    for t in open_t:
        u = t.get("unrealizedPnlUsd")
        if u is None:
            u = t.get("pnlUsd")
        if isinstance(u, (int, float)):
            open_unreal_usd += float(u)
        p = t.get("unrealizedPnlPct")
        if p is None:
            p = t.get("pnlPct")
        if isinstance(p, (int, float)):
            open_unreal_pct_w.append(float(p))

    by_cat = defaultdict(lambda: {"n": 0, "wins": 0, "pnlUsdSum": 0.0, "tickets": []})
    by_sym = defaultdict(lambda: {"n": 0, "wins": 0, "open": 0, "pnlUsdSum": 0.0, "tickets": []})

    for t in trades:
        cat = catalyst_bucket(t.get("softCatalyst"))
        sym = t.get("symbol") or "?"
        by_cat[cat]["n"] += 1
        by_cat[cat]["tickets"].append(t["id"])
        by_sym[sym]["n"] += 1
        by_sym[sym]["tickets"].append(t["id"])
        status = (t.get("status") or "").lower()
        usd = t.get("pnlUsd")
        if status in CLOSED_STATUSES and isinstance(usd, (int, float)):
            by_cat[cat]["pnlUsdSum"] += float(usd)
            by_sym[sym]["pnlUsdSum"] += float(usd)
            if pnl_result(t) == "win":
                by_cat[cat]["wins"] += 1
                by_sym[sym]["wins"] += 1
        if status in OPEN_STATUSES:
            by_sym[sym]["open"] += 1
            if isinstance(t.get("unrealizedPnlUsd"), (int, float)):
                by_sym[sym]["pnlUsdSum"] += float(t["unrealizedPnlUsd"])

    lessons = []
    for t in trades:
        if t.get("lesson"):
            lessons.append({
                "id": t["id"],
                "symbol": t.get("symbol"),
                "outcomeTag": t.get("outcomeTag"),
                "lesson": t["lesson"],
                "refineHint": t.get("refineHint") or "",
            })

    # Refine rules derived from losses
    refine_rules = []
    for t in losses:
        hint = (t.get("refineHint") or "").strip()
        if hint:
            refine_rules.append({
                "fromTicket": t["id"],
                "symbol": t.get("symbol"),
                "outcomeTag": t.get("outcomeTag"),
                "rule": hint,
            })
    # Deduplicate near-identical
    seen = set()
    uniq_rules = []
    for r in refine_rules:
        key = r["rule"][:80]
        if key not in seen:
            seen.add(key)
            uniq_rules.append(r)

    live = open_t[0] if open_t else None
    live_mfe = None
    if live:
        live_mfe = {
            "id": live["id"],
            "symbol": live.get("symbol"),
            "contract": live.get("contract"),
            "entryAsk": live.get("entryAsk"),
            "lastMark": live.get("lastMark"),
            "peakMark": live.get("peakMark"),
            "troughMark": live.get("troughMark"),
            "mfePct": live.get("mfePct"),
            "maePct": live.get("maePct"),
            "mfeUsd": live.get("mfeUsd"),
            "maeUsd": live.get("maeUsd"),
            "unrealizedPnlPct": live.get("unrealizedPnlPct", live.get("pnlPct")),
            "unrealizedPnlUsd": live.get("unrealizedPnlUsd", live.get("pnlUsd")),
            "holdHours": live.get("holdHours"),
            "outcomeTag": live.get("outcomeTag"),
        }

    scorecard = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "updatedAtPT": format_pt(),
        "mandate": ledger.get("mandate", "V1.8"),
        "disclaimer": "Research / paper tracking only. Zero live execution from OID.",
        "summary": {
            "ticketsTotal": len(trades),
            "closedN": len(closed),
            "openN": len(open_t),
            "winsN": len(wins),
            "lossesN": len(losses),
            "scratchN": len(scratches),
            "winRule": "realized P&L sign: >0 win, <0 loss, 0 scratch (excluded from win rate)",
            "closedWinRatePct": round(win_rate, 1) if win_rate is not None else None,
            "avgWinPct": avg(win_pcts),
            "avgLossPct": avg(loss_pcts),
            "expectancyUsdPerTicket": expectancy,
            "closedPnlUsdSum": round(sum(closed_usd), 2) if closed_usd else 0.0,
            "openUnrealizedUsd": round(open_unreal_usd, 2),
            "openUnrealizedPctSample": open_unreal_pct_w,
        },
        "byCatalyst": {
            k: {
                "n": v["n"],
                "wins": v["wins"],
                "pnlUsdSum": round(v["pnlUsdSum"], 2),
                "tickets": v["tickets"],
            }
            for k, v in sorted(by_cat.items())
        },
        "bySymbol": {
            k: {
                "n": v["n"],
                "wins": v["wins"],
                "open": v["open"],
                "pnlUsdSum": round(v["pnlUsdSum"], 2),
                "tickets": v["tickets"],
            }
            for k, v in sorted(by_sym.items())
        },
        "liveTicket": live_mfe,
        "lessons": lessons,
        "refineRulesFromLosses": uniq_rules,
        "tickets": [
            {
                "id": t["id"],
                "symbol": t.get("symbol"),
                "contract": t.get("contract"),
                "status": t.get("status"),
                "result": t.get("result"),
                "outcomeTag": t.get("outcomeTag"),
                "pnlPct": t.get("pnlPct"),
                "pnlUsd": t.get("pnlUsd"),
                "mfePct": t.get("mfePct"),
                "maePct": t.get("maePct"),
                "holdHours": t.get("holdHours"),
                "softCatalyst": t.get("softCatalyst"),
                "mfeMaePartial": t.get("mfeMaePartial"),
            }
            for t in trades
        ],
    }

    OUT_JSON.write_text(json.dumps(scorecard, indent=2) + "\n")

    s = scorecard["summary"]
    wr = f"{s['closedWinRatePct']}%" if s["closedWinRatePct"] is not None else "n/a"
    lines = [
        f"# OID Paper Scorecard",
        f"",
        f"Updated **{scorecard['updatedAtPT']}** · Mandate {scorecard['mandate']} · Research only",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Closed win rate | **{wr}** ({s['winsN']}W/{s['lossesN']}L, {s['scratchN']} scratch; by realized P&L sign) |",
        f"| Avg win % | {s['avgWinPct'] if s['avgWinPct'] is not None else '—'} |",
        f"| Avg loss % | {s['avgLossPct'] if s['avgLossPct'] is not None else '—'} |",
        f"| Expectancy $/ticket (closed) | **${s['expectancyUsdPerTicket']}** |" if s["expectancyUsdPerTicket"] is not None else "| Expectancy $/ticket (closed) | — |",
        f"| Closed P&L sum | ${s['closedPnlUsdSum']} |",
        f"| Open unrealized | **${s['openUnrealizedUsd']}** ({s['openN']} ticket) |",
        f"| Tickets total | {s['ticketsTotal']} |",
        f"",
    ]
    if live_mfe:
        lines += [
            f"## Live ticket MFE/MAE",
            f"",
            f"**{live_mfe['id']}** · {live_mfe.get('contract')}",
            f"",
            f"| | |",
            f"|--|--|",
            f"| Entry ask | ${live_mfe.get('entryAsk')} |",
            f"| Last mark | ${live_mfe.get('lastMark')} |",
            f"| Peak (MFE) | ${live_mfe.get('peakMark')} · **{live_mfe.get('mfePct')}%** / ${live_mfe.get('mfeUsd')} |",
            f"| Trough (MAE) | ${live_mfe.get('troughMark')} · **{live_mfe.get('maePct')}%** / ${live_mfe.get('maeUsd')} |",
            f"| Unrealized | {live_mfe.get('unrealizedPnlPct')}% / ${live_mfe.get('unrealizedPnlUsd')} |",
            f"| Hold hours | {live_mfe.get('holdHours')} |",
            f"| Tag | `{live_mfe.get('outcomeTag')}` |",
            f"",
        ]

    lines += [f"## By catalyst", f""]
    for k, v in scorecard["byCatalyst"].items():
        lines.append(f"- **{k}**: n={v['n']}, closed-wins={v['wins']}, pnlUsdSum=${v['pnlUsdSum']}")
    lines += [f"", f"## By symbol", f""]
    for k, v in scorecard["bySymbol"].items():
        lines.append(
            f"- **{k}**: n={v['n']}, wins={v['wins']}, open={v['open']}, pnlUsdSum=${v['pnlUsdSum']}"
        )

    lines += [f"", f"## Top lessons", f""]
    for L in lessons:
        lines.append(f"- **{L['id']}** (`{L.get('outcomeTag')}`): {L['lesson']}")
        if L.get("refineHint"):
            lines.append(f"  - Refine: {L['refineHint']}")

    lines += [f"", f"## Current refine rules (from losses)", f""]
    if uniq_rules:
        for i, r in enumerate(uniq_rules, 1):
            lines.append(f"{i}. ({r['fromTicket']} / {r.get('symbol')}) {r['rule']}")
    else:
        lines.append("_No closed losses with refine hints yet._")

    lines += [
        f"",
        f"## Ticket blotter",
        f"",
        f"| ID | Sym | Status | Tag | P&L% | MFE% | MAE% | Hold h |",
        f"|----|-----|--------|-----|------|------|------|--------|",
    ]
    for t in scorecard["tickets"]:
        lines.append(
            f"| {t['id']} | {t.get('symbol')} | {t.get('status')} | `{t.get('outcomeTag')}` | "
            f"{t.get('pnlPct')} | {t.get('mfePct')} | {t.get('maePct')} | {t.get('holdHours')} |"
        )
    lines += [f"", f"_{scorecard['disclaimer']}_", f""]

    OUT_MD.write_text("\n".join(lines))
    print("wrote", OUT_JSON)
    print("wrote", OUT_MD)
    print(
        f"TLDR win_rate={wr} expectancy=${s['expectancyUsdPerTicket']} "
        f"open_unreal=${s['openUnrealizedUsd']}"
    )


if __name__ == "__main__":
    main()
