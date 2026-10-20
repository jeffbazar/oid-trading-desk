"""oidctl: list | status | enable JOB.. | disable JOB.. | enable-group G | disable-group G | all-off |
run JOB (foreground, same env as launchd, ignores flag) | token-handoff [--minutes N] | selfcheck |
read-token add NAME [--rotate] | read-token revoke NAME | read-token list | read-token handoff NAME --from IP [--minutes N]

Every job ships disabled. enable = render plist -> ~/Library/LaunchAgents + bootstrap + clear flag.
disable = write flag + bootout + remove plist (rollback for any job is `oidctl disable <job>`).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Optional

from . import jobs as J
from . import status as S
from . import util


def _py() -> str:
    return os.environ.get("OID_DESK_PY", str(util.root() / "venv" / "bin" / "python"))


def _expand(reg: dict, names: list[str]) -> list[str]:
    out = []
    for n in names:
        if n not in reg["jobs"]:
            raise SystemExit(f"unknown job {n}; known: {', '.join(reg['jobs'])}")
        out.append(n)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="oidctl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "status", "enable", "disable", "enable-group", "disable-group", "all-off",
                                    "run", "token-handoff", "selfcheck", "read-token"])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--force", action="store_true", help="enable a job on hold (owner agreed)")
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--rotate", action="store_true", help="read-token add: replace an existing token")
    ap.add_argument("--from", dest="from_ip", help="read-token handoff: the only Tailscale IP allowed to fetch")
    a = ap.parse_args(argv)
    if a.cmd == "read-token":
        return _read_token(a)
    reg = J.load()
    if a.cmd == "list":
        for j, s in reg["jobs"].items():
            print(f"{j:13s} {'on ' if J.is_enabled(j) else 'off'}  {s.get('group',''):7s} {s['kind']:8s} {s.get('desc','')}"
                  + (f"  [HOLD: {s['hold']}]" if s.get("hold") else ""))
        return 0
    if a.cmd == "status":
        r = S.evaluate(reg)
        print(json.dumps({k: r[k] for k in ("session", "alarm", "alarm_reasons", "collector")}, indent=1))
        for row in r["jobs"]:
            print(f"  {row['job']:13s} {row['state']:8s} age={row['age_s']} ttl={row['ttl_s']} launchd={row['launchd']}")
        return 1 if r["alarm"] else 0
    if a.cmd in ("enable", "disable"):
        for j in _expand(reg, a.names):
            print(J.enable(reg, j, py=_py(), force=a.force) if a.cmd == "enable" else J.disable(reg, j))
        return 0
    if a.cmd in ("enable-group", "disable-group"):
        sel = [j for j, s in reg["jobs"].items() if s.get("group") in a.names]
        for j in sel:
            print(J.enable(reg, j, py=_py(), force=a.force) if a.cmd == "enable-group" else J.disable(reg, j))
        return 0
    if a.cmd == "all-off":
        for j in reg["jobs"]:
            print(J.disable(reg, j))
        return 0
    if a.cmd == "run":
        import plistlib
        j = _expand(reg, a.names[:1])[0]
        pl = plistlib.loads(J.render_plist(reg, j, py=_py()))
        env = dict(os.environ, **pl["EnvironmentVariables"], OID_DESK_IGNORE_FLAG="1")
        return subprocess.call(pl["ProgramArguments"], cwd=pl["WorkingDirectory"], env=env)
    if a.cmd == "token-handoff":
        f = util.root() / "state" / "token-handoff.json"
        util.atomic_write_json(f, {"armed_pt": util.now_pt_str(), "expires_epoch": time.time() + a.minutes * 60})
        print(f"write-token handoff armed for {a.minutes} min (served once to the box mirror, then disarmed)")
        return 0
    if a.cmd == "selfcheck":
        problems = []
        for j, s in reg["jobs"].items():
            plist = J.render_plist(reg, j, py=_py())
            if b"<key>Label</key>" not in plist:
                problems.append(f"{j}: bad plist")
            for n in s.get("secrets", []):
                if n in (s.get("optional_secrets") or []):
                    continue
                if not (util.secrets_dir() / n).exists():
                    problems.append(f"{j}: secret {n} missing (needed before enable)")
        for need in ("config/mirror-feeds.json", "config/mini-desk.json", "dashboard/live_refresh.py", "quotes/mini_poller.py"):
            if not (util.desk() / need).exists():
                problems.append(f"desk missing {need}")
        print("\n".join(problems) if problems else "selfcheck ok")
        return 0
    return 2


def _read_token(a) -> int:
    from . import tokens as T
    sub, rest = (a.names[0] if a.names else "list"), a.names[1:]
    try:
        if sub == "list":
            rows = T.listing()
            for r in rows:
                print(f"{r['name']:24s} mode={r['mode']} created={r['created_pt']} uses={r['uses']} "
                      f"last_used={r['last_used_pt']} handoff={'ARMED from ' + str(r['handoff_from']) if r['handoff_armed'] else '-'}")
            if not rows:
                print("no named read tokens")
            return 0
        if sub in ("add", "revoke", "handoff") and len(rest) != 1:
            raise SystemExit(f"usage: oidctl read-token {sub} NAME")
        if sub == "add":
            print(T.add(rest[0], rotate=a.rotate))
            return 0
        if sub == "revoke":
            print(T.revoke(rest[0]))
            return 0
        if sub == "handoff":
            if not a.from_ip:
                raise SystemExit("read-token handoff needs --from <tailscale ip of the fetching host>")
            code = T.arm_handoff(rest[0], a.from_ip, a.minutes)
            mins = max(1, min(a.minutes, 60))
            print(f"read-token handoff for {rest[0]} armed for {mins} min, only from {a.from_ip}, single use.")
            print(f"ONE-TIME CODE (give it to the fetching host via secure input only): {code}")
            return 0
    except (ValueError, FileExistsError, FileNotFoundError) as e:
        print(f"error: {e}")
        return 1
    raise SystemExit(f"unknown read-token subcommand {sub}; use add|revoke|list|handoff")


if __name__ == "__main__":
    sys.exit(main())
