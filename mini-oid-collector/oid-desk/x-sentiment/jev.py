"""TypeSafe Jev (System One) post-stance scorer for x-sentiment. Stdlib only.
One request per post: state = {ticker, post}, one Choice question -> calibrated probabilities over
{bullish, bearish, neutral, not_about_ticker}. Cost-guarded with its own ledger. The API key is read from a file
at runtime and never logged. Any error -> None so the caller falls back to the lexicon."""
import datetime as dt, json, os, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
URL = "https://api.typesafe.ai/v1/systemone"
DEFAULTS = {"enabled": True, "model": "jev-1.14.0", "key_path": "~/oid-data/secrets/TYPESAFE_API_KEY",
            "usd_per_mtok_input": 0.042, "daily_usd_cap": 0.50, "monthly_usd_cap": 10.0, "max_posts_per_day": 3000,
            "timeout_s": 10, "workers": 4, "offtopic_min_p": 0.5, "max_post_chars": 1200}
QUESTION = {
    "type": "choice",
    "instructions": "What stance does `post` take on the stock `ticker`, i.e. which way does the author expect or argue its price will go?",
    "criteria": {
        "bullish": "Expects or argues the ticker's price will rise: buying or adding, calls, upgrades, breakouts, strong results or guidance, price-target raises, squeeze talk.",
        "bearish": "Expects or argues the ticker's price will fall: selling or trimming, shorting, puts, downgrades, breakdowns, weak results or guidance, dilution, price-target cuts.",
        "neutral": "Is about the ticker but takes no directional view: plain news or data without slant, a question, a mixed or balanced take.",
        "not_about_ticker": "The ticker is only listed in passing among others, or the post is really about something else (other stocks, promotion, spam, unrelated topic).",
    },
}
LAB = {"bullish": "bull", "bearish": "bear", "neutral": "neu", "not_about_ticker": "off"}


def _now():
    return dt.datetime.now(PT)


class JevScorer:
    def __init__(s, cfg_scorer, state_dir):
        s.c = {**DEFAULTS, **(cfg_scorer or {})}
        s.ledger_path = Path(state_dir) / "jev_budget.json"
        s.lock = threading.Lock()
        today, month = _now().strftime("%Y-%m-%d"), _now().strftime("%Y-%m")
        try: L = json.loads(s.ledger_path.read_text())
        except Exception: L = {}
        if L.get("day_pt") != today: L.update({"day_pt": today, "day_usd": 0.0, "day_tokens": 0, "day_posts": 0, "day_errors": 0})
        if L.get("month") != month: L.update({"month": month, "month_usd": 0.0, "month_tokens": 0})
        s.L = L
        p = Path(os.path.expanduser(s.c["key_path"]))
        s.key = p.read_text().strip() if p.exists() else None
        s.last_error = None

    def available(s):
        return bool(s.c.get("enabled")) and bool(s.key)

    def _guard(s, est_usd):
        L, c = s.L, s.c
        if L["day_usd"] + est_usd > c["daily_usd_cap"]: return "jev_day_cap"
        if L["month_usd"] + est_usd > c["monthly_usd_cap"]: return "jev_month_cap"
        if L["day_posts"] >= c["max_posts_per_day"]: return "jev_post_cap"
        return None

    def _record(s, tokens, ok):
        usd = tokens * s.c["usd_per_mtok_input"] / 1e6
        with s.lock:
            L = s.L; L["day_usd"] = round(L["day_usd"] + usd, 6); L["month_usd"] = round(L["month_usd"] + usd, 6)
            L["day_tokens"] += tokens; L["month_tokens"] += tokens; L["day_posts"] += 1
            if not ok: L["day_errors"] += 1
        return usd

    def save(s):
        s.L["updated_pt"] = _now().strftime("%Y-%m-%d %I:%M:%S %p PT")
        tmp = s.ledger_path.with_suffix(".tmp"); tmp.write_text(json.dumps(s.L, indent=1)); os.replace(tmp, s.ledger_path)

    def _one(s, sym, text):
        body = {"model": s.c["model"], "state": {"ticker": "$" + sym, "post": (text or "")[: int(s.c["max_post_chars"])]},
                "questions": {"stance": QUESTION}}
        data = json.dumps(body).encode()
        with s.lock:
            why = s._guard(len(data) / 3.0 * s.c["usd_per_mtok_input"] / 1e6)
        if why: s.last_error = why; return None
        req = urllib.request.Request(URL, data=data, method="POST", headers={
            "Authorization": "Bearer " + s.key, "Content-Type": "application/json", "User-Agent": "oid-x-sentiment/jev"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=float(s.c["timeout_s"])) as r:
                    resp = json.loads(r.read().decode())
                a = resp["answers"]["stance"]; probs = {k: float(v) for k, v in a["probabilities"].items()}
                tok = int((resp.get("usage") or {}).get("input_tokens") or 0)
                usd = s._record(tok, True)
                return {"choice": a["choice"], "p": {k: round(probs.get(k, 0.0), 4) for k in QUESTION["criteria"]},
                        "conf": round(float(a.get("confidence") or 0), 3), "model": resp.get("model"), "tokens": tok, "usd": usd}
            except urllib.error.HTTPError as e:
                s.last_error = f"http_{e.code}"
                if e.code in (429, 529) and attempt < 2: time.sleep(0.5 * (2 ** attempt)); continue
                s._record(0, False); return None
            except Exception as e:   # timeout, network, schema change
                s.last_error = type(e).__name__
                if attempt < 1: time.sleep(0.3); continue
                s._record(0, False); return None
        return None

    def classify(s, sym, texts):
        """-> list aligned with texts: dict or None (None = use the lexicon for that post)."""
        if not texts or not s.available(): return [None] * len(texts)
        with ThreadPoolExecutor(max_workers=max(1, int(s.c["workers"]))) as ex:
            out = list(ex.map(lambda t: s._one(sym, t), texts))
        s.save()
        return out
