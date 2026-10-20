"""Job registry (jobs.json) + launchd plist rendering + flags. Used by oidctl, status and install."""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from . import util

def launch_agents() -> Path:
    return Path(os.environ.get("OID_LAUNCH_AGENTS", str(Path.home() / "Library" / "LaunchAgents")))


def jobs_file() -> Path:
    return Path(os.environ.get("OID_DESK_JOBS", str(util.root() / "app" / "jobs.json")))


def load() -> dict:
    d = util.read_json(jobs_file())
    if not isinstance(d, dict) or "jobs" not in d:
        raise RuntimeError(f"jobs registry missing/invalid: {jobs_file()}")
    return d


def label(reg: dict, job: str) -> str:
    return reg.get("label_prefix", "com.oid.desk.") + job


def flag(job: str) -> Path:
    return util.root() / "flags" / f"{job}.disabled"


def is_enabled(job: str) -> bool:
    return not flag(job).exists()


def render_plist(reg: dict, job: str, *, py: str) -> bytes:
    spec = reg["jobs"][job]
    r = util.root()
    cwd_key = spec.get("cwd", "desk")
    cwd = r / cwd_key if cwd_key in ("app", "desk") or cwd_key.startswith("desk/") else r / "desk"
    args = [str(r / "bin" / "run-job.sh"), job] + [a.replace("{py}", py) for a in spec["cmd"]]
    env = {"OID_DESK_ROOT": str(r), "OID_DESK_DIR": str(r / "desk"), "PYTHONPATH": str(r / "app"),
           "PYTHONUNBUFFERED": "1", "OID_SECRETS_DIR": str(util.secrets_dir()),
           "OID_MINI_URL": "http://127.0.0.1:8787", "OID_MINI_PROXY": "",
           "OID_QUOTE_TOKEN_FILE": str(util.secrets_dir() / "OID_QUOTE_TOKEN"),
           "HERENOW_PUBLISH_SCRIPT": str(r / "app" / "vendor" / "herenow-publish.sh"),
           "PATH": f"{Path(py).parent}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"}
    env.update(spec.get("env") or {})
    pl: dict[str, Any] = {
        "Label": label(reg, job), "ProgramArguments": args, "WorkingDirectory": str(cwd),
        "EnvironmentVariables": env, "RunAtLoad": True, "ProcessType": "Background",
        "StandardOutPath": str(r / "logs" / f"{job}.out.log"), "StandardErrorPath": str(r / "logs" / f"{job}.err.log"),
        "ThrottleInterval": 15, "LowPriorityIO": True, "Nice": 5,
    }
    if spec["kind"] == "interval":
        pl["StartInterval"] = int(spec["interval_s"])
    else:
        pl["KeepAlive"] = {"SuccessfulExit": False}
    return plistlib.dumps(pl)


def launchctl(*args: str) -> tuple[int, str]:
    if sys.platform != "darwin" or os.environ.get("OID_DESK_FAKE_LAUNCHCTL"):
        log = util.root() / "state" / "launchctl-fake.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as fh:
            fh.write(" ".join(args) + "\n")
        return 0, "fake"
    p = subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=20)
    return p.returncode, (p.stdout + p.stderr)[-2000:]


def domain() -> str:
    return f"gui/{os.getuid()}"


def launchd_state(reg: dict, job: str) -> dict:
    """{'loaded': bool, 'running': bool, 'pid': int|None, 'last_exit': str|None} (darwin only)."""
    if sys.platform != "darwin" or os.environ.get("OID_DESK_FAKE_LAUNCHCTL"):
        return {"loaded": None, "running": None, "pid": None, "last_exit": None}
    rc, out = launchctl("print", f"{domain()}/{label(reg, job)}")
    if rc != 0:
        return {"loaded": False, "running": False, "pid": None, "last_exit": None}
    st = {"loaded": True, "running": False, "pid": None, "last_exit": None}
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("state = "):
            st["running"] = s.endswith("running")
        elif s.startswith("pid = "):
            try:
                st["pid"] = int(s.split("=")[1])
            except ValueError:
                pass
        elif s.startswith("last exit code = "):
            st["last_exit"] = s.split("=", 1)[1].strip()
    return st


def enable(reg: dict, job: str, *, py: str, force: bool = False) -> str:
    spec = reg["jobs"][job]
    if spec.get("hold") and not force:
        return f"REFUSED {job}: {spec['hold']} (use --force only after the owner agrees)"
    r = util.root()
    src = r / "launchd" / f"{label(reg, job)}.plist"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(render_plist(reg, job, py=py))
    launch_agents().mkdir(parents=True, exist_ok=True)
    dst = launch_agents() / src.name
    dst.write_bytes(src.read_bytes())
    flag(job).unlink(missing_ok=True)
    launchctl("bootout", f"{domain()}/{label(reg, job)}")
    rc, out = launchctl("bootstrap", domain(), str(dst))
    return f"enabled {job} (bootstrap rc={rc})" + ("" if rc == 0 else f": {out.strip()[:300]}")


def disable(reg: dict, job: str) -> str:
    f = flag(job)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(util.now_pt_str() + "\n")
    rc, _ = launchctl("bootout", f"{domain()}/{label(reg, job)}")
    (launch_agents() / f"{label(reg, job)}.plist").unlink(missing_ok=True)
    return f"disabled {job} (bootout rc={rc}; flag {f})"
