#!/usr/bin/env python3
"""OID Rates · Vol · Oil macro spot builder (research / paper only).

Sources (honest):
  - US 10Y / 30Y Treasury yield %: PRIMARY = Macro Bot morning wire
    (rates_note / metric_scores 10Y_yield) when present; FRED DGS10 daily
    is secondary lag only (often 1–2 sessions behind the wire).
  - VIX: Robinhood get_index_quotes (+ day bars for prev close). Not Yahoo.
  - WTI / Brent $/bbl: PRIMARY = futures (tmp/oil-futures.json or Macro Bot
    oil_note); FRED DCOILWTICO / DCOILBRENTEU = secondary lagged daily spot.

Yahoo ^TNX / ^VIX / CL=F / BZ=F intentionally unused (box egress 429).
Never places orders. Soft/paper only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OID = ROOT.parent
PT = ZoneInfo("America/Los_Angeles")

VIX_INSTRUMENT_ID = "3b912aa2-88f9-4682-8ae3-e39520bdf4db"

FRED_US10Y = "DGS10"
FRED_WTI = "DCOILWTICO"
FRED_BRENT = "DCOILBRENTEU"


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


def _day_pct(last: Optional[float], prev: Optional[float]) -> Optional[float]:
    if last is None or prev is None or prev == 0:
        return None
    return round((float(last) - float(prev)) / float(prev) * 100.0, 4)


def _load_json(path: Optional[Path]) -> Any:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fred_last_two(series_id: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """(spot, prev, as_of_date) from FRED via refresh_market_tape.fetch_fred_series."""
    import refresh_market_tape as rmt

    series = rmt.fetch_fred_series(series_id, years=2)
    if not series:
        return None, None, None
    spot_d, spot = series[-1]
    prev = series[-2][1] if len(series) >= 2 else None
    return float(spot), (float(prev) if prev is not None else None), spot_d


def _parse_vix_quote(payload: Any) -> Optional[float]:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    quotes = data.get("quotes") if isinstance(data, dict) else None
    if isinstance(quotes, list):
        for q in quotes:
            if not isinstance(q, dict):
                continue
            iid = str(q.get("instrument_id") or "")
            sym = str(q.get("symbol") or "").upper()
            if iid == VIX_INSTRUMENT_ID or sym == "VIX":
                return _f(q.get("value") or q.get("last") or q.get("price"))
        if quotes and isinstance(quotes[0], dict):
            return _f(quotes[0].get("value") or quotes[0].get("last"))
    if isinstance(data, dict) and "value" in data:
        return _f(data.get("value"))
    return _f(payload.get("value") or payload.get("vix") or payload.get("spot"))


def _parse_vix_prev(payload: Any) -> Optional[float]:
    """Prev RTH close from get_index_historicals day bars (skip interpolated)."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    results = []
    if isinstance(data, dict):
        results = data.get("results") or data.get("historicals") or []
    if not isinstance(results, list):
        return None
    bars: list[tuple[str, float]] = []
    for block in results:
        if not isinstance(block, dict):
            continue
        iid = str(block.get("instrument_id") or "")
        sym = str(block.get("symbol") or "").upper()
        if iid and iid != VIX_INSTRUMENT_ID and sym not in ("", "VIX"):
            continue
        for b in block.get("bars") or []:
            if not isinstance(b, dict) or b.get("interpolated") is True:
                continue
            close = _f(b.get("close_value") or b.get("close") or b.get("value"))
            begins = str(b.get("begins_at") or b.get("date") or "")
            if close is not None:
                bars.append((begins, close))
    if not bars:
        return None
    bars.sort(key=lambda x: x[0])
    return bars[-1][1]


def _cell(
    *,
    id: str,
    label: str,
    spot: Optional[float],
    prev_close: Optional[float],
    unit: str,
    source: str,
    as_of: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict[str, Any]:
    day_chg = None
    if spot is not None and prev_close is not None:
        day_chg = round(float(spot) - float(prev_close), 6)
    day_pct = _day_pct(spot, prev_close)
    out: dict[str, Any] = {
        "id": id,
        "label": label,
        "spot": spot,
        "prev_close": prev_close,
        "day_chg": day_chg,
        "day_pct": day_pct,
        "unit": unit,
        "source": source,
        "as_of": as_of or _as_of_pt(),
    }
    if id == "us10y" and day_chg is not None:
        out["day_chg_bp"] = round(day_chg * 100.0, 2)
    if extra:
        out.update(extra)
    return out


def _parse_oil_note_futures(note: str) -> dict[str, dict]:
    """Parse Macro Bot oil_note into wti/brent futures marks (spot + day_pct).

    Accepts single-price and overnight range formats, e.g.:
      WTI CL Nov ~$87.4–88.4 (−1.1 to −2.2%)
      Brent Dec ~$98.1–98.6 (−1.7 to −2.3%)
      WTI CL ~$89.42 (−3.71%); Brent Dec ~$99.71 (−2.54%)
    Display spot / day_pct = first number in each range (not mid).
    """
    import re

    out: dict[str, dict] = {}
    if not note:
        return out
    num = r"[0-9]+(?:\.[0-9]+)?"
    sign = r"[+\-−–]"
    for sym, cid, label in (("WTI", "wti", "WTI fut"), ("Brent", "brent", "Brent fut")):
        # Allow contract junk (CL Nov / Dec) between symbol and price; stop before the other symbol.
        pat = (
            rf"{sym}(?:(?!Brent|WTI)[^\d$]){{0,24}}~?\$?\s*"
            rf"({num})(?:\s*[–\-−~]\s*{num})?\s*"
            rf"\(\s*({sign}?\s*{num})\s*"
            rf"(?:%?\s*(?:to|[–\-−])\s*{sign}?\s*{num})?\s*%\s*\)"
        )
        m = re.search(pat, note, re.I)
        if not m:
            continue
        spot = float(m.group(1))
        day_pct = float(m.group(2).replace("−", "-").replace("–", "-").replace(" ", ""))
        out[cid] = {
            "id": cid,
            "label": label,
            "spot": spot,
            "day_pct": day_pct,
            "day_chg": round(spot * day_pct / 100.0, 2),
            "unit": "$/bbl",
            "source": "Macro Bot oil_note (futures)",
            "kind": "futures",
        }
    return out



def _parse_rates_note(note: str, *, metric_value: str | None = None) -> dict[str, dict]:
    """Parse Macro Bot rates_note / 10Y_yield metric into us10y/us30y wire marks.

    Accepts single prints and overnight ranges, e.g.:
      10Y ~5.326-5.336% (+5-6 bp); 30Y ~5.706-5.713% (+5-7 bp)
      10Y ~5.33% (+5-6 bp); 30Y ~5.71% (+5-7 bp)
      ~5.33% (+5-6 bp); 30Y ~5.71% (+5-7 bp)   # metric_scores value
      10Y ~5.28–5.29% (−3 bp); 30Y ~5.63% (−3 bp)
    Display spot = mid of a range (else the single print). day_chg_bp = mid of bp range.
    """
    import re

    out: dict[str, dict] = {}
    num = r"[0-9]+(?:\.[0-9]+)?"
    sign = r"[+\-−–]"
    dash = r"[–\-−~]"

    def _clean_num(s: Optional[str]) -> Optional[float]:
        if s is None or s == "":
            return None
        raw = str(s).replace("−", "-").replace("–", "-").replace(" ", "")
        try:
            return float(raw)
        except ValueError:
            return None

    def _mid(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None:
            return None
        if b is None:
            return round(float(a), 3)
        return round((float(a) + float(b)) / 2.0, 3)

    def _parse_bp_after(tail: str) -> Optional[float]:
        bpm = re.search(
            rf"\(\s*({sign}?\s*{num})\s*(?:(?:{dash}|to)\s*({sign}?\s*{num}))?\s*bp",
            tail[:48],
            re.I,
        )
        if not bpm:
            return None
        a = _clean_num(bpm.group(1))
        b = _clean_num(bpm.group(2)) if bpm.group(2) else None
        if a is None:
            return None
        if b is None:
            return round(float(a), 1)
        # Inherit sign from first when second is unsigned magnitude in a +N–M range
        if a < 0 < b:
            b = -b
        return round((float(a) + float(b)) / 2.0, 1)

    def _tenor(text: str, tenor: str) -> Optional[dict]:
        if not text:
            return None
        if tenor == "10Y":
            pats = [
                rf"(?:10Y|10\s*[- ]?year)\D{{0,16}}~?\s*({num})(?:\s*{dash}\s*({num}))?\s*%",
                rf"^~?\s*({num})(?:\s*{dash}\s*({num}))?\s*%",
            ]
        else:
            pats = [
                rf"(?:30Y|30\s*[- ]?year)\D{{0,16}}~?\s*({num})(?:\s*{dash}\s*({num}))?\s*%",
            ]
        for pat in pats:
            m = re.search(pat, text, re.I | re.M)
            if not m:
                continue
            spot = _mid(_clean_num(m.group(1)), _clean_num(m.group(2)) if m.lastindex >= 2 else None)
            if spot is None:
                continue
            bp = _parse_bp_after(text[m.end() :])
            return {"spot": spot, "day_chg_bp": bp}
        return None

    blobs = [note or "", metric_value or ""]
    for cid, tenor, label in (
        ("us10y", "10Y", "10Y Treasury"),
        ("us30y", "30Y", "30Y Treasury"),
    ):
        parsed = None
        for blob in blobs:
            parsed = _tenor(blob, tenor)
            if parsed:
                break
        if not parsed:
            continue
        spot = parsed["spot"]
        bp = parsed.get("day_chg_bp")
        day_chg = round(float(bp) / 100.0, 6) if isinstance(bp, (int, float)) else None
        prev = round(float(spot) - float(day_chg), 6) if day_chg is not None else None
        day_pct = _day_pct(spot, prev) if prev is not None else None
        cell: dict[str, Any] = {
            "id": cid,
            "label": label,
            "spot": spot,
            "prev_close": prev,
            "day_chg": day_chg,
            "day_pct": day_pct,
            "unit": "%",
            "source": "Macro Bot rates_note (wire)",
            "kind": "wire",
        }
        if isinstance(bp, (int, float)):
            cell["day_chg_bp"] = float(bp)
        out[cid] = cell
    return out


def _load_rates_wire_override() -> dict[str, dict]:
    """Prefer Macro Bot morning wire yields over lagging FRED DGS10 when present."""
    out: dict[str, dict] = {}
    for cand in (
        OID / "market-data" / "latest" / "macro-morning.json",
        *sorted((OID / "tmp").glob("macro-morning*.json"), reverse=True)[:3],
    ):
        data = _load_json(cand)
        if not isinstance(data, dict):
            continue
        body = data.get("payload") if isinstance(data.get("payload"), dict) else data
        if not isinstance(body, dict):
            continue
        note = str(body.get("rates_note") or "")
        metric_value = None
        for row in body.get("metric_scores") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("metric") or "") == "10Y_yield":
                metric_value = str(row.get("value") or "") or None
                break
        # Prefer explicit rates_parsed block when ingest already computed it
        pre = body.get("rates_parsed")
        if isinstance(pre, dict) and (pre.get("us10y") or pre.get("us30y")):
            for cid in ("us10y", "us30y"):
                block = pre.get(cid)
                if isinstance(block, dict) and _f(block.get("spot")) is not None:
                    cell = dict(block)
                    cell.setdefault("id", cid)
                    cell.setdefault("label", "10Y Treasury" if cid == "us10y" else "30Y Treasury")
                    cell.setdefault("unit", "%")
                    cell.setdefault("source", "Macro Bot rates_note (wire)")
                    cell.setdefault("kind", "wire")
                    cell["as_of"] = body.get("as_of_pt") or _as_of_pt()
                    if cell.get("day_chg_bp") is None and cell.get("day_chg") is not None:
                        cell["day_chg_bp"] = round(float(cell["day_chg"]) * 100.0, 2)
                    out[cid] = cell
            if out:
                return out
        parsed = _parse_rates_note(note, metric_value=metric_value)
        for cid, cell in parsed.items():
            cell = dict(cell)
            cell["as_of"] = body.get("as_of_pt") or _as_of_pt()
            out[cid] = cell
        if out:
            return out
    return out


def _load_oil_futures_override() -> dict[str, dict]:
    """Prefer live/futures marks from tmp/oil-futures.json or Macro Bot oil_note — never let FRED win when futures exist."""
    out: dict[str, dict] = {}
    fut_path = OID / "tmp" / "oil-futures.json"
    raw = _load_json(fut_path)
    if isinstance(raw, dict):
        for key, cid, label in (("wti", "wti", "WTI fut"), ("brent", "brent", "Brent fut")):
            block = raw.get(key)
            if isinstance(block, dict) and _f(block.get("spot")) is not None:
                spot = _f(block.get("spot"))
                day_pct = _f(block.get("day_pct"))
                day_chg = _f(block.get("day_chg"))
                out[cid] = {
                    "id": cid,
                    "label": label,
                    "spot": spot,
                    "prev_close": _f(block.get("prev_close")),
                    "day_pct": day_pct,
                    "day_chg": day_chg,
                    "unit": "$/bbl",
                    "as_of": raw.get("as_of_pt") or _as_of_pt(),
                    "source": raw.get("source") or "tmp/oil-futures.json",
                    "kind": "futures",
                }
    if out:
        return out
    # Macro morning oil_note
    for cand in (
        OID / "market-data" / "latest" / "macro-morning.json",
        *sorted((OID / "tmp").glob("macro-morning*.json"), reverse=True)[:3],
    ):
        data = _load_json(cand)
        if not isinstance(data, dict):
            continue
        body = data.get("payload") if isinstance(data.get("payload"), dict) else data
        note = str(body.get("oil_note") or "")
        if not note:
            continue
        parsed = _parse_oil_note_futures(note)
        for cid, cell in parsed.items():
            cell = dict(cell)
            cell["as_of"] = body.get("as_of_pt") or _as_of_pt()
            out[cid] = cell
        if out:
            return out
    return out


def build_macro_spot(
    *,
    index_quotes: Any = None,
    index_historicals: Any = None,
    index_quotes_file: Optional[Path] = None,
    index_historicals_file: Optional[Path] = None,
    uw_yield_curve_file: Optional[Path] = None,
    skip_fred: bool = False,
) -> dict[str, Any]:
    """Build Rates · Vol · Oil macro block."""
    if index_quotes is None:
        index_quotes = _load_json(index_quotes_file)
    if index_historicals is None:
        index_historicals = _load_json(index_historicals_file)

    items: list[dict[str, Any]] = []
    errors: list[str] = []

    # --- 10Y / 30Y Treasury: wire PRIMARY (Macro Bot rates_note); FRED DGS10 secondary lag ---
    rates_wire = _load_rates_wire_override()
    fred_10y_cell = None
    if not skip_fred:
        try:
            spot, prev, as_of_d = _fred_last_two(FRED_US10Y)
            uw = _load_json(uw_yield_curve_file)
            uw_note = None
            if isinstance(uw, list) and uw:
                row = uw[0] if isinstance(uw[0], dict) else {}
                uw10 = _f(row.get("bc_10year") or row.get("bc10year") or row.get("ten_year"))
                uw_d = row.get("new_date") or row.get("date")
                if uw10 is not None:
                    uw_note = f"UW yield curve {uw_d}: {uw10}"
                    if uw_d and as_of_d and str(uw_d) >= str(as_of_d):
                        spot = uw10
                        as_of_d = str(uw_d)
            extra: dict[str, Any] = {"fred_id": FRED_US10Y, "kind": "fred_spot"}
            if uw_note:
                extra["uw_note"] = uw_note
            fred_10y_cell = _cell(
                id="us10y_fred",
                label="10Y Treasury (FRED)",
                spot=spot,
                prev_close=prev,
                unit="%",
                source=f"FRED CSV {FRED_US10Y}" + (" + UW yield curve" if uw_note else "") + " (daily; lags wire)",
                as_of=as_of_d,
                extra=extra,
            )
        except Exception as e:
            errors.append(f"us10y_fred: {e}"[:200])

    if "us10y" in rates_wire:
        cell = dict(rates_wire["us10y"])
        cell.setdefault("kind", "wire")
        items.append(cell)
        if fred_10y_cell is not None:
            errors.append(
                f"us10y: using Macro Bot wire {cell.get('spot')}%; "
                f"FRED lag {fred_10y_cell.get('spot')}% as of {fred_10y_cell.get('as_of')}"
            )
    elif fred_10y_cell is not None:
        fallback = dict(fred_10y_cell)
        fallback["id"] = "us10y"
        fallback["label"] = "10Y Treasury"
        # Keep clear lag cue in source; banner tip shows as_of date
        items.append(fallback)
        errors.append("us10y: no Macro Bot rates wire; using FRED DGS10 lag")
    else:
        items.append(
            _cell(
                id="us10y",
                label="10Y Treasury",
                spot=None,
                prev_close=None,
                unit="%",
                source="rates wire unavailable" if skip_fred else f"FRED CSV {FRED_US10Y}",
                extra={"error": "no_rates_wire_and_no_fred", "fred_id": FRED_US10Y},
            )
        )

    if "us30y" in rates_wire:
        cell30 = dict(rates_wire["us30y"])
        cell30.setdefault("kind", "wire")
        items.append(cell30)

    # --- VIX (Robinhood index) ---
    vix_spot = _parse_vix_quote(index_quotes)
    vix_prev = _parse_vix_prev(index_historicals)
    vix_src = "user-robinhood-trading get_index_quotes"
    if vix_prev is not None:
        vix_src += " + get_index_historicals (day)"
    if vix_spot is None:
        errors.append("vix: missing index quotes file / payload")
    items.append(
        _cell(
            id="vix",
            label="VIX",
            spot=vix_spot,
            prev_close=vix_prev,
            unit="pts",
            source=vix_src,
            as_of=_as_of_pt(),
            extra={
                "instrument_id": VIX_INSTRUMENT_ID,
                "error": None if vix_spot is not None else "no_rh_vix_quote",
            },
        )
    )

    # --- WTI / Brent: FUTURES primary (tmp/oil-futures.json or Macro Bot oil_note); FRED spot secondary lag only ---
    fut_override = _load_oil_futures_override()
    fred_secondary: dict[str, Any] = {}
    for mid, label, fred_id in (
        ("wti", "WTI", FRED_WTI),
        ("brent", "Brent", FRED_BRENT),
    ):
        fred_cell = None
        if not skip_fred:
            try:
                spot, prev, as_of_d = _fred_last_two(fred_id)
                fred_cell = _cell(
                    id=f"{mid}_fred",
                    label=f"{label} spot (FRED)",
                    spot=spot,
                    prev_close=prev,
                    unit="$/bbl",
                    source=f"FRED CSV {fred_id} (daily spot $/bbl; lags futures)",
                    as_of=as_of_d,
                    extra={"fred_id": fred_id, "kind": "fred_spot"},
                )
                fred_secondary[mid] = fred_cell
            except Exception as e:
                errors.append(f"{mid}_fred: {e}"[:200])
        if mid in fut_override:
            cell = dict(fut_override[mid])
            cell.setdefault("kind", "futures")
            if "day_pct" not in cell or cell.get("day_pct") is None:
                # recompute via _cell helper fields
                pass
            items.append(cell)
        elif fred_cell is not None:
            # No futures available — show FRED but keep clear lag label
            fallback = dict(fred_cell)
            fallback["id"] = mid
            fallback["label"] = f"{label} (FRED lag)"
            items.append(fallback)
            errors.append(f"{mid}: no futures override; using FRED lag spot")
        else:
            items.append(
                _cell(
                    id=mid,
                    label=f"{label} fut",
                    spot=None,
                    prev_close=None,
                    unit="$/bbl",
                    source="futures unavailable",
                    extra={"error": "no_futures_and_no_fred", "fred_id": fred_id},
                )
            )

    by_id = {c["id"]: c for c in items if c.get("id")}
    for mid, fc in fred_secondary.items():
        by_id[fc["id"]] = fc
    if fred_10y_cell is not None:
        by_id[fred_10y_cell["id"]] = fred_10y_cell

    oil_note = None
    if fut_override:
        bits = []
        for mid in ("wti", "brent"):
            c = fut_override.get(mid) or {}
            if c.get("spot") is not None:
                pct = c.get("day_pct")
                pct_s = f" ({pct:+.2f}%)" if isinstance(pct, (int, float)) else ""
                bits.append(f"{c.get('label', mid)} ${c['spot']:,.2f}{pct_s}")
        oil_note = " · ".join(bits) if bits else None

    rates_note = None
    if rates_wire:
        bits = []
        for mid in ("us10y", "us30y"):
            c = rates_wire.get(mid) or {}
            if c.get("spot") is not None:
                bp = c.get("day_chg_bp")
                bp_s = f" ({bp:+.0f} bp)" if isinstance(bp, (int, float)) else ""
                short = "10Y" if mid == "us10y" else "30Y"
                bits.append(f"{short} {float(c['spot']):.2f}%{bp_s}")
        rates_note = " · ".join(bits) if bits else None

    return {
        "as_of_pt": _as_of_pt(),
        "title": "Rates · Vol · Oil",
        "mandate": "Research / paper only · Soft color · Zero execution",
        "items": items,
        "by_id": by_id,
        "oil_note": oil_note,
        "rates_note": rates_note,
        "oil_prefer": "futures",
        "rates_prefer": "wire",
        "source_policy": (
            "VIX=RH index quotes; "
            "10Y/30Y PRIMARY=Macro Bot rates_note wire (metric_scores 10Y_yield); "
            "FRED DGS10 = secondary lag only; "
            "WTI/Brent PRIMARY=futures (tmp/oil-futures.json or Macro Bot oil_note); "
            "FRED DCOIL* = secondary lag spot only. "
            "Yahoo ^TNX/^VIX/CL=F/BZ=F not used (egress 429)."
        ),
        "errors": errors or None,
    }


def default_input_paths() -> dict[str, Path]:
    tmp = OID / "tmp"
    return {
        "index_quotes_file": tmp / "vix-index-quotes.json",
        "index_historicals_file": tmp / "vix-index-historicals.json",
        "uw_yield_curve_file": tmp / "uw-yield-curve.json",
    }


if __name__ == "__main__":
    # Dry local parse smoke — no FRED/RH/network, no publish, no orders.
    _samples = [
        "WTI CL Nov ~$87.4–88.4 (−1.1 to −2.2%) and Brent Dec ~$98.1–98.6 (−1.7 to −2.3%)",
        "WTI CL Nov $91.50 (+1.19%); Brent Dec $100.10 (+2.11%).",
        "WTI CL ~$89.42 (−3.71%); Brent Dec ~$99.71 (−2.54%).",
        "WTI ~$89.9 (−1.3%), Brent Dec ~$101.5 (−0.8%)",
    ]
    for _s in _samples:
        _p = _parse_oil_note_futures(_s)
        _w, _b = _p.get("wti"), _p.get("brent")
        print(
            f"wti={None if not _w else (_w['spot'], _w['day_pct'])} "
            f"brent={None if not _b else (_b['spot'], _b['day_pct'])} | {_s[:72]}"
        )
    _rsamples = [
        "10Y ~5.326-5.336% (+5-6 bp); 30Y ~5.706-5.713% (+5-7 bp), highest since 2002.",
        "10Y ~5.33% (+5-6 bp); 30Y ~5.71% (+5-7 bp)",
        "10Y ~5.28–5.29% (−3 bp); 30Y ~5.63% (−3 bp)",
    ]
    for _s in _rsamples:
        _p = _parse_rates_note(_s)
        _a, _b = _p.get("us10y"), _p.get("us30y")
        print(
            f"10Y={None if not _a else (_a['spot'], _a.get('day_chg_bp'))} "
            f"30Y={None if not _b else (_b['spot'], _b.get('day_chg_bp'))} | {_s[:72]}"
        )
