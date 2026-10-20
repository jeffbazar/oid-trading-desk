"""news_surge (log-only) + the `surges` archive table (schema v1, SCHEMAS.md §3) for the fast vol loop.

Imported by oid_triggers.py --vol-surge-loop. Stdlib only, Python 3.9+ (the mini runs /usr/bin/python3 3.9).
news_surge NEVER posts to the webhook; it only writes archive rows (+ a local news-surge-events.jsonl).
Archive writes are inert unless the data root (~/oid-data) exists, and never raise into the loop.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

SURGES_VERSION = "0.5.0"
WRITER = f"oid-triggers@{SURGES_VERSION}"
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000

NS_DEFAULTS = {
    "enabled": True,              # news_surge detection (log-only; there is no live/notify switch on purpose)
    "min_rvol_1m": 3.0,           # gate A
    "min_pace_rvol_10s": 6.0,     # gate B (with shares_10s >= floor/4)
    "rearm_min": 10.0,            # (i) >= 10 min since the last fire for the ticker
    "rearm_rvol_below": 1.5,      # (ii) rvol_1m < 1.5 ...
    "rearm_below_s": 120.0,       # ... for >= 2 consecutive minutes
    "etfs": ["SPY", "QQQ", "DIA", "RSP", "VTV", "VUG", "TQQQ", "SMH", "SOXX", "EWY", "DRAM"],
}
ARCHIVE_DEFAULTS = {"enabled": True, "root": "~/oid-data/archive",
                    "quotes_url": "http://127.0.0.1:8787/v1/quotes", "quote_max_age_s": 5.0}



def x_fetch_status_for(sym: str) -> str:
    """Phase 3: pending when fetch_enabled; else disabled. Reads live config if present."""
    try:
        import json as _json
        from pathlib import Path as _P
        for cand in (_P("~/oid-data/config/x-on-surge-config.json").expanduser(),
                     _P("~/oid-desk/x-on-surge/lib/x-on-surge-config.json").expanduser()):
            if cand.is_file():
                if bool(_json.loads(cand.read_text()).get("fetch_enabled")):
                    return "pending"
                return "disabled"
    except Exception:
        pass
    return "disabled"


def ns_cfg(cfg: dict) -> dict:
    c = dict(NS_DEFAULTS)
    c.update({k: v for k, v in ((cfg or {}).get("news_surge") or {}).items() if not str(k).startswith("_")})
    return c


def arch_cfg(cfg: dict) -> dict:
    c = dict(ARCHIVE_DEFAULTS)
    c.update({k: v for k, v in ((cfg or {}).get("archive") or {}).items() if not str(k).startswith("_")})
    return c


def config_hash(cfg: dict) -> str:
    blob = json.dumps({"vol_surge": (cfg or {}).get("vol_surge"), "news_surge": ns_cfg(cfg)}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def iso_ns(ns: int) -> str:
    s, frac = divmod(int(ns), NS)
    return dt.datetime.fromtimestamp(s, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{frac:09d}Z"


def et_date(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / NS, ET).strftime("%Y-%m-%d")


class SurgeIds:
    """{TICKER}-{YYYYMMDDTHHMMSSZ}-{news|vol}; same-second collisions get -2, -3, ..."""

    def __init__(self):
        self.used: Dict[str, int] = {}

    def make(self, sym: str, t: float, trigger: str) -> str:
        base = f"{sym}-{dt.datetime.fromtimestamp(int(t), dt.timezone.utc):%Y%m%dT%H%M%SZ}-{trigger}"
        n = self.used.get(base, 0) + 1
        self.used[base] = n
        if len(self.used) > 5000:
            self.used = {base: n}
        return base if n == 1 else f"{base}-{n}"


class JsonlWriter:
    """Same layout as oid_archive.common.JsonlWriter: <root>/<table>/date=YYYY-MM-DD/part-<writer>-<seq>.jsonl."""

    def __init__(self, table: str, writer_name: str, root: Path):
        self.table, self.writer_name, self.root = table, writer_name, Path(root)
        self._paths: Dict[str, Path] = {}
        self.errors = 0
        self.rows = 0

    def path_for(self, date: str) -> Path:
        p = self._paths.get(date)
        if p is None:
            d = self.root / self.table / f"date={date}"
            d.mkdir(parents=True, exist_ok=True)
            pat = re.compile(rf"^part-{re.escape(self.writer_name)}-(\d+)\.jsonl$")
            seqs = [int(m.group(1)) for m in (pat.match(f.name) for f in d.iterdir()) if m]
            p = d / f"part-{self.writer_name}-{(max(seqs) + 1) if seqs else 1}.jsonl"
            self._paths = {date: p}
        return p

    def write(self, rows: List[dict]) -> bool:
        if not rows:
            return True
        try:
            by: Dict[str, List[str]] = {}
            for r in rows:
                by.setdefault(et_date(r["event_ts_ns"]), []).append(json.dumps(r, separators=(",", ":"), allow_nan=False))
            for date, lines in sorted(by.items()):
                with open(self.path_for(date), "a") as f:
                    f.write("\n".join(lines) + "\n")
            self.rows += len(rows)
            return True
        except Exception:  # noqa: BLE001
            self.errors += 1
            return False


def floor_for(vc: dict, sym: str, row: dict) -> float:
    """vol_surge's share floor: per_symbol_min_shares_60s[SYM], else norm_median_1m clamped to [low, min_shares_60s]."""
    per = vc.get("per_symbol_min_shares_60s") or {}
    if per.get(sym) is not None:
        return float(per[sym])
    med = row.get("norm_median_1m")
    if med is None:
        return float(vc["min_shares_60s"])
    return min(float(vc["min_shares_60s"]), max(float(vc["min_shares_floor_low"]), float(med)))


class NewsSurge:
    def __init__(self, state_dir: Path, cfg: dict):
        self.state_path = Path(state_dir) / "newssurge-state.json"
        self.cfg = cfg
        try:
            self.st = json.loads(self.state_path.read_text())
        except Exception:  # noqa: BLE001
            self.st = {}

    def _roll(self, t: float) -> None:
        d = dt.datetime.fromtimestamp(t, ET).strftime("%Y-%m-%d")
        if self.st.get("date") != d:
            self.st = {"date": d, "syms": {}}

    def check(self, live: dict, t: float, vc: dict) -> List[Tuple[str, dict, str]]:
        """Returns [(sym, row, gate)] for tickers that fire now. Caller has already applied vol_surge's global gate
        (RTH, first 2 min, half day, stream health, norms current). Updates re-arm tracking for every symbol."""
        nc = ns_cfg(self.cfg)
        self._roll(t)
        if not nc.get("enabled"):
            return []
        out = []
        syms = self.st["syms"]
        for sym, row in (live.get("symbols") or {}).items():
            rv = row.get("rvol_1m")
            s = syms.get(sym)
            if s and not s.get("armed"):  # re-arm tracking after a fire
                if rv is not None and rv < float(nc["rearm_rvol_below"]):
                    if s.get("below_since") is None:
                        s["below_since"] = t
                    if (t - float(s["last_fire"]) >= float(nc["rearm_min"]) * 60
                            and t - float(s["below_since"]) >= float(nc["rearm_below_s"])):
                        s["armed"] = True  # both conditions met; stays armed until the next fire
                else:
                    s["below_since"] = None
                if not s.get("armed"):
                    continue
            if row.get("last") is None:
                continue
            if (row.get("lag_s") or 0) > float(vc["max_lag_s"]) or (row.get("last_age_s") or 1e9) > float(vc["max_last_age_s"]):
                continue
            fl = floor_for(vc, sym, row)
            v60, v10, pace = row.get("vol_60s") or 0, row.get("vol_10s") or 0, row.get("pace_rvol_10s")
            ga = rv is not None and rv >= float(nc["min_rvol_1m"]) and v60 >= fl
            gb = pace is not None and pace >= float(nc["min_pace_rvol_10s"]) and v10 >= fl / 4.0
            if not (ga or gb):
                continue
            syms[sym] = {"last_fire": t, "below_since": None, "armed": False}
            out.append((sym, row, "AB" if ga and gb else ("A" if ga else "B")))
        return out

    def save(self) -> None:
        try:
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.st, indent=1)); tmp.replace(self.state_path)
        except Exception:  # noqa: BLE001
            pass


def fetch_quotes(url: str, token: Optional[str], syms: List[str], timeout: float = 1.0) -> Dict[str, dict]:
    if not token or not syms:
        return {}
    try:
        req = urllib.request.Request(f"{url}?symbols={','.join(sorted(set(syms)))}",
                                     headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (json.loads(r.read().decode()).get("quotes") or {})
    except Exception:  # noqa: BLE001 - never log URL/token
        return {}


def surge_row(*, surge_id: str, sym: str, trigger: str, gate: str, t: float, row: dict, vc: dict, cfg: dict,
              crossed: Optional[Tuple[str, float]], notify_status: str, quote: Optional[dict], qmax: float,
              ingest_ns: Optional[int] = None) -> dict:
    fire_ns = int(t * NS)
    last, ref = row.get("last"), row.get("px_60s_ago")
    move = ((float(last) / float(ref) - 1) * 1e4) if (last and ref) else None
    direction = None if move is None else ("flat" if abs(move) < 1 else ("up" if move > 0 else "down"))
    bid = ask = spread = None
    if quote and quote.get("source_age_s") is not None and float(quote["source_age_s"]) <= qmax:
        bid, ask = quote.get("bid"), quote.get("ask")
        if bid and ask and float(ask) >= float(bid) > 0:
            spread = (float(ask) - float(bid)) / ((float(ask) + float(bid)) / 2) * 1e4
    ing = time.time_ns() if ingest_ns is None else ingest_ns
    lag = row.get("lag_s")
    return {
        "surge_id": surge_id, "symbol": sym, "trigger": trigger, "gate": gate, "mode": "dry",
        "fire_ts_ns": fire_ns, "fire_ts_iso": iso_ns(fire_ns), "session": "rth", "direction": direction,
        "move_60s_bps": move, "last": last, "bid": bid, "ask": ask, "spread_bps": spread,
        "rvol_1m": row.get("rvol_1m"), "pace_rvol_10s": row.get("pace_rvol_10s"), "pace_rvol_30s": row.get("pace_rvol_30s"),
        "shares_10s": row.get("vol_10s"), "shares_60s": row.get("vol_60s"), "floor_shares_60s": int(floor_for(vc, sym, row)),
        "norm_1m": row.get("norm_1m"), "day_rvol": row.get("day_rvol"), "crossed_level": bool(crossed),
        "level_name": crossed[0] if crossed else None, "level_price": crossed[1] if crossed else None,
        "is_etf": sym in set(ns_cfg(cfg)["etfs"]), "notify_status": notify_status, "x_fetch_status": x_fetch_status_for(sym),
        "config_hash": config_hash(cfg), "lag_ms": (float(lag) * 1000.0) if lag is not None else None,
        "schema_version": "v1", "event_ts_ns": fire_ns, "event_ts_iso": iso_ns(fire_ns),
        "ingest_ts_ns": ing, "ingest_ts_iso": iso_ns(ing), "writer": WRITER,
    }


class SurgeArchive:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        ac = arch_cfg(cfg)
        self.root = Path(os.path.expanduser(ac["root"]))
        self.w = JsonlWriter("surges", "oid-triggers", self.root)

    def enabled(self) -> bool:
        return bool(arch_cfg(self.cfg).get("enabled")) and self.root.parent.exists()

    def write(self, rows: List[dict]) -> bool:
        return self.w.write(rows) if (rows and self.enabled()) else False
