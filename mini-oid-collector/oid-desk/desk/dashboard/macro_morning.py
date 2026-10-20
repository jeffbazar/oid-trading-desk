#!/usr/bin/env python3
"""OID Morning Daily Macro + Macro Tech soft-status builder (research / paper only).

Writes market-data/latest/macro-morning.json (TTL ~6h).

Modes:
  1) Ingest Macro Bot morning JSON (--ingest / auto-detect tmp/macro-morning*.json)
  2) Compute scores from live tape + fidelity + macro-spot (VIX/SPY/QQQ/HY/WTI fut)
     and attach 1–3 news drivers from newest tmp/macro-soft-*.json (+ Hormuz etc.)

Tone map (both cards): +2/+1 → soft-calm · 0 → soft-neutral · −1 → soft-warm · −2 → soft-stress
Scores clamped −2..+2. Soft color only — never a trade signal / never elevates alone.
Never places Robinhood orders.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OID = ROOT.parent
TMP = OID / "tmp"
LATEST = OID / "market-data" / "latest"
PT = ZoneInfo("America/Los_Angeles")

TTL_SECONDS = 21600  # ~6h

sys.path.insert(0, str(OID / "market-data"))
from cache_io import write_feed, format_as_of_pt  # noqa: E402


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_of_pt(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = _now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PT).strftime("%Y-%m-%d %-I:%M %p PT")


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_json(path: Optional[Path]) -> Any:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _payload(rec: Any) -> Any:
    if not isinstance(rec, dict):
        return rec
    p = rec.get("payload")
    return p if isinstance(p, dict) else rec


def _tone_from_score(score: int) -> str:
    if score >= 1:
        return "calm"
    if score <= -2:
        return "stress"
    if score == -1:
        return "warm"
    return "neutral"


def _tone_class(tone: str) -> str:
    t = (tone or "neutral").lower().replace("soft-", "")
    if t in ("calm", "warm", "stress", "neutral"):
        return f"soft-{t}"
    return "soft-neutral"


def _label_from_score(score: int, *, kind: str) -> str:
    if kind == "daily_macro":
        return {
            2: "risk-on / calm",
            1: "mild risk-on",
            0: "balanced / contested",
            -1: "mild risk-off",
            -2: "risk-off / stress",
        }.get(score, "balanced / contested")
    return {
        2: "tech leadership / calm",
        1: "mild tech bid",
        0: "tech in-line",
        -1: "mild risk-off / higher vol",
        -2: "tech stress",
    }.get(score, "tech in-line")


def _clamp_score(x: float) -> int:
    return int(max(-2, min(2, round(x))))


def _index_day(tape: dict, sym: str) -> Optional[float]:
    for row in tape.get("indices") or []:
        if str(row.get("symbol") or "").upper() == sym.upper():
            return _f(row.get("day_pct"))
    return None


def _macro_cell_day(macro: dict, cid: str) -> Optional[float]:
    bid = macro.get("by_id") if isinstance(macro.get("by_id"), dict) else {}
    cell = bid.get(cid) if isinstance(bid, dict) else None
    if not isinstance(cell, dict):
        for it in macro.get("items") or []:
            if isinstance(it, dict) and it.get("id") == cid:
                cell = it
                break
    if not isinstance(cell, dict):
        return None
    return _f(cell.get("day_pct"))


def _hy_quartile(fid: dict) -> Optional[int]:
    cr = fid.get("credit_spreads") or {}
    hy = cr.get("hy_oas") or {}
    q = hy.get("quartile")
    try:
        return int(q) if q is not None else None
    except (TypeError, ValueError):
        return None


def compute_daily_macro_score(
    *,
    vix_day_pct: Optional[float],
    spy_day_pct: Optional[float],
    hy_quartile: Optional[int],
    wti_fut_day_pct: Optional[float],
) -> tuple[int, list[str]]:
    """Daily Macro score (soft). Documented in MARKET-TAPE.md."""
    score = 0.0
    reasons: list[str] = []
    if vix_day_pct is not None:
        if vix_day_pct >= 5.0:
            score -= 1
            reasons.append(f"VIX day {vix_day_pct:+.2f}% ≥ +5% → −1")
        elif vix_day_pct <= -5.0:
            score += 1
            reasons.append(f"VIX day {vix_day_pct:+.2f}% ≤ −5% → +1")
    if spy_day_pct is not None:
        if spy_day_pct <= -0.75:
            score -= 1
            reasons.append(f"SPY day {spy_day_pct:+.2f}% ≤ −0.75% → −1")
        elif spy_day_pct >= 0.75:
            score += 1
            reasons.append(f"SPY day {spy_day_pct:+.2f}% ≥ +0.75% → +1")
    if hy_quartile == 4:
        score -= 1
        reasons.append("HY OAS Q4 → −1")
    elif hy_quartile == 1:
        reasons.append("HY OAS Q1 → +0 (no add)")
    if wti_fut_day_pct is not None:
        if wti_fut_day_pct >= 3.0:
            score -= 1
            reasons.append(f"WTI fut day {wti_fut_day_pct:+.2f}% ≥ +3% (geo oil spike) → −1")
        elif wti_fut_day_pct <= -3.0:
            reasons.append(f"WTI fut day {wti_fut_day_pct:+.2f}% ≤ −3% → +0")
    return _clamp_score(score), reasons


def compute_macro_tech_score(
    *,
    qqq_day_pct: Optional[float],
    spy_day_pct: Optional[float],
    vix_day_pct: Optional[float],
) -> tuple[int, list[str]]:
    """Macro Tech score (soft). Documented in MARKET-TAPE.md."""
    score = 0.0
    reasons: list[str] = []
    if qqq_day_pct is not None and spy_day_pct is not None:
        spread = qqq_day_pct - spy_day_pct
        if spread <= -0.3:
            score -= 1
            reasons.append(f"QQQ−SPY {spread:+.2f}pp ≤ −0.3pp → −1")
        elif spread >= 0.3:
            score += 1
            reasons.append(f"QQQ−SPY {spread:+.2f}pp ≥ +0.3pp → +1")
    if qqq_day_pct is not None:
        if qqq_day_pct <= -1.0:
            score -= 1
            reasons.append(f"QQQ day {qqq_day_pct:+.2f}% ≤ −1% → −1")
        elif qqq_day_pct >= 1.0:
            score += 1
            reasons.append(f"QQQ day {qqq_day_pct:+.2f}% ≥ +1% → +1")
    if vix_day_pct is not None and vix_day_pct >= 5.0:
        score -= 1
        reasons.append(f"VIX day {vix_day_pct:+.2f}% ≥ +5% → −1")
    return _clamp_score(score), reasons


def _newest_macro_soft_files(limit: int = 5) -> list[Path]:
    files = sorted(
        TMP.glob("macro-soft-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[:limit]


def _drivers_from_soft(limit: int = 3) -> list[str]:
    """Pull 1–3 news driver bullets from newest macro-soft JSON files."""
    out: list[str] = []
    for path in _newest_macro_soft_files(8):
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        title = str(data.get("title") or "").strip()
        event = str(data.get("event") or "").strip()
        bias = str(data.get("bias") or "").strip()
        notes = str(data.get("notes") or "").strip()
        bullet = None
        if title and event:
            bullet = f"{title}: {event}"
        elif event:
            bullet = event
        elif title:
            bullet = title
        if bullet:
            if bias and bias.lower() not in bullet.lower():
                bullet = f"{bullet} ({bias})"
            out.append(bullet[:280])
        elif notes:
            out.append(notes[:280])
        if len(out) >= limit:
            break
    return out[:limit]


def _normalize_card(raw: Any, *, kind: str, fallback_score: int = 0) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    score = raw.get("score")
    try:
        score_i = _clamp_score(float(score)) if score is not None else fallback_score
    except (TypeError, ValueError):
        score_i = fallback_score
    tone = str(raw.get("tone") or _tone_from_score(score_i)).lower().replace("soft-", "")
    if tone not in ("calm", "neutral", "warm", "stress"):
        tone = _tone_from_score(score_i)
    label = str(raw.get("label") or _label_from_score(score_i, kind=kind))
    drivers = raw.get("drivers") or []
    if isinstance(drivers, str):
        drivers = [drivers]
    drivers = [str(d).strip() for d in drivers if str(d).strip()][:3]
    return {
        "tone": tone,
        "tone_class": _tone_class(tone),
        "label": label,
        "score": score_i,
        "drivers": drivers,
    }


def _ensure_drivers(card: dict[str, Any], soft_drivers: list[str]) -> dict[str, Any]:
    drivers = list(card.get("drivers") or [])
    for d in soft_drivers:
        if len(drivers) >= 3:
            break
        if d and d not in drivers:
            drivers.append(d)
    if not drivers and soft_drivers:
        drivers = soft_drivers[:1]
    card["drivers"] = drivers[:3]
    return card


def _parse_oil_note(note: str) -> dict[str, Any]:
    """Best-effort parse of Macro Bot oil_note into WTI/Brent fut marks."""
    out: dict[str, Any] = {"raw": note}
    if not note:
        return out
    wti = re.search(
        r"WTI[^\d$]{0,12}(?:\$\s*)?(~?\s*)([0-9]{2,3}\.[0-9]{1,2}).{0,40}?"
        r"[\(−\-–]?\s*([+\-−]?\s*[0-9]+\.?[0-9]*)\s*%",
        note,
        re.I,
    )
    brent = re.search(
        r"Brent[^\d$]{0,12}(?:\$\s*)?(~?\s*)([0-9]{2,3}\.[0-9]{1,2}).{0,40}?"
        r"[\(−\-–]?\s*([+\-−]?\s*[0-9]+\.?[0-9]*)\s*%",
        note,
        re.I,
    )
    if wti:
        out["wti_fut"] = _f(wti.group(2))
        out["wti_day_pct"] = _f(wti.group(3).replace("−", "-").replace(" ", ""))
    if brent:
        out["brent_fut"] = _f(brent.group(2))
        out["brent_day_pct"] = _f(brent.group(3).replace("−", "-").replace(" ", ""))
    return out


def _find_bot_ingest_candidates() -> list[Path]:
    cands: list[Path] = []
    for p in sorted(TMP.glob("macro-morning*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        cands.append(p)
    latest = LATEST / "macro-morning.json"
    if latest.is_file():
        cands.append(latest)
    return cands


def ingest_bot_payload(data: Any) -> Optional[dict[str, Any]]:
    """Normalize Macro Bot / seeded morning JSON into our payload shape.

    Macro Bot soft scores are authoritative when present. Do NOT recompute or
    sum metric_scores[] into daily_macro / macro_tech — those rows are evidence
    chips only. Mechanical --recompute is fallback when no bot pack exists.
    """
    if not isinstance(data, dict):
        return None
    body = _payload(data)
    if not isinstance(body, dict):
        return None
    if not (body.get("daily_macro") or body.get("macro_tech") or data.get("daily_macro")):
        # raw bot without envelope
        if "daily_macro" not in body and "daily_macro" in data:
            body = data
        else:
            return None
    soft = _drivers_from_soft(3)
    daily = _normalize_card(body.get("daily_macro") or data.get("daily_macro"), kind="daily_macro")
    tech = _normalize_card(body.get("macro_tech") or data.get("macro_tech"), kind="macro_tech")
    daily = _ensure_drivers(daily, soft)
    tech = _ensure_drivers(tech, soft)
    oil_note = body.get("oil_note") or data.get("oil_note")
    sources = body.get("sources") or data.get("sources") or []
    as_of = body.get("as_of_pt") or data.get("as_of_pt") or _as_of_pt()
    metric_scores = body.get("metric_scores") or data.get("metric_scores") or []
    if not isinstance(metric_scores, list):
        metric_scores = []
    rates_note = body.get("rates_note") or data.get("rates_note")
    metric_10y = None
    for row in metric_scores:
        if isinstance(row, dict) and str(row.get("metric") or "") == "10Y_yield":
            metric_10y = str(row.get("value") or "") or None
            break
    rates_parsed: dict[str, Any] = {"raw": rates_note}
    try:
        # Prefer shared wire parser from macro_spot (10Y/30Y + bp)
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import macro_spot as _ms

        parsed = _ms._parse_rates_note(str(rates_note or ""), metric_value=metric_10y)
        for cid, cell in (parsed or {}).items():
            rates_parsed[cid] = {
                "spot": cell.get("spot"),
                "day_chg_bp": cell.get("day_chg_bp"),
                "day_chg": cell.get("day_chg"),
                "prev_close": cell.get("prev_close"),
                "unit": "%",
                "kind": "wire",
            }
    except Exception:
        # Best-effort local fallback: keep raw only
        pass
    # Preserve Macro Bot soft scores verbatim (already in daily/tech via _normalize_card).
    # Never overwrite with compute_* here — metric_scores are evidence, not a sum.
    daily["score_authority"] = "macro_bot"
    tech["score_authority"] = "macro_bot"
    out = {
        "as_of_pt": as_of,
        "daily_macro": daily,
        "macro_tech": tech,
        "oil_note": oil_note,
        "oil_parsed": _parse_oil_note(str(oil_note or "")),
        "rates_parsed": rates_parsed,
        "sources": sources,
        "metric_scores": metric_scores,
        "source": body.get("source") or data.get("source") or "Macro Bot",
        "builder": "macro_morning.py",
        "mode": "ingest",
        "score_authority": "macro_bot",
        "mandate": "Research / paper only · Soft color · Zero execution",
        "indicator_logic": INDICATOR_LOGIC_BLURB,
        "score_note": (
            "Macro Bot soft scores win when this pack is ingested. "
            "metric_scores[] are evidence chips only — do not sum into macro_tech.score. "
            "Use --recompute only when no Macro Bot pack is available."
        ),
    }
    for k in ("rates_note", "usd_note", "vol_note"):
        v = body.get(k) or data.get(k)
        if v:
            out[k] = v
    return out


INDICATOR_LOGIC_BLURB = (
    "Daily Macro (mechanical fallback): start 0; VIX day% ≥+5 → −1; ≤−5 → +1; "
    "SPY ≤−0.75% → −1; ≥+0.75% → +1; HY OAS Q4 → −1; Q1 → +0; WTI fut day% ≥+3 → −1; "
    "≤−3 → +0; clamp −2..+2. "
    "Macro Tech (mechanical fallback): start 0; QQQ−SPY ≤−0.3pp → −1; ≥+0.3pp → +1; "
    "QQQ ≤−1% → −1; ≥+1% → +1; VIX ≥+5% day → −1; clamp −2..+2. "
    "Tone: +2/+1 calm, 0 neutral, −1 warm, −2 stress. "
    "When Macro Bot pack is present, its soft daily_macro/macro_tech scores win — "
    "do not re-score or sum metric_scores into the cards."
)


def build_from_feeds(
    *,
    tape: Optional[dict] = None,
    fidelity: Optional[dict] = None,
    macro_spot: Optional[dict] = None,
) -> dict[str, Any]:
    tape = tape or _payload(_load_json(LATEST / "market-tape.json")) or {}
    fidelity = fidelity or _payload(_load_json(LATEST / "fidelity-three.json")) or {}
    macro_spot = macro_spot or _payload(_load_json(LATEST / "macro-spot.json")) or {}

    spy = _index_day(tape, "SPY")
    qqq = _index_day(tape, "QQQ")
    vix = _macro_cell_day(macro_spot, "vix")
    wti = _macro_cell_day(macro_spot, "wti")  # futures primary when present
    hy_q = _hy_quartile(fidelity)

    d_score, d_reasons = compute_daily_macro_score(
        vix_day_pct=vix, spy_day_pct=spy, hy_quartile=hy_q, wti_fut_day_pct=wti
    )
    t_score, t_reasons = compute_macro_tech_score(
        qqq_day_pct=qqq, spy_day_pct=spy, vix_day_pct=vix
    )
    soft = _drivers_from_soft(3)
    daily = _normalize_card(
        {"score": d_score, "tone": _tone_from_score(d_score), "label": _label_from_score(d_score, kind="daily_macro"), "drivers": soft[:2]},
        kind="daily_macro",
        fallback_score=d_score,
    )
    tech = _normalize_card(
        {"score": t_score, "tone": _tone_from_score(t_score), "label": _label_from_score(t_score, kind="macro_tech"), "drivers": soft[:2]},
        kind="macro_tech",
        fallback_score=t_score,
    )
    daily = _ensure_drivers(daily, soft)
    tech = _ensure_drivers(tech, soft)
    daily["score_reasons"] = d_reasons
    tech["score_reasons"] = t_reasons

    # oil note from macro-spot futures cells if present
    bid = macro_spot.get("by_id") or {}
    wti_c = bid.get("wti") or {}
    brent_c = bid.get("brent") or {}
    oil_note = None
    if wti_c.get("spot") is not None or brent_c.get("spot") is not None:
        parts = []
        if wti_c.get("spot") is not None:
            dp = wti_c.get("day_pct")
            dps = f" ({dp:+.2f}%)" if isinstance(dp, (int, float)) else ""
            parts.append(f"WTI fut ~${float(wti_c['spot']):.2f}{dps}")
        if brent_c.get("spot") is not None:
            dp = brent_c.get("day_pct")
            dps = f" ({dp:+.2f}%)" if isinstance(dp, (int, float)) else ""
            parts.append(f"Brent fut ~${float(brent_c['spot']):.2f}{dps}")
        oil_note = " / ".join(parts) + " · from macro-spot"

    return {
        "as_of_pt": _as_of_pt(),
        "daily_macro": daily,
        "macro_tech": tech,
        "oil_note": oil_note,
        "inputs": {
            "spy_day_pct": spy,
            "qqq_day_pct": qqq,
            "vix_day_pct": vix,
            "wti_fut_day_pct": wti,
            "hy_oas_quartile": hy_q,
        },
        "source": "feeds+macro-soft (computed)",
        "builder": "macro_morning.py",
        "mode": "compute",
        "mandate": "Research / paper only · Soft color · Zero execution",
        "indicator_logic": INDICATOR_LOGIC_BLURB,
    }


def build_macro_morning(
    *,
    ingest_path: Optional[Path] = None,
    recompute: bool = False,
    prefer_bot: bool = True,
) -> dict[str, Any]:
    """Build morning payload. Prefer Macro Bot ingest when available unless recompute."""
    if ingest_path:
        data = _load_json(ingest_path)
        got = ingest_bot_payload(data)
        if got:
            got["ingest_path"] = str(ingest_path)
            return got
        raise SystemExit(f"Failed to ingest {ingest_path}")

    if prefer_bot and not recompute:
        for cand in _find_bot_ingest_candidates():
            data = _load_json(cand)
            # Skip computed-only self-writes when looking for bot
            body = _payload(data) if isinstance(data, dict) else None
            if not isinstance(body, dict):
                continue
            src = str(body.get("source") or (data or {}).get("source") or "")
            mode = str(body.get("mode") or "")
            # Never treat a prior --recompute feed as Macro Bot authority
            if mode == "compute" or "feeds+macro-soft" in src:
                continue
            if "Macro Bot" in src or body.get("daily_macro") and mode != "compute":
                # Accept feed envelope from oid-ingest-macro-bot
                if (data or {}).get("writer") == "oid-ingest-macro-bot" or "Macro Bot" in src or body.get("oil_note"):
                    got = ingest_bot_payload(data)
                    if got:
                        got["ingest_path"] = str(cand)
                        return got
            # also accept raw bot shape on tmp files
            if cand.parent == TMP and body.get("daily_macro") and body.get("macro_tech"):
                got = ingest_bot_payload(data)
                if got:
                    got["ingest_path"] = str(cand)
                    return got

    return build_from_feeds()


def write_morning(payload: dict[str, Any], *, writer: str = "macro_morning.py") -> dict[str, Any]:
    rec = write_feed(
        "macro-morning",
        source=str(payload.get("source") or "macro_morning.py"),
        writer=writer,
        symbols=[],
        payload=payload,
        ttl_seconds=TTL_SECONDS,
    )
    # dated snapshot under tmp for audit
    day = datetime.now(PT).strftime("%Y%m%d")
    snap = TMP / f"macro-morning-{day}.json"
    TMP.mkdir(parents=True, exist_ok=True)
    # write payload-shaped snapshot (bot-compatible)
    snap.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="OID morning Daily Macro + Macro Tech soft status")
    ap.add_argument("--ingest", type=Path, help="Macro Bot / seeded morning JSON")
    ap.add_argument("--recompute", action="store_true", help="Ignore bot cache; score from feeds")
    ap.add_argument("--no-prefer-bot", action="store_true", help="Do not auto-ingest existing bot JSON")
    ap.add_argument("--dry-run", action="store_true", help="Print payload; do not write feed")
    ap.add_argument("--writer", default="macro_morning.py")
    args = ap.parse_args()

    payload = build_macro_morning(
        ingest_path=args.ingest,
        recompute=bool(args.recompute),
        prefer_bot=not bool(args.no_prefer_bot),
    )
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    rec = write_morning(payload, writer=args.writer)
    print(
        json.dumps(
            {
                "ok": True,
                "as_of_pt": rec.get("as_of_pt"),
                "mode": payload.get("mode"),
                "daily_macro": {
                    "tone": payload["daily_macro"]["tone"],
                    "score": payload["daily_macro"]["score"],
                    "label": payload["daily_macro"]["label"],
                    "drivers_n": len(payload["daily_macro"].get("drivers") or []),
                },
                "macro_tech": {
                    "tone": payload["macro_tech"]["tone"],
                    "score": payload["macro_tech"]["score"],
                    "label": payload["macro_tech"]["label"],
                    "drivers_n": len(payload["macro_tech"].get("drivers") or []),
                },
                "oil_note": (payload.get("oil_note") or "")[:120],
                "feed": "market-data/latest/macro-morning.json",
                "ttl_seconds": TTL_SECONDS,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
