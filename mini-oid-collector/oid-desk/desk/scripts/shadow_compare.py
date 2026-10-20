#!/usr/bin/env python3
"""Shadow-run comparison: Mac mini feeds (market-data/shadow/<path>, written by the mirror) vs the box's live files.

  python3 scripts/shadow_compare.py [--out-dir journal/shadow] [--json] [--root DIR]
Writes journal/shadow/SHADOW-YYYYMMDD-HHMM.md (+ .json) and prints the verdict table.
Verdict per group: PASS | WARN | FAIL | NO_DATA. A group can be flipped (scripts/oid-cutover.sh flip <g>)
after PASS (or an explained WARN) for one full session. Research / paper only; reads files, calls nothing.

Checks
  fa     same call/put wall per focus symbol; gamma flip within 1.5%; only names fetched within 20 min of each other
  uw     net-prem day net call premium within 5% when both saw the same last tape minute; tide last within 5%
  bars   same session_date + bar count (+-1); last 5m close within 5 bps; session RVOL within 0.05
  marks  mini SIP last vs RH last within 10 bps (RTH) and IDENTICAL prev_close; mini OPRA marks coverage
  macro  VIX within 0.15 pts of the box macro-spot VIX; FRED inputs present
  edgar  mini EDGAR ran, filings count vs box premarket-edgar (box path is RH filing index)
  status mini-status present and alarm=false
  fresh  every shadow file's age (as written by the mini) vs its TTL
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

OID = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
RANK = {"PASS": 0, "NO_DATA": 1, "WARN": 2, "FAIL": 3}


def _read(p: Path) -> Any:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _payload(d: Any) -> Any:
    return d.get("payload") if isinstance(d, dict) and "payload" in d else d


def _f(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b) * 100.0


def _epoch(s: Any) -> Optional[float]:
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


class Compare:
    def __init__(self, root: Path = OID):
        self.root = root
        cat = _read(root / "config" / "mirror-feeds.json") or {}
        self.shadow = root / cat.get("shadow_root", "market-data/shadow")

    def pair(self, rel: str) -> tuple[Any, Any]:
        return _read(self.shadow / rel), _read(self.root / rel)

    # ------------------------------------------------------------------ groups
    def fa(self) -> dict:
        s, b = self.pair("market-data/latest/fa-focus-levels.json")
        if not s or not b:
            return {"verdict": "NO_DATA", "rows": [], "note": "fa-focus-levels missing on " + ("mini" if not s else "box")}
        rows, worst = [], "PASS"
        sl, bl = (s.get("levels") or {}), (b.get("levels") or {})
        for sym in sorted(set(sl) & set(bl)):
            a, c = sl[sym], bl[sym]
            ta, tc = _epoch(a.get("as_of")), _epoch(c.get("as_of"))
            if ta and tc and abs(ta - tc) > 1200:
                rows.append({"sym": sym, "verdict": "SKIP", "why": f"fetched {abs(ta-tc)/60:.0f} min apart"})
                continue
            v = "PASS"
            why = []
            for k in ("call_wall", "put_wall"):
                if _f(a.get(k)) != _f(c.get(k)):
                    v = "FAIL"
                    why.append(f"{k} mini {a.get(k)} vs box {c.get(k)}")
            fp = _pct(_f(a.get("gamma_flip")), _f(c.get("gamma_flip")))
            if fp is not None and fp > 1.5:
                v = max(v, "WARN", key=RANK.get)
                why.append(f"flip diff {fp:.2f}%")
            rows.append({"sym": sym, "verdict": v, "why": "; ".join(why) or "match"})
            worst = max(worst, v, key=RANK.get)
        compared = [r for r in rows if r["verdict"] != "SKIP"]
        return {"verdict": worst if compared else "NO_DATA", "rows": rows,
                "note": f"{len(compared)} compared, {len(rows) - len(compared)} skipped (timing)"}

    def uw(self) -> dict:
        s, b = self.pair("market-data/latest/uw-net-prem.json")
        rows, worst = [], "PASS"
        if s and b:
            sp, bp = (_payload(s) or {}).get("per_ticker") or {}, (_payload(b) or {}).get("per_ticker") or {}
            for sym in sorted(set(sp) & set(bp)):
                a, c = sp[sym], bp[sym]
                if a.get("last_tape_time") != c.get("last_tape_time"):
                    rows.append({"sym": sym, "verdict": "SKIP", "why": "different tape minute"})
                    continue
                d = _pct(_f((a.get("day") or {}).get("net_call_premium")), _f((c.get("day") or {}).get("net_call_premium")))
                v = "PASS" if d is None or d <= 5 else "WARN"
                rows.append({"sym": sym, "verdict": v, "why": f"net call prem diff {d:.1f}%" if d is not None else "n/a"})
                worst = max(worst, v, key=RANK.get)
        ts, tb = self.pair("market-data/latest/uw-market-tide.json")
        if ts and tb:
            a, c = (_payload(ts) or {}).get("last") or {}, (_payload(tb) or {}).get("last") or {}
            if a.get("ts") == c.get("ts"):
                d = _pct(_f(a.get("net_call_premium")), _f(c.get("net_call_premium")))
                v = "PASS" if d is None or d <= 5 else "WARN"
                rows.append({"sym": "TIDE", "verdict": v, "why": f"tide diff {d:.1f}%" if d is not None else "n/a"})
                worst = max(worst, v, key=RANK.get)
        ws, wb = self.pair("chart-bot/whale-flow/latest/summary.json")
        if ws is not None:
            rows.append({"sym": "WHALE", "verdict": "PASS" if wb is not None else "WARN", "why": "whale summary mirrored"})
        compared = [r for r in rows if r["verdict"] != "SKIP"]
        return {"verdict": worst if compared else "NO_DATA", "rows": rows}

    def bars(self) -> dict:
        s, b = self.pair("cache/bars/summary.json")
        if not s or not b:
            return {"verdict": "NO_DATA", "rows": []}
        rows, worst = [], "PASS"
        ss, bs = s.get("symbols") or {}, b.get("symbols") or {}
        for sym in sorted(set(ss) & set(bs)):
            a, c = ss[sym], bs[sym]
            v, why = "PASS", []
            if a.get("session_date") != c.get("session_date"):
                rows.append({"sym": sym, "verdict": "SKIP", "why": "different session"})
                continue
            if abs(int(a.get("bars_5m") or 0) - int(c.get("bars_5m") or 0)) > 1:
                v = "WARN"
                why.append(f"bars {a.get('bars_5m')} vs {c.get('bars_5m')}")
            if a.get("last_bar_et") == c.get("last_bar_et"):
                d = _pct(_f(a.get("last_close")), _f(c.get("last_close")))
                if d is not None and d * 100 > 5:
                    v = "FAIL"
                    why.append(f"last close {d*100:.1f} bps")
                r1, r2 = _f(a.get("session_rvol")), _f(c.get("session_rvol"))
                if r1 is not None and r2 is not None and abs(r1 - r2) > 0.05:
                    v = max(v, "WARN", key=RANK.get)
                    why.append(f"rvol {r1} vs {r2}")
            rows.append({"sym": sym, "verdict": v, "why": "; ".join(why) or "match"})
            worst = max(worst, v, key=RANK.get)
        compared = [r for r in rows if r["verdict"] != "SKIP"]
        return {"verdict": worst if compared else "NO_DATA", "rows": rows}

    def marks(self, session: str) -> dict:
        s, b = self.pair("market-data/latest/rh-quotes.json")
        rows, worst = [], "PASS"
        if s and b:
            sq, bq = (_payload(s) or {}).get("quotes") or {}, (_payload(b) or {}).get("quotes") or {}
            dt = None
            ts, tb = _epoch(s.get("as_of")), _epoch(b.get("as_of"))
            if ts and tb:
                dt = abs(ts - tb)
            for sym in sorted(set(sq) & set(bq)):
                a, c = sq[sym], bq[sym]
                v, why = "PASS", []
                p1, p2 = _f(a.get("prev_close")), _f(c.get("prev_close"))
                if p1 is not None and p2 is not None and abs(p1 - p2) > 0.005:
                    v = "FAIL"
                    why.append(f"prev_close mini {p1} vs RH {p2}")
                d = _pct(_f(a.get("last")), _f(c.get("last")))
                if d is not None and session == "rth" and (dt is None or dt <= 120):
                    bps = d * 100
                    if bps > 25:
                        v = "FAIL"
                    elif bps > 10:
                        v = max(v, "WARN", key=RANK.get)
                    why.append(f"last {bps:.1f} bps")
                rows.append({"sym": sym, "verdict": v, "why": "; ".join(why) or "match"})
                worst = max(worst, v, key=RANK.get)
            if dt is not None:
                rows.append({"sym": "_timing", "verdict": "INFO", "why": f"files {dt:.0f}s apart"})
        om_s, om_b = self.pair("market-data/latest/mini-option-marks.json")
        if om_s and om_b:
            a, c = set((_payload(om_s) or {}).get("mini_opra") or []), set((_payload(om_b) or {}).get("mini_opra") or [])
            v = "PASS" if a >= c else "WARN"
            rows.append({"sym": "OPRA", "verdict": v, "why": f"mini priced {len(a)} vs box {len(c)}; missing {sorted(c - a)[:5]}"})
            worst = max(worst, v, key=RANK.get)
        real = [r for r in rows if r["verdict"] not in ("SKIP", "INFO")]
        return {"verdict": worst if real else "NO_DATA", "rows": rows}

    def macro(self) -> dict:
        s = _read(self.shadow / "market-data/latest/macro-public.json")
        b = _read(self.root / "market-data/latest/macro-spot.json")
        if not s:
            return {"verdict": "NO_DATA", "rows": []}
        p = _payload(s) or {}
        rows, worst = [], "PASS"
        vx = (p.get("vix") or {})
        bv = None
        for it in ((_payload(b) or {}).get("items") or []):
            if it.get("id") == "vix":
                bv = _f(it.get("spot"))
        if vx.get("value") is None:
            rows.append({"sym": "VIX", "verdict": "WARN", "why": f"no VIX ({vx.get('errors')})"})
            worst = "WARN"
        elif bv is not None:
            d = abs(float(vx["value"]) - bv)
            v = "PASS" if d <= 0.15 else "WARN"
            rows.append({"sym": "VIX", "verdict": v, "why": f"mini {vx['value']} ({vx.get('provider')}) vs box {bv}"})
            worst = max(worst, v, key=RANK.get)
        fred = p.get("fred") or {}
        bad = [k for k, v in fred.items() if isinstance(v, dict) and v.get("error")]
        rows.append({"sym": "FRED", "verdict": "WARN" if bad else "PASS", "why": f"{len(fred) - len(bad)}/{len(fred)} series ok"})
        if bad:
            worst = max(worst, "WARN", key=RANK.get)
        rows.append({"sym": "EIA", "verdict": "INFO", "why": json.dumps(p.get("eia"))[:120]})
        return {"verdict": worst, "rows": rows}

    def edgar(self) -> dict:
        s = _read(self.shadow / "market-data/latest/premarket-edgar-mini.json")
        b = _read(self.root / "market-data/latest/premarket-edgar.json")
        if not s:
            return {"verdict": "NO_DATA", "rows": []}
        if s.get("error"):
            return {"verdict": "FAIL", "rows": [{"sym": "EDGAR", "verdict": "FAIL", "why": s["error"]}]}
        p = _payload(s) or {}
        bn = sum(len(v) if isinstance(v, list) else 1 for v in ((_payload(b) or {}).get("filings") or {}).values())
        return {"verdict": "PASS", "rows": [{"sym": "EDGAR", "verdict": "PASS",
                                             "why": f"mini {p.get('counts')} since {p.get('since')}; box RH index filings {bn}"}]}

    def status(self) -> dict:
        s = _read(self.shadow / "market-data/latest/mini-status.json")
        if not s:
            return {"verdict": "NO_DATA", "rows": []}
        p = _payload(s) or {}
        v = "WARN" if p.get("alarm") else "PASS"
        return {"verdict": v, "rows": [{"sym": "ALARM", "verdict": v, "why": ", ".join(p.get("alarm_reasons") or []) or "none"}]}

    def freshness(self, now: float) -> list[dict]:
        out = []
        if not self.shadow.exists():
            return out
        for p in sorted(self.shadow.rglob("*.json")):
            d = _read(p)
            ttl = d.get("ttl_seconds") if isinstance(d, dict) else None
            ts = None
            if isinstance(d, dict):
                ts = _epoch(d.get("as_of")) or _epoch(d.get("written_epoch")) or _epoch(d.get("generated_epoch"))
            age = now - (ts or p.stat().st_mtime)
            out.append({"file": str(p.relative_to(self.shadow)), "age_s": round(age), "ttl_s": ttl,
                        "stale": bool(ttl and age > ttl)})
        return out

    def run(self, session: Optional[str] = None) -> dict:
        now = time.time()
        if session is None:
            try:
                import sys
                sys.path.insert(0, str(self.root / "quotes"))
                sys.path.insert(0, str(self.root / "paper-trades"))
                import mini_client
                session = mini_client.current_session()
            except Exception:  # noqa: BLE001
                session = "closed"
        groups = {"fa": self.fa(), "uw": self.uw(), "bars": self.bars(), "marks": self.marks(session),
                  "macro": self.macro(), "edgar": self.edgar(), "status": self.status()}
        return {"at_pt": datetime.fromtimestamp(now, PT).strftime("%Y-%m-%d %-I:%M %p PT"), "session": session,
                "groups": groups, "freshness": self.freshness(now),
                "flip_ready": [g for g, r in groups.items() if r["verdict"] == "PASS"]}


def render_md(r: dict) -> str:
    lines = [f"# Mini shadow comparison · {r['at_pt']}", "",
             f"Session: {r['session']}. Mini files = `market-data/shadow/`, box = live paths. Research / paper only.", "",
             "| Group | Verdict | Detail |", "| --- | --- | --- |"]
    for g, res in r["groups"].items():
        bad = [x for x in res["rows"] if x["verdict"] in ("WARN", "FAIL")]
        detail = "; ".join(f"{x['sym']}: {x['why']}" for x in bad[:6]) or res.get("note") or f"{len(res['rows'])} rows"
        lines.append(f"| {g} | **{res['verdict']}** | {detail} |")
    lines += ["", f"Flip-ready (PASS): {', '.join(r['flip_ready']) or 'none'}", "", "## Shadow file freshness", "",
              "| File | Age | TTL | Stale |", "| --- | --- | --- | --- |"]
    for f in r["freshness"]:
        lines.append(f"| {f['file']} | {f['age_s']}s | {f['ttl_s'] or '-'} | {'yes' if f['stale'] else ''} |")
    lines += ["", "## Detail", ""]
    for g, res in r["groups"].items():
        lines.append(f"### {g} ({res['verdict']})")
        for x in res["rows"][:60]:
            lines.append(f"- {x['sym']}: {x['verdict']} - {x['why']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Mini shadow comparison report")
    ap.add_argument("--root", type=Path, default=OID)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--session")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = Compare(a.root).run(a.session)
    out = a.out_dir or (a.root / "journal" / "shadow")
    out.mkdir(parents=True, exist_ok=True)
    stem = "SHADOW-" + datetime.now(PT).strftime("%Y%m%d-%H%M")
    (out / f"{stem}.md").write_text(render_md(r))
    (out / f"{stem}.json").write_text(json.dumps(r, indent=1))
    if a.json:
        print(json.dumps(r, indent=1))
    else:
        for g, res in r["groups"].items():
            print(f"{g:7s} {res['verdict']}")
        print(f"report: {out / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
