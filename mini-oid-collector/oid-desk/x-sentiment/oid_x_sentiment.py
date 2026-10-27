#!/usr/bin/env python3
"""OID per-ticker X sentiment feed (SHADOW). Runs on the Mac mini only.

pull      : one pass. Tier picked by clock unless --tier/--symbols given:
            hot tier every run (launchd every 300 s), full universe when minute % 15 < 5.
            Per ticker: GET /2/tweets/counts/recent (minute buckets, $0.005/request) for chatter, and
            GET /2/tweets/search/recent (max_results>=10, since_id, $0.005/post) for the tone sample.
baseline  : once per day per ticker, counts/recent granularity=hour over 7 days -> trailing RTH pace.
scorecard : after close; joins sentiment rows to 5 s SIP closes in score snapshots and checks lead/lag.

Shadow only: writes ~/oid-data/sentiment/x/. Nothing in the score, orders or alerts reads it.
Budget: every request is prechecked against its worst-case cost, a per-day/month ledger
(~/oid-data/state/x/sentiment_budget.json) and the desk's combined X day cap (x-on-surge + name-credit + this).
Kill: touch ~/oid-data/state/x/STOP or ~/oid-data/state/x/SENTIMENT_STOP, or fetch_enabled=false in config.
The bearer token is read from the existing desk secret file and is never printed or logged.
"""
import argparse, datetime as dt, json, math, os, re, statistics, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HOME = Path.home()
DATA = Path(os.environ.get("OID_DATA_ROOT", str(HOME / "oid-data")))
CFG_PATH = Path(os.environ.get("OID_XSENT_CONFIG", str(DATA / "config/x-sentiment-config.json")))
OUT = DATA / "sentiment/x"
STATE = DATA / "state/x"
LEDGER = STATE / "sentiment_budget.json"
SSTATE = STATE / "sentiment_state.json"
VERSION = "x-sentiment-v0.4"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lexicon as LX  # noqa: E402
import jev as JEV  # noqa: E402


def now_pt():
    return dt.datetime.now(PT)


def pt_str(t):
    return dt.datetime.fromtimestamp(t, PT).strftime("%Y-%m-%d %I:%M:%S %p PT")


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def save_json(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp"); tmp.write_text(json.dumps(obj, indent=1, default=str)); os.replace(tmp, p)


def log(msg):
    print(f"[{now_pt().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------- budget ----------------
class Budget:
    """Worst-case precheck. Counts all desk X ledgers toward the shared day cap."""
    def __init__(s, cfg):
        s.cfg = cfg; b = cfg["budget"]
        s.day_cap = float(b["sentiment_daily_usd_cap"]); s.month_cap = float(b["sentiment_monthly_usd_cap"])
        s.desk_day_cap = float(b["desk_x_daily_usd_hard_cap"]); s.desk_month_cap = float(b["desk_x_monthly_usd_hard_cap"])
        s.post = float(b["post_read_usd"]); s.count_req = float(b["counts_request_usd"])
        today = now_pt().strftime("%Y-%m-%d"); month = now_pt().strftime("%Y-%m")
        L = load_json(LEDGER, {})
        if L.get("day_pt") != today:
            L.update({"day_pt": today, "day_spent": 0.0, "requests_day": 0, "posts_day": 0, "counts_requests_day": 0})
        if L.get("month") != month:
            L.update({"month": month, "month_spent": 0.0})
        L.setdefault("calls", [])
        s.L = L; s.today = today; s.month = month

    def other_day_month(s):
        day = month = 0.0
        xs = load_json(STATE / "budget.json", {})
        if xs.get("day_pt") == s.today: day += float(xs.get("day_spent") or 0)
        month += float(xs.get("month_spent") or 0)
        nc = load_json(STATE / "name_credit_budget.json", {})
        if nc.get("day_pt") == s.today: day += float(nc.get("day_spent") or 0)
        if nc.get("month") == s.month: month += float(nc.get("month_spent") or 0)
        return day, month

    def stopped(s):
        return (STATE / "STOP").exists() or (STATE / "SENTIMENT_STOP").exists()

    def precheck(s, worst_usd):
        if s.stopped(): return False, "kill_file"
        if s.L["day_spent"] + worst_usd > s.day_cap: return False, "sentiment_day_cap"
        if s.L["month_spent"] + worst_usd > s.month_cap: return False, "sentiment_month_cap"
        od, om = s.other_day_month()
        if od + s.L["day_spent"] + worst_usd > s.desk_day_cap: return False, "desk_day_cap"
        if om + s.L["month_spent"] + worst_usd > s.desk_month_cap: return False, "desk_month_cap"
        return True, None

    def record(s, kind, usd, sym, status, posts=0):
        s.L["day_spent"] = round(s.L["day_spent"] + usd, 4); s.L["month_spent"] = round(s.L["month_spent"] + usd, 4)
        s.L["requests_day"] += 1
        if kind == "counts": s.L["counts_requests_day"] += 1
        s.L["posts_day"] += posts
        s.L["calls"] = (s.L["calls"] + [{"pt": now_pt().strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "sym": sym,
                                         "status": status, "posts": posts, "usd": round(usd, 4)}])[-500:]
        s.L["updated_pt"] = now_pt().strftime("%Y-%m-%d %I:%M:%S %p PT")
        save_json(LEDGER, s.L)


# ---------------- X API ----------------
def read_token(cfg):
    p = Path(os.path.expanduser(cfg["credentials"]["x_bearer_token_path"]))
    if not p.is_file(): return None
    t = p.read_text().strip()
    return t or None


def x_get(token, path, params, timeout=20.0):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"https://api.x.com{path}?{q}",
                                 headers={"Authorization": f"Bearer {token}", "User-Agent": f"oid-{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            return r.status, hdrs, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        try: body = json.loads(raw.decode())
        except Exception: body = {"raw": raw[:200].decode(errors="replace")}
        return int(e.code), {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}, body
    except Exception as e:
        return 0, {}, {"error": type(e).__name__, "msg": str(e)[:200]}


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cashtag_query(sym, cfg):
    q = cfg["query"]
    return f"${sym} {q['suffix']}".strip()


# ---------------- universe ----------------
def core_universe(cfg):
    if cfg["universe"].get("core"): return list(cfg["universe"]["core"])
    sd = DATA / "score"
    files = sorted(sd.glob("scores-2*.jsonl"))
    syms = set()
    if files:
        with open(files[-1]) as f:
            for i, line in enumerate(f):
                try: syms.add(json.loads(line)["sym"])
                except Exception: pass
                if i > 5000: break
    return sorted(syms)


def latest_score_rows():
    sd = DATA / "score"; files = sorted(sd.glob("scores-2*.jsonl"))
    last = {}
    if not files: return last
    p = files[-1]
    with open(p, "rb") as f:
        f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 400_000)); tail = f.read().decode(errors="ignore").splitlines()[1:]
    for line in tail:
        try: d = json.loads(line); last[d["sym"]] = d
        except Exception: pass
    return last


def hot_tier(cfg, core):
    u = cfg["universe"]; hot = list(u.get("hot_static", []))
    pt = load_json(HOME / "oid-desk/desk/market-data/latest/position-triggers.json", {})
    for s in (pt.get("symbols") or []):
        if isinstance(s, str): hot.append(s)
    rows = latest_score_rows()
    movers = sorted((r for r in rows.values() if r.get("chg_pct") is not None and r["sym"] not in u.get("etfs_no_movers", [])),
                    key=lambda r: -abs(float(r["chg_pct"])))
    hot += [r["sym"] for r in movers[: int(u.get("movers_n", 6))]]
    seen, out = set(), []
    for s in hot:
        if s not in seen: seen.add(s); out.append(s)
    return out[: int(u.get("hot_max", 12))]


# ---------------- scoring ----------------
def author_weight(pm_user, cfg):
    if not pm_user: return 1.0
    f = int(pm_user.get("followers_count") or 0)
    return 1.0 + math.log10(1 + f) / 2.0          # 0 -> 1.0, 1k -> 2.5, 100k -> 3.5, 10M -> 4.5


def engagement_weight(pm):
    if not pm: return 1.0
    e = int(pm.get("like_count") or 0) + 2 * int(pm.get("retweet_count") or 0) + int(pm.get("reply_count") or 0) + 2 * int(pm.get("quote_count") or 0)
    return 1.0 + math.log10(1 + e)


def spam_reason(post, sym, cfg, users, blocked):
    txt = post.get("text") or ""
    tags = re.findall(r"\$[A-Za-z]{1,6}\b", txt)
    if len(tags) > int(cfg["filters"]["max_cashtags"]): return "cashtag_stuffing"
    low = txt.lower()
    for w in cfg["filters"]["spam_terms"]:
        if w in low: return "spam_term"
    u = users.get(post.get("author_id") or "")
    if u:
        if (u.get("username") or "").lower() in blocked: return "blocklist"
        pm = u.get("public_metrics") or {}
        fol, fing, tw = int(pm.get("followers_count") or 0), int(pm.get("following_count") or 0), int(pm.get("tweet_count") or 0)
        if fing >= 1000 and fing >= 5 * max(1, fol): return "follow_farm"
        if tw < 20: return "low_activity"
    return None


def score_posts(sym, posts, cfg, users, blocked, jev=None):
    """Spam filter, then per-post stance. Jev (TypeSafe) when available: s = P(bull) - P(bear), posts Jev calls
    not_about_ticker (P >= offtopic_min_p) are dropped. Any Jev error for a post -> lexicon score for that post."""
    cand, drops = [], {}
    for p in posts:
        why = spam_reason(p, sym, cfg, users, blocked)
        if why: drops[why] = drops.get(why, 0) + 1; continue
        cand.append(p)
    jr = jev.classify(sym, [p.get("text") or "" for p in cand]) if (jev and cand) else [None] * len(cand)
    off_min = float(((cfg.get("scorer") or {}).get("offtopic_min_p", 0.5)))
    kept, engines = [], {"jev": 0, "lexicon": 0}
    for p, j in zip(cand, jr):
        u = users.get(p.get("author_id") or "")
        w = author_weight((u or {}).get("public_metrics"), cfg) * engagement_weight(p.get("public_metrics"))
        rec = {"id": p["id"], "w": round(w, 3), "known_author": bool(u), "text": (p.get("text") or "")[:280]}
        if j is not None:
            pr = j["p"]
            rec.update({"engine": "jev", "p_bull": pr["bullish"], "p_bear": pr["bearish"], "p_neu": pr["neutral"],
                        "p_off": pr["not_about_ticker"], "conf": j["conf"], "jev_choice": j["choice"]})
            if pr["not_about_ticker"] >= off_min or j["choice"] == "not_about_ticker":
                drops["not_about_ticker"] = drops.get("not_about_ticker", 0) + 1
                rec["dropped"] = "not_about_ticker"; kept.append(rec); continue
            s = pr["bullish"] - pr["bearish"]
            lab = {"bullish": "bull", "bearish": "bear"}.get(j["choice"], "neu")
            engines["jev"] += 1
        else:
            s = LX.score_text(p.get("text") or "", sym)
            lab = "bull" if s >= LX.THRESH else "bear" if s <= -LX.THRESH else "neu"
            rec["engine"] = "lexicon"; engines["lexicon"] += 1
        rec.update({"s": round(s, 3), "lab": lab}); kept.append(rec)
    used = [k for k in kept if not k.get("dropped")]
    bull = sum(1 for k in used if k["lab"] == "bull"); bear = sum(1 for k in used if k["lab"] == "bear")
    wall = sum(k["w"] for k in used)
    net = sum(k["w"] * k["s"] for k in used) / wall if wall else None          # -1..+1; neutral posts dilute
    pol = sum(k["w"] * abs(k["s"]) for k in used)
    net_polar = sum(k["w"] * k["s"] for k in used) / pol if pol else None
    return {"n_kept": len(used), "bull": bull, "bear": bear, "neu": len(used) - bull - bear,
            "net": None if net is None else round(net, 3), "net_polar": None if net_polar is None else round(net_polar, 3),
            "drops": drops, "posts": kept, "engines": engines, "jev_error": (jev.last_error if jev and engines["lexicon"] else None)}


# ---------------- baseline ----------------
def rth_hour(t):
    d = dt.datetime.fromtimestamp(t, PT)
    return d.weekday() < 5 and (d.hour, d.minute) >= (6, 30) and d.hour < 13


def ensure_baseline(sym, cfg, token, budget, st, dry):
    b = st.setdefault("baseline", {}).get(sym)
    today = now_pt().strftime("%Y-%m-%d")
    if b and b.get("day") == today: return b
    ok, why = budget.precheck(budget.count_req)
    if not ok or dry: return b
    end = time.time() - 15; start = end - 7 * 86400 + 120
    status, hdrs, body = x_get(token, "/2/tweets/counts/recent",
                               {"query": cashtag_query(sym, cfg), "granularity": "hour", "start_time": iso(start), "end_time": iso(end)})
    budget.record("counts_baseline", budget.count_req if status == 200 else 0.0, sym, status)
    if status != 200:
        log(f"baseline {sym} HTTP {status} {str(body)[:160]}"); return b
    vals = []
    today_start = dt.datetime.now(PT).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    for r in body.get("data", []):
        t0 = dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")).timestamp()
        if t0 < today_start and rth_hour(t0 + 1800):
            vals.append(r["tweet_count"] / 4.0)        # per-15-min pace
    if len(vals) >= 6:
        b = {"day": today, "mean15": round(statistics.mean(vals), 2), "sd15": round(statistics.pstdev(vals) or 1.0, 2),
             "n_hours": len(vals), "total_7d": body.get("meta", {}).get("total_tweet_count")}
        st["baseline"][sym] = b
    return b


# ---------------- pull ----------------
def pull(args, cfg):
    token = read_token(cfg)
    budget = Budget(cfg)
    st = load_json(SSTATE, {})
    n = now_pt()
    status = {"writer": VERSION, "updated_pt": n.strftime("%Y-%m-%d %I:%M:%S %p PT"), "shadow": True,
              "fetch_enabled": bool(cfg.get("fetch_enabled")), "token_present": bool(token)}
    if not args.force_session:
        in_rth = n.weekday() < 5 and (n.hour, n.minute) >= (6, 30) and n.hour < 13
        if not in_rth:
            status["last"] = "outside_rth"; save_json(OUT / "status.json", status); return 0
    if not cfg.get("fetch_enabled") and not args.test:
        status["last"] = "disabled"; save_json(OUT / "status.json", status); return 0
    if not token:
        status["last"] = "skipped:no_token"; save_json(OUT / "status.json", status); log("no token file"); return 2
    core = core_universe(cfg)
    if args.symbols:
        syms, tier = [s.strip().upper() for s in args.symbols.split(",") if s.strip()], "manual"
    else:
        cad = cfg.get("cadence", {})
        m = (n.hour * 60 + n.minute) - (6 * 60 + 30)          # minutes since the 06:30 PT open
        fe, he = int(cad.get("full_every_min", 15)), int(cad.get("hot_every_min", 5))
        # slot dedupe (robust to launchd drift/sleep): a tier runs once per N-minute block, on the first wake inside it
        done = st.setdefault("slots_done", {}); dkey = n.strftime("%Y-%m-%d")
        if done.get("day") != dkey: done.clear(); done["day"] = dkey
        tier = args.tier
        if tier is None:
            if fe > 0 and done.get("full") != m // fe: tier = "full"
            elif he > 0 and done.get("hot") != m // he: tier = "hot"
        if tier is None:
            status["last"] = "idle_slot"; save_json(OUT / "status.json", status); return 0
        syms = core if tier == "full" else hot_tier(cfg, core)
        if tier == "full":   # hot names first so they are served if the budget runs short
            hot = hot_tier(cfg, core); syms = hot + [s for s in core if s not in hot]
    mr = max(10, int(args.max_results or cfg["sample"]["max_results"]))
    # tone sample (search, ~$0.05) is the expensive part; cadence decides whether this pass samples
    do_sample = True
    if tier in ("full", "hot"):
        cad = cfg.get("cadence", {}); se = int(cad.get(f"{tier}_sample_every_min", 0) or 0)
        m = (n.hour * 60 + n.minute) - (6 * 60 + 30)
        sd = st.setdefault("slots_done", {}); skey = f"{tier}_sample"
        do_sample = bool(cad.get(f"{tier}_sample", True)) and (se <= 0 or sd.get(skey) != m // se)
        if not args.tier and not args.symbols:   # mark the blocks done (scheduled passes only)
            sd[tier] = m // int(cad.get(f"{tier}_every_min", 15) or 15)
            if do_sample and se > 0: sd[skey] = m // se
    if not do_sample: mr_cost = 0
    else: mr_cost = mr
    users = load_json(STATE / "user_cache.json", {}).get("users", {})
    sc_cfg = cfg.get("scorer") or {}
    jev = JEV.JevScorer(sc_cfg, STATE) if sc_cfg.get("engine", "lexicon") == "jev" and not args.dry_run else None
    bl = load_json(HOME / "oid-desk/x-on-surge/lib/x-blocklist.json", {})
    blocked = {(b.get("handle") or "").lower() for b in bl.get("block", [])}
    window = int(cfg["sample"]["window_min"]) * 60
    t_now = time.time(); end = t_now - 15
    date = n.strftime("%Y%m%d"); OUT.mkdir(parents=True, exist_ok=True)
    rows, spent0 = [], budget.L["day_spent"]
    latest = load_json(OUT / "latest.json", {}).get("tickers", {})
    for sym in syms:
        q = cashtag_query(sym, cfg)
        row = {"sym": sym, "t": round(t_now, 1), "t_pt": pt_str(t_now), "date": n.strftime("%Y-%m-%d"),
               "slot": n.strftime("%H:%M"), "tier": tier, "writer": VERSION, "shadow": True, "query": q, "window_min": window // 60}
        # chatter: minute counts over the window (one request)
        ok, why = budget.precheck(budget.count_req + mr_cost * budget.post)
        if not ok:
            row["status"] = f"skipped:{why}"; rows.append(row); continue
        base = ensure_baseline(sym, cfg, token, budget, st, args.dry_run)
        if args.dry_run:
            row["status"] = "dry_run"; rows.append(row); continue
        cs, ch, cb = x_get(token, "/2/tweets/counts/recent",
                           {"query": q, "granularity": "minute", "start_time": iso(end - window), "end_time": iso(end)})
        budget.record("counts", budget.count_req if cs == 200 else 0.0, sym, cs)
        cnt = cb.get("meta", {}).get("total_tweet_count") if cs == 200 else None
        row["count"] = cnt
        if cnt is not None and base:
            per = base["mean15"] * (window / 900.0); sd = base["sd15"] * math.sqrt(window / 900.0)
            row["base_count"] = round(per, 1); row["chatter_ratio"] = round(cnt / per, 2) if per > 0 else None
            row["chatter_z"] = round((cnt - per) / sd, 2) if sd > 0 else None
        if not do_sample:   # chatter-only pass: carry the last tone forward
            row.update({"status": "ok" if cs == 200 else f"http:{cs}", "sampled": False, "n_posts": 0,
                        "rate_remaining": ch.get("x-rate-limit-remaining"), "cost_usd": budget.count_req if cs == 200 else 0.0,
                        "net_ewma": (latest.get(sym) or {}).get("net_ewma")})
            rows.append(row); latest.setdefault(sym, {}).update({k: row.get(k) for k in ("t", "t_pt", "tier", "count", "base_count",
                                                                                        "chatter_ratio", "chatter_z", "status")})
            continue
        row["sampled"] = True
        # tone sample: newest posts since last seen id (one request, <= mr posts)
        since = st.setdefault("since_id", {}).get(sym)
        params = {"query": q, "max_results": str(mr), "sort_order": "recency", "end_time": iso(end),
                  "tweet.fields": "created_at,author_id,lang,public_metrics,entities"}
        if since: params["since_id"] = since
        else: params["start_time"] = iso(end - window)
        ss, sh, sb = x_get(token, "/2/tweets/search/recent", params)
        posts = sb.get("data", []) if ss == 200 else []
        budget.record("search", len(posts) * budget.post, sym, ss, posts=len(posts))
        if ss == 200 and sb.get("meta", {}).get("newest_id"): st["since_id"][sym] = sb["meta"]["newest_id"]
        sc = score_posts(sym, posts, cfg, users, blocked, jev)
        row.update({"status": "ok" if (cs == 200 and ss == 200) else f"http:{cs}/{ss}", "n_posts": len(posts),
                    **{k: sc[k] for k in ("n_kept", "bull", "bear", "neu", "net", "net_polar", "drops", "engines", "jev_error")},
                    "rate_remaining": sh.get("x-rate-limit-remaining"), "cost_usd": round((budget.count_req if cs == 200 else 0.0) + len(posts) * budget.post, 4)})
        if ss != 200: row["error"] = str(sb)[:200]
        row["post_scores"] = sc["posts"]   # per-post engine, probabilities, weight, text (always logged)
        # smoothed net (EWMA over passes; sample sizes are small)
        prev = (latest.get(sym) or {}).get("net_ewma")
        if row.get("net") is not None:
            a = float(cfg["sample"]["ewma_alpha"]); row["net_ewma"] = round(row["net"] if prev is None else a * row["net"] + (1 - a) * prev, 3)
        else: row["net_ewma"] = prev
        rows.append(row); latest[sym] = {k: row.get(k) for k in ("t", "t_pt", "tier", "count", "base_count", "chatter_ratio", "chatter_z",
                                                                  "n_posts", "n_kept", "bull", "bear", "neu", "net", "net_ewma", "status")}
    with open(OUT / f"{date}.jsonl", "a") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    save_json(OUT / "latest.json", {"as_of_pt": n.strftime("%Y-%m-%d %I:%M:%S %p PT"), "writer": VERSION, "shadow": True,
                                    "note": "SHADOW: not used by the direction score, orders or alerts", "tickers": latest})
    save_json(SSTATE, st)
    spent = round(budget.L["day_spent"] - spent0, 4)
    status.update({"last": "ok", "tier": tier, "n_syms": len(syms), "rows": len(rows), "pass_usd": spent,
                   "day_spent": budget.L["day_spent"], "month_spent": budget.L["month_spent"],
                   "skipped": sum(1 for r in rows if str(r.get("status", "")).startswith("skipped"))})
    save_json(OUT / "status.json", status)
    log(f"pass tier={tier} syms={len(syms)} usd={spent} day={budget.L['day_spent']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull")
    p.add_argument("--tier", choices=["full", "hot"]); p.add_argument("--symbols"); p.add_argument("--max-results", type=int)
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--force-session", action="store_true")
    p.add_argument("--test", action="store_true", help="manual test pass even if fetch_enabled=false (still budget-guarded)")
    p.add_argument("--keep-posts", action="store_true", help="no-op since v0.4 (post_scores always logged)")
    s = sub.add_parser("scorecard"); s.add_argument("--date")
    a = ap.parse_args()
    cfg = load_json(CFG_PATH, None)
    if cfg is None: print(f"missing config {CFG_PATH}", file=sys.stderr); return 2
    if a.cmd == "pull": return pull(a, cfg)
    import scorecard; return scorecard.run(a, cfg, DATA, OUT)


if __name__ == "__main__":
    sys.exit(main())
