"""SEC EDGAR filings for the desk universe -> market-data/latest/premarket-edgar-mini.json.

Replaces the RH get_sec_filing_index pull in the premarket EDGAR ping. Public SEC JSON (no key):
  https://www.sec.gov/files/company_tickers.json            (ticker -> CIK, cached daily)
  https://data.sec.gov/submissions/CIK##########.json        (recent filings incl. Form 4 where the company is issuer)
SEC fair access: descriptive User-Agent with a contact email (config edgar.sec_user_agent), <=10 req/s.
--if-due runs at the ET times in edgar.due_et (launchd fires hourly). UW insider detail stays a UW read.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from . import net, util

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
JOB = "edgar"


def user_agent(cfg: dict) -> str:
    ua = (cfg.get("sec_user_agent") or "").strip()
    if not ua or "SET-ME" in ua or "@" not in ua:
        raise RuntimeError("config/mini-desk.json edgar.sec_user_agent must name a contact email (SEC policy)")
    return ua


def universe(cfg: dict) -> list[str]:
    d = util.desk()
    syms: list[str] = []
    al = util.read_json(d / "config" / "stream-quote-allowlist.json") or {}
    syms += al.get("underlyings") or []
    lv = util.read_json(d / "chart-bot" / "levels" / "latest" / "levels.json") or {}
    if isinstance(lv, dict):  # Chart Bot 37-name Tech+chip universe
        syms += [n.get("symbol") for n in (lv.get("names") or []) if isinstance(n, dict) and n.get("symbol")]
    syms += cfg.get("universe_extra") or []
    etfs = {"SPY", "QQQ", "SMH", "IWM", "DIA", "TLT", "HYG", "USO", "RSP", "VTV", "VUG", "SOXX"}
    seen: set[str] = set()
    return [s for s in (x.upper() for x in syms if isinstance(x, str)) if s not in etfs and not (s in seen or seen.add(s))]


def cik_map(ua: str) -> dict[str, int]:
    cache = util.desk() / "cache" / "sec-company-tickers.json"
    c = util.read_json(cache)
    if isinstance(c, dict) and time.time() - float(c.get("epoch") or 0) < 86400:
        return {k: int(v) for k, v in c["map"].items()}
    raw = net.get_json(TICKERS_URL, headers={"User-Agent": ua}, timeout=20)
    m = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in raw.values()}
    util.atomic_write_json(cache, {"epoch": time.time(), "map": m})
    return m


def recent_filings(sub: dict, forms: set[str], since: str) -> list[dict[str, Any]]:
    r = ((sub or {}).get("filings") or {}).get("recent") or {}
    out = []
    for i, form in enumerate(r.get("form") or []):
        fdate = (r.get("filingDate") or [""])[i] if i < len(r.get("filingDate") or []) else ""
        if form in forms and fdate >= since:
            acc = (r.get("accessionNumber") or [""])[i]
            doc = (r.get("primaryDocument") or [""])[i]
            cik = int(sub.get("cik") or 0)
            out.append({"form": form, "filed": fdate, "accession": acc,
                        "accepted": (r.get("acceptanceDateTime") or [None] * (i + 1))[i],
                        "items": (r.get("items") or [""] * (i + 1))[i] or None,
                        "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}" if acc and doc else None})
    return out


def run(cfg: dict) -> dict:
    ua = user_agent(cfg)
    forms = set(cfg.get("forms") or ["4", "8-K"])
    since = (datetime.now(util.ET) - timedelta(days=int(cfg.get("lookback_days", 3)))).strftime("%Y-%m-%d")
    syms = universe(cfg)
    cmap = cik_map(ua)
    filings: dict[str, list] = {}
    missing, errors = [], {}
    for s in syms:
        cik = cmap.get(s) or cmap.get(s.replace(".", "-"))
        if not cik:
            missing.append(s)
            continue
        try:
            sub = net.get_json(SUBS_URL.format(cik=cik), headers={"User-Agent": ua}, timeout=20)
            f = recent_filings(sub, forms, since)
            if f:
                filings[s] = f
        except Exception as e:  # noqa: BLE001
            errors[s] = type(e).__name__
        time.sleep(0.15)  # well under SEC's 10 req/s
    n4 = sum(1 for v in filings.values() for f in v if f["form"] == "4")
    return {"since": since, "symbols": syms, "filings": filings, "no_cik": missing, "errors": errors,
            "counts": {"symbols_with_filings": len(filings), "form4": n4,
                       "total": sum(len(v) for v in filings.values())},
            "status": "WATCH_ONLY", "source_note": "SEC EDGAR submissions JSON (public); replaces RH get_sec_filing_index"}


def due(cfg: dict, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(util.ET)
    if now.weekday() >= 5:
        return False
    last = util.read_json(util.desk() / "market-data" / "latest" / "premarket-edgar-mini.json") or {}
    last_slot = ((last.get("payload") or {}).get("slot"))
    for hhmm in cfg.get("due_et") or ["08:15"]:
        h, m = map(int, hhmm.split(":"))
        slot_t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        slot = slot_t.strftime("%Y-%m-%d ") + hhmm
        if slot_t <= now < slot_t + timedelta(minutes=59) and last_slot != slot:
            return True
    return False


def current_slot(cfg: dict, now: Optional[datetime] = None) -> Optional[str]:
    now = now or datetime.now(util.ET)
    for hhmm in cfg.get("due_et") or []:
        h, m = map(int, hhmm.split(":"))
        st = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if st <= now < st + timedelta(minutes=59):
            return now.strftime("%Y-%m-%d ") + hhmm
    return None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID mini EDGAR filings")
    ap.add_argument("--if-due", action="store_true")
    a = ap.parse_args(argv)
    cfg = util.desk_config("mini-desk.json").get("edgar") or {}
    if a.if_due and not due(cfg):
        print(json.dumps({"skipped": "not due"}))
        return 0
    try:
        p = run(cfg)
        p["slot"] = current_slot(cfg)
        util.write_feed("premarket-edgar-mini", source="SEC EDGAR submissions JSON", writer="mini:oid_desk.edgar_form4",
                        symbols=p["symbols"], payload=p, ttl_seconds=86400)
        print(json.dumps(p["counts"]))
        return 0
    except Exception as e:  # noqa: BLE001
        util.log(JOB, f"error {type(e).__name__}: {str(e)[:200]}")
        util.write_feed("premarket-edgar-mini", source="SEC EDGAR submissions JSON", writer="mini:oid_desk.edgar_form4",
                        symbols=[], payload={"slot": current_slot(cfg)}, ttl_seconds=86400,
                        error=f"{type(e).__name__}: {str(e)[:160]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
