#!/usr/bin/env python3
"""Phase 3: on-surge X recent search (x_on_surge@0.1).

Tails ~/oid-data/archive/surges for new rows, calls GET /2/tweets/search/recent
when budget_guard allows, writes posts_raw / post_query_hits / item_filter / fetch_log.
Caps: $5/day, $100/month (config). Kill switch: ~/oid-data/state/x/STOP
No filtered stream. Never logs the bearer token.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
LIB = HERE / "lib"
sys.path.insert(0, str(LIB))

import budget_guard as bg  # noqa: E402
import build_queries as bq  # noqa: E402
import prefilter as pf  # noqa: E402

PT = ZoneInfo("America/Los_Angeles")
UTC = dt.timezone.utc
NS = 1_000_000_000
WRITER = "x_on_surge@0.1"
COMPONENT = "x-search"
STATUS_PATH_REL = "state/x/status.json"
BUDGET_PATH_REL = "state/x/budget.json"
SEEN_PATH_REL = "state/x/seen_surges.json"
OFFSET_PATH_REL = "state/x/tail_offsets.json"
USER_CACHE_REL = "state/x/user_cache.json"


def data_root() -> Path:
    return Path(os.environ.get("OID_DATA_ROOT", "~/oid-data")).expanduser()


def load_config() -> dict:
    """Prefer live config under oid-data; fall back to packaged lib copy."""
    cands = [
        data_root() / "config" / "x-on-surge-config.json",
        LIB / "x-on-surge-config.json",
    ]
    for p in cands:
        if p.exists():
            cfg = json.loads(p.read_text())
            # Keep budget_guard's module CFG in sync (it loaded lib copy at import).
            bg.CFG.clear()
            bg.CFG.update(cfg)
            bg.P = cfg["pricing_assumption"]
            bg.C = cfg["caps"]
            return cfg
    raise FileNotFoundError("x-on-surge-config.json not found")


def ensure_dirs(cfg: dict) -> None:
    root = data_root()
    for d in ("state/x", "logs", "config", "archive/posts_raw", "archive/post_query_hits",
              "archive/item_filter", "archive/fetch_log", "spool/grader/incoming"):
        (root / d).mkdir(parents=True, exist_ok=True)
    # Remove stale kill file only if operator asks; never auto-delete STOP.


def read_token(cfg: dict) -> str | None:
    path = Path(os.path.expanduser(cfg["credentials"]["x_bearer_token_path"]))
    if not path.is_file():
        return None
    tok = path.read_text().strip()
    return tok or None


def et_date_from_ns(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / NS, ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def now_pt_str() -> str:
    return dt.datetime.now(PT).strftime("%Y-%m-%d %I:%M:%S %p PT")


class JsonlWriter:
    """Minimal append-only writer matching oid_archive.common.JsonlWriter layout."""

    def __init__(self, table: str, writer_name: str):
        self.table = table
        self.writer_name = writer_name
        self.root = data_root() / "archive"
        self._paths: dict[str, Path] = {}
        self.rows = 0
        self.errors = 0

    def path_for(self, date: str) -> Path:
        if date not in self._paths:
            d = self.root / self.table / f"date={date}"
            d.mkdir(parents=True, exist_ok=True)
            import re
            pat = re.compile(rf"^part-{re.escape(self.writer_name)}-(\d+)\.jsonl$")
            seqs = [int(m.group(1)) for f in d.iterdir() if (m := pat.match(f.name))]
            self._paths = {date: d / f"part-{self.writer_name}-{(max(seqs) + 1) if seqs else 1}.jsonl"}
        return self._paths[date]

    def write(self, rows: list[dict]) -> bool:
        if not rows:
            return True
        try:
            by: dict[str, list[str]] = {}
            for r in rows:
                by.setdefault(et_date_from_ns(int(r["event_ts_ns"])), []).append(
                    json.dumps(r, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                )
            for date, lines in sorted(by.items()):
                with open(self.path_for(date), "a") as f:
                    f.write("\n".join(lines) + "\n")
                    f.flush()
            self.rows += len(rows)
            return True
        except Exception:
            self.errors += 1
            return False


class State:
    def __init__(self):
        self.root = data_root()
        self.seen: set[str] = set()
        self.offsets: dict[str, int] = {}
        self.user_cache: dict[str, dict] = {}
        self.budget_meta = {"month_spent": 0.0, "day_spent": 0.0, "day_pt": None,
                            "surges": 0, "requests": 0, "sweep_spent": 0.0}
        self._load()

    def _load(self):
        sp = self.root / SEEN_PATH_REL
        if sp.exists():
            try:
                self.seen = set(json.loads(sp.read_text()).get("ids", []))
            except Exception:
                self.seen = set()
        op = self.root / OFFSET_PATH_REL
        if op.exists():
            try:
                self.offsets = json.loads(op.read_text())
            except Exception:
                self.offsets = {}
        uc = self.root / USER_CACHE_REL
        if uc.exists():
            try:
                blob = json.loads(uc.read_text())
                self.user_cache = blob.get("users", {})
            except Exception:
                self.user_cache = {}
        bp = self.root / BUDGET_PATH_REL
        if bp.exists():
            try:
                self.budget_meta.update(json.loads(bp.read_text()))
            except Exception:
                pass

    def save_seen(self):
        p = self.root / SEEN_PATH_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        # Keep last 5k ids
        ids = list(self.seen)[-5000:]
        self.seen = set(ids)
        p.write_text(json.dumps({"ids": ids, "updated_pt": now_pt_str()}))

    def save_offsets(self):
        p = self.root / OFFSET_PATH_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.offsets))

    def save_budget(self, guard: bg.Guard):
        today = dt.datetime.now(PT).strftime("%Y-%m-%d")
        blob = {
            "day_pt": today,
            "day_spent": guard.day_spent,
            "month_spent": guard.month_spent,
            "surges": guard.surges,
            "requests": guard.requests,
            "sweep_spent": guard.sweep_spent,
            "allow": guard.allow,
            "updated_pt": now_pt_str(),
        }
        self.budget_meta = blob
        p = self.root / BUDGET_PATH_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(blob, indent=1))

    def save_user_cache(self):
        p = self.root / USER_CACHE_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        # Drop entries older than 7 days
        cutoff = time.time() - 7 * 86400
        keep = {k: v for k, v in self.user_cache.items()
                if float(v.get("_cached_at", 0)) >= cutoff}
        self.user_cache = keep
        p.write_text(json.dumps({"users": keep, "updated_pt": now_pt_str()}))

    def write_status(self, **kw):
        p = self.root / STATUS_PATH_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        cur = {}
        if p.exists():
            try:
                cur = json.loads(p.read_text())
            except Exception:
                cur = {}
        cur.update(kw)
        cur["updated_pt"] = now_pt_str()
        p.write_text(json.dumps(cur, indent=1))


def trading_days_left_in_month() -> int:
    """Rough count of remaining weekdays incl today in the calendar month (PT)."""
    now = dt.datetime.now(PT).date()
    if now.month == 12:
        end = dt.date(now.year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(now.year, now.month + 1, 1) - dt.timedelta(days=1)
    n = 0
    d = now
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return max(1, n)


def make_guard(state: State) -> bg.Guard:
    today = dt.datetime.now(PT).strftime("%Y-%m-%d")
    meta = state.budget_meta
    month = float(meta.get("month_spent") or 0.0)
    # Reset day counters at PT midnight
    if meta.get("day_pt") != today:
        day_spent = 0.0
        surges = 0
        requests = 0
        sweep = 0.0
    else:
        day_spent = float(meta.get("day_spent") or 0.0)
        surges = int(meta.get("surges") or 0)
        requests = int(meta.get("requests") or 0)
        sweep = float(meta.get("sweep_spent") or 0.0)
    g = bg.Guard(month_spent=month, trading_days_left=trading_days_left_in_month())
    g.day_spent = day_spent
    g.surges = surges
    g.requests = requests
    g.sweep_spent = sweep
    return g


def list_surge_parts(date: str) -> list[Path]:
    d = data_root() / "archive" / "surges" / f"date={date}"
    if not d.exists():
        return []
    return sorted(d.glob("part-*.jsonl"))


def tail_new_surges(state: State, date: str) -> list[dict]:
    """Read only new bytes from surge parts; return new JSON rows."""
    out = []
    for p in list_surge_parts(date):
        key = str(p)
        off = int(state.offsets.get(key, 0))
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size < off:
            off = 0  # rotated/truncated
        if size == off:
            continue
        with open(p, "rb") as f:
            f.seek(off)
            data = f.read()
            new_off = f.tell()
        state.offsets[key] = new_off
        # Drop trailing partial line
        if data and not data.endswith(b"\n"):
            data = data.rsplit(b"\n", 1)[0] + b"\n"
            # keep partial for next read: rewind offset to last newline
            state.offsets[key] = off + len(data)
        for ln in data.splitlines():
            if not ln.strip():
                continue
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    return out


def x_get(token: str, path: str, params: dict, timeout: float = 20.0) -> tuple[int, dict, dict, bytes]:
    """GET api.x.com; returns (status, headers_subset, json_or_empty, raw_bytes). Never logs token."""
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"https://api.x.com{path}?{q}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "oid-x-on-surge/0.1",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {}
            return resp.status, hdrs, body, raw
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        hdrs = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        return int(e.code), hdrs, body, raw
    except Exception as e:
        return 0, {}, {"error": type(e).__name__}, str(e).encode()[:300]


def build_fetch_log(fetch_id, surge_id, symbols, started_ns, finished_ns, status, n_items,
                    raw_len, hdrs, est_cost, error_class, error_msg, params_redacted) -> dict:
    lat = (finished_ns - started_ns) / 1e6
    def hi(name):
        v = hdrs.get(name) or hdrs.get(name.replace("_", "-"))
        try:
            return int(v) if v is not None else None
        except Exception:
            return None
    reset = hdrs.get("x-rate-limit-reset")
    reset_ns = int(reset) * NS if reset and str(reset).isdigit() else None
    return {
        "fetch_id": fetch_id,
        "component": COMPONENT,
        "endpoint": "api.x.com/2/tweets/search/recent",
        "method": "GET",
        "params_redacted": json.dumps(params_redacted),
        "surge_id": surge_id,
        "symbols": symbols,
        "started_ns": started_ns,
        "started_iso": pf.ns_to_iso(started_ns),
        "finished_ns": finished_ns,
        "latency_ms": lat,
        "http_status": status or None,
        "n_items": n_items,
        "bytes": raw_len,
        "rate_limit_limit": hi("x-rate-limit-limit"),
        "rate_limit_remaining": hi("x-rate-limit-remaining"),
        "rate_limit_reset_ns": reset_ns,
        "est_cost_usd": est_cost,
        "error_class": error_class,
        "error_msg": (error_msg[:300] if error_msg else None),
        **pf.common(started_ns, finished_ns, WRITER),
    }


def eligible(row: dict, cfg: dict) -> tuple[bool, str | None]:
    """Return (ok, skip_reason). ETFs are sweeps-only in Phase 3 MVP (crowd skip)."""
    sym = (row.get("symbol") or "").upper()
    if not sym:
        return False, "no_symbol"
    etfs = set(cfg.get("etfs_sweeps_only") or [])
    if sym in etfs:
        return False, "etf_sweeps_only"
    if row.get("surge_id") is None:
        return False, "no_surge_id"
    return True, None


SEL_DEFAULT = {"enabled": True, "gates": ["A", "AB"], "mover_alerts": True, "followed_only": True,
               "per_ticker_gap_min": 20, "session_pt": ["06:30", "13:00"], "burst": 4, "spend_floor_share": 0.15}


def followed_names() -> set:
    try:
        d = json.loads((Path.home() / "oid-live-page/sectors.json").read_text())
        out = {str(t).upper() for g in d.get("groups") or [] for t in g.get("tickers") or []}
    except Exception:
        out = set()
    return out - {"WDC", "STX", "SNDK", "VIX", "WTI", "BRENT"}


class Selector:
    """2026-10-20 budget pacing (caps unchanged): fetch only for gate-A surges (gate A/AB) or mover-alert moves on
    followed names; one fetch per ticker per per_ticker_gap_min; spread surge_fetches_per_day and today's allowance
    across the session (burst + linear pace) so the money lasts until the close. Volsurge gate-B / level-only "news"
    dry triggers are no longer fetch candidates."""
    PATH = "state/x/last_fetch_sym.json"

    def __init__(self):
        self.p = data_root() / self.PATH
        try:
            self.last = json.loads(self.p.read_text())
        except Exception:
            self.last = {}
        self.fol, self.fol_t = followed_names(), time.time()

    def mark(self, sym):
        self.last[sym] = time.time()
        try:
            self.p.write_text(json.dumps(self.last))
        except Exception:
            pass

    def frac(self, c):
        n = dt.datetime.now(PT)
        a, b = c["session_pt"]
        t0 = n.replace(hour=int(a[:2]), minute=int(a[3:]), second=0, microsecond=0)
        t1 = n.replace(hour=int(b[:2]), minute=int(b[3:]), second=0, microsecond=0)
        return max(0.0, min(1.0, (n - t0).total_seconds() / max(1, (t1 - t0).total_seconds())))

    def check(self, row, cfg, guard):
        c = dict(SEL_DEFAULT, **(cfg.get("selection") or {}))
        if not c.get("enabled", True):
            return True, None
        if time.time() - self.fol_t > 300:
            self.fol, self.fol_t = followed_names(), time.time()
        sym = (row.get("symbol") or "").upper()
        src = row.get("_src") or "surge"
        if src == "mover_alert":
            if not c.get("mover_alerts", True):
                return False, "select:mover_off"
        elif str(row.get("gate")) not in set(c["gates"]):
            return False, "select:not_gate_a"
        if c.get("followed_only", True) and sym not in self.fol:
            return False, "select:not_followed"
        if time.time() - float(self.last.get(sym, 0)) < c["per_ticker_gap_min"] * 60:
            return False, "select:ticker_gap"
        f = self.frac(c)
        cap_n = int(cfg["caps"].get("surge_fetches_per_day", 40))
        if guard.surges >= min(cap_n, int(c["burst"] + cap_n * f)):
            return False, "select:pace_count"
        if guard.day_spent >= guard.allow * min(1.0, c["spend_floor_share"] + (1 - c["spend_floor_share"]) * f):
            return False, "select:pace_spend"
        return True, None


def tail_mover_alerts(state) -> list:
    """New non-test mover alerts (com.oid.desk.mover-alert) as fetch candidates."""
    p = Path.home() / "oid-desk/state/mover-alert/alerts.jsonl"
    key = "mover:" + str(p)
    try:
        size = p.stat().st_size
    except OSError:
        return []
    off = int(state.offsets.get(key, -1))
    if off < 0 or size < off:  # first sight: start at EOF (no backlog burn)
        state.offsets[key] = size
        return []
    if size == off:
        return []
    with open(p, "rb") as f:
        f.seek(off)
        data = f.read()
    data = data[: data.rfind(b"\n") + 1]
    state.offsets[key] = off + len(data)
    out = []
    for ln in data.splitlines():
        try:
            a = json.loads(ln)
        except ValueError:
            continue
        if a.get("test") or not a.get("symbol"):
            continue
        out.append({"surge_id": "mover-" + str(a.get("alert_id")), "symbol": a["symbol"], "gate": "mover", "_src": "mover_alert",
                    "fire_ts_ns": time.time_ns(), "move_60s_bps": abs(float(a.get("move_pct") or 0)) * 100})
    return out


def process_surge(row, cfg, token, guard, state, writers) -> str:
    """Fetch + archive for one surge. Returns x_fetch_status."""
    sid = row["surge_id"]
    sym = row["symbol"].upper()
    if sid in state.seen:
        return "skipped:recent"
    fire_ns = int(row.get("fire_ts_ns") or row.get("event_ts_ns") or time.time_ns())
    now_ns = time.time_ns()

    # Reuse recent fetch for same symbol
    reused_id = guard.recent(sym, now_ns)
    if reused_id:
        state.seen.add(sid)
        state.save_seen()
        return "skipped:recent"

    if not token:
        state.seen.add(sid)
        state.save_seen()
        return "skipped:no_token"

    if not guard.enabled():
        state.seen.add(sid)
        state.save_seen()
        return "disabled"

    big = abs(float(row.get("move_60s_bps") or 0)) >= float(cfg["caps"].get("big_move_bps", 50))
    thin = sym in set(cfg.get("thin_mid_names") or [])
    after_reserve = dt.datetime.now(PT).strftime("%H:%M") >= cfg["caps"].get("reserve_release_pt", "12:30")
    max_r = int(cfg["crowd_query"]["max_results"])
    ok, mr, why = guard.precheck("crowd", max_results=max_r, big_move=big, thin=thin,
                                 after_reserve_release=after_reserve)
    if not ok:
        state.seen.add(sid)
        state.save_seen()
        state.save_budget(guard)
        return why or "skipped:budget"

    try:
        query = bq.build(sym)
    except Exception:
        # Unknown ticker in map — cashtag-only fallback
        query = f"(${sym}) -is:retweet -is:nullcast lang:en"

    cq = cfg["crowd_query"]
    # X requires end_time >= 10s in the past
    end_dt = dt.datetime.fromtimestamp(fire_ns / NS, UTC) - dt.timedelta(seconds=int(cq.get("end_offset_s", 10)))
    start_dt = end_dt - dt.timedelta(minutes=int(cq.get("lookback_min", 15)))
    # Clamp end to now-10s
    now_end = dt.datetime.now(UTC) - dt.timedelta(seconds=10)
    if end_dt > now_end:
        end_dt = now_end
        start_dt = end_dt - dt.timedelta(minutes=int(cq.get("lookback_min", 15)))

    def fmt(t: dt.datetime) -> str:
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "query": query,
        "max_results": str(mr),
        "start_time": fmt(start_dt),
        "end_time": fmt(end_dt),
        "sort_order": cq.get("sort_order", "recency"),
        "tweet.fields": cq.get("tweet.fields"),
    }
    if cq.get("exclude_replies"):
        # Prefer operator in query; already have -is:retweet. Add -is:reply if not present.
        if "-is:reply" not in query:
            params["query"] = query + " -is:reply"

    started_ns = time.time_ns()
    fetch_id = f"x-search-{started_ns}"
    query_id = f"crowd:{sym}"
    status, hdrs, body, raw = x_get(token, "/2/tweets/search/recent", params)
    finished_ns = time.time_ns()
    n_posts = len(body.get("data") or []) if isinstance(body, dict) else 0
    err_class = err_msg = None
    if status != 200:
        err_class = "http" if status else "timeout"
        err_msg = json.dumps(body)[:300] if body else f"status={status}"

    # Stage-1 prefilter (text only) then optional user lookup
    ingest_ns = finished_ns
    posts = pf.to_posts_raw(body if status == 200 else {"data": []}, query_id, sid, "search",
                            [sym], ingest_ns=ingest_ns, user_cache=None, fetch_id=fetch_id)
    hits = pf.post_query_hits(body if status == 200 else {"data": []}, query_id, fetch_id, sid,
                              started_ns, fire_ts_ns=fire_ns, reused=False, ingest_ns=ingest_ns)
    # Stage 1 filter → which author_ids need a user lookup (design helper)
    need_users = pf.user_ids_to_lookup(
        [{**p, "author_followers": None} for p in posts],
        sym,
        cache_ids=tuple(state.user_cache.keys()),
    )[:100]
    n_users = 0
    if need_users and status == 200:
        ok_u, n_u, why_u = guard.precheck("users", n_users=len(need_users))
        if ok_u and n_u:
            # batch lookup
            u_params = {
                "ids": ",".join(need_users[:n_u]),
                "user.fields": cfg["crowd_query"].get("user.fields", "created_at,public_metrics,verified_type,username"),
            }
            ustatus, _, ubody, _ = x_get(token, "/2/users", u_params)
            if ustatus == 200:
                for u in ubody.get("data") or []:
                    u["_cached_at"] = time.time()
                    state.user_cache[u["id"]] = u
                n_users = len(ubody.get("data") or [])
                guard.record("users", n_users=n_users)
                state.save_user_cache()
            # ignore user lookup failures; posts still kept with null author metrics

    # Rebuild posts with user cache and final prefilter
    posts = pf.to_posts_raw(body if status == 200 else {"data": []}, query_id, sid, "search",
                            [sym], ingest_ns=ingest_ns, user_cache=state.user_cache, fetch_id=fetch_id)
    items = pf.prefilter(posts, sym, now_ns=finished_ns, ingest_ns=ingest_ns, stage=2,
                         users=state.user_cache, job_id=sid)

    est = 0.0
    if status == 200:
        est = guard.record("crowd", n_posts=n_posts, sym=sym, now_ns=now_ns, fetch_id=fetch_id)
    else:
        # still count a failed request against request cap? Design: record actual. Count request.
        guard.requests += 1

    fl = build_fetch_log(
        fetch_id, sid, sym, started_ns, finished_ns, status, n_posts, len(raw), hdrs, est,
        err_class, err_msg,
        {"query": params["query"][:200], "max_results": mr, "start_time": params["start_time"],
         "end_time": params["end_time"], "symbol": sym},
    )
    writers["fetch_log"].write([fl])
    if posts:
        writers["posts_raw"].write(posts)
    if hits:
        writers["post_query_hits"].write(hits)
    if items:
        writers["item_filter"].write(items)

    state.seen.add(sid)
    state.save_seen()
    state.save_budget(guard)
    state.save_offsets()

    if status != 200:
        return "error"
    return "ok"


def run_loop(once: bool = False, catch_up: bool = False):
    cfg = load_config()
    ensure_dirs(cfg)
    state = State()
    guard = make_guard(state)
    token = read_token(cfg)
    writers = {
        "posts_raw": JsonlWriter("posts_raw", "x-on-surge"),
        "post_query_hits": JsonlWriter("post_query_hits", "x-on-surge"),
        "item_filter": JsonlWriter("item_filter", "x-on-surge"),
        "fetch_log": JsonlWriter("fetch_log", "x-on-surge"),
    }

    # On first start without catch_up: seed offsets to EOF so we only process NEW surges
    # (avoid burning the whole day's 160+ surges into the $5 cap).
    today = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    if not catch_up and not state.offsets:
        for p in list_surge_parts(today):
            try:
                state.offsets[str(p)] = p.stat().st_size
            except OSError:
                pass
        state.save_offsets()

    state.write_status(
        running=True, fetch_enabled=bool(cfg.get("fetch_enabled")),
        token_present=bool(token), phase="3_on_surge_recent_search_only",
        caps={"daily_usd": cfg["caps"]["x_daily_usd_cap"], "monthly_usd": cfg["caps"]["x_monthly_usd_cap"]},
        kill_file=cfg["caps"]["kill_file"],
        day_spent=guard.day_spent, month_spent=guard.month_spent, allow=guard.allow,
        surges_fetched=guard.surges, requests=guard.requests,
        seen=len(state.seen), last_error=None, started_pt=now_pt_str(),
    )

    SEL = Selector()
    sel_skips = {}
    ticks = 0
    fetched = 0
    skipped = 0
    errors = 0
    while True:
        try:
            cfg = load_config()  # hot-reload fetch_enabled / caps
            guard_enabled = bool(cfg.get("fetch_enabled"))
            # Refresh token presence each loop (never print it)
            token = read_token(cfg)
            today = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
            # Day rollover
            if state.budget_meta.get("day_pt") != dt.datetime.now(PT).strftime("%Y-%m-%d"):
                guard = make_guard(state)

            rows = tail_new_surges(state, today)
            try:
                rows += tail_mover_alerts(state)
            except Exception:
                pass
            for row in rows:
                sid = row.get("surge_id")
                if not sid or sid in state.seen:
                    continue
                ok, reason = eligible(row, cfg)
                if not ok:
                    state.seen.add(sid)
                    continue
                if not guard_enabled:
                    state.seen.add(sid)
                    skipped += 1
                    continue
                ok2, why2 = SEL.check(row, cfg, guard)
                if not ok2:
                    state.seen.add(sid)
                    skipped += 1
                    sel_skips[why2] = sel_skips.get(why2, 0) + 1
                    continue
                try:
                    status = process_surge(row, cfg, token, guard, state, writers)
                except Exception as e:
                    errors += 1
                    state.seen.add(sid)
                    state.write_status(last_error=f"{type(e).__name__}: {e}"[:300],
                                       last_error_pt=now_pt_str())
                    traceback.print_exc()
                    continue
                if status == "ok":
                    fetched += 1
                    SEL.mark(row["symbol"].upper())
                else:
                    skipped += 1
                state.write_status(
                    running=True, fetch_enabled=guard_enabled, token_present=bool(token),
                    day_spent=guard.day_spent, month_spent=guard.month_spent, allow=guard.allow,
                    surges_fetched=guard.surges, requests=guard.requests,
                    fetched_ok=fetched, skipped=skipped, errors=errors,
                    last_status=status, last_surge_id=sid, last_symbol=row.get("symbol"),
                    select_skips=sel_skips,
                    ticks=ticks, seen=len(state.seen),
                    kill_active=os.path.exists(os.path.expanduser(cfg["caps"]["kill_file"])),
                )
            state.save_offsets()
            ticks += 1
            if ticks % 30 == 0:
                state.write_status(
                    running=True, fetch_enabled=guard_enabled, token_present=bool(token),
                    day_spent=guard.day_spent, month_spent=guard.month_spent, allow=guard.allow,
                    surges_fetched=guard.surges, requests=guard.requests,
                    fetched_ok=fetched, skipped=skipped, errors=errors, ticks=ticks,
                    seen=len(state.seen),
                    kill_active=os.path.exists(os.path.expanduser(cfg["caps"]["kill_file"])),
                )
        except Exception as e:
            errors += 1
            state.write_status(last_error=f"loop {type(e).__name__}: {e}"[:300],
                               last_error_pt=now_pt_str(), errors=errors)
            traceback.print_exc()
        if once:
            break
        time.sleep(2.0)


def main():
    ap = argparse.ArgumentParser(description="Phase 3 x_on_surge fetcher")
    ap.add_argument("--once", action="store_true", help="One poll then exit")
    ap.add_argument("--catch-up", action="store_true",
                    help="Process existing today's surges (default: start at EOF)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        cfg = load_config()
        assert cfg.get("fetch_enabled") is True, "fetch_enabled should be True for Phase 3 go"
        assert cfg["caps"]["x_daily_usd_cap"] == 5.0
        assert cfg["caps"]["x_monthly_usd_cap"] == 100.0
        g = bg.Guard(0, 22)
        assert g.enabled()
        ok, mr, why = g.precheck("crowd", max_results=50, big_move=False, thin=True)
        assert ok and mr >= 10, (ok, mr, why)
        q = bq.build("NVDA")
        assert "$NVDA" in q and len(q) <= 512
        print("selftest ok", {"fetch_enabled": True, "allow": g.allow, "query_nvda_len": len(q)})
        return
    run_loop(once=args.once, catch_up=args.catch_up)


if __name__ == "__main__":
    main()
