"""OID news sentiment (2026-10-20): per-ticker score -2..+2 for a headline / X post. Local only, free.

Method: FinBERT (ProsusAI/finbert via transformers, CPU) when it imports; otherwise a finance keyword lexicon.
A small analyst-action rule layer runs on top of both (FinBERT reads "Maintains Underweight ... Lowers PT" poorly).
Per-ticker: the same document score applies to every ticker on the item, except analyst-action headlines
("<Firm> ... on <Company>") where the rule score applies. Research only.
"""
from __future__ import annotations
import re

METHOD = "lexicon"
_PIPE = None


def init(try_finbert=True):
    global _PIPE, METHOD
    if not try_finbert:
        return METHOD
    try:
        import os
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from transformers import pipeline  # noqa
        _PIPE = pipeline("text-classification", model="ProsusAI/finbert", top_k=None, truncation=True, max_length=256)
        _PIPE("warm up")
        METHOD = "finbert"
    except Exception:
        _PIPE, METHOD = None, "lexicon"
    return METHOD


POS = {"beat": 1.0, "beats": 1.0, "tops": 0.8, "surpass": 0.8, "raises": 0.6, "raised": 0.6, "upgrade": 1.2, "upgrades": 1.2,
       "upgraded": 1.2, "outperform": 0.8, "overweight": 0.6, "buy": 0.5, "bullish": 1.0, "record": 0.6, "surge": 0.9,
       "surges": 0.9, "soar": 1.0, "soars": 1.0, "jump": 0.8, "jumps": 0.8, "rally": 0.8, "rallies": 0.8, "gain": 0.5,
       "gains": 0.5, "higher": 0.4, "strong": 0.6, "growth": 0.4, "expands": 0.5, "partnership": 0.5, "deal": 0.4,
       "contract": 0.4, "awarded": 0.6, "approval": 0.8, "approved": 0.8, "wins": 0.7, "accelerat": 0.5, "boost": 0.6,
       "boosts": 0.6, "buyback": 0.7, "repurchase": 0.6, "dividend": 0.3, "breakout": 0.7, "upside": 0.6, "positive": 0.5,
       "exceeds": 0.8, "guidance raise": 1.2, "all-time high": 0.8, "acquire": 0.3, "invest": 0.3, "demand": 0.3}
NEG = {"miss": 1.0, "misses": 1.0, "missed": 1.0, "lowers": 0.6, "lowered": 0.6, "cut": 0.7, "cuts": 0.7, "downgrade": 1.2,
       "downgrades": 1.2, "downgraded": 1.2, "underperform": 0.8, "underweight": 0.6, "sell": 0.5, "bearish": 1.0,
       "plunge": 1.0, "plunges": 1.0, "tumble": 0.9, "tumbles": 0.9, "slump": 0.9, "drop": 0.6, "drops": 0.6, "falls": 0.6,
       "fall": 0.5, "lower": 0.4, "weak": 0.7, "weakness": 0.7, "decline": 0.6, "declines": 0.6, "loss": 0.6, "losses": 0.6,
       "lawsuit": 0.8, "probe": 0.8, "investigation": 0.8, "subpoena": 0.9, "recall": 0.7, "halt": 0.6, "delay": 0.6,
       "delays": 0.6, "warns": 0.9, "warning": 0.7, "layoffs": 0.6, "bankruptcy": 1.5, "fraud": 1.5, "short seller": 1.0,
       "offering": 0.6, "dilution": 0.9, "downside": 0.6, "negative": 0.5, "concern": 0.4, "concerns": 0.4, "risk": 0.2,
       "squeez": 0.3, "tariff": 0.4, "ban": 0.7, "restrict": 0.6, "sanction": 0.7, "guidance cut": 1.2, "resigns": 0.5}
_W = re.compile(r"[a-z][a-z\-']+")


def _lex(text):
    t = text.lower()
    s = 0.0
    for k, w in POS.items():
        if (" " in k and k in t) or (" " not in k and re.search(r"\b" + re.escape(k), t)):
            s += w
    for k, w in NEG.items():
        if (" " in k and k in t) or (" " not in k and re.search(r"\b" + re.escape(k), t)):
            s -= w
    return max(-1.0, min(1.0, s / 1.6))


_ANALYST = re.compile(r"\b(maintains|reiterates|upgrades|downgrades|initiates|assumes|resumes|raises price target|lowers price target)\b", re.I)


def _analyst(text):
    t = text.lower()
    if not _ANALYST.search(t):
        return None
    s = 0.0
    if "upgrade" in t:
        s += 1.5
    if "downgrade" in t:
        s -= 1.5
    if "raises price target" in t:
        s += 0.8
    if "lowers price target" in t:
        s -= 0.8
    if re.search(r"\b(overweight|outperform|buy|strong buy|positive)\b", t):
        s += 0.6
    if re.search(r"\b(underweight|underperform|sell|negative|reduce)\b", t):
        s -= 0.6
    return max(-2, min(2, int(s + (0.5 if s > 0 else -0.5)) if s else 0))


def _bucket(x):
    return 2 if x >= 0.6 else 1 if x >= 0.2 else -2 if x <= -0.6 else -1 if x <= -0.2 else 0


def score(text, tickers):
    """-> (doc_score -2..2, {sym: score}, raw float -1..1, method)."""
    text = " ".join(str(text or "").split())[:600]
    if not text:
        return 0, {s: 0 for s in tickers}, 0.0, METHOD
    raw = None
    if _PIPE is not None:
        try:
            out = _PIPE(text)[0]
            p = {d["label"].lower(): d["score"] for d in out}
            raw = p.get("positive", 0) - p.get("negative", 0)
        except Exception:
            raw = None
    m = METHOD if raw is not None else "lexicon"
    if raw is None:
        raw = _lex(text)
    doc = _bucket(raw)
    a = _analyst(text)
    if a is not None:
        doc, m = a, m + "+analyst"
    return doc, {s: doc for s in tickers}, round(raw, 3), m
