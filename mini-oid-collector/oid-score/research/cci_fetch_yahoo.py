"""CCI-breakout research (2026-10-25): Yahoo Finance fetch (run on the box; mini venv has no yfinance).
Daily max history for QQQ, ^NDX, NQ=F; 60m bars (Yahoo limit ~730 days) for NQ=F and QQQ (incl. prepost for QQQ).
Output CSVs: t,o,h,l,c,v with t as ISO UTC."""
import yfinance as yf, pandas as pd
def save(df, name):
    df = df.dropna(subset=["Open","High","Low","Close"])
    idx = df.index.tz_convert("UTC") if df.index.tz is not None else df.index
    out = pd.DataFrame({"t": [x.isoformat() for x in idx], "o": df.Open.values, "h": df.High.values, "l": df.Low.values, "c": df.Close.values, "v": df.Volume.values})
    out.to_csv(name, index=False); print(name, len(out), out.t.iloc[0], out.t.iloc[-1])
for s in ["QQQ", "^NDX", "NQ=F"]:
    df = yf.Ticker(s).history(period="max", interval="1d", auto_adjust=True)
    save(df, f"yahoo_{s.replace('^','').replace('=','')}_1d.csv")
for s, pp in [("NQ=F", False), ("QQQ", True)]:
    df = yf.Ticker(s).history(period="730d", interval="60m", prepost=pp, auto_adjust=True)
    save(df, f"yahoo_{s.replace('=','')}_60m.csv")
