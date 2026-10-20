#!/usr/bin/env python3
"""Box read-only mirror of the Mac mini desk feeds (+ desk-state push). Research / paper only - zero execution.

Each cycle (15 s RTH / 60 s otherwise):
  1. GET  <mini>:8788/v1/feeds                 (read token)  manifest {name, group, sha256, as_of}
  2. for groups in shadow|live: when the local target's sha differs, GET /v1/feed?name=..., verify sha256, then
       shadow -> market-data/shadow/<name>
       live   -> <name> or catalog live_target[name]; JSON with an older as_of than the local file is NOT written
  3. marks group live + something changed -> hook apply_marks (file-only live_refresh on the box ledger, <=1/min)
  4. every push_every_s: POST /v1/desk-state with changed allow-listed desk files (write token)
Heartbeat cache/mirror-poller.json. Kill switch cache/mirror.disabled. Config config/mirror.json, catalog
config/mirror-feeds.json. Tokens are read from files and never printed.

  python3 quotes/mirror_poller.py once|loop|status|push-now|fetch-write-token
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote

OID = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OID / "quotes"))
sys.path.insert(0, str(OID / "paper-trades"))

Opener = Callable[[urllib.request.Request, float], tuple[int, bytes, dict]]


def _now_pt() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %-I:%M:%S %p PT")


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def _sha(p: Path) -> Optional[str]:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _as_of_key(obj: Any) -> Optional[float]:
    """Comparable freshness for envelope/heartbeat JSON (epoch seconds) or None when unknown."""
    if not isinstance(obj, dict):
        return None
    for k in ("written_epoch", "generated_epoch", "epoch"):
        if isinstance(obj.get(k), (int, float)):
            return float(obj[k])
    from datetime import datetime, timezone
    for k in ("as_of",):
        v = obj.get(k)
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
            except ValueError:
                pass
    return None


class Mirror:
    def __init__(self, root: Path = OID, *, opener: Optional[Opener] = None, session_fn=None,
                 hook_runner: Optional[Callable[[list[str]], int]] = None):
        self.root = root
        self.cfg = _read_json(root / "config" / "mirror.json") or {}
        self.cat = _read_json(root / "config" / "mirror-feeds.json") or {"groups": {}}
        self._opener = opener or self._default_open
        self._session_fn = session_fn
        self._hook_runner = hook_runner or self._run_hook
        self.state_path = root / "cache" / "mirror-poller.json"
        self.push_state_path = root / "cache" / "mirror-push-state.json"

    # ---------------------------------------------------------------- http
    def _default_open(self, req: urllib.request.Request, timeout: float) -> tuple[int, bytes, dict]:
        proxy = self.cfg.get("proxy")
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy} if proxy else {}))
        try:
            with op.open(req, timeout=timeout) as fh:
                return fh.status, fh.read(), dict(fh.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers or {})

    def _token(self, key: str) -> Optional[str]:
        p = Path(os.environ.get("OID_MIRROR_" + key.upper(), self.cfg.get(key) or ""))
        try:
            v = p.read_text(encoding="utf-8").strip()
            return v or None
        except OSError:
            return None

    def _req(self, path: str, *, token_key: str = "read_token_file", data: Optional[bytes] = None) -> tuple[int, bytes, dict]:
        tok = self._token(token_key)
        if not tok:
            raise RuntimeError(f"{token_key} missing")
        h = {"Authorization": f"Bearer {tok}", "User-Agent": "oid-box-mirror/1"}
        if data is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.cfg.get("base_url", "").rstrip("/") + path, headers=h, data=data,
                                     method="POST" if data is not None else "GET")
        return self._opener(req, float(self.cfg.get("timeout_s", 8)))

    # ---------------------------------------------------------------- targets
    def mode(self, group: str) -> str:
        return (self.cfg.get("groups") or {}).get(group, "off")

    def target(self, name: str, group: str) -> Optional[Path]:
        m = self.mode(group)
        if m == "shadow":
            return self.root / self.cat.get("shadow_root", "market-data/shadow") / name
        if m == "live":
            lt = (self.cat["groups"].get(group) or {}).get("live_target") or {}
            return self.root / lt.get(name, name)
        return None

    @staticmethod
    def _safe(name: str) -> bool:
        return bool(name) and not name.startswith("/") and ".." not in Path(name).parts

    # ---------------------------------------------------------------- pull
    def pull(self) -> dict:
        res: dict[str, Any] = {"written": [], "unchanged": 0, "skipped_older": [], "errors": {}, "groups": {}}
        code, body, _ = self._req("/v1/feeds")
        if code != 200:
            raise RuntimeError(f"/v1/feeds http {code}")
        feeds = json.loads(body).get("feeds", [])
        catalog_groups = set(self.cat.get("groups", {}))
        for f in feeds:
            name, group = f.get("name", ""), f.get("group", "")
            if group not in catalog_groups or not self._safe(name):
                continue
            tgt = self.target(name, group)
            g = res["groups"].setdefault(group, {"mode": self.mode(group), "files": 0, "written": 0})
            if tgt is None:
                continue
            g["files"] += 1
            if _sha(tgt) == f.get("sha256"):
                res["unchanged"] += 1
                continue
            try:
                c, data, hdr = self._req("/v1/feed?name=" + quote(name, safe="/"))
                if c != 200:
                    raise RuntimeError(f"http {c}")
                if hashlib.sha256(data).hexdigest() != hdr.get("X-OID-SHA256", f.get("sha256")):
                    raise RuntimeError("sha256 mismatch")
                if self.mode(group) == "live" and tgt.suffix == ".json" and tgt.exists():
                    old_k, new_k = _as_of_key(_read_json(tgt)), _as_of_key(json.loads(data or b"null"))
                    if old_k is not None and new_k is not None and new_k < old_k:
                        res["skipped_older"].append(name)
                        continue
                _atomic(tgt, data)
                res["written"].append(name)
                g["written"] += 1
            except Exception as e:  # noqa: BLE001
                res["errors"][name] = f"{type(e).__name__}: {str(e)[:120]}"
        return res

    # ---------------------------------------------------------------- hooks
    def _run_hook(self, cmd: list[str]) -> int:
        return subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, timeout=240).returncode

    def apply_marks(self, written: list[str], st: dict) -> Optional[dict]:
        if self.mode("marks") != "live":
            return None
        marks_files = set((self.cat["groups"].get("marks") or {}).get("files", []))
        if not any(n in marks_files for n in written):
            return None
        last = float(st.get("apply_marks_epoch") or 0)
        if time.time() - last < float(self.cfg.get("apply_marks_every_s", 60)):
            return {"skipped": "throttled"}
        src = self.root / "cache" / "mirror" / "mini-rh-quotes.json"
        rec = _read_json(src) or {}
        quotes = ((rec.get("payload") or {}).get("quotes") or {})
        if not quotes:
            return {"skipped": "no mirrored equity quotes"}
        eq = self.root / "tmp" / "mirror-equity-quotes.json"
        _atomic(eq, json.dumps(quotes).encode())
        rc = self._hook_runner([sys.executable, str(self.root / "dashboard" / "live_refresh.py"),
                                "--equity-quotes-file", str(eq), "--options-from-mini", "--skip-rebuild"])
        st["apply_marks_epoch"] = time.time()
        return {"rc": rc}

    # ---------------------------------------------------------------- push
    def push(self, *, force: bool = False) -> dict:
        if not self.cfg.get("push_desk_state", True):
            return {"skipped": "push disabled"}
        if not self._token("write_token_file"):
            return {"skipped": "no write token"}
        ps = _read_json(self.push_state_path) or {}
        if not force and time.time() - float(ps.get("epoch") or 0) < float(self.cfg.get("push_every_s", 60)):
            return {"skipped": "not due"}
        shas = ps.get("shas") or {}
        files: dict[str, Any] = {}
        new_shas = dict(shas)
        for rel in self.cat.get("desk_state", []):
            p = self.root / rel
            s = _sha(p)
            if s is None or (s == shas.get(rel) and not force):
                continue
            obj = _read_json(p)
            if obj is None:
                continue
            files[rel] = obj
            new_shas[rel] = s
        out: dict[str, Any] = {"files": sorted(files)}
        if files:
            body = json.dumps({"files": files}).encode()
            if len(body) > int(self.cat.get("desk_state_max_bytes", 4_000_000)):
                return {"error": "desk-state too large", "bytes": len(body)}
            code, data, _ = self._req("/v1/desk-state", token_key="write_token_file", data=body)
            out["http"] = code
            if code not in (200, 207):
                return out
            out["result"] = json.loads(data or b"{}")
            for rel in (out["result"].get("rejected") or {}):
                new_shas.pop(rel, None)
        _atomic(self.push_state_path, json.dumps({"epoch": time.time(), "at_pt": _now_pt(), "shas": new_shas}).encode())
        return out

    def fetch_write_token(self) -> str:
        code, body, _ = self._req("/v1/desk-write-token")
        if code != 200:
            return f"not armed (http {code}); run on the mini: ~/oid-desk/bin/oidctl token-handoff"
        d = json.loads(body)
        dst = Path(self.cfg.get("write_token_file"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        old = os.umask(0o077)
        try:
            dst.write_text(d["value"] + "\n")
        finally:
            os.umask(old)
        os.chmod(dst, 0o600)
        return f"saved write token to {dst} (600, not printed)"

    # ---------------------------------------------------------------- cycle
    def session(self) -> str:
        if self._session_fn:
            return self._session_fn()
        try:
            import mini_client
            return mini_client.current_session()
        except Exception:  # noqa: BLE001
            return "closed"

    def cycle(self) -> dict:
        st = _read_json(self.state_path) or {}
        out: dict[str, Any] = {"at_pt": _now_pt(), "epoch": time.time(), "ok": False, "session": self.session(),
                               "modes": dict(self.cfg.get("groups") or {}), "writer": "quotes/mirror_poller.py"}
        if (self.root / "cache" / "mirror.disabled").exists():
            out.update(ok=True, skipped="cache/mirror.disabled")
        else:
            try:
                r = self.pull()
                out.update(pull={k: (v if k != "written" else len(v)) for k, v in r.items()}, written=r["written"][:50])
                out["hook"] = self.apply_marks(r["written"], st)
                out["push"] = self.push()
                out["ok"] = not r["errors"]
                out["last_ok_epoch"] = time.time()
            except Exception as e:  # noqa: BLE001
                out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        out["last_ok_epoch"] = out.get("last_ok_epoch") or st.get("last_ok_epoch")
        out["apply_marks_epoch"] = st.get("apply_marks_epoch")
        _atomic(self.state_path, json.dumps(out, indent=1, default=str).encode())
        return out

    def loop(self) -> None:
        pidf = self.root / "cache" / "mirror-poller.pid"
        _atomic(pidf, str(os.getpid()).encode())
        while True:
            t0 = time.time()
            r = self.cycle()
            iv = float(self.cfg.get("interval_rth_s", 15) if r.get("session") == "rth" else self.cfg.get("interval_other_s", 60))
            time.sleep(max(2.0, iv - (time.time() - t0)))
            self.cfg = _read_json(self.root / "config" / "mirror.json") or self.cfg  # hot reload (cutover flips)
            self.cat = _read_json(self.root / "config" / "mirror-feeds.json") or self.cat


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID box mirror of the Mac mini desk feeds")
    ap.add_argument("cmd", choices=["once", "loop", "status", "push-now", "fetch-write-token"])
    a = ap.parse_args(argv)
    m = Mirror()
    if a.cmd == "loop":
        m.loop()
        return 0
    if a.cmd == "status":
        print(json.dumps(_read_json(m.state_path) or {"status": "never ran"}, indent=1))
        return 0
    if a.cmd == "push-now":
        print(json.dumps(m.push(force=True), indent=1))
        return 0
    if a.cmd == "fetch-write-token":
        print(m.fetch_write_token())
        return 0
    r = m.cycle()
    print(json.dumps({k: r.get(k) for k in ("at_pt", "ok", "session", "pull", "hook", "push", "error", "skipped")}, indent=1, default=str))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
