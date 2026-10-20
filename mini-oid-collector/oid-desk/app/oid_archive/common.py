"""Shared archive helpers: paths, clocks, ET sessions, append-only JSONL writer/reader (stdlib only)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from zoneinfo import ZoneInfo

from . import SCHEMA_VERSION, __version__

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")
UTC = dt.timezone.utc
NS = 1_000_000_000

# NYSE early closes (13:00 ET) for the backfill year + ahead. Extend each year.
HALF_DAYS = {"2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24", "2027-11-26"}
ETFS = {"SPY", "QQQ", "DIA", "RSP", "VTV", "VUG", "TQQQ", "SMH", "SOXX", "EWY", "DRAM"}
TABLES = ("volume_5s", "surges", "bars_1m", "bars_5m", "bars_15m", "bars_1h", "bars_1d", "fetch_log")
WRITER = f"oid-archive@{__version__}"


def data_root() -> Path:
    return Path(os.environ.get("OID_DATA_ROOT", "~/oid-data")).expanduser()


def archive_root() -> Path:
    return Path(os.environ.get("OID_ARCHIVE_ROOT", str(data_root() / "archive"))).expanduser()


def secrets_dir() -> Path:
    return data_root() / "secrets"


def now_ns() -> int:
    return time.time_ns()


def iso_ns(ns: Optional[int]) -> Optional[str]:
    if ns is None:
        return None
    s, frac = divmod(int(ns), NS)
    return dt.datetime.fromtimestamp(s, UTC).strftime("%Y-%m-%dT%H:%M:%S") + f".{frac:09d}Z"


def parse_iso_ns(s: str) -> int:
    """RFC3339 (Z or offset, up to ns) -> epoch ns."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$", s.strip())
    if not m:
        raise ValueError(f"bad timestamp {s!r}")
    base = dt.datetime.fromisoformat(m.group(1) + (m.group(3) or "Z").replace("Z", "+00:00"))
    frac = (m.group(2) or "").ljust(9, "0")[:9]
    return int(base.timestamp()) * NS + int(frac or 0)


def et_date(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / NS, ET).strftime("%Y-%m-%d")


def session_of(ns: int, half_days: Iterable[str] = HALF_DAYS) -> Optional[str]:
    """pre 04:00-09:30, rth 09:30-16:00 (13:00 half days), post to 20:00 ET; None = overnight/weekend."""
    t = dt.datetime.fromtimestamp(ns / NS, ET)
    if t.weekday() >= 5:
        return None
    m = t.hour * 60 + t.minute
    close = 13 * 60 if t.strftime("%Y-%m-%d") in set(half_days) else 16 * 60
    if 240 <= m < 570:
        return "pre"
    if 570 <= m < close:
        return "rth"
    if close <= m < 1200:
        return "post"
    return None


def session_bounds_ns(date: str, session: str, half_days: Iterable[str] = HALF_DAYS) -> tuple[int, int]:
    d = dt.date.fromisoformat(date)
    close = (13, 0) if date in set(half_days) else (16, 0)
    a, b = {"pre": ((4, 0), (9, 30)), "rth": ((9, 30), close), "post": (close, (20, 0))}[session]
    mk = lambda hm: int(dt.datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=ET).timestamp()) * NS  # noqa: E731
    return mk(a), mk(b)


def common(event_ns: int, ingest_ns: Optional[int] = None, writer: str = WRITER) -> dict[str, Any]:
    ing = now_ns() if ingest_ns is None else ingest_ns
    return {"schema_version": SCHEMA_VERSION, "event_ts_ns": int(event_ns), "event_ts_iso": iso_ns(event_ns),
            "ingest_ts_ns": int(ing), "ingest_ts_iso": iso_ns(ing), "writer": writer}


class JsonlWriter:
    """Append-only `<root>/<table>/date=YYYY-MM-DD/part-<writer>-<seq>.jsonl`. One instance = one writer per table.
    seq is chosen once per (process, date) as 1 + the highest existing seq for this writer, so a restart never
    appends into another process's file. Full lines + flush per batch; never raises (returns False on error)."""

    def __init__(self, table: str, writer_name: str, root: Optional[Path] = None):
        self.table, self.writer_name = table, re.sub(r"[^A-Za-z0-9_.-]", "-", writer_name)
        self.root = Path(root) if root else archive_root()
        self._paths: dict[str, Path] = {}
        self.errors = 0
        self.rows = 0

    def path_for(self, date: str) -> Path:
        p = self._paths.get(date)
        if p is None:
            d = self.root / self.table / f"date={date}"
            d.mkdir(parents=True, exist_ok=True)
            pat = re.compile(rf"^part-{re.escape(self.writer_name)}-(\d+)\.jsonl$")
            seqs = [int(m.group(1)) for f in d.iterdir() if (m := pat.match(f.name))]
            p = d / f"part-{self.writer_name}-{(max(seqs) + 1) if seqs else 1}.jsonl"
            self._paths = {date: p}  # keep only the current date open
        return p

    def write(self, rows: list[dict[str, Any]]) -> bool:
        if not rows:
            return True
        try:
            by_date: dict[str, list[str]] = {}
            for r in rows:
                by_date.setdefault(et_date(r["event_ts_ns"]), []).append(json.dumps(r, separators=(",", ":"), allow_nan=False))
            for date, lines in sorted(by_date.items()):
                with open(self.path_for(date), "a") as f:
                    f.write("\n".join(lines) + "\n")
                    f.flush()
            self.rows += len(rows)
            return True
        except Exception:  # noqa: BLE001 - archive writes must never break the caller
            self.errors += 1
            return False


def iter_jsonl(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    """Rows from JSONL parts; a trailing partial line (writer mid-append) or a bad line is skipped."""
    for p in sorted(paths):
        try:
            with open(p, "rb") as f:
                data = f.read()
        except OSError:
            continue
        lines = data.split(b"\n")
        if data and not data.endswith(b"\n"):
            lines = lines[:-1]
        for ln in lines:
            if not ln.strip():
                continue
            try:
                yield json.loads(ln)
            except ValueError:
                continue


def partition_dir(table: str, date: str, parquet: bool = False, root: Optional[Path] = None) -> Path:
    r = Path(root) if root else archive_root()
    return (r / "parquet" / table / f"date={date}") if parquet else (r / table / f"date={date}")


def jsonl_parts(table: str, date: str, root: Optional[Path] = None) -> list[Path]:
    d = partition_dir(table, date, root=root)
    return sorted(d.glob("part-*.jsonl")) if d.exists() else []


def read_universe(path: Optional[str] = None) -> list[str]:
    """The collector's stock universe (61 names since v0.4.1)."""
    cands = [path] if path else [os.environ.get("OID_UNIVERSE_FILE"), "~/oid-quote/stream-quote-allowlist.json",
                                  "~/oid-quote/app/stream-quote-allowlist.json"]
    for c in cands:
        if c and Path(c).expanduser().exists():
            d = json.loads(Path(c).expanduser().read_text())
            syms = d.get("underlyings") if isinstance(d, dict) else d
            return sorted({s.upper() for s in syms or [] if s})
    raise FileNotFoundError("stream-quote-allowlist.json not found")


def read_secret_file(p: Path) -> Optional[str]:
    try:
        v = Path(p).expanduser().read_text().strip()
        return v or None
    except OSError:
        return None


def atomic_write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True))
    os.replace(tmp, p)
