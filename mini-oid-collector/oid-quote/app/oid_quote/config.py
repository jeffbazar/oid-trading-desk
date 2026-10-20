"""Configuration: built-in defaults <- <root>/config.json <- env vars <- CLI flags."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent.parent  # .../app (or the unpacked source folder)

VALID_STOCK_FEEDS = {"sip", "iex", "delayed_sip", "boats", "overnight", "test"}
VALID_OPTION_FEEDS = {"opra", "indicative"}


@dataclass
class Config:
    root: Path = field(default_factory=lambda: Path(os.path.expanduser("~/oid-quote")))
    host: str = "0.0.0.0"  # Tailscale-only bind comes later; set to the 100.x IP then.
    port: int = 8787

    # Stocks (Alpaca market data v2). sip = consolidated (Algo Trader Plus); iex = fallback.
    stock_feed: str = "sip"
    stock_feed_fallback: str | None = "iex"
    fallback_retry_primary_s: float = 1800.0
    stocks_ws_base: str = "wss://stream.data.alpaca.markets/v2"
    stock_channels: list[str] = field(default_factory=lambda: ["quotes", "trades"])
    # Overnight (8 PM-4 AM ET, Sun night -> Fri morning): the SAME single stock connection is moved from
    # `stock_feed` to this feed on a session schedule (never two stock sockets at once). null/"off" disables.
    stock_overnight_feed: str | None = "overnight"
    overnight_ws_base: str = "wss://stream.data.alpaca.markets/v1beta1"
    feed_schedule_interval_s: float = 10.0

    # Options (Alpaca v1beta1, msgpack only). opra = real-time; indicative = derived/delayed.
    options_feed: str = "opra"
    options_feed_fallback: str | None = None
    options_ws_base: str = "wss://stream.data.alpaca.markets/v1beta1"
    option_channels: list[str] = field(default_factory=lambda: ["quotes", "trades"])
    option_cap: int = 1000
    enable_options: bool = True
    # v0.3.0: seed subscribed contracts that have no quote yet (new subs, weekends, pre-open) from Alpaca's
    # market-data REST snapshot (latest quote + trade). Data-only endpoint; same keys; read-only GET.
    option_seed_enabled: bool = True
    options_snapshot_url: str = "https://data.alpaca.markets/v1beta1/options/snapshots"
    option_seed_interval_s: float = 15.0
    option_seed_retry_s: float = 300.0

    # live volume v1 (2026-10-18): seconds-level rolling volume from SIP prints + ws 1-min bars + 1-min norms
    live_volume_enabled: bool = True
    volume_5s_enabled: bool = True  # v0.5.0 archive writer (volume_5s + live bars_1m); inert unless ~/oid-data exists
    archive_dir: str | None = None  # default ~/oid-data/archive (env OID_ARCHIVE_ROOT)
    stock_bar_channels: list[str] = field(default_factory=lambda: ["bars", "updatedBars"])
    stock_bar_feeds: list[str] = field(default_factory=lambda: ["sip", "iex"])  # never on the overnight socket
    live_store_dir: str | None = None  # default ~/oid-desk/desk/cache/bars/store (else <root>/cache/bars/store)
    live_tick_s: float = 1.0
    ws_bar_grace_s: float = 15.0
    norm_lookback: int = 20
    full_session_min_bars: int = 30  # thin names: minute gaps allowed (missing = 0); must trade into 15:50 ET
    min_norm_sessions: int = 5
    vol_surge_state_dir: str = "~/oid-desk/state/triggers"  # trigger engine state (events.jsonl, volsurge-status.json); read-only
    backfill_calendar_days: int = 36
    backfill_check_s: float = 60.0
    finalize_after_et: str = "16:20"
    half_days: list[str] = field(default_factory=lambda: ["2026-11-27", "2026-12-24", "2027-11-26"])

    allowlist_path: str | None = None  # default: <root>/stream-quote-allowlist.json if present, else app copy
    options_subs_path: str | None = None  # default: <root>/options-subs.json

    snapshot_interval_s: float = 2.0
    subs_poll_interval_s: float = 5.0
    keys_poll_interval_s: float = 15.0
    stale_after_s: float = 120.0
    prune_unsubscribed_after_s: float = 6 * 3600.0
    backoff_initial_s: float = 1.0
    backoff_max_s: float = 60.0
    ws_heartbeat_s: float = 20.0

    log_max_bytes: int = 5_000_000
    log_backups: int = 5
    log_to_stderr: bool = True

    # ---- derived paths ----
    @property
    def secrets_dir(self) -> Path:
        return self.root / "secrets"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def cache_file(self) -> Path:
        return self.cache_dir / "quotes.json"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "collector.log"

    def resolved_allowlist(self) -> Path:
        if self.allowlist_path:
            return Path(os.path.expanduser(self.allowlist_path))
        override = self.root / "stream-quote-allowlist.json"
        if override.exists():
            return override
        return APP_DIR / "stream-quote-allowlist.json"

    def resolved_options_subs(self) -> Path:
        if self.options_subs_path:
            return Path(os.path.expanduser(self.options_subs_path))
        return self.root / "options-subs.json"

    def public_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            v = getattr(self, f.name)
            out[f.name] = str(v) if isinstance(v, Path) else v
        out["allowlist_resolved"] = str(self.resolved_allowlist())
        out["options_subs_resolved"] = str(self.resolved_options_subs())
        return out


ENV_MAP = {
    "OID_QUOTE_HOST": ("host", str),
    "OID_QUOTE_PORT": ("port", int),
    "OID_QUOTE_STOCK_FEED": ("stock_feed", str),
    "OID_QUOTE_STOCK_FEED_FALLBACK": ("stock_feed_fallback", str),
    "OID_QUOTE_STOCK_OVERNIGHT_FEED": ("stock_overnight_feed", str),
    "OID_QUOTE_OVERNIGHT_WS_BASE": ("overnight_ws_base", str),
    "OID_QUOTE_OPTIONS_FEED": ("options_feed", str),
    "OID_QUOTE_STOCKS_WS_BASE": ("stocks_ws_base", str),
    "OID_QUOTE_OPTIONS_WS_BASE": ("options_ws_base", str),
    "OID_QUOTE_OPTIONS_SNAPSHOT_URL": ("options_snapshot_url", str),
}


def _apply(cfg: Config, key: str, value: Any) -> None:
    names = {f.name for f in fields(Config)}
    if key not in names or key == "root":
        return
    if isinstance(value, str) and value.lower() in {"", "none", "null", "off"} and (key.endswith("fallback") or key == "stock_overnight_feed"):
        value = None
    setattr(cfg, key, value)


def load_config(root: str | None = None, config_path: str | None = None, overrides: dict[str, Any] | None = None) -> Config:
    root_s = root or os.environ.get("OID_QUOTE_ROOT") or "~/oid-quote"
    cfg = Config(root=Path(os.path.expanduser(root_s)).resolve())
    path = Path(os.path.expanduser(config_path)) if config_path else cfg.root / "config.json"
    if path.exists():
        data = json.loads(path.read_text())
        for k, v in data.items():
            if not k.startswith("_"):
                _apply(cfg, k, v)
    for env, (key, typ) in ENV_MAP.items():
        if env in os.environ:
            _apply(cfg, key, typ(os.environ[env]))
    for k, v in (overrides or {}).items():
        if v is not None:
            _apply(cfg, k, v)
    if cfg.stock_feed not in VALID_STOCK_FEEDS:
        raise ValueError(f"stock_feed must be one of {sorted(VALID_STOCK_FEEDS)}")
    if cfg.stock_overnight_feed is not None and cfg.stock_overnight_feed not in VALID_STOCK_FEEDS:
        raise ValueError(f"stock_overnight_feed must be null or one of {sorted(VALID_STOCK_FEEDS)}")
    if cfg.options_feed not in VALID_OPTION_FEEDS:
        raise ValueError(f"options_feed must be one of {sorted(VALID_OPTION_FEEDS)}")
    cfg.option_cap = max(0, min(int(cfg.option_cap), 1000))
    return cfg
