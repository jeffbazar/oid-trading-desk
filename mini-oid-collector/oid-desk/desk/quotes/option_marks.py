#!/usr/bin/env python3
"""Mini OPRA option marks: declare contracts -> poll the Mac mini -> pick the best mark (research / paper only).

Mac mini collector (v0.3.0+) streams Alpaca OPRA for the OCC contracts the box declares with
``PUT /v1/options/subs``; brand-new / quote-less contracts are seeded from Alpaca's REST snapshot so
weekend and pre-open reads still return the last session's final quote.

Box side (this module):
  desired_contracts()        open paper seats + legs (trades.json), paper-open.json seats, live RH option
                             positions (cache/rh-live-option-positions.json), config/option-watch-contracts.json.
                             Expired contracts are reported, never subscribed.
  push_subs(occs)            PUT the list to the mini (replaces the whole list; box is the only declarer).
  build_cache_record(occs)   GET /v1/options -> normalized rows; the poller writes cache/mini-option-quotes.json.
  pick_mark(occ, rh=...)     mini OPRA first when live (<=60 s RTH), else Robinhood, else newest of either
                             with mark_class "final" (session closed) or "stale". Records mark_source.

PRIVATE: cache/mini-option-quotes.json is box-only (never packaged/published). The public blotter only
shows marks/P&L for our own seats, exactly as before. Token is never printed or written. Zero orders.

CLI:
  python3 quotes/option_marks.py contracts            # what would be declared (+ expired/skipped)
  python3 quotes/option_marks.py push                 # declare to the mini now
  python3 quotes/option_marks.py poll                 # one poll -> cache/mini-option-quotes.json
  python3 quotes/option_marks.py marks [--occ A,B] [--rh-quotes-file F]   # best mark per contract (JSON)
  python3 quotes/option_marks.py occ NVDA 2026-11-20 call 245             # -> NVDA261120C00245000
  python3 quotes/option_marks.py set-live-positions FILE   # store live RH option positions (occ list) for subs
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mini_client as mc  # noqa: E402

OID = mc.OID
TRADES_PATH = OID / "paper-trades" / "trades.json"
PAPER_OPEN_PATH = OID / "paper-trades" / "paper-open.json"
LIVE_POS_PATH = Path(os.environ.get("OID_RH_LIVE_OPTIONS", str(OID / "cache" / "rh-live-option-positions.json")))
WATCH_PATH = OID / "config" / "option-watch-contracts.json"
OPT_CACHE_PATH = Path(os.environ.get("OID_MINI_OPT_CACHE", str(OID / "cache" / "mini-option-quotes.json")))
SUBS_STATE_PATH = OID / "cache" / "mini-option-subs-state.json"

MINI_OPRA_SOURCE = "mini-opra"
RH_SOURCE = "rh"
# Option quote freshness (seconds) per desk session. Options only quote 9:30-16:00 ET (+15 min for ETFs),
# so PRE/AH/closed have no "live" window: the last quote is the session's final quote.
LIVE_MAX_AGE_S = {"rth": 60.0, "pre": 0.0, "ah": 0.0, "overnight": 0.0, "closed": 0.0}
FINAL_MAX_AGE_S = 4 * 24 * 3600.0  # final quote of the last session (covers 3-day weekends)
RH_LIVE_MAX_AGE_S = 120.0
OPT_CACHE_MAX_FILE_AGE_S = 30.0
OPEN_STATUSES = frozenset({"open", "watching", "paper", "live"})
WATCH_STATUSES = frozenset({"leopold_watch", "watch_external"})
OCC_RE = re.compile(r"^([A-Z][A-Z0-9]{0,5})(\d{6})([CP])(\d{8})$")


# ---------------------------------------------------------------- OCC helpers
def occ_symbol(root: str, expiry: Any, right: Any, strike: Any) -> Optional[str]:
    """('NVDA', '2026-11-20', 'call', 245) -> 'NVDA261120C00245000'. None when a field is missing/bad."""
    try:
        root = str(root or "").strip().upper().replace(" ", "")
        if not root or not re.match(r"^[A-Z][A-Z0-9]{0,5}$", root):
            return None
        d = expiry if isinstance(expiry, date) else datetime.strptime(str(expiry)[:10], "%Y-%m-%d").date()
        r = str(right or "").strip().lower()
        cp = "C" if r in ("c", "call", "calls") else "P" if r in ("p", "put", "puts") else None
        if cp is None:
            return None
        k = round(float(strike) * 1000)
        if k <= 0 or k >= 10 ** 8:
            return None
        return f"{root}{d.strftime('%y%m%d')}{cp}{k:08d}"
    except (TypeError, ValueError):
        return None


def parse_occ(occ: str) -> Optional[dict[str, Any]]:
    m = OCC_RE.match(str(occ or "").strip().upper())
    if not m:
        return None
    root, ymd, cp, k = m.groups()
    exp = datetime.strptime(ymd, "%y%m%d").date()
    return {"root": root, "expiry": exp.isoformat(), "right": "call" if cp == "C" else "put", "strike": int(k) / 1000.0}


def _today_et() -> date:
    try:
        from market_session import now_et  # type: ignore

        return now_et().date()
    except Exception:  # pragma: no cover
        return datetime.now(timezone.utc).date()


def _row_right(t: dict) -> Any:
    return t.get("right") or t.get("optionType") or t.get("type") or t.get("callPut")


def _row_expiry(t: dict) -> Any:
    return t.get("expiry") or t.get("expiration") or t.get("expiration_date")


def row_occ(t: dict) -> Optional[str]:
    """OCC for a single-leg seat/leg dict (explicit occ fields win)."""
    for k in ("occ", "occSymbol", "occ_symbol"):
        v = t.get(k)
        if isinstance(v, str) and OCC_RE.match(v.strip().upper()):
            return v.strip().upper()
    root = t.get("symbol") or t.get("underlying") or t.get("ticker") or t.get("chain_symbol")
    if isinstance(root, dict):
        root = root.get("symbol")
    return occ_symbol(root, _row_expiry(t), _row_right(t), t.get("strike") if t.get("strike") is not None else t.get("strike_price"))


def leg_key(leg: dict) -> str:
    """legMarks key used by Hal: short70P / long68P."""
    k = float(leg.get("strike"))
    ks = str(int(k)) if k.is_integer() else f"{k:g}"
    cp = "P" if str(_row_right(leg) or "").lower().startswith("p") else "C"
    return f"{(leg.get('side') or '').lower()}{ks}{cp}"


# ---------------------------------------------------------------- contract discovery
def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _ledger_rows(ledger: dict) -> list[dict]:
    rows = [t for t in ledger.get("trades", []) if (t.get("status") or "").lower() in OPEN_STATUSES | WATCH_STATUSES]
    rows += list(ledger.get("leopoldWatches") or [])
    return rows


def desired_contracts(*, today: Optional[date] = None, ledger: Optional[dict] = None,
                      paper_open: Optional[dict] = None, live: Optional[Any] = None,
                      watch: Optional[Any] = None) -> dict[str, Any]:
    """Every option contract the desk marks. Returns {contracts:[occ], refs:{occ:[ref..]}, expired:{occ:[ref]}, unparsed:[ref]}."""
    today = today or _today_et()
    ledger = ledger if ledger is not None else (_read_json(TRADES_PATH) or {})
    paper_open = paper_open if paper_open is not None else (_read_json(PAPER_OPEN_PATH) or {})
    live = live if live is not None else _read_json(LIVE_POS_PATH)
    watch = watch if watch is not None else _read_json(WATCH_PATH)
    refs: dict[str, list[str]] = {}
    expired: dict[str, list[str]] = {}
    unparsed: list[str] = []

    def add(occ: Optional[str], ref: str) -> None:
        if not occ:
            unparsed.append(ref)
            return
        p = parse_occ(occ)
        if p and date.fromisoformat(p["expiry"]) < today:
            expired.setdefault(occ, [])
            if ref not in expired[occ]:
                expired[occ].append(ref)
            return
        refs.setdefault(occ, [])
        if ref not in refs[occ]:
            refs[occ].append(ref)

    by_id = {str(t.get("id")): t for t in ledger.get("trades", []) if t.get("id")}
    seen_ids: set[str] = set()

    def add_row(t: dict, kind: str) -> None:
        tid = str(t.get("id") or t.get("instrumentId") or "?")
        seen_ids.add(tid)
        legs = t.get("legs") if isinstance(t.get("legs"), list) else None
        if legs:
            for leg in legs:
                if isinstance(leg, dict):
                    lg = dict(leg)
                    lg.setdefault("symbol", t.get("symbol") or t.get("underlying"))
                    lg.setdefault("expiry", _row_expiry(t))
                    add(row_occ(lg), f"{kind}:{tid}:{leg.get('side', '')}")
            return
        add(row_occ(t), f"{kind}:{tid}")

    for t in _ledger_rows(ledger):
        st = (t.get("status") or "").lower()
        kind = "watch" if (st in WATCH_STATUSES or t.get("agent") == "Leopold") else ("hal" if t.get("agent") == "Hal" else "seat")
        add_row(t, kind)
    for key in ("seats", "roseSeats", "halSeats"):
        for s in (paper_open or {}).get(key) or []:
            if not isinstance(s, dict):
                continue
            sid = str(s.get("id") or "")
            if sid in seen_ids:
                continue
            src = by_id.get(sid, s)
            add_row(src, "hal" if key == "halSeats" else "seat")
    live_list = live.get("positions") if isinstance(live, dict) else live
    for p in live_list or []:
        if isinstance(p, dict):
            add(row_occ(p), f"live:{p.get('acct') or p.get('account') or '?'}:{p.get('option_id') or ''}"[:80])
        elif isinstance(p, str):
            add(p.strip().upper() if OCC_RE.match(p.strip().upper()) else None, f"live:{p}")
    watch_list = watch.get("contracts") if isinstance(watch, dict) else watch
    for w in watch_list or []:
        if isinstance(w, str):
            add(w.strip().upper() if OCC_RE.match(w.strip().upper()) else None, f"watchlist:{w}")
        elif isinstance(w, dict):
            add(row_occ(w), f"watchlist:{w.get('label') or w.get('occ') or '?'}")
    return {"contracts": sorted(refs), "refs": refs, "expired": expired, "unparsed": unparsed,
            "today_et": today.isoformat()}


def instrument_occ_map(ledger: dict) -> dict[str, str]:
    """RH instrumentId -> OCC for single-leg rows and legs (lets RH-keyed quote maps take mini overlays)."""
    out: dict[str, str] = {}
    for t in _ledger_rows(ledger):
        if t.get("instrumentId") and not t.get("legs"):
            o = row_occ(t)
            if o:
                out[str(t["instrumentId"])] = o
        for leg in t.get("legs") or []:
            if isinstance(leg, dict) and leg.get("instrumentId"):
                lg = dict(leg)
                lg.setdefault("symbol", t.get("symbol"))
                lg.setdefault("expiry", _row_expiry(t))
                o = row_occ(lg)
                if o:
                    out[str(leg["instrumentId"])] = o
    return out


# ---------------------------------------------------------------- transport
def _http(method: str, path: str, *, body: Any = None, params: Optional[dict] = None,
          timeout: float = 4.0, opener=None) -> tuple[int, Any]:
    url = mc.MINI_BASE_URL.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    tok = mc._read_token()
    if not tok:
        raise mc.MiniError(f"token file missing/empty: {mc.TOKEN_FILE}")
    headers = {"Accept": "application/json", "User-Agent": "oid-option-marks/1.0", "Authorization": "Bearer " + tok,
               "X-OID-Client": "oid-box/option_marks"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    if opener is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": mc.MINI_PROXY} if mc.MINI_PROXY else {})).open
    try:
        resp = opener(req, timeout=timeout)
        status = getattr(resp, "status", None) or resp.getcode()
        raw = resp.read()
    except urllib.error.HTTPError as e:
        raise mc.MiniError(f"HTTP {e.code} from mini {method} {path}") from None
    except Exception as e:
        raise mc.MiniError(f"mini unreachable {method} {path}: {type(e).__name__}") from None
    try:
        return int(status), json.loads(raw.decode("utf-8"))
    except Exception:
        raise mc.MiniError(f"bad JSON from mini {path}") from None


def push_subs(occs: Iterable[str], *, opener=None, state_path: Optional[Path] = None) -> dict[str, Any]:
    occs = sorted({o.strip().upper() for o in occs if o})
    status, res = _http("PUT", "/v1/options/subs", body={"contracts": occs, "source": "oid-box/option_marks"}, opener=opener)
    out = {"ok": bool(res.get("ok")), "http_status": status, "count": res.get("count"), "invalid": res.get("invalid"),
           "changed": res.get("changed"), "pushed_at_pt": mc._pt_stamp(), "pushed_epoch": round(time.time(), 1),
           "contracts": occs}
    sp = state_path or SUBS_STATE_PATH
    try:
        _atomic_write(sp, out)
    except OSError:
        pass
    return out


def maybe_push(desired: list[str], *, max_age_s: float = 3600.0, opener=None, state_path: Optional[Path] = None) -> Optional[dict]:
    """Push when the desired set changed vs the last push, or hourly (self-heal after a mini reinstall).

    OID_OPTION_SUBS_PUSH=0 disables declaring (mini shadow run: exactly one declarer at a time). Default on.
    """
    if os.environ.get("OID_OPTION_SUBS_PUSH", "1") == "0":
        return None
    sp = state_path or SUBS_STATE_PATH
    st = _read_json(sp) or {}
    if st.get("ok") and sorted(st.get("contracts") or []) == sorted(desired) and time.time() - float(st.get("pushed_epoch") or 0) < max_age_s:
        return None
    return push_subs(desired, opener=opener, state_path=sp)


def normalize_option_row(occ: str, row: dict, *, mini_as_of: Optional[float]) -> dict[str, Any]:
    r = mc.normalize_row(occ, row, mini_as_of=mini_as_of)
    r["source"] = MINI_OPRA_SOURCE
    bid, ask, last = r.get("bid"), r.get("ask"), r.get("last")
    # Option NBBO: bid may be 0 on far-OTM contracts; mid of 0/x is still the venue mark RH would show.
    if bid is not None and ask is not None and ask > 0 and ask >= bid >= 0:
        r["mid"] = round((bid + ask) / 2.0, 4)
    r["mark"] = r.get("mid") if r.get("mid") is not None else last
    r["seeded"] = "snapshot" in str(row.get("quote_feed") or "") or "snapshot" in str(row.get("trade_feed") or "")
    r["contract_id"] = occ
    return r


def fetch_options(occs: list[str], *, opener=None, timeout: float = 4.0) -> dict[str, Any]:
    res: dict[str, Any] = {"ok": False, "rows": {}, "missing": list(occs), "error": None}
    if not occs:
        res.update(ok=True, missing=[])
        return res
    try:
        status, data = _http("GET", "/v1/options", params={"contracts": ",".join(occs)}, opener=opener, timeout=timeout)
    except mc.MiniError as e:
        res["error"] = str(e)
        return res
    mini_as_of = mc._parse_ts(data.get("as_of"))
    rows = {}
    for occ, row in (data.get("options") or {}).items():
        if isinstance(row, dict):
            rows[occ] = normalize_option_row(occ, row, mini_as_of=mini_as_of)
    feed = data.get("feed") or {}
    res.update(ok=True, http_status=status, rows=rows, missing=[o for o in occs if o not in rows],
               collector_status=data.get("status"),
               options_feed={"state": feed.get("state"), "connected": feed.get("connected"), "feed": feed.get("feed"),
                             "subscribed_count": feed.get("subscribed_count")})
    return res


def build_cache_record(occs: list[str], *, opener=None, desired_info: Optional[dict] = None) -> dict[str, Any]:
    f = fetch_options(occs, opener=opener)
    t = time.time()
    sess = mc.current_session()
    rec = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
        "as_of_pt": mc._pt_stamp(t),
        "written_epoch": round(t, 3),
        "writer": "quotes/option_marks.py (via quotes/mini_poller.py)",
        "source": "oid-mini collector · Alpaca OPRA (real-time) · REST snapshot seed for quote-less contracts",
        "private": "box-only; never publish raw OPRA rows",
        "session": sess,
        "live_max_age_s": LIVE_MAX_AGE_S.get(sess, 60.0),
        "ok": f["ok"],
        "error": f.get("error"),
        "collector_status": f.get("collector_status"),
        "options_feed": f.get("options_feed"),
        "contracts": occs,
        "missing": f["missing"],
        "quotes": f["rows"],
        "mandate": "Research / paper only · zero RH execution",
    }
    if desired_info:
        rec["expired_skipped"] = sorted(desired_info.get("expired") or {})
        rec["refs"] = desired_info.get("refs")
    return rec


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)
        fh.write("\n")
    os.replace(tmp, path)


def write_cache(rec: dict, path: Optional[Path] = None) -> None:
    _atomic_write(path or OPT_CACHE_PATH, rec)


def read_option_cache(*, path: Optional[Path] = None, now: Optional[float] = None,
                      max_file_age_s: float = OPT_CACHE_MAX_FILE_AGE_S) -> dict[str, Any]:
    """Rows with ages re-computed to *now* (quote_age_s/trade_age_s/age_s += seconds since write).

    A cache file older than max_file_age_s is still returned (fresh_file False) because its rows
    carry their own source timestamps; pick_mark classifies them by age.
    """
    p = path or OPT_CACHE_PATH
    t = time.time() if now is None else now
    out: dict[str, Any] = {"fresh_file": False, "file_age_s": None, "quotes": {}, "path": str(p)}
    rec = _read_json(p)
    if not isinstance(rec, dict):
        out["error"] = "missing_or_unreadable"
        return out
    w = float(rec.get("written_epoch") or 0)
    fa = max(0.0, t - w) if w else None
    out["file_age_s"] = round(fa, 2) if fa is not None else None
    out["fresh_file"] = fa is not None and fa <= max_file_age_s
    for occ, row in (rec.get("quotes") or {}).items():
        if not isinstance(row, dict):
            continue
        r = dict(row)
        for k in ("quote_age_s", "trade_age_s", "age_s"):
            if r.get(k) is not None and fa is not None:
                r[k] = round(float(r[k]) + fa, 2)
        out["quotes"][occ] = r
    return out


# ---------------------------------------------------------------- mark selection
def _rh_epoch(q: dict) -> Optional[float]:
    return mc._parse_ts(q.get("quoted_at")) if q else None


def pick_mark(occ: str, *, rh: Optional[dict] = None, mini_rows: Optional[dict] = None,
              session: Optional[str] = None, now: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Best mark for one contract. rh = refresh_marks.normalize_quotes() row (mark/bid/ask/quoted_at/delayed).

    Order: mini OPRA live (quote <= 60 s in RTH) -> RH live (<=120 s, not delayed) -> newest of either
    (mark_class "final" when the session is closed and the quote is from the last session, else "stale").
    Returns None only when neither source has any price.
    """
    t = time.time() if now is None else now
    sess = session or mc.current_session()
    if mini_rows is None:
        mini_rows = read_option_cache(now=t)["quotes"]
    m = mini_rows.get(occ) if mini_rows else None
    live_lim = LIVE_MAX_AGE_S.get(sess, 60.0)
    cands: list[dict[str, Any]] = []
    if m and m.get("mark") is not None:
        qa = m.get("quote_age_s") if m.get("mid") is not None else m.get("trade_age_s")
        ts = mc._parse_ts(m.get("quote_time") if m.get("mid") is not None else m.get("trade_time"))
        cands.append({"mark": float(m["mark"]), "bid": m.get("bid"), "ask": m.get("ask"), "last": m.get("last"),
                      "quoted_at": m.get("quote_time") or m.get("trade_time"), "epoch": ts, "age_s": qa,
                      "mark_source": MINI_OPRA_SOURCE, "delayed": bool(m.get("delayed")), "seeded": bool(m.get("seeded")),
                      "live": qa is not None and live_lim > 0 and qa <= live_lim and not m.get("delayed")})
    if rh and rh.get("mark") is not None:
        ts = _rh_epoch(rh)
        age = round(t - ts, 1) if ts else None
        cands.append({"mark": float(rh["mark"]), "bid": rh.get("bid"), "ask": rh.get("ask"), "last": None,
                      "quoted_at": rh.get("quoted_at"), "epoch": ts, "age_s": age, "mark_source": RH_SOURCE,
                      "delayed": bool(rh.get("delayed")),
                      "live": sess == "rth" and age is not None and age <= RH_LIVE_MAX_AGE_S and not rh.get("delayed")})
    if not cands:
        return None
    live = [c for c in cands if c["live"]]
    if live:
        best = live[0]  # mini listed first -> wins when both are live
        best["mark_class"] = "live"
    else:
        best = max(cands, key=lambda c: (c["epoch"] or 0.0, c["mark_source"] == MINI_OPRA_SOURCE))
        fin = sess != "rth" and best["age_s"] is not None and best["age_s"] <= FINAL_MAX_AGE_S
        best["mark_class"] = "final" if fin else "stale"
    best["stale"] = best["mark_class"] == "stale"
    best["session"] = sess
    best["occ"] = occ
    best.pop("live", None)
    return best


def overlay_rh_option_quotes(quotes: dict[str, dict], iid_to_occ: dict[str, str], *, mini_rows: Optional[dict] = None,
                             session: Optional[str] = None, now: Optional[float] = None) -> dict[str, Any]:
    """refresh_marks hook: for each instrumentId with an OCC, replace the RH row with pick_mark()'s winner.

    Greeks / prior close / underlying always stay from RH (OPRA has none). Rows RH did not return are
    ADDED from mini so the seat is not left unmarked. Mutates quotes; returns a summary.
    """
    t = time.time() if now is None else now
    sess = session or mc.current_session()
    if mini_rows is None:
        mini_rows = read_option_cache(now=t)["quotes"]
    summ: dict[str, Any] = {"session": sess, "mini_opra": [], "rh": [], "added_from_mini": [], "none": []}
    for iid, occ in iid_to_occ.items():
        rh = quotes.get(iid)
        best = pick_mark(occ, rh=rh, mini_rows=mini_rows, session=sess, now=t)
        if best is None:
            summ["none"].append(occ)
            continue
        row = dict(rh or {})
        row.update({"mark": best["mark"], "bid": best.get("bid"), "ask": best.get("ask"), "quoted_at": best.get("quoted_at"),
                    "delayed": best.get("delayed"), "mark_source": best["mark_source"], "mark_class": best["mark_class"],
                    "mark_age_s": best.get("age_s"), "occ": occ})
        if best["mark_source"] == MINI_OPRA_SOURCE:
            summ["mini_opra"].append(occ)
            if rh is None:
                summ["added_from_mini"].append(occ)
        else:
            summ["rh"].append(occ)
        quotes[iid] = row
    return summ


# ---------------------------------------------------------------- CLI
def _cli(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Mini OPRA option marks (no token output, zero orders)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("contracts")
    sub.add_parser("push")
    sub.add_parser("poll")
    mk = sub.add_parser("marks")
    mk.add_argument("--occ", default="", help="comma OCC list (default: all desired contracts)")
    mk.add_argument("--rh-quotes-file", type=Path, help="RH get_option_quotes JSON to compare/fall back to")
    oc = sub.add_parser("occ")
    oc.add_argument("root"); oc.add_argument("expiry"); oc.add_argument("right"); oc.add_argument("strike")
    sl = sub.add_parser("set-live-positions")
    sl.add_argument("file", type=Path, help="JSON list of {occ|chain_symbol,expiration_date,type/option_type,strike_price, acct, option_id, qty}")
    a = ap.parse_args(argv)

    if a.cmd == "occ":
        print(occ_symbol(a.root, a.expiry, a.right, a.strike))
        return 0
    if a.cmd == "set-live-positions":
        data = json.loads(a.file.read_text())
        items = data.get("positions") if isinstance(data, dict) else data
        out = []
        for p in items or []:
            o = row_occ({**p, "right": p.get("right") or p.get("option_type") or p.get("type")})
            if o:
                out.append({"occ": o, "acct": str(p.get("acct") or p.get("account") or "")[-4:], "option_id": p.get("option_id")})
        _atomic_write(LIVE_POS_PATH, {"updated_at_pt": mc._pt_stamp(), "writer": "option_marks.py set-live-positions",
                                      "private": "box-only", "positions": out})
        print(json.dumps({"ok": True, "n": len(out), "path": str(LIVE_POS_PATH)}))
        return 0
    d = desired_contracts()
    if a.cmd == "contracts":
        print(json.dumps(d, indent=2))
        return 0
    if a.cmd == "push":
        try:
            print(json.dumps(push_subs(d["contracts"]), indent=2))
        except mc.MiniError as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1
        return 0
    if a.cmd == "poll":
        rec = build_cache_record(d["contracts"], desired_info=d)
        write_cache(rec)
        print(json.dumps({"ok": rec["ok"], "error": rec["error"], "contracts": len(rec["contracts"]),
                          "rows": len(rec["quotes"]), "missing": rec["missing"], "path": str(OPT_CACHE_PATH)}))
        return 0
    # marks
    occs = [o.strip().upper() for o in a.occ.split(",") if o.strip()] or d["contracts"]
    rh_by_occ: dict[str, dict] = {}
    if a.rh_quotes_file:
        sys.path.insert(0, str(OID / "dashboard"))
        from refresh_marks import normalize_quotes  # type: ignore

        rhq = normalize_quotes(json.loads(a.rh_quotes_file.read_text()))
        imap = instrument_occ_map(_read_json(TRADES_PATH) or {})
        for iid, q in rhq.items():
            if iid in imap:
                rh_by_occ[imap[iid]] = q
    c = read_option_cache()
    out = {"cache_file_age_s": c.get("file_age_s"), "session": mc.current_session(), "marks": {}}
    for o in occs:
        out["marks"][o] = pick_mark(o, rh=rh_by_occ.get(o), mini_rows=c["quotes"])
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
