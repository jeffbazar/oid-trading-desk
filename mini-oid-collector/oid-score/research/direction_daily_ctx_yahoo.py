"""Daily context for direction-analysis: 20/50-day SMA and prior-day return from Yahoo split-adjusted closes
(reuses ma200-gate yahoo_close_splitadj.csv) + ^VIX daily OHLC via yfinance. SMAs use closes strictly before the session."""
import pandas as pd, json, yfinance as yf, warnings
warnings.filterwarnings("ignore")
d=pd.read_csv("/workspace/ma200/yahoo_close_splitadj.csv",index_col=0)
v=yf.download(["^VIX","SPY","QQQ"],start="2026-10-12",end="2026-10-24",auto_adjust=False,progress=False)
out={"source":"Yahoo Finance via yfinance, fetched 2026-10-24 (closes split-adjusted, not dividend-adjusted)","by_date":{},"vix":{},"index_day":{}}
for D in ["2026-10-19","2026-10-20","2026-10-21","2026-10-22","2026-10-23"]:
    for s in d.columns:
        c=d[s][d.index<D].dropna()
        if len(c)<50: continue
        out["by_date"].setdefault(D,{})[s]={"sma20":round(float(c.tail(20).mean()),4),"sma50":round(float(c.tail(50).mean()),4),
            "prev_close":round(float(c.iloc[-1]),4),"ret5d_prev_pct":round(float(c.iloc[-1]/c.iloc[-6]-1)*100,2)}
    k=pd.Timestamp(D)
    out["vix"][D]={x:round(float(v[x]["^VIX"].loc[k]),2) for x in ("Open","High","Low","Close")}
    for s in ("SPY","QQQ"):
        o=float(v["Open"][s].loc[k]); cl=float(v["Close"][s].loc[k]); pc=float(v["Close"][s].shift(1).loc[k])
        out["index_day"].setdefault(D,{})[s]={"open_to_close_pct":round((cl/o-1)*100,2),"close_to_close_pct":round((cl/pc-1)*100,2)}
json.dump(out,open("daily_ctx.json","w"),indent=0)
print(json.dumps({"vix":out["vix"],"idx":out["index_day"]},indent=0))
