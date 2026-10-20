"""Read-only /v1/archive/* routes for the mini data API (:8788, tailnet only; SCHEMAS §10).
Auth: `Authorization: Bearer <~/oid-data/secrets/OID_ARCHIVE_READ_TOKEN>` only (separate from the quote/desk tokens).
Raw text columns (raw_json, text) are dropped unless include_text=1. Never writes anything.
Quality: GET /v1/archive/quality[?table=&symbol=&date=] lists exclusions (quality/exclusions.json). /rows and /bars
never drop rows by default; apply_exclusions=1 filters matching rows. /bars always reports matching exclusions in `quality`."""
from __future__ import annotations

import hmac
import json
import re
from typing import Any, Optional

from .common import NS, parse_iso_ns, read_secret_file, secrets_dir
from .schemas import KEYS, columns, schema_json

TEXT_COLS = {"raw_json", "text"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SYM_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")


def authorized(header: Optional[str]) -> tuple[bool, int, str]:
    tok = read_secret_file(secrets_dir() / "OID_ARCHIVE_READ_TOKEN")
    if not tok:
        return False, 503, "archive_token_not_configured"
    got = (header or "")[7:].strip() if (header or "").startswith("Bearer ") else ""
    if not got or not hmac.compare_digest(got.encode(), tok.encode()):
        return False, 401, "unauthorized"
    return True, 200, ""


def _q(q: dict, k: str, default: Optional[str] = None) -> Optional[str]:
    v = q.get(k)
    return (v[0] if isinstance(v, list) else v) if v else default


def _ts(s: str) -> int:
    return int(s) if s.isdigit() else parse_iso_ns(s if "T" in s else s + "T00:00:00Z")


def handle(path: str, q: dict, auth_header: Optional[str]) -> tuple[int, Any, str]:
    """Returns (status, body, content_type). body is a JSON-able object or bytes."""
    ok, code, why = authorized(auth_header)
    if not ok:
        return code, {"error": why}, "application/json"
    from . import quality, reader
    if path == "/v1/archive/tables":
        qd = quality.load()
        return 200, {"tables": reader.tables_summary(), "quality": {"exclusions": len(qd["exclusions"]),
                     "updated_iso": qd.get("updated_iso"), "route": "/v1/archive/quality"}}, "application/json"
    if path == "/v1/archive/quality":
        t, date, sym = _q(q, "table"), _q(q, "date"), (_q(q, "symbol") or "").upper() or None
        if (t and t not in KEYS) or (date and not DATE_RE.match(date)) or (sym and not SYM_RE.match(sym)):
            return 400, {"error": "bad_query"}, "application/json"
        qd = quality.load()
        ex = qd["exclusions"]
        if t:
            ex = quality.matching(t, date, sym, doc=qd)
        elif sym:
            ex = [e for e in ex if e.get("symbol") == sym]
        return 200, {"schema_version": qd.get("schema_version", "v1"), "updated_iso": qd.get("updated_iso"),
                     "exclusions": ex}, "application/json"
    if path == "/v1/archive/schema":
        t = _q(q, "table")
        if t not in KEYS:
            return 404, {"error": "unknown_table"}, "application/json"
        return 200, schema_json(t), "application/json"
    if path == "/v1/archive/rows":
        t, date = _q(q, "table"), _q(q, "date") or ""
        if t not in KEYS:
            return 404, {"error": "unknown_table"}, "application/json"
        if not DATE_RE.match(date):
            return 400, {"error": "bad_date"}, "application/json"
        sym = (_q(q, "symbol") or "").upper() or None
        if sym and not SYM_RE.match(sym):
            return 400, {"error": "bad_symbol"}, "application/json"
        cols = [c for c in (_q(q, "cols") or "").split(",") if c] or None
        exs = quality.matching(t, date, sym) if _q(q, "apply_exclusions") == "1" else []
        strip_sym = bool(exs and cols and "symbol" not in cols)
        rows, src = reader.partition_rows(t, date, sym, (cols + ["symbol"]) if strip_sym else cols)
        if exs:  # partition date is authoritative; match on each row's symbol
            rows = [r for r in rows if not any(quality._hit(e, t, r.get("symbol") or "", date) for e in exs)]
            if strip_sym:
                rows = [{k: v for k, v in r.items() if k != "symbol"} for r in rows]
        if _q(q, "include_text") != "1":
            rows = [{k: v for k, v in r.items() if k not in TEXT_COLS} for r in rows]
        if _q(q, "format") == "parquet":
            import io
            import pyarrow as pa
            import pyarrow.parquet as pq
            buf = io.BytesIO()
            pq.write_table(pa.Table.from_pylist(rows), buf, compression="zstd")
            return 200, buf.getvalue(), "application/vnd.apache.parquet"
        body = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + ("\n" if rows else "")).encode()
        return 200, body, "application/x-ndjson"
    if path == "/v1/archive/bars":
        sym, tf = (_q(q, "symbol") or "").upper(), _q(q, "tf", "1m")
        if not SYM_RE.match(sym) or tf not in reader.TF_TABLE:
            return 400, {"error": "bad_symbol_or_tf"}, "application/json"
        try:
            a, b = _ts(_q(q, "start") or ""), _ts(_q(q, "end") or "")
        except (ValueError, TypeError):
            return 400, {"error": "bad_range"}, "application/json"
        if b <= a or b - a > 400 * 86400 * NS:
            return 400, {"error": "bad_range"}, "application/json"
        rows = reader.bars(sym, tf, a, b, cap=20000)
        table = reader.TF_TABLE[tf]
        exs = quality.matching(table, None, sym)
        dropped = 0
        if exs and _q(q, "apply_exclusions") == "1":
            n0 = len(rows)
            rows = [r for r in rows if not quality.excluded(r, table, exs)]
            dropped = n0 - len(rows)
        keep = [c for c in columns(reader.TF_TABLE[tf]) if c not in ("event_ts_iso", "ingest_ts_iso", "writer", "schema_version")]
        return 200, {"symbol": sym, "tf": tf, "n": len(rows), "capped": len(rows) >= 20000,
                     "quality": {"exclusions": exs, "applied": _q(q, "apply_exclusions") == "1", "dropped": dropped},
                     "bars": [{k: r.get(k) for k in keep} for r in rows]}, "application/json"
    return 404, {"error": "not_found"}, "application/json"
