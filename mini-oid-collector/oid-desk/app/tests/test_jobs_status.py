import json
import os
import plistlib
import subprocess
import time
from pathlib import Path

from oid_desk import jobs as J
from oid_desk import status as S

from .base import BIN, MiniCase


class JobsTest(MiniCase):
    def test_every_job_renders_and_is_disabled_by_flag(self):
        reg = J.load()
        for job in reg["jobs"]:
            pl = plistlib.loads(J.render_plist(reg, job, py="/x/venv/bin/python"))
            self.assertEqual(pl["Label"], "com.oid.desk." + job)
            self.assertTrue(pl["ProgramArguments"][0].endswith("bin/run-job.sh"))
            self.assertEqual(pl["ProgramArguments"][1], job)
            self.assertEqual(pl["EnvironmentVariables"]["OID_MINI_URL"], "http://127.0.0.1:8787")
            self.assertEqual(pl["EnvironmentVariables"]["OID_MINI_PROXY"], "")
            if reg["jobs"][job]["kind"] == "interval":
                self.assertIn("StartInterval", pl)
            else:
                self.assertEqual(pl["KeepAlive"], {"SuccessfulExit": False})

    def test_enable_disable_roundtrip_and_hold(self):
        reg = J.load()
        J.disable(reg, "uw-refresh")
        self.assertFalse(J.is_enabled("uw-refresh"))
        msg = J.enable(reg, "uw-refresh", py="/x/python")
        self.assertIn("enabled", msg)
        self.assertTrue(J.is_enabled("uw-refresh"))
        self.assertTrue((self.tmp / "LaunchAgents" / "com.oid.desk.uw-refresh.plist").exists())
        J.disable(reg, "uw-refresh")
        self.assertFalse((self.tmp / "LaunchAgents" / "com.oid.desk.uw-refresh.plist").exists())
        self.assertIn("REFUSED", J.enable(reg, "benzinga", py="/x/python"))
        self.assertFalse((self.tmp / "LaunchAgents" / "com.oid.desk.benzinga.plist").exists())

    def test_publish_job_sets_all_sessions(self):
        reg = J.load()
        pl = plistlib.loads(J.render_plist(reg, "publish", py="/p"))
        self.assertEqual(pl["EnvironmentVariables"]["OID_PUBLISH_ALL_SESSIONS"], "1")


class StatusTest(MiniCase):
    def test_disabled_never_alarms_enabled_stale_does(self):
        reg = J.load()
        for job in reg["jobs"]:
            J.disable(reg, job)
        r = S.evaluate(reg, sess="rth", collector={"ok": True})
        self.assertFalse(r["alarm"])
        (self.root / "flags" / "uw-refresh.disabled").unlink()
        r = S.evaluate(reg, sess="rth", collector={"ok": True})
        self.assertIn("uw-refresh:stale", r["alarm_reasons"])
        hb = self.put("cache/uw-refresh.json", {"ok": 1})
        r = S.evaluate(reg, sess="rth", collector={"ok": True})
        self.assertFalse(r["alarm"], r["alarm_reasons"])
        os.utime(hb, (time.time() - 3600, time.time() - 3600))
        self.assertTrue(S.evaluate(reg, sess="rth", collector={"ok": True})["alarm"])
        self.assertFalse(S.evaluate(reg, sess="closed", collector={"ok": False})["alarm"])

    def test_collector_down_alarms_in_session(self):
        reg = J.load()
        for job in reg["jobs"]:
            J.disable(reg, job)
        r = S.evaluate(reg, sess="rth", collector={"ok": False, "status": "unreachable:URLError"})
        self.assertEqual(r["alarm_reasons"], ["collector:unreachable:URLError"])


class RunJobTest(MiniCase):
    def run_job(self, job, *cmd, extra_env=None):
        env = dict(os.environ, OID_DESK_PY=__import__("sys").executable, **(extra_env or {}))
        (self.root / "app").mkdir(exist_ok=True)
        (self.root / "app" / "jobs.json").write_text(Path(os.environ["OID_DESK_JOBS"]).read_text())
        return subprocess.run(["bash", str(BIN / "run-job.sh"), job, *cmd], env=env, capture_output=True, text=True)

    def test_flag_blocks_start(self):
        (self.root / "flags" / "uw-refresh.disabled").write_text("x")
        out = self.tmp / "ran"
        r = self.run_job("uw-refresh", "touch", str(out))
        self.assertEqual(r.returncode, 0)
        self.assertFalse(out.exists())
        r = self.run_job("uw-refresh", "touch", str(out), extra_env={"OID_DESK_IGNORE_FLAG": "1"})
        self.assertFalse(out.exists())  # still blocked: UW_API_KEY missing
        self.assertIn("required secret UW_API_KEY missing", (self.root / "logs" / "uw-refresh.log").read_text())

    def test_secret_exported_and_env_file(self):
        self.secret("UW_API_KEY", "uwvalue")
        (self.root / "env" / "uw-refresh.env").write_text("# c\nOID_X=1\nbad-key=2\n")
        out = self.tmp / "env.txt"
        r = self.run_job("uw-refresh", "bash", "-c", f'echo "$UW_API_KEY|$OID_X" > {out}')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out.read_text().strip(), "uwvalue|1")
        self.assertNotIn("uwvalue", (self.root / "logs" / "uw-refresh.log").read_text())

    def test_optional_secret(self):
        out = self.tmp / "m"
        r = self.run_job("macro-public", "touch", str(out))
        self.assertEqual(r.returncode, 0)
        self.assertTrue(out.exists())
