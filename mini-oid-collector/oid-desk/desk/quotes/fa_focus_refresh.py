#!/usr/bin/env python3
"""Box-side 5-minute FlashAlpha wall refresh for FOCUS names only (Jeffrey 2026-10-09).

Research / paper only. Calls ONLY GET https://lab.flashalpha.com/v1/flow/levels/{SYM} (live call wall,
put wall, gamma flip, max pain) and the free GET /v1/account for quota. Key read at call time from
secrets/flashalpha-api-key and sent only as the X-Api-Key header - never logged or printed.
Everything else stays on the routines' hourly / Q5 FlashAlpha cadence.

Single desk FlashAlpha client: every box-side FlashAlpha caller (this refresher, focus_watch's thread,
chart-bot whale_flow top-ups, routine --once pulls, the data-sources quota card) goes through _get()
here, so all of them use the Growth account key in secrets/flashalpha-api-key (2,500/day). Never add
a second key, env var or the unkeyed MCP path.

Results go to:
  market-data/latest/fa-focus-levels.json  (this refresher's own file; focus_watch prefers it when newer)
  market-data/latest/fa-levels.json        (merged per symbol via quotes/fa_levels_merge.py; others untouched)
  market-data/latest/api-quotas.json       (payload.flashalpha remaining/usage when checked)

Quota policy (config/focus-watch.json "fa_refresh"): planned calls = focus names x RTH 5-min slots left.
If that exceeds min(daily_budget - used_by_refresher, remaining - reserve_remaining) -> 10-min cadence;
still too much -> open-seat names only; remaining <= hard_floor -> pause (walls go STALE, labelled).
Driven by quotes/focus_watch.py in a background thread (same process), or standalone:
  python3 quotes/fa_focus_refresh.py --once [SYM ...]     python3 quotes/fa_focus_refresh.py --account
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

OID = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OID / "quotes"))
sys.path.insert(0, str(OID / "market-data"))
BASE = "https://lab.flashalpha.com"
KEY_PATH = OID / "secrets" / "flashalpha-api-key"
FOCUS_LEVELS = OID / "market-data" / "latest" / "fa-focus-levels.json"
QUOTAS = OID / "market-data" / "latest" / "api-quotas.json"
STATE = OID / "cache" / "fa-focus-refresh-state.json"
ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")
RTH_SLOTS = 78
DEFAULTS = {"enabled": True, "interval_min": 5, "fallback_interval_min": 10, "daily_budget": 900,
            "reserve_remaining": 500, "hard_floor": 100, "account_check_min": 30, "timeout_s": 10}


def _get(path: str, timeout: float) -> dict:
    key = KEY_PATH.read_text(encoding="utf-8").strip()
    req = urllib.request.Request(BASE + path, headers={"X-Api-Key": key, "Accept": "application/json",
                                                       "User-Agent": "oid-focus-refresh/1"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh)


def account(timeout: float = 10) -> dict:
    a = _get("/v1/account", timeout)
    return {"plan": a.get("plan"), "daily_limit": int(a.get("daily_limit") or 0),
            "usage_today": int(a.get("usage_today") or 0), "remaining": int(a.get("remaining") or 0),
            "resets_at": a.get("resets_at")}


def flow_levels(sym: str, timeout: float = 10) -> dict:
    return _get(f"/v1/flow/levels/{sym}", timeout)


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(p: Path, data) -> None:
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")
    tmp.replace(p)


def _pt(epoch=None) -> str:
    return datetime.fromtimestamp(time.time() if epoch is None else epoch, PT).strftime("%Y-%m-%d %-I:%M:%S %p PT")


def slots_left(now: float) -> int:
    d = datetime.fromtimestamp(now, ET)
    m = d.hour * 60 + d.minute
    return max(0, min(RTH_SLOTS, (960 - m + 4) // 5))


class Refresher:
    def __init__(self, log=lambda m: None):
        self.log = log
        st = _read(STATE, {})
        self.state = {"date": st.get("date"), "calls_today": st.get("calls_today", 0),
                      "last_slot": st.get("last_slot"), "last_account": st.get("last_account"),
                      "last_account_epoch": st.get("last_account_epoch", 0), "mode": st.get("mode"),
                      "last_run_pt": st.get("last_run_pt"), "last_error": st.get("last_error"),
                      "errors_today": st.get("errors_today", 0)}

    def cfg(self, focus_cfg: dict) -> dict:
        c = dict(DEFAULTS)
        c.update(focus_cfg.get("fa_refresh") or {})
        return c

    def plan(self, now: float, focus: dict[str, dict], c: dict) -> dict:
        names = sorted(focus)
        seat_names = sorted(s for s, f in focus.items() if f.get("seats"))
        acct = self.state.get("last_account") or {}
        remaining = acct.get("remaining")
        left = slots_left(now)
        budget_left = max(0, c["daily_budget"] - self.state["calls_today"])
        cap = budget_left if remaining is None else min(budget_left, remaining - c["reserve_remaining"])
        per_day_full = len(names) * RTH_SLOTS
        mode, interval, use = "full_5m", c["interval_min"], names
        if remaining is not None and remaining <= c["hard_floor"]:
            mode, interval, use = "paused_quota_floor", None, []
        elif len(names) * left * (5 / c["interval_min"]) > cap:
            if len(names) * left * (5 / c["fallback_interval_min"]) <= cap:
                mode, interval = "backoff_10m", c["fallback_interval_min"]
            elif len(seat_names) * left * (5 / c["fallback_interval_min"]) <= cap and seat_names:
                mode, interval, use = "seats_only_10m", c["fallback_interval_min"], seat_names
            else:
                mode, interval, use = "paused_budget", None, []
        return {"mode": mode, "interval_min": interval, "symbols": use, "focus_names": names,
                "calls_per_day_full": per_day_full, "slots_left": left, "cap_calls": cap,
                "planned_calls_rest_of_day": (len(use) * left * 5 // interval) if interval else 0,
                "daily_budget": c["daily_budget"], "calls_today": self.state["calls_today"],
                "remaining": remaining, "reserve_remaining": c["reserve_remaining"]}

    def maybe_run(self, now: float, focus: dict[str, dict], focus_cfg: dict, session: str) -> dict | None:
        c = self.cfg(focus_cfg)
        today = datetime.fromtimestamp(now, ET).strftime("%Y-%m-%d")
        if self.state["date"] != today:
            self.state.update({"date": today, "calls_today": 0, "errors_today": 0, "last_slot": None})
        if not c["enabled"] or session != "rth" or not focus:
            return None
        if now - (self.state.get("last_account_epoch") or 0) > c["account_check_min"] * 60:
            try:
                self.state["last_account"] = account(c["timeout_s"])
                self.state["last_account_epoch"] = now
                self._stamp_quota(now)
            except Exception as e:  # noqa: BLE001
                self.state["last_error"] = f"account {type(e).__name__}: {str(e)[:120]}"
                self.state["last_account_epoch"] = now - c["account_check_min"] * 60 + 300  # retry in 5 min
        p = self.plan(now, focus, c)
        self.state["mode"] = p["mode"]
        self.state["plan"] = p
        if not p["interval_min"]:
            self._save()
            return None
        slot = int(now // (p["interval_min"] * 60))
        if self.state["last_slot"] == slot or (now % (p["interval_min"] * 60)) < 10:
            self._save()
            return None  # run once per slot, ~10 s after the slot opens
        self.state["last_slot"] = slot
        return self.refresh(p["symbols"], c, now, plan=p)

    def refresh(self, syms: list[str], c: dict | None = None, now: float | None = None, plan=None) -> dict:
        c = c or dict(DEFAULTS)
        now = time.time() if now is None else now
        today = datetime.fromtimestamp(now, ET).strftime("%Y-%m-%d")
        if self.state["date"] != today:  # --once callers bypass maybe_run's day roll
            self.state.update({"date": today, "calls_today": 0, "errors_today": 0, "last_slot": None})
        results, errors = [], {}
        for s in syms:
            try:
                r = flow_levels(s, c["timeout_s"])
                self.state["calls_today"] += 1
                if r.get("live_call_wall") is None and r.get("live_put_wall") is None:
                    errors[s] = "no_levels"
                    continue
                results.append({k: r.get(k) for k in ("symbol", "as_of", "underlying_price", "live_gamma_flip",
                                                      "gamma_flip_status", "live_call_wall", "live_put_wall",
                                                      "live_max_pain")})
            except urllib.error.HTTPError as e:
                self.state["calls_today"] += 1
                errors[s] = f"http {e.code}"
                if e.code in (402, 429):
                    # Don't assume the Growth account is empty (a 429 can be a burst limit): force a real
                    # /v1/account re-check on the next cycle instead of pinning remaining=0 for 30 min.
                    self.state["last_account_epoch"] = 0
                    self.state["last_error"] = f"{_pt(now)} http {e.code} on {s}; account re-check queued"
            except Exception as e:  # noqa: BLE001
                errors[s] = f"{type(e).__name__}: {str(e)[:100]}"
        merged = []
        if results:
            doc = _read(FOCUS_LEVELS, {"levels": {}})
            for r in results:
                doc.setdefault("levels", {})[r["symbol"].upper()] = {
                    "call_wall": r["live_call_wall"], "put_wall": r["live_put_wall"],
                    "gamma_flip": r["live_gamma_flip"], "gamma_flip_status": r["gamma_flip_status"],
                    "max_pain": r["live_max_pain"], "underlying_price": r["underlying_price"],
                    "as_of": r["as_of"], "fetched_pt": _pt(now), "oi_feed": "get_flow_levels", "freshness": "FRESH"}
            doc.update({"as_of_pt": _pt(now), "written_epoch": now, "writer": "quotes/fa_focus_refresh.py",
                        "source": "FlashAlpha REST /v1/flow/levels (box key)", "mode": (plan or {}).get("mode"),
                        "mandate": "research/paper only"})
            _write(FOCUS_LEVELS, doc)
            try:
                import fa_levels_merge
                merged = fa_levels_merge.merge(results, writer="focus-refresh (box)", source_note="rest")["merged"]
            except Exception as e:  # noqa: BLE001
                errors["_merge"] = f"{type(e).__name__}: {str(e)[:100]}"
        if errors:
            self.state["errors_today"] += 1
            self.state["last_error"] = f"{_pt(now)} {errors}"
        self.state["last_run_pt"] = _pt(now)
        self._save()
        out = {"ok": bool(results), "symbols": syms, "merged": merged, "errors": errors,
               "calls_today": self.state["calls_today"], "at": _pt(now)}
        self.log(f"fa-refresh {json.dumps(out)}")
        return out

    def _stamp_quota(self, now: float) -> None:
        try:
            q = _read(QUOTAS, None)
            if not q:
                return
            a = self.state["last_account"]
            fa = q.setdefault("payload", {}).setdefault("flashalpha", {})
            fa.update({"plan": a["plan"], "daily_limit": a["daily_limit"], "usage_today": a["usage_today"],
                       "remaining": a["remaining"], "resets_at": a["resets_at"],
                       "verified_at": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "focus_refresh_calls_today": self.state["calls_today"]})
            q["as_of"] = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            q["as_of_pt"] = datetime.fromtimestamp(now, PT).strftime("%Y-%m-%d %-I:%M %p PT")
            _write(QUOTAS, q)
        except Exception:  # noqa: BLE001
            pass

    def _save(self) -> None:
        try:
            _write(STATE, self.state)
        except OSError:
            pass


def check_account(stamp: bool = True) -> dict:
    """Growth-account quota check (same key as the refresher); optionally stamps api-quotas + state."""
    r = Refresher()
    now = time.time()
    r.state["last_account"] = account()
    r.state["last_account_epoch"] = now
    if stamp:
        r._stamp_quota(now)
        r._save()
    return r.state["last_account"]


if __name__ == "__main__":
    if "--account" in sys.argv:
        print(json.dumps(check_account(stamp="--no-stamp" not in sys.argv)))
    elif "--once" in sys.argv:
        syms = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]
        r = Refresher(log=print)
        print(json.dumps(r.refresh(syms)))
    else:
        print(__doc__)
