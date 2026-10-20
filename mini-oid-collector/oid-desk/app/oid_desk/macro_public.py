"""Public macro inputs on the mini -> market-data/latest/macro-public.json (feed macro-public).

FRED (no key): HY/IG OAS, DGS10/30, WTI/Brent daily spot. EIA API v2 WPSR when EIA_API_KEY exists.
VIX via oid_desk.vix (pluggable; default agent_rh). Each input fails independently (error recorded, never
presented as fresh). Macro Bot still authors the morning note; this only replaces the box's FRED/EIA pulls.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Optional
from urllib.parse import urlencode

from . import net, util, vix

EIA_URL = "https://api.eia.gov/v2/seriesid/PET.{sid}.W?"


def fred_block(series: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, sid in series.items():
        if name == "vixcls":
            continue
        try:
            s = vix.fred_series(sid)
            if not s:
                raise ValueError("empty")
            last = s[-1]
            prev = s[-2] if len(s) > 1 else (None, None)
            out[name] = {"series": sid, "date": last[0], "value": last[1], "prev_date": prev[0], "prev": prev[1],
                         "chg": round(last[1] - prev[1], 4) if prev[1] is not None else None}
        except Exception as e:  # noqa: BLE001
            out[name] = {"series": sid, "error": type(e).__name__}
    return out


def eia_block(series: dict[str, str]) -> dict[str, Any]:
    key = util.read_secret("EIA_API_KEY")
    if not key:
        return {"skipped": "no EIA_API_KEY on the mini"}
    out: dict[str, Any] = {}
    for name, sid in series.items():
        try:
            url = EIA_URL.format(sid=sid) + urlencode({"api_key": key, "length": 2, "sort[0][column]": "period",
                                                       "sort[0][direction]": "desc"})
            data = (net.get_json(url, timeout=20).get("response") or {}).get("data") or []
            if not data:
                raise ValueError("empty")
            cur = data[0]
            prv = data[1] if len(data) > 1 else {}
            v, pv = float(cur.get("value")), (float(prv["value"]) if prv.get("value") is not None else None)
            out[name] = {"series": sid, "period": cur.get("period"), "value": v, "prev": pv,
                         "chg": round(v - pv, 3) if pv is not None else None, "units": cur.get("units")}
        except Exception as e:  # noqa: BLE001
            out[name] = {"series": sid, "error": type(e).__name__}
    return out


def build() -> dict:
    cfg = util.desk_config("mini-desk.json")
    return {"fred": fred_block(cfg.get("fred_series") or {}),
            "eia": eia_block((cfg.get("eia") or {}).get("series") or {}),
            "vix": vix.get_vix(cfg.get("vix") or {}),
            "notes": "FRED daily series lag 1-2 sessions; VIX provider per config/mini-desk.json vix.source"}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID mini public macro")
    ap.add_argument("--print", action="store_true")
    a = ap.parse_args(argv)
    p = build()
    errs = [k for k, v in p["fred"].items() if isinstance(v, dict) and v.get("error")]
    util.write_feed("macro-public", source="FRED public CSV + EIA API v2 + VIX provider", writer="mini:oid_desk.macro_public",
                    symbols=[], payload=p, ttl_seconds=2700, error=(f"fred errors: {errs}" if errs else None))
    if a.print:
        print(json.dumps(p, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
