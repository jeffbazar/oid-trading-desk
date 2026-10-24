import yfinance as yf, pandas as pd, json, warnings
warnings.filterwarnings("ignore")
syms="AAL AAOI AAPL ACHR ADI AG AGNC ALAB AMAT AMC AMD AMZN ANET APLD ARM ASML ASTS AVGO BA BABA BAC BE BIDU BMNR BMY BULL C CAT CBRS CCJ CCL CIFR CLF CLSK CMCSA CMG COHR COIN CORZ COST CRCL CRDO CRM CRWD CRWV CSCO CVNA CVX DAL DELL DIA DIS DKNG DRAM DVN EOSE ET ETHA EWY EWZ F FCX FRMI FRO FSLR GDX GEO GFL GLD GLW GM GME GOOG GOOGL GRAB HIMS HL HOOD HPE HTZ HYG IBIT IBM IEF IGV INTC INTU IONQ IREN IWM JBLU JETS JOBY JPM KBE KEYS KHC KLAC KO KRE LCID LITE LLY LQD LRCX LULU MARA MCD META MH MO MP MPT MRNA MRVL MSFT MSTR MU NBIS NEE NFLX NIO NKE NLY NOK NOW NU NUAI NVDA NVO O OKLO ON ONDS OPEN ORCL OXY PBR PCG PDD PEP PFE PG PLTR QCOM QQQ QS QXO RBLX RDDT RDW RIG RIOT RIVN RKLB RKT RSP RUN SHOP SKHY SLS SLV SMCI SMH SMR SNAP SNDK SOFI SOXX SPCX SPY STX T TE TEM TLT TQQQ TSLA TSM TXN UAL UBER UNH UPS USAR USO UUP UUUU VALE VG VKTX VRT VST VTV VUG VZ WDC WFC WMT WULF XBI XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY XOM XPEV".split()
d=yf.download(syms,start="2025-06-01",end="2026-10-24",auto_adjust=False,progress=False,threads=True)["Close"]
d.index=d.index.strftime("%Y-%m-%d")
d.to_csv("yahoo_close_splitadj.csv")
out={}
for D in ["2026-10-19","2026-10-20","2026-10-21","2026-10-22","2026-10-23"]:
    for s in syms:
        c=d[s][d.index<D].dropna() if s in d else pd.Series(dtype=float)
        if len(c)>=200:
            out.setdefault(D,{})[s]={"sma200":round(float(c.tail(200).mean()),4),"prev_close":round(float(c.iloc[-1]),4),"n_hist":int(len(c)),"last_hist_date":c.index[-1]}
        else:
            out.setdefault(D,{})[s]={"sma200":None,"n_hist":int(len(c))}
json.dump({"source":"Yahoo Finance daily closes via yfinance (split-adjusted, not dividend-adjusted), fetched 2026-10-24 from the box","sma":"mean of the 200 daily closes strictly before the session date (known before the open)","by_date":out},open("sma200.json","w"),indent=0)
for D in out: print(D, sum(1 for v in out[D].values() if v["sma200"]), "of", len(out[D]), [s for s,v in out[D].items() if not v["sma200"]])
print(d.tail(1)[["SPY","NVDA","TSLA","AAPL","KLAC"]])
