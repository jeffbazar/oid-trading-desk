"""Frozen v1 column lists (SCHEMAS.md §2-§7). type names: string,int64,int32,int16,int8,float64,bool."""
from __future__ import annotations

from typing import Any

COMMON = [("schema_version", "string"), ("event_ts_ns", "int64"), ("event_ts_iso", "string"),
          ("ingest_ts_ns", "int64"), ("ingest_ts_iso", "string"), ("writer", "string")]

_BAR = [("symbol", "string"), ("timeframe", "string"), ("bar_start_ns", "int64"), ("bar_start_iso", "string"),
        ("bar_end_ns", "int64"), ("session", "string"), ("open", "float64"), ("high", "float64"), ("low", "float64"),
        ("close", "float64"), ("volume", "int64"), ("vwap", "float64"), ("trade_count", "int32"), ("src", "string"),
        ("feed", "string"), ("adjustment", "string"), ("final", "bool"), ("revised_ts_ns", "int64")]
_ROLL = _BAR + [("n_1m_bars", "int16"), ("span_s", "int32")]

TABLE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "volume_5s": [("symbol", "string"), ("bucket_start_ns", "int64"), ("bucket_start_iso", "string"),
                  ("bucket_end_ns", "int64"), ("session", "string"), ("volume", "int64"), ("trade_count", "int32"),
                  ("open", "float64"), ("high", "float64"), ("low", "float64"), ("close", "float64"), ("vwap", "float64"),
                  ("rvol_1m_at_end", "float64"), ("pace_rvol_10s_at_end", "float64"), ("stream_feed", "string"),
                  ("stream_ok", "bool"), ("late_prints", "int32")],
    "surges": [("surge_id", "string"), ("symbol", "string"), ("trigger", "string"), ("gate", "string"), ("mode", "string"),
               ("fire_ts_ns", "int64"), ("fire_ts_iso", "string"), ("session", "string"), ("direction", "string"),
               ("move_60s_bps", "float64"), ("last", "float64"), ("bid", "float64"), ("ask", "float64"),
               ("spread_bps", "float64"), ("rvol_1m", "float64"), ("pace_rvol_10s", "float64"), ("pace_rvol_30s", "float64"),
               ("shares_10s", "int64"), ("shares_60s", "int64"), ("floor_shares_60s", "int64"), ("norm_1m", "float64"),
               ("day_rvol", "float64"), ("crossed_level", "bool"), ("level_name", "string"), ("level_price", "float64"),
               ("is_etf", "bool"), ("notify_status", "string"), ("x_fetch_status", "string"), ("config_hash", "string"),
               ("lag_ms", "float64")],
    "bars_1m": _BAR, "bars_5m": _ROLL, "bars_15m": _ROLL, "bars_1h": _ROLL,
    "bars_1d": [("symbol", "string"), ("trade_date", "string"), ("bar_start_ns", "int64"), ("bar_start_iso", "string"),
                ("open", "float64"), ("high", "float64"), ("low", "float64"), ("close", "float64"), ("volume", "int64"),
                ("vwap", "float64"), ("trade_count", "int64"), ("split_factor", "float64"), ("half_day", "bool"),
                ("src", "string"), ("final", "bool")],
    "fetch_log": [("fetch_id", "string"), ("component", "string"), ("endpoint", "string"), ("method", "string"),
                  ("params_redacted", "string"), ("surge_id", "string"), ("symbols", "string"), ("started_ns", "int64"),
                  ("started_iso", "string"), ("finished_ns", "int64"), ("latency_ms", "float64"), ("http_status", "int32"),
                  ("n_items", "int32"), ("bytes", "int64"), ("rate_limit_limit", "int32"), ("rate_limit_remaining", "int32"),
                  ("rate_limit_reset_ns", "int64"), ("est_cost_usd", "float64"), ("error_class", "string"), ("error_msg", "string")],
}
TABLE_COLUMNS = {k: v + COMMON for k, v in TABLE_COLUMNS.items()}

KEYS = {"volume_5s": ("symbol", "bucket_start_ns"), "surges": ("surge_id",), "bars_1m": ("symbol", "bar_start_ns"),
        "bars_5m": ("symbol", "bar_start_ns"), "bars_15m": ("symbol", "bar_start_ns"), "bars_1h": ("symbol", "bar_start_ns"),
        "bars_1d": ("symbol", "trade_date"), "fetch_log": ("fetch_id",)}


def columns(table: str) -> list[str]:
    return [c for c, _ in TABLE_COLUMNS[table]]


def schema_json(table: str) -> dict[str, Any]:
    return {"schema_version": "v1", "table": table, "key": list(KEYS[table]),
            "columns": [{"name": c, "type": t} for c, t in TABLE_COLUMNS[table]], "source": "SCHEMAS.md v1 (2026-10-18)"}


def conform(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Exactly the frozen columns, in order; missing -> None; values coerced to the column type."""
    out = {}
    for c, t in TABLE_COLUMNS[table]:
        v = row.get(c)
        if v is not None:
            try:
                if t.startswith("int"):
                    v = int(round(v)) if isinstance(v, float) else int(v)
                elif t == "float64":
                    v = float(v)
                elif t == "bool":
                    v = bool(v)
                elif t == "string":
                    v = str(v)
            except (TypeError, ValueError):
                v = None
        out[c] = v
    return out
