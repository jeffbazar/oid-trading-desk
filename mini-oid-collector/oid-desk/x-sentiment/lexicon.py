"""Small finance/trader lexicon for X posts (local, no network, no paid model).
score_text() returns a value in [-1, 1]; |s| >= THRESH is labeled bull/bear, else neutral.
Handles: weighted words/phrases, emoji, simple negation (3-token window), options slang (calls/puts with
buy/sell context), and price-target up/down phrasing. Deliberately conservative: unknown text -> 0 (neutral)."""
import re

THRESH = 0.2

BULL = {
    "bullish": 2.0, "bull": 1.2, "long": 0.8, "buy": 1.0, "buying": 1.0, "bought": 0.9, "adding": 1.0, "added": 0.8, "accumulate": 1.2,
    "accumulating": 1.2, "breakout": 1.5, "breaking out": 1.6, "ripping": 1.5, "rip": 1.0, "moon": 1.5, "mooning": 1.5, "squeeze": 1.0,
    "rally": 1.2, "rallying": 1.2, "surge": 1.2, "surging": 1.3, "soar": 1.3, "soaring": 1.3, "pop": 0.8, "popping": 1.0, "higher": 0.7,
    "upside": 1.0, "upgrade": 1.5, "upgraded": 1.5, "outperform": 1.3, "overweight": 1.0, "beat": 1.2, "beats": 1.2, "crushed it": 1.5,
    "raise": 0.8, "raised": 0.9, "raises": 0.9, "strong": 0.9, "strength": 0.9, "record": 0.8, "all-time high": 1.3, "ath": 1.0,
    "new high": 1.2, "new highs": 1.2, "bounce": 0.8, "reclaim": 1.0, "reclaimed": 1.0, "support held": 1.2, "green": 0.6, "winner": 0.9,
    "undervalued": 1.2, "cheap": 0.6, "calls": 0.7, "call sweep": 1.3, "call sweeps": 1.3, "bullish flow": 1.8, "send it": 1.2,
    "loading": 1.0, "loaded": 0.9, "gap up": 1.2, "beat and raise": 2.0, "guidance raised": 1.8, "buyback": 1.0, "partnership": 0.6,
    "demand": 0.5, "momentum": 0.5, "uptrend": 1.2, "higher low": 1.0, "golden cross": 1.2, "pt raised": 1.6, "price target raised": 1.6,
}
BEAR = {
    "bearish": 2.0, "bear": 1.2, "short": 0.8, "shorting": 1.2, "shorted": 1.0, "sell": 1.0, "selling": 1.0, "sold": 0.8, "dump": 1.3,
    "dumping": 1.4, "crash": 1.6, "crashing": 1.6, "tank": 1.3, "tanking": 1.4, "plunge": 1.4, "plunging": 1.4, "drop": 0.8, "dropping": 0.9,
    "falling": 0.9, "lower": 0.7, "downside": 1.0, "downgrade": 1.5, "downgraded": 1.5, "underperform": 1.3, "underweight": 1.0,
    "miss": 1.2, "missed": 1.2, "misses": 1.2, "cut": 0.8, "cuts": 0.8, "weak": 0.9, "weakness": 0.9, "breakdown": 1.5, "breaking down": 1.6,
    "rejected": 1.0, "rejection": 1.0, "overvalued": 1.2, "bubble": 1.0, "puts": 0.7, "put sweep": 1.3, "put sweeps": 1.3,
    "bearish flow": 1.8, "red": 0.6, "gap down": 1.2, "lower high": 1.0, "downtrend": 1.2, "death cross": 1.2, "dilution": 1.3,
    "offering": 0.8, "lawsuit": 1.0, "probe": 0.8, "investigation": 0.9, "guidance cut": 1.8, "lowered guidance": 1.8, "bagholder": 1.2,
    "bagholders": 1.2, "rug": 1.3, "fraud": 1.5, "sell-off": 1.3, "selloff": 1.3, "capitulation": 1.0, "pt cut": 1.6, "price target cut": 1.6,
    "lost support": 1.3, "lose support": 1.0, "fade": 0.8, "fading": 0.9, "trim": 0.6, "trimmed": 0.7, "trimming": 0.7, "exit": 0.5,
}
EMOJI = {"🚀": 1.2, "📈": 1.0, "🟢": 0.7, "💎": 0.6, "🐂": 1.0, "🔥": 0.4, "📉": -1.0, "🔴": -0.7, "🐻": -1.0, "💀": -0.6, "🩸": -0.9, "⚠️": -0.3}
NEG = {"not", "no", "never", "isn't", "isnt", "wasn't", "dont", "don't", "won't", "wont", "without", "hardly", "nor", "cant", "can't"}
TOKEN = re.compile(r"[a-z][a-z'\-]*")
_PHRASES = sorted([(k, v) for k, v in BULL.items() if " " in k] + [(k, -v) for k, v in BEAR.items() if " " in k], key=lambda kv: -len(kv[0]))
_WORDS = {**{k: v for k, v in BULL.items() if " " not in k}, **{k: -v for k, v in BEAR.items() if " " not in k}}


def score_text(text, sym=None):
    t = text.lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"@\w+", " ", t)
    total = 0.0; hits = 0
    for ph, v in _PHRASES:
        if ph in t:
            total += v; hits += 1; t = t.replace(ph, " ")
    toks = TOKEN.findall(t)
    for i, w in enumerate(toks):
        v = _WORDS.get(w)
        if v is None: continue
        if any(x in NEG for x in toks[max(0, i - 3):i]): v = -0.7 * v
        total += v; hits += 1
    for e, v in EMOJI.items():
        c = text.count(e)
        if c: total += v * min(c, 3); hits += 1
    # price-target phrasing: "pt 250 -> 300"
    m = re.search(r"(?:pt|target)\D{0,12}(\d+(?:\.\d+)?)\s*(?:->|→|to)\s*(\d+(?:\.\d+)?)", t)
    if m:
        a, b = float(m.group(1)), float(m.group(2)); total += 1.2 if b > a else -1.2 if b < a else 0; hits += 1
    if not hits: return 0.0
    return max(-1.0, min(1.0, total / (abs(total) + 2.0)))   # squash; one strong word ~0.5
