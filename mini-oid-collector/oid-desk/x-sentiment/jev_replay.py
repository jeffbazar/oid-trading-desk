"""Replay saved posts (no X reads) through the Jev scorer vs the lexicon.
usage: jev_replay.py [posts_raw.jsonl] [--n 12] [--per-sym 3]"""
import argparse, collections, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lexicon as LX, jev as JEV
ROOT = Path(os.environ.get("OID_DATA_ROOT", Path.home() / "oid-data"))
ap = argparse.ArgumentParser(); ap.add_argument("path", nargs="?"); ap.add_argument("--n", type=int, default=12); ap.add_argument("--per-sym", type=int, default=3)
a = ap.parse_args()
path = Path(a.path) if a.path else sorted((ROOT / "archive/posts_raw").glob("date=*/part-x-on-surge-*.jsonl"))[-1]
cfg = json.load(open(ROOT / "config/x-sentiment-config.json"))
seen, per, picks = set(), collections.Counter(), []
for l in open(path):
    r = json.loads(l); sym = (r.get("symbols") or "").split(",")[0].strip()
    if not sym or r["post_id"] in seen or per[sym] >= a.per_sym or r.get("lang") not in ("en", None): continue
    seen.add(r["post_id"]); per[sym] += 1; picks.append((sym, r["post_id"], r["text"]))
    if len(picks) >= a.n: break
J = JEV.JevScorer(cfg.get("scorer"), ROOT / "state/x")
print(f"source={path}  posts={len(picks)}  model={J.c["model"]}  key_present={J.available()}")
tot_tok = 0
for sym, pid, text in picks:
    j = J.classify(sym, [text])[0]; lx = LX.score_text(text, sym)
    t = " ".join(text.split())[:90]
    if j:
        tot_tok += j["tokens"]; p = j["p"]
        print(f"{sym:5} {pid}  jev={j["choice"]:16} bull={p["bullish"]:.2f} bear={p["bearish"]:.2f} neu={p["neutral"]:.2f} off={p["not_about_ticker"]:.2f} conf={j["conf"]:.2f} s={p["bullish"]-p["bearish"]:+.2f} | lex={lx:+.2f} tok={j["tokens"]} | {t}")
    else:
        print(f"{sym:5} {pid}  JEV-ERR {J.last_error} | lex={lx:+.2f} | {t}")
print(f"tokens={tot_tok} usd={tot_tok*J.c["usd_per_mtok_input"]/1e6:.6f}  ledger={json.dumps({k: J.L[k] for k in ("day_usd","day_tokens","day_posts","day_errors")})}")
