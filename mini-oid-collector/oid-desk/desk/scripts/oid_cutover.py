#!/usr/bin/env python3
"""Cutover / rollback of one feed group from the box daemons to the Mac mini (MINI-MIGRATION-PLAN phases 2-3).

  python3 scripts/oid_cutover.py status
  python3 scripts/oid_cutover.py shadow  <group|all>   mirror writes market-data/shadow/ only (default)
  python3 scripts/oid_cutover.py flip    <group>       mirror -> live paths, box daemons for the group: flag + stop
  python3 scripts/oid_cutover.py rollback <group>      mirror -> shadow, clear flags, restart box daemons now
  python3 scripts/oid_cutover.py off     <group>       mirror ignores the group (box daemons untouched)
Groups and their box daemons come from config/mirror-feeds.json. Flags are the same files the mini-link
watchdog already honours, so a rollback is also self-healing within 60 s. Never touches the mini: the
mini-side step for each flip is printed (run it via the deploy runbook on mars.local).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

OID = Path(__file__).resolve().parents[1]

DAEMONS = {
    "uw-refresh":  {"flag": "cache/uw-refresh.disabled",  "stop": ["scripts/uw-refresh.sh", "stop"],  "start": ["scripts/uw-refresh.sh", "start"]},
    "whale-flow":  {"flag": "cache/whale-flow.disabled",  "stop": ["chart-bot/whale-flow/run.sh", "stop"], "start": ["chart-bot/whale-flow/run.sh", "ensure"]},
    "focus-watch": {"flag": "cache/focus-watch.disabled", "stop": ["scripts/focus-watch.sh", "stop"], "start": ["scripts/focus-watch.sh", "start"]},
    "bars-poller": {"flag": "cache/bars-poller.disabled", "stop": ["scripts/bars-poller.sh", "stop"], "start": ["scripts/bars-poller.sh", "start"]},
    "mini-poller": {"flag": "cache/mini-poller.disabled", "stop": ["scripts/mini-poller.sh", "stop"], "start": ["scripts/mini-poller.sh", "start"]},
}
MINI_STEPS = {
    "uw": "on the mini: rm ~/oid-desk/overrides/uw-refresh.json && ~/oid-desk/bin/oidctl disable uw-refresh && ~/oid-desk/bin/oidctl enable uw-refresh (then box: python3 quotes/mirror_poller.py push-now so the un-overridden config lands)",
    "fa": "on the mini: rm ~/oid-desk/overrides/focus-watch.json && ~/oid-desk/bin/oidctl disable fa-focus && ~/oid-desk/bin/oidctl enable fa-focus (then box: python3 quotes/mirror_poller.py push-now)",
    "bars": "none (mini bars job already full cadence)",
    "marks": "on the mini: rm ~/oid-desk/env/option-subs.env && ~/oid-desk/bin/oidctl disable option-subs && ~/oid-desk/bin/oidctl enable option-subs  (mini becomes the only OPRA subs declarer)",
    "macro": "none", "edgar": "none", "status": "none",
}
MODES = ("off", "shadow", "live")


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _save(p: Path, d: dict) -> None:
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2) + "\n")
    os.replace(tmp, p)


class Cutover:
    def __init__(self, root: Path = OID, runner: Optional[Callable[[list[str]], int]] = None):
        self.root = root
        self.cfg_path = root / "config" / "mirror.json"
        self.cat = _load(root / "config" / "mirror-feeds.json")
        self.runner = runner or (lambda cmd: subprocess.run(cmd, cwd=str(root), env=os.environ.copy()).returncode)
        self.log = root / "cache" / "cutover.log"

    def _log(self, msg: str) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S %Z ") + msg + "\n")
        print(msg)

    def groups(self, g: str) -> list[str]:
        allg = list(self.cat["groups"])
        if g == "all":
            return allg
        if g not in allg:
            raise SystemExit(f"unknown group {g}; known: {', '.join(allg)}")
        return [g]

    def set_mode(self, group: str, mode: str) -> None:
        cfg = _load(self.cfg_path)
        cfg.setdefault("groups", {})[group] = mode
        _save(self.cfg_path, cfg)

    def daemons(self, group: str) -> list[str]:
        return list(self.cat["groups"][group].get("box_daemons") or [])

    def flip(self, group: str) -> None:
        cfg = _load(self.cfg_path)
        if (cfg.get("groups") or {}).get(group) != "shadow":
            raise SystemExit(f"{group}: flip only from shadow (now {cfg.get('groups', {}).get(group)}) - shadow first and check the compare report")
        self.set_mode(group, "live")
        for d in self.daemons(group):
            spec = DAEMONS[d]
            (self.root / spec["flag"]).write_text(f"cutover flip {group} {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
            rc = self.runner([str(self.root / spec["stop"][0]), *spec["stop"][1:]])
            self._log(f"flip {group}: {d} flagged + stopped (rc={rc})")
        self._log(f"flip {group}: mirror -> live. Mini step: {MINI_STEPS.get(group, 'none')}")

    def rollback(self, group: str) -> None:
        self.set_mode(group, "shadow")
        for d in self.daemons(group):
            spec = DAEMONS[d]
            (self.root / spec["flag"]).unlink(missing_ok=True)
            rc = self.runner([str(self.root / spec["start"][0]), *spec["start"][1:]])
            self._log(f"rollback {group}: {d} flag cleared + started (rc={rc})")
        self._log(f"rollback {group}: mirror -> shadow (box daemons own the live files again)")

    def status(self) -> dict:
        cfg = _load(self.cfg_path)
        out = {}
        for g in self.cat["groups"]:
            out[g] = {"mode": (cfg.get("groups") or {}).get(g, "off"),
                      "box_daemons": {d: ("flagged-off" if (self.root / DAEMONS[d]["flag"]).exists() else "box-owned")
                                      for d in self.daemons(g)}}
        return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["status", "shadow", "flip", "rollback", "off"])
    ap.add_argument("group", nargs="?")
    a = ap.parse_args(argv)
    c = Cutover()
    if a.cmd == "status":
        print(json.dumps(c.status(), indent=1))
        return 0
    if not a.group:
        ap.error("group required")
    for g in c.groups(a.group):
        if a.cmd == "flip":
            c.flip(g)
        elif a.cmd == "rollback":
            c.rollback(g)
        else:
            c.set_mode(g, a.cmd)
            c._log(f"{g}: mirror mode -> {a.cmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
