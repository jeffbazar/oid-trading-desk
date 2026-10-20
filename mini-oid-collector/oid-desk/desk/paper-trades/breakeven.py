#!/usr/bin/env python3
"""Paper breakeven helpers (research only)."""
from __future__ import annotations
import re
from typing import Any, Optional

def _f(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    return None

def parse_strike_type(trade: dict) -> tuple[Optional[float], Optional[str]]:
    """Return (strike, call|put) from trade fields or contract string."""
    strike = _f(trade.get("strike")) or _f(trade.get("strikePrice"))
    otype = (trade.get("optionType") or trade.get("type") or trade.get("side") or "").lower()
    if "call" in otype:
        otype = "call"
    elif "put" in otype:
        otype = "put"
    else:
        otype = None
    contract = str(trade.get("contract") or "")
    if strike is None:
        # "NBIS 2027-01-15 290 call" or "SPY Sep18 755/750P credit"
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*(c|call|p|put)\b", contract, re.I)
        if m:
            strike = float(m.group(1))
            otype = "call" if m.group(2).lower().startswith("c") else "put"
        else:
            # vertical: take short/long first strike mentioned for credit structures — skip complex
            m2 = re.search(r"\b(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)([CP])?", contract, re.I)
            if m2:
                strike = float(m2.group(1))
                if m2.group(3):
                    otype = "call" if m2.group(3).upper() == "C" else "put"
                elif "P" in contract.upper() and "C" not in contract.upper().replace("CONTRACT",""):
                    otype = "put"
    if otype is None:
        if re.search(r"\bcall\b", contract, re.I):
            otype = "call"
        elif re.search(r"\bput\b", contract, re.I):
            otype = "put"
    return strike, otype

def entry_premium(trade: dict) -> Optional[float]:
    for k in ("entryAsk", "entryMark", "entryBid", "costBasis", "entryCredit"):
        x = _f(trade.get(k))
        if x is not None:
            return x
    return None

def is_credit(trade: dict) -> bool:
    strat = (trade.get("strategy") or "").lower()
    side = (trade.get("side") or "").lower()
    if "credit" in strat or "short" in side:
        return True
    if trade.get("entryCredit") is not None and trade.get("entryAsk") is None:
        return True
    return False

def break_even_entry(trade: dict) -> Optional[float]:
    """Classic entry BE for single-leg long/short; simple vertical approx.
    Long call: strike + debit. Long put: strike - debit.
    Short call: strike + credit. Short put: strike - credit.
    """
    strike, otype = parse_strike_type(trade)
    prem = entry_premium(trade)
    if strike is None or prem is None or otype is None:
        return _f(trade.get("breakEven")) or _f(trade.get("breakEvenEntry"))
    credit = is_credit(trade)
    if otype == "call":
        return round(strike + prem, 4) if not credit else round(strike + prem, 4)
    # put
    return round(strike - prem, 4)

def apply_breakeven(trade: dict) -> Optional[float]:
    be = break_even_entry(trade)
    if be is not None:
        trade["breakEvenEntry"] = be
        trade["breakEven"] = be  # alias for blotter
    # RH live BE if present (mark-implied)
    rh = _f(trade.get("breakEvenRh")) or _f(trade.get("break_even_price"))
    if rh is not None:
        trade["breakEvenRh"] = rh
    return be
