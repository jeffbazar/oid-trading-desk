#!/usr/bin/env python3
"""Idempotent patch: add C/P momentum (OPTMOM) to optflow.py -> v0.3.0.
Usage: patch_optflow_mom.py <path/to/optflow.py>   (re-run safe; marker 'OPTMOM')"""
import sys
from pathlib import Path
p = Path(sys.argv[1]); s = p.read_text()
LEVEL = 3 if "OPTMOM3" in s else 2 if "OPTMOM2" in s else 1 if "OPTMOM" in s else 0
if LEVEL >= 3:
    print("already patched", p); sys.exit(0)

def rep(old, new, label, lvl=1):
    global s
    if lvl is True:
        lvl = 2
    if lvl <= LEVEL:
        return
    if old not in s:
        raise SystemExit(f"anchor missing: {label}")
    s = s.replace(old, new, 1)

rep("import asyncio, json, logging, os, re, signal, ssl, statistics, sys, time\n",
    "import asyncio, gzip, json, logging, math, os, queue, re, signal, ssl, statistics, sys, threading, time\n", "imports")

rep('OCC = re.compile(r"^([A-Z0-9]+?)(\\d{6})([CP])(\\d{8})$")\n',
    'OCC = re.compile(r"^([A-Z0-9]+?)(\\d{6})([CP])(\\d{8})$")\n'
    '# --- OPTMOM: C/P momentum (spec docs/live-page/22-cp-momentum-spec.md)\n'
    'MOMENTUM = os.environ.get("OID_OPTFLOW_MOMENTUM", "1") != "0"      # kill switch\n'
    'HIST_LOG = os.environ.get("OID_OPTFLOW_HIST_LOG", "1") != "0"\n'
    'HIST_N = int(os.environ.get("OID_OPTFLOW_HIST_N", "6"))\n'
    'HIST_KEEP_D = int(os.environ.get("OID_OPTFLOW_HIST_KEEP_D", "365"))\n'
    'HIST_DIR = ROOT / "data/cp-history"\n'
    'SAMPLE_S = 15\n'
    'MOM_SLOTS = 4                       # slope over the last 4 slots (45 s span)\n'
    'MOM_MIN_VALID = 3\n'
    'STALE_S = 30.0\n'
    'RERANK_MIN_OVERLAP = 0.70\n'
    'L_CAP = math.log(10)\n'
    'DB = {"15s": (float(os.environ.get("OID_OPTFLOW_DB15_IN", "0.35")), float(os.environ.get("OID_OPTFLOW_DB15_OUT", "0.20"))),\n'
    '      "60s": (float(os.environ.get("OID_OPTFLOW_DB60_IN", "0.20")), float(os.environ.get("OID_OPTFLOW_DB60_OUT", "0.10")))}\n'
    'WKEYS = {"15s": "15", "60s": "60"}\n\n\n'
    'def _logratio(cb, pb):\n'
    '    """OPTMOM: smoothed, clamped ln(call-buy / put-buy premium)."""\n'
    '    k = max(2000.0, 0.05 * (cb + pb))\n'
    '    return max(-L_CAP, min(L_CAP, math.log((cb + k) / (pb + k))))\n\n\n'
    'def _rth(ts):\n'
    '    d = datetime.fromtimestamp(ts, ET)\n'
    '    if d.weekday() >= 5:\n'
    '        return False\n'
    '    m = d.hour * 60 + d.minute\n'
    '    return 570 <= m < 960\n\n\n'
    'def _open_epoch(ts):\n'
    '    d = datetime.fromtimestamp(ts, ET)\n'
    '    return d.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()\n\n\n'
    'def _ols_slope(pts):\n'
    '    n = len(pts); mx = sum(t for t, _ in pts) / n; my = sum(v for _, v in pts) / n\n'
    '    den = sum((t - mx) ** 2 for t, _ in pts)\n'
    '    return 0.0 if den <= 0 else sum((t - mx) * (v - my) for t, v in pts) / den\n',
    "consts")

rep("        self.started = time.time()\n        self.snapshot = {}\n",
    "        self.started = time.time()\n        self.snapshot = {}\n"
    "        # OPTMOM state\n"
    "        self.hist: dict[str, dict] = defaultdict(lambda: {w: deque(maxlen=HIST_N) for w in WKEYS})  # und -> {win: deque[slot]}\n"
    "        self.last_boundary = None\n"
    "        self.last_d: dict[str, dict] = defaultdict(dict)\n"
    "        self.mom: dict[str, dict] = {}\n"
    "        self.rerank_at: dict[str, float] = {}\n"
    "        self.histq: queue.Queue = queue.Queue(maxsize=200)\n", "state init")

rep("        if self.day_date != dd:\n            self.day.clear(); self.day_date = dd\n",
    "        if self.day_date != dd:\n            self.day.clear(); self.day_date = dd\n"
    "            self.hist.clear(); self.last_d.clear(); self.mom.clear(); self.last_boundary = None  # OPTMOM\n", "rollover")

rep("            res[\"contracts\"] = (self.coverage.get(und) or {}).get(\"n\")\n            out[und] = res\n",
    "            res[\"contracts\"] = (self.coverage.get(und) or {}).get(\"n\")\n            out[und] = res\n"
    "        if MOMENTUM:  # OPTMOM\n"
    "            try:\n"
    "                self.sample(now, out)\n"
    "            except Exception as e:  # never break the chips\n"
    "                log.warning(\"momentum sample failed: %s\", e)\n"
    "            for und, res in out.items():\n"
    "                if und in self.mom:\n"
    "                    res[\"mom\"] = self.mom[und]\n", "attach mom")

rep('"service": "oid-optflow", "version": "0.2.0",', '"service": "oid-optflow", "version": "0.3.0",', "version")
rep("multi-leg + stock-tied (complex), cancel/late excluded\",",
    "multi-leg + stock-tied (complex), cancel/late excluded\" + (\"; momentum (mom): 15 s slots of L=ln((cb+k)/(pb+k)), k=max(2000,5% of cb+pb), clamped +-ln10; OLS slope of last 4 slots per min; >=3 valid incl latest; deadband w/ hysteresis\" if MOMENTUM else \"\"),\n"
    "            \"momentum\": ({\"enabled\": True, \"hist_n\": HIST_N, \"sample_s\": SAMPLE_S, \"deadband\": DB} if MOMENTUM else {\"enabled\": False}),", "method")

# sampler + momentum methods, inserted before _r()
rep("\n\ndef _r(a, b):\n",
    "\n"
    "    # ------------------------------------------------------------- OPTMOM\n"
    "    def _why(self, und, w, wsec, b, sm):\n"
    "        if not _rth(b):\n"
    "            return \"closed\"\n"
    "        if b - wsec < _open_epoch(b):\n"
    "            return \"warmup\"\n"
    "        if self.ws_state != \"subscribed_ready\" or not self.ws_connected_at or (b - wsec) < self.ws_connected_at:\n"
    "            return \"ws\"\n"
    "        lt = self.last_trade.get(und)\n"
    "        if not lt or b - lt[1] > STALE_S:\n"
    "            return \"stale\"\n"
    "        if not sm or sm.get(\"thin\", True):\n"
    "            return \"thin\"\n"
    "        if (sm.get(\"cb\") or 0) + (sm.get(\"pb\") or 0) <= 0:\n"
    "            return \"nobuy\"\n"
    "        return None\n\n"
    "    def sample(self, now, out):\n"
    "        b = math.floor(now / SAMPLE_S) * SAMPLE_S\n"
    "        if self.last_boundary is not None and b <= self.last_boundary:\n"
    "            return\n"
    "        if self.last_boundary is not None and b - self.last_boundary > SAMPLE_S:\n"
    "            miss = int((b - self.last_boundary) // SAMPLE_S) - 1\n"
    "            for k in range(max(0, miss - HIST_N), miss):\n"
    "                tb = self.last_boundary + (k + 1) * SAMPLE_S\n"
    "                for und in list(self.hist):\n"
    "                    for w in WKEYS:\n"
    "                        self.hist[und][w].append({\"t\": tb, \"cp\": None, \"L\": None, \"cb\": 0, \"pb\": 0, \"n\": 0, \"why\": \"missed\"})\n"
    "        self.last_boundary = b\n"
    "        line = {}\n"
    "        for und in set(out) | set(self.hist):\n"
    "            res = out.get(und) or {}\n"
    "            lu = {}\n"
    "            for w in WKEYS:\n"
    "                sm = res.get(w) or {}\n"
    "                why = self._why(und, w, int(w[:-1]), b, sm)\n"
    "                cb, pb = sm.get(\"cb\") or 0, sm.get(\"pb\") or 0\n"
    "                L = None if why else round(_logratio(cb, pb), 4)\n"
    "                cp = None if why else sm.get(\"cp_buy\")\n"
    "                self.hist[und][w].append({\"t\": b, \"cp\": cp, \"L\": L, \"cb\": cb, \"pb\": pb, \"n\": sm.get(\"n\") or 0, \"why\": why})\n"
    "                lu[WKEYS[w]] = [cp, L, cb, pb, sm.get(\"n\") or 0, why]\n"
    "            line[und] = lu\n"
    "            self.mom[und] = {w: self.momentum(und, w) for w in WKEYS}\n"
    "        if HIST_LOG and _rth(b):\n"
    "            try:\n"
    "                self.histq.put_nowait({\"t\": b, \"pt\": datetime.fromtimestamp(b, PT).strftime(\"%H:%M:%S\"),\n"
    "                                       \"sel\": _iso(self.selected_at), \"u\": line})\n"
    "            except queue.Full:\n"
    "                pass\n\n"
    "    def momentum(self, und, w):\n"
    "        wsec = int(w[:-1])\n"
    "        sl = list(self.hist[und][w])\n"
    "        h = [x[\"cp\"] for x in sl]\n"
    "        rr = self.rerank_at.get(und)\n"
    "        last = sl[-MOM_SLOTS:]\n"
    "        ok = lambda x: x[\"L\"] is not None and not (rr and x[\"t\"] - wsec < rr)\n"
    "        valid = [x for x in last if ok(x)]\n"
    "        d = s = None\n"
    "        if last and ok(last[-1]) and len(valid) >= MOM_MIN_VALID:\n"
    "            s = _ols_slope([(x[\"t\"], x[\"L\"]) for x in valid]) * 60.0\n"
    "            din, dout = DB[w]\n"
    "            prev = self.last_d[und].get(w)\n"
    "            sg = 1 if s > 0 else -1\n"
    "            if prev in (1, -1) and s * prev >= dout:\n"
    "                d = prev\n"
    "            elif abs(s) >= din:\n"
    "                d = sg\n"
    "            else:\n"
    "                d = 0\n"
    "            s = round(s, 2)\n"
    "        self.last_d[und][w] = d\n"
    "        return {\"d\": d, \"s\": s, \"nv\": len(valid), \"h\": h, \"rr\": bool(rr and last and any(x[\"t\"] - wsec < rr for x in last))}\n"
    "\n\ndef _r(a, b):\n", "methods")

# selector: re-rank overlap tracking
rep("            if chosen:\n                ST.subs = chosen;",
    "            if chosen:\n"
    "                if ST.subs:  # OPTMOM: flag names whose contract set changed a lot\n"
    "                    def _by(lst):\n"
    "                        g = defaultdict(set)\n"
    "                        for c in lst:\n"
    "                            m = OCC.match(c)\n"
    "                            if m: g[m.group(1)].add(c)\n"
    "                        return g\n"
    "                    old, new = _by(ST.subs), _by(chosen)\n"
    "                    t_rr = time.time()\n"
    "                    for u, oc in old.items():\n"
    "                        if oc and len(oc & new.get(u, set())) / len(oc) < RERANK_MIN_OVERLAP:\n"
    "                            ST.rerank_at[u] = t_rr\n"
    "                ST.subs = chosen;", "selector")

# JSONL writer thread, warm-start, rotation
rep("async def h_flow(req):\n",
    "def _hist_rotate():\n"
    "    \"\"\"OPTMOM: gzip non-today JSONL, delete gz older than HIST_KEEP_D days.\"\"\"\n"
    "    HIST_DIR.mkdir(parents=True, exist_ok=True)\n"
    "    today = datetime.now(ET).date()\n"
    "    for f in HIST_DIR.glob(\"*.jsonl\"):\n"
    "        try:\n"
    "            if date.fromisoformat(f.stem) < today:\n"
    "                with open(f, \"rb\") as src, gzip.open(str(f) + \".gz\", \"wb\") as dst:\n"
    "                    dst.write(src.read())\n"
    "                f.unlink()\n"
    "        except Exception as e:\n"
    "            log.warning(\"hist rotate %s: %s\", f.name, e)\n"
    "    for f in HIST_DIR.glob(\"*.jsonl.gz\"):\n"
    "        try:\n"
    "            if (today - date.fromisoformat(f.name[:10])).days > HIST_KEEP_D:\n"
    "                f.unlink()\n"
    "        except Exception:\n"
    "            pass\n\n\n"
    "def _hist_thread():\n"
    "    cur = None\n"
    "    while True:\n"
    "        rec = ST.histq.get()\n"
    "        try:\n"
    "            day = datetime.fromtimestamp(rec[\"t\"], ET).date().isoformat()\n"
    "            f = HIST_DIR / f\"{day}.jsonl\"\n"
    "            if cur != day:\n"
    "                _hist_rotate(); cur = day\n"
    "            new = not f.exists()\n"
    "            with open(f, \"a\") as fh:\n"
    "                if new:\n"
    "                    fh.write(json.dumps({\"hdr\": 1, \"version\": \"0.3.0\", \"tuple\": [\"cp\", \"L\", \"cb\", \"pb\", \"n\", \"why\"],\n"
    "                                         \"deadband\": DB, \"hist_n\": HIST_N, \"sample_s\": SAMPLE_S}) + \"\\n\")\n"
    "                fh.write(json.dumps(rec, separators=(\",\", \":\")) + \"\\n\")\n"
    "        except Exception as e:\n"
    "            log.warning(\"hist log write: %s\", e)\n\n\n"
    "def _hist_warm():\n"
    "    \"\"\"OPTMOM: refill deques from the tail of today's JSONL after a restart.\"\"\"\n"
    "    f = HIST_DIR / f\"{datetime.now(ET).date().isoformat()}.jsonl\"\n"
    "    if not f.exists():\n"
    "        return 0\n"
    "    try:\n"
    "        with open(f, \"rb\") as fh:\n"
    "            fh.seek(0, 2); sz = fh.tell(); fh.seek(max(0, sz - 60000))\n"
    "            lines = fh.read().decode(\"utf-8\", \"ignore\").splitlines()[1:]\n"
    "        recs = [json.loads(l) for l in lines[-HIST_N:] if l.startswith('{\"t\"')]\n"
    "    except Exception as e:\n"
    "        log.warning(\"hist warm: %s\", e); return 0\n"
    "    cut = time.time() - HIST_N * SAMPLE_S\n"
    "    n = 0\n"
    "    for rec in recs:\n"
    "        if rec[\"t\"] < cut:\n"
    "            continue\n"
    "        for und, lu in rec[\"u\"].items():\n"
    "            for w, k in WKEYS.items():\n"
    "                v = lu.get(k)\n"
    "                if v:\n"
    "                    ST.hist[und][w].append({\"t\": rec[\"t\"], \"cp\": v[0], \"L\": v[1], \"cb\": v[2], \"pb\": v[3], \"n\": v[4], \"why\": v[5]})\n"
    "        ST.last_boundary = rec[\"t\"]; n += 1\n"
    "    return n\n\n\n"
    "async def h_history(req):\n"
    "    u = req.query.get(\"sym\", \"NVDA\").upper()\n"
    "    h = ST.hist.get(u) or {}\n"
    "    return web.json_response({\"sym\": u, \"mom\": ST.mom.get(u), \"slots\": {w: list(h.get(w, [])) for w in WKEYS}})\n\n\n"
    "async def h_flow(req):\n", "hist funcs")

rep("    app.router.add_get(\"/v1/recent\", h_recent)\n",
    "    app.router.add_get(\"/v1/recent\", h_recent)\n"
    "    app.router.add_get(\"/v1/history\", h_history)  # OPTMOM\n"
    "    if MOMENTUM:\n"
    "        try:\n"
    "            _hist_rotate()\n"
    "            log.info(\"momentum on; warm-started %d slots from JSONL\", _hist_warm())\n"
    "        except Exception as e:\n"
    "            log.warning(\"hist init: %s\", e)\n"
    "        if HIST_LOG:\n"
    "            threading.Thread(target=_hist_thread, daemon=True, name=\"cp-hist\").start()\n", "main")

# OPTMOM2: a window is only valid once contracts are actually subscribed (not just authenticated)
rep("        self.histq: queue.Queue = queue.Queue(maxsize=200)\n",
    "        self.histq: queue.Queue = queue.Queue(maxsize=200)\n"
    "        self.subs_ready_at = None  # OPTMOM2: first non-empty subscription ack on this connection\n", "fix2 state", True)
rep("        if self.ws_state != \"subscribed_ready\" or not self.ws_connected_at or (b - wsec) < self.ws_connected_at:\n",
    "        if (self.ws_state != \"subscribed_ready\" or not self.ws_connected_at or not self.subs_ready_at\n"
    "                or (b - wsec) < max(self.ws_connected_at, self.subs_ready_at)):  # OPTMOM2\n", "fix2 why", True)
rep("                                    self.have = set(m.get(\"quotes\") or []) & set(m.get(\"trades\") or [])\n",
    "                                    _had = bool(self.have)\n"
    "                                    self.have = set(m.get(\"quotes\") or []) & set(m.get(\"trades\") or [])\n"
    "                                    if self.have and not _had:\n"
    "                                        self.st.subs_ready_at = recv  # OPTMOM2\n", "fix2 sub", True)
rep("                        self.ws = ws; self.have = set(); self.st.ws_state = \"connected\"\n",
    "                        self.ws = ws; self.have = set(); self.st.ws_state = \"connected\"; self.st.subs_ready_at = None  # OPTMOM2\n", "fix2 reconnect", True)

# OPTMOM3: don't wipe the warm-started history on the first compute() (day_date starts as None)
rep("            self.hist.clear(); self.last_d.clear(); self.mom.clear(); self.last_boundary = None  # OPTMOM\n",
    "            if self.day_date_seen:  # OPTMOM3: real rollover only, keep warm-start on boot\n"
    "                self.hist.clear(); self.last_d.clear(); self.mom.clear(); self.last_boundary = None  # OPTMOM\n"
    "            self.day_date_seen = True\n", "fix3 rollover", 3)
rep("        self.subs_ready_at = None  # OPTMOM2: first non-empty subscription ack on this connection\n",
    "        self.subs_ready_at = None  # OPTMOM2: first non-empty subscription ack on this connection\n"
    "        self.day_date_seen = False  # OPTMOM3\n", "fix3 state", 3)
p.write_text(s)
print("patched", p)
