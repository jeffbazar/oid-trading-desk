"""CCI-breakout research library (2026-10-25). Pure Python (the mini has no numpy). Research only.
Bars: list of dicts/tuples (t_utc datetime, o, h, l, c). Indicators are computed on the given bar series and are
evaluated for an entry on bar i using bars <= i-1 only (TradeStation 'next bar' semantics)."""
import csv, math, random, statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago"); ET = ZoneInfo("America/New_York")

def load_csv(path):
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            t = r["t"].replace("Z", "+00:00")
            dt = datetime.fromisoformat(t)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            o, h, l, c = float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"])
            if not (o > 0 and h > 0 and l > 0 and c > 0): continue
            out.append((dt, o, h, l, c))
    out.sort(key=lambda x: x[0])
    return out

# ---------- indicators (value at index j uses bars <= j) ----------
def sma(x, n):
    out = [None] * len(x); s = 0.0
    for j, v in enumerate(x):
        s += v
        if j >= n: s -= x[j - n]
        if j >= n - 1: out[j] = s / n
    return out
def cci(H, L, C, n):
    tp = [(h + l + c) / 3 for h, l, c in zip(H, L, C)]
    m = sma(tp, n); out = [None] * len(tp)
    for j in range(n - 1, len(tp)):
        mu = m[j]; md = sum(abs(tp[k] - mu) for k in range(j - n + 1, j + 1)) / n
        out[j] = 0.0 if md == 0 else (tp[j] - mu) / (0.015 * md)
    return out
def atr(H, L, C, n):
    tr = [H[0] - L[0]] + [max(H[j] - L[j], abs(H[j] - C[j - 1]), abs(L[j] - C[j - 1])) for j in range(1, len(H))]
    return sma(tr, n)
def rsi(C, n=14):
    out = [None] * len(C); g = l = 0.0
    for j in range(1, len(C)):
        d = C[j] - C[j - 1]; up, dn = max(d, 0), max(-d, 0)
        if j <= n:
            g += up / n; l += dn / n
            if j == n: out[j] = 100 if l == 0 else 100 - 100 / (1 + g / l)
        else:
            g = (g * (n - 1) + up) / n; l = (l * (n - 1) + dn) / n
            out[j] = 100 if l == 0 else 100 - 100 / (1 + g / l)
    return out
def lowest_lt(x, look, thr):
    """mask[i] = min(x[i-look .. i-1]) < thr (bars before i). None -> False."""
    out = [False] * len(x)
    for i in range(look, len(x)):
        w = x[i - look:i]
        if any(v is None for v in w): continue
        out[i] = min(w) < thr
    return out
def any_below_sma(C, n, look):
    m = sma(C, n); out = [False] * len(C)
    for i in range(look, len(C)):
        out[i] = any(m[k] is not None and C[k] < m[k] for k in range(i - look, i))
    return out
def pullback_atr(H, L, A, look, depth):
    """lowest low of last `look` bars is >= depth*ATR below the highest high of the last 2*look bars (all before i)."""
    out = [False] * len(H)
    for i in range(2 * look, len(H)):
        a = A[i - 1]
        if a is None: continue
        out[i] = max(H[i - 2 * look:i]) - min(L[i - look:i]) >= depth * a
    return out

def filter_bank(H, L, C, A40, neighborhood=False, n_random=20, seed=7):
    F = {}
    c27 = cci(H, L, C, 27)
    F["CCI27_lo18<-100 (post)"] = lowest_lt(c27, 18, -100)
    F["NOT CCI (complement)"] = [not v for v in F["CCI27_lo18<-100 (post)"]]
    F["RSI14_lo18<30"] = lowest_lt(rsi(C, 14), 18, 30)
    F["close<SMA20 in last 18"] = any_below_sma(C, 20, 18)
    p = sum(F["CCI27_lo18<-100 (post)"]) / max(1, len(C))
    # same-selectivity generic pullback filters: thresholds set so each passes the same share of bars as the CCI rule
    # (full-sample quantile = a slight look-ahead that favours the generic filters, i.e. conservative for the CCI claim)
    r14 = rsi(C, 14); s20 = sma(C, 20)
    def roll_min_prev(x, look):
        out = [None] * len(x)
        for i in range(look, len(x)):
            w = x[i - look:i]
            if any(v is None for v in w): continue
            out[i] = min(w)
        return out
    def calib(score):  # pass if score below its p-quantile
        v = sorted(x for x in score if x is not None)
        if not v: return [False] * len(score), None
        q = v[min(len(v) - 1, int(p * len(v)))]
        return [x is not None and x < q for x in score], q
    lr = roll_min_prev(r14, 18)
    F["RSI14_lo18 calibrated"], q1 = calib(lr)
    dist = [None if (s20[j] is None or A40[j] is None or A40[j] == 0) else (C[j] - s20[j]) / A40[j] for j in range(len(C))]
    F["min(close-SMA20)/ATR lo18 calibrated"], q2 = calib(roll_min_prev(dist, 18))
    dd = [None] * len(C)
    for i in range(36, len(C)):
        a = A40[i - 1]
        if a: dd[i] = -(max(H[i - 36:i]) - min(L[i - 18:i])) / a
    F["pullback depth (36h high - 18 low)/ATR calibrated"], q3 = calib(dd)
    F["_calib"] = {"rsi_lo18_thr": q1, "dist_sma20_atr_thr": q2, "pullback_atr_thr": (-q3 if q3 is not None else None)}
    rng = random.Random(seed)
    for k in range(n_random):
        F[f"RANDOM#{k}"] = [rng.random() < p for _ in C]
    if neighborhood:
        cache = {27: c27}
        for n in (14, 20, 27, 40, 60):
            cv = cache.get(n) or cci(H, L, C, n)
            for look in (9, 18, 36):
                for thr in (-50, -100, -150):
                    F[f"NB CCI{n}_lo{look}<{thr}"] = lowest_lt(cv, look, thr)
    return F, p

# ---------- intraday post-style engine ----------
def prep_intraday(bars, mode):
    """mode 'nq': CME. session label = CT date (bars >=17:00 CT belong to next day's session ending 16:00 CT);
       trading day = CT calendar date Mon-Fri, window bars start 00:00-22:00 CT (exit 23:00 CT, per the post).
       mode 'eq_ext': ET date; session & window = all bars 04:00-19:00 starts. mode 'eq_rth': only bars starting 09:00-15:00 ET
       (the 09:00 hourly bar includes 09:00-09:30 pre-market). Returns dict of arrays."""
    T, O, H, L, C, day, lab, inwin, hour = [], [], [], [], [], [], [], [], []
    for dt, o, h, l, c in bars:
        if mode == "nq":
            lt = dt.astimezone(CT); d = lt.date()
            if lt.weekday() >= 5 and not (lt.weekday() == 6 and lt.hour >= 17): continue
            sl = d.toordinal() + (1 if lt.hour >= 17 else 0)
            w = lt.weekday() < 5 and lt.hour <= 22
        else:
            lt = dt.astimezone(ET); d = lt.date()
            if mode == "eq_rth" and not (9 <= lt.hour <= 15): continue
            sl = d.toordinal(); w = lt.weekday() < 5
        T.append(dt); O.append(o); H.append(h); L.append(l); C.append(c)
        day.append(d.toordinal()); lab.append(sl); inwin.append(w); hour.append(lt.hour + lt.minute / 60)
    n = len(C)
    # previous completed session stats for each bar
    sess = {}
    for i in range(n):
        s = sess.setdefault(lab[i], [H[i], L[i], C[i]])
        s[0] = max(s[0], H[i]); s[1] = min(s[1], L[i]); s[2] = C[i]
    labs = sorted(sess); prev = {labs[k]: labs[k - 1] for k in range(1, len(labs))}
    pH, pL, pC = [None] * n, [None] * n, [None] * n
    for i in range(n):
        pl = prev.get(lab[i])
        if pl is not None: pH[i], pL[i], pC[i] = sess[pl]
    # trading-day windows
    days = {}
    for i in range(n):
        if inwin[i]: days.setdefault(day[i], []).append(i)
    return dict(T=T, O=O, H=H, L=L, C=C, day=day, hour=hour, pH=pH, pL=pL, pC=pC, days=days, n=n)

def run_intraday(P, A, ref, k, start_hour, exit_rule, active=None, cost_bp=0.0):
    """One long trade per trading day. Buy stop at level (ref + k*ATR[i-1]); fills at max(open, level) on the first window
    bar (start hour >= start_hour) where the order is active (filter evaluated on bars <= i-1) and high >= level.
    exit_rule: EOD | H4 | H8 | SL1 | SL2 | TP2SL1 (stops/targets checked from the bar after entry; stop first if both)."""
    O, H, L, C = P["O"], P["H"], P["L"], P["C"]
    trades = []
    cache = P.setdefault("_dbs", {})
    if start_hour not in cache:
        cache[start_hour] = [[i for i in idx if P["hour"][i] >= start_hour] for d, idx in sorted(P["days"].items())]
        cache[start_hour] = [x for x in cache[start_hour] if len(x) >= 2]
    refarr = None if ref == "OPEN" else {"LOD": P["pL"], "COD": P["pC"], "HOD": P["pH"]}[ref]
    for idx in cache[start_hour]:
        last = idx[-1]; ent = None
        for i in idx:
            a = A[i - 1] if i > 0 else None
            if a is None: continue
            if refarr is None: base = O[idx[0]]
            else:
                base = refarr[i]
                if base is None: continue
            lvl = base + k * a
            if active is not None and not active[i]: continue
            if H[i] >= lvl:
                ent = (i, max(O[i], lvl), a); break
        if ent is None: continue
        i0, px, a = ent
        xp = None
        stop = px - (1 if exit_rule in ("SL1", "TP2SL1") else 2) * a if exit_rule in ("SL1", "SL2", "TP2SL1") else None
        tgt = px + 2 * a if exit_rule == "TP2SL1" else None
        hold = {"H4": 4, "H8": 8}.get(exit_rule)
        for j in idx[idx.index(i0):]:
            if j > i0 and stop is not None and L[j] <= stop: xp = min(O[j], stop); break
            if j > i0 and tgt is not None and H[j] >= tgt: xp = max(O[j], tgt); break
            if hold and (j - i0 + 1) >= hold: xp = C[j]; break
            if j == last: xp = C[j]; break
        if xp is None: xp = C[last]
        trades.append((P["T"][i0], px, xp, 1e4 * (xp / px - 1) - cost_bp, xp - px))
    trades.sort(key=lambda t: t[0])
    return trades

# ---------- daily Donchian engine ----------
def run_daily(T, O, H, L, C, A20, N, entry, exit_rule, active=None, cost_bp=0.0):
    """Signal: close[i] > highest high of bars i-N..i-1. Entry at close[i] ('close') or open[i+1] ('next_open').
    One position at a time. Exits: hold1/5/10/20 (closes), SL2 (2*ATR20 stop, max 20), TRAIL (close < lowest low of prior
    max(3,N//2) bars, max 60), TP3SL2 (3ATR target / 2ATR stop, max 20). active[i]: filter using bars <= i-1."""
    n = len(C); trades = []; i = N
    while i < n - 1:
        if C[i] > max(H[i - N:i]) and (active is None or active[i]) and A20[i] is not None:
            e = i if entry == "close" else i + 1
            px = C[i] if entry == "close" else O[i + 1]
            a = A20[i]; xp = None; j = e
            mh = {"hold1": 1, "hold5": 5, "hold10": 10, "hold20": 20, "SL2": 20, "TRAIL": 60, "TP3SL2": 20}[exit_rule]
            stop = px - 2 * a if exit_rule in ("SL2", "TP2SL1", "TP3SL2") else None
            tgt = px + 3 * a if exit_rule == "TP3SL2" else None
            m = max(3, N // 2)
            for j in range(e + 1, min(n, e + mh + 1)):
                if stop is not None and L[j] <= stop: xp = min(O[j], stop); break
                if tgt is not None and H[j] >= tgt: xp = max(O[j], tgt); break
                if exit_rule == "TRAIL" and C[j] < min(L[j - m:j]): xp = C[j]; break
            if xp is None: j = min(n - 1, e + mh); xp = C[j]
            trades.append((T[e], px, xp, 1e4 * (xp / px - 1) - cost_bp, xp - px))
            i = j + 1
        else:
            i += 1
    return trades

# ---------- stats ----------
def stats(tr):
    r = [t[3] for t in tr]
    if not r: return dict(n=0, win=None, avg=None, net=0.0, dd=0.0, pdd=None, pts=None)
    eq = pk = dd = 0.0
    for x in r:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    net = sum(r)
    return dict(n=len(r), win=sum(x > 0 for x in r) / len(r), avg=net / len(r), net=net, dd=dd,
                pdd=(net / dd if dd > 0 else None), pts=sum(t[4] for t in tr) / len(r))
def split(tr, cut):
    return [t for t in tr if t[0] < cut], [t for t in tr if t[0] >= cut]
