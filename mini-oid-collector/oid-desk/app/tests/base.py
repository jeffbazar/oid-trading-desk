"""Temp mini layout for tests: OID_DESK_ROOT/{desk,flags,...}, OID_SECRETS_DIR, fake launchctl."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]          # minihost/  or  ~/oid-desk/app
JOBS = APP / "jobs.json"
BIN = APP / "bin" if (APP / "bin" / "run-job.sh").exists() else APP.parent / "bin"

CATALOG = {
    "version": "T", "shadow_root": "market-data/shadow",
    "groups": {
        "uw": {"files": ["market-data/latest/uw-net-prem.json", "chart-bot/whale-flow/latest/*.json"], "box_daemons": []},
        "fa": {"files": ["market-data/latest/fa-focus-levels.json"], "box_daemons": []},
        "status": {"files": ["market-data/latest/mini-status.json"], "box_daemons": []},
    },
    "desk_state": ["paper-trades/trades.json", "config/focus-watch.json"],
    "desk_state_max_bytes": 100000,
}


class MiniCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="oid-mini-test-"))
        self.root = self.tmp / "oid-desk"
        self.desk = self.root / "desk"
        self.secrets = self.tmp / "secrets"
        for d in (self.desk / "config", self.desk / "market-data" / "latest", self.desk / "cache", self.secrets,
                  self.root / "flags", self.root / "state", self.root / "overrides", self.root / "env"):
            d.mkdir(parents=True, exist_ok=True)
        (self.desk / "config" / "mirror-feeds.json").write_text(json.dumps(CATALOG))
        self._env = dict(os.environ)
        os.environ.update({"OID_DESK_ROOT": str(self.root), "OID_DESK_DIR": str(self.desk),
                           "OID_SECRETS_DIR": str(self.secrets), "OID_DESK_JOBS": str(JOBS),
                           "OID_DESK_FAKE_LAUNCHCTL": "1", "OID_LAUNCH_AGENTS": str(self.tmp / "LaunchAgents")})
        for k in ("UW_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "EIA_API_KEY"):
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)
        from oid_desk import net
        net.set_opener(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def secret(self, name: str, value: str) -> None:
        (self.secrets / name).write_text(value + "\n")

    def put(self, rel: str, obj) -> Path:
        p = self.desk / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)
        return p
