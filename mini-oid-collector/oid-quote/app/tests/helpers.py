from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
from pathlib import Path

from oid_quote.config import APP_DIR, load_config

KEY_ENV = ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "OID_QUOTE_TOKEN")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def clear_env() -> None:
    for k in KEY_ENV:
        os.environ.pop(k, None)


def make_root(token: str | None = "test-token-abcdef123456", options: list[str] | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="oidq-test-"))
    for d in ("secrets", "app", "logs", "cache"):
        (root / d).mkdir()
    shutil.copy(APP_DIR / "stream-quote-allowlist.json", root / "stream-quote-allowlist.json")
    if token:
        (root / "secrets" / "OID_QUOTE_TOKEN").write_text(token + "\n")
    (root / "options-subs.json").write_text(json.dumps(options or []))
    return root


def fast_config(root: Path, port: int, **over):
    base = dict(
        host="127.0.0.1",
        port=port,
        snapshot_interval_s=0.2,
        subs_poll_interval_s=0.2,
        keys_poll_interval_s=0.2,
        backoff_initial_s=0.1,
        backoff_max_s=0.5,
        log_to_stderr=False,
        stock_overnight_feed="off",  # deterministic: tests that need the schedule turn it on explicitly
        feed_schedule_interval_s=0.1,
        live_store_dir=str(root / "cache" / "bars" / "store"),  # never the real desk store in tests
    )
    base.update(over)
    return load_config(root=str(root), overrides=base)
