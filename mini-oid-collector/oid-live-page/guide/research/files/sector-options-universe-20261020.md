# Sector options universe: candidates for wider live-page scan (2026-10-20)

**Starter list: 144 names** (top ≤10 per bucket below). The CSV has all 270 screened rows, 197 of them core (at least 20k/day).

**Source:** Unusual Whales stock screener (`get_stock_screener`), pulled 2026-10-20 ~12:55 PM PT. Volume is UW's 30-day average daily options volume (calls + puts, in contracts). The 7-day average, prior-day volume and today's partial volume are in the CSV.

**Threshold:** stocks at or above 20k contracts/day on the 30-day average are **core**. Names from 10k to 20k are **secondary**. They are listed only where a sector is thin, plus a few sector ETFs for reference. Real Estate was screened down to 5k because the sector is thin.

**Excluded:** everything already on the live page (the 61-name stream allowlist plus `sectors.json` groups, e.g. SPCX, BE, VRT, IREN, WULF, NBIS, GOOG, AAPL, MSFT, ORCL, AMAT, LRCX, GLW, CRDO, COHR, ALAB, ANET, ON, SMH, SOXX, EWY, DIA). WDC, STX and SNDK are excluded entirely.

**Liquidity:** deep = at least 100k/day and at least 1M OI; good = at least 40k/day; ok = 20–40k/day; thin = under 20k/day. Option bid/ask spreads were **not** measured; the screener has no contract-level spread. The `stock_spread_bps` column is the underlying's quote spread at fetch time. Call share = 30-day average call volume divided by total.

Research only; nothing was subscribed or changed. Sector placement follows UW's sector tags with a few manual moves (crypto, autos, airlines, nuclear and solar into power, HIMS into healthcare); see the notes column.

## Energy (oil & gas, LNG)

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | PBR | 62,694 | 68% | 97,191 | 2,316,393 | good |  |
| 2 | XOM | 56,972 | 66% | 63,749 | 1,017,792 | good |  |
| 3 | OXY | 43,018 | 82% | 33,526 | 745,610 | good |  |
| 4 | CVX | 36,902 | 67% | 38,947 | 483,719 | ok |  |
| 5 | ET | 25,762 | 82% | 23,272 | 928,876 | ok |  |
| 6 | RIG | 24,329 | 69% | 25,493 | 1,203,754 | ok |  |
| 7 | FRO | 23,534 | 81% | 16,623 | 194,497 | ok |  |
| 8 | DVN | 22,780 | 74% | 17,309 | 406,172 | ok |  |
| 9 | VG | 22,753 | 70% | 20,651 | 715,631 | ok | UW tags it Telecom Services; placed in Energy assuming LNG exporter; verify |
| 10 | NUAI | 20,589 | 73% | 24,268 | 343,979 | ok | small cap <$1B, speculative |

Also in CSV: EQT, WMB, VLO, BP, SLB, HAL, DHT, COP

## Financials: banks/brokers/fintech

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | SOFI | 354,808 | 70% | 484,300 | 3,976,707 | deep |  |
| 2 | HOOD | 296,103 | 67% | 325,776 | 1,761,585 | deep | UW tags it Technology |
| 3 | BAC | 171,029 | 56% | 237,795 | 2,404,164 | deep |  |
| 4 | NU | 125,706 | 73% | 86,367 | 2,183,969 | deep |  |
| 5 | RKT | 71,189 | 75% | 81,863 | 1,028,632 | good |  |
| 6 | GRAB | 63,881 | 74% | 44,858 | 2,263,913 | good |  |
| 7 | JPM | 57,449 | 62% | 70,263 | 617,123 | good |  |
| 8 | C | 55,564 | 53% | 86,740 | 1,077,802 | good |  |
| 9 | WFC | 53,405 | 52% | 76,501 | 1,119,335 | good |  |
| 10 | BULL | 52,631 | 77% | 42,016 | 1,012,853 | good | UW tags it Software; broker |

Also in CSV: XP, PYPL, GS, BRKB, OWL, MS, V, BX, SCHW, UPST, APO, AXP

## Crypto-linked (miners, treasuries, exchanges)

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | MSTR | 467,732 | 64% | 444,546 | 2,432,242 | deep |  |
| 2 | MARA | 211,718 | 73% | 238,960 | 1,771,578 | deep |  |
| 3 | CIFR | 167,018 | 72% | 227,256 | 1,856,399 | deep | AI-hosting/miner hybrid |
| 4 | COIN | 160,643 | 64% | 142,091 | 939,302 | good |  |
| 5 | BMNR | 141,345 | 67% | 120,071 | 1,648,612 | deep |  |
| 6 | APLD | 96,675 | 68% | 126,876 | 863,715 | good | AI-hosting/miner hybrid |
| 7 | RIOT | 83,240 | 65% | 118,562 | 993,744 | good |  |
| 8 | CRCL | 80,563 | 64% | 71,646 | 708,191 | good |  |
| 9 | CORZ | 59,040 | 71% | 99,455 | 1,492,786 | good | AI-hosting/miner hybrid |
| 10 | CLSK | 48,240 | 73% | 52,444 | 718,944 | good |  |

Also in CSV: ASST, PURR, HUT, GLXY, BTDR, SBET, FIGR, BTBT

## Industrials & Defense/Aerospace

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | RKLB | 135,619 | 68% | 161,477 | 1,243,293 | deep |  |
| 2 | BA | 96,895 | 65% | 76,392 | 891,410 | good |  |
| 3 | ACHR | 33,426 | 81% | 38,780 | 681,865 | ok |  |
| 4 | GFL | 33,380 | 88% | 39,183 | 507,363 | ok |  |
| 5 | QXO | 23,390 | 51% | 32,435 | 705,619 | ok |  |
| 6 | CAT | 21,306 | 48% | 24,950 | 233,996 | ok |  |
| 7 | RDW | 21,287 | 60% | 21,700 | 347,142 | ok |  |

Also in CSV: LUNR, PL, GE, KTOS, SPCE, RTX

## Transportation/Airlines

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | UBER | 105,439 | 65% | 87,968 | 1,328,730 | deep | UW tags it Technology |
| 2 | AAL | 91,131 | 55% | 96,450 | 1,946,016 | good |  |
| 3 | JBLU | 46,226 | 55% | 62,032 | 1,283,844 | good |  |
| 4 | HTZ | 44,190 | 84% | 52,752 | 1,177,938 | good | small cap <$1B, speculative |
| 5 | DAL | 39,950 | 74% | 52,682 | 408,411 | ok |  |
| 6 | UAL | 21,810 | 70% | 20,656 | 296,803 | ok |  |
| 7 | JOBY | 21,545 | 69% | 23,366 | 480,641 | ok |  |
| 8 | UPS | 20,513 | 66% | 21,568 | 388,569 | ok |  |

## Healthcare/Biotech/Pharma

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | MRNA | 126,597 | 61% | 171,677 | 811,785 | good |  |
| 2 | PFE | 76,974 | 68% | 88,348 | 2,168,266 | good |  |
| 3 | HIMS | 71,148 | 72% | 86,188 | 740,623 | good | UW tags it Consumer Defensive (Household & Personal Products) |
| 4 | UNH | 65,509 | 59% | 110,523 | 880,612 | good |  |
| 5 | NVO | 58,736 | 56% | 42,987 | 1,433,087 | good |  |
| 6 | SLS | 33,338 | 69% | 35,698 | 782,467 | ok |  |
| 7 | LLY | 32,661 | 54% | 39,276 | 320,486 | ok |  |
| 8 | TEM | 31,874 | 68% | 24,388 | 348,278 | ok |  |
| 9 | VKTX | 31,629 | 73% | 21,434 | 272,700 | ok |  |
| 10 | BMY | 28,049 | 53% | 27,616 | 728,129 | ok |  |

Also in CSV: MRK, IBRX, BSX, MDT, JNJ, IOVA, LQDA, RXRX, NVAX, CLOV, CVS, OSCR, ABBV, AMGN

## Consumer Discretionary/Retail

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | GME | 308,269 | 87% | 401,781 | 1,825,846 | deep |  |
| 2 | NKE | 186,757 | 62% | 130,887 | 2,168,928 | deep |  |
| 3 | BABA | 122,109 | 68% | 113,558 | 1,780,719 | deep |  |
| 4 | CCL | 57,492 | 60% | 35,045 | 966,361 | good |  |
| 5 | CMG | 54,382 | 57% | 51,822 | 855,034 | good |  |
| 6 | MCD | 52,999 | 61% | 41,864 | 416,489 | good |  |
| 7 | LULU | 43,235 | 51% | 28,739 | 466,231 | good |  |
| 8 | CVNA | 42,059 | 48% | 50,895 | 903,593 | good |  |
| 9 | DKNG | 41,198 | 71% | 33,312 | 932,860 | good |  |
| 10 | PDD | 29,649 | 54% | 30,766 | 962,572 | ok |  |

Also in CSV: NCLH, ONON, JD, HD, SBUX, CHWY, BKNG

## Autos/EV

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | RIVN | 96,146 | 71% | 102,356 | 2,175,062 | good |  |
| 2 | F | 79,255 | 59% | 60,744 | 1,769,255 | good |  |
| 3 | NIO | 55,359 | 81% | 54,129 | 2,442,145 | good |  |
| 4 | LCID | 34,510 | 51% | 39,729 | 884,646 | ok |  |
| 5 | QS | 17,902 | 81% | 22,080 | 684,266 | thin |  |
| 6 | XPEV | 16,937 | 69% | 12,243 | 369,296 | thin |  |
| 7 | GM | 15,051 | 54% | 15,760 | 298,862 | thin |  |

## Consumer Staples

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | WMT | 139,901 | 73% | 195,820 | 1,210,078 | deep |  |
| 2 | KO | 48,314 | 70% | 59,631 | 687,818 | good |  |
| 3 | COST | 42,437 | 54% | 40,597 | 286,516 | good |  |
| 4 | PEP | 36,060 | 65% | 37,488 | 327,318 | ok |  |
| 5 | KHC | 33,110 | 83% | 29,242 | 376,430 | ok |  |
| 6 | PG | 21,046 | 71% | 26,881 | 312,326 | ok |  |
| 7 | MO | 20,853 | 70% | 19,942 | 304,207 | ok |  |

Also in CSV: CELH, KR, TGT, GIS

## Communication/Media

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | ASTS | 136,018 | 65% | 244,824 | 1,174,980 | deep |  |
| 2 | AMC | 100,893 | 81% | 88,934 | 997,640 | good |  |
| 3 | SNAP | 77,104 | 82% | 137,396 | 1,314,512 | good |  |
| 4 | T | 62,327 | 63% | 100,895 | 1,023,904 | good |  |
| 5 | VZ | 57,024 | 64% | 102,937 | 984,607 | good |  |
| 6 | RDDT | 42,288 | 58% | 43,177 | 462,003 | good |  |
| 7 | CMCSA | 28,581 | 59% | 25,527 | 787,535 | ok |  |
| 8 | DIS | 27,069 | 57% | 34,358 | 595,451 | ok |  |
| 9 | BIDU | 24,848 | 61% | 22,724 | 354,935 | ok |  |
| 10 | RBLX | 24,719 | 65% | 24,969 | 369,998 | ok |  |

Also in CSV: NN, SIRI, LUMN, TMUS, ECHO, TTWO, DJT, PINS

## Materials/Metals & Mining (incl. gold, uranium)

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | CLF | 54,475 | 58% | 94,677 | 819,061 | good |  |
| 2 | USAR | 39,026 | 62% | 47,128 | 545,763 | ok |  |
| 3 | FCX | 35,858 | 61% | 31,420 | 908,083 | ok |  |
| 4 | AG | 29,027 | 67% | 38,278 | 947,728 | ok |  |
| 5 | VALE | 26,297 | 54% | 17,465 | 1,660,765 | ok |  |
| 6 | CCJ | 25,048 | 37% | 35,145 | 426,961 | ok |  |
| 7 | MP | 24,482 | 56% | 26,074 | 476,032 | ok |  |
| 8 | HL | 22,872 | 67% | 22,310 | 796,723 | ok |  |
| 9 | UUUU | 21,538 | 72% | 23,261 | 512,073 | ok |  |

Also in CSV: CRML, B, CDE, AA, TMC, DOW, UEC, NEM, MOS

## Utilities/Power (incl. nuclear, AI power)

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | PCG | 103,668 | 83% | 98,851 | 2,364,507 | deep |  |
| 2 | EOSE | 54,775 | 72% | 74,330 | 1,600,092 | good | small cap <$1B, speculative |
| 3 | OKLO | 54,240 | 65% | 52,823 | 680,720 | good |  |
| 4 | VST | 49,270 | 64% | 42,362 | 492,242 | good |  |
| 5 | SMR | 48,991 | 67% | 37,026 | 494,172 | good |  |
| 6 | FSLR | 33,691 | 55% | 41,181 | 720,190 | ok | UW tags it Technology (solar) |
| 7 | TE | 25,225 | 77% | 29,879 | 398,878 | ok | small cap <$1B, speculative; UW tags it Electrical Equipment |
| 8 | RUN | 22,569 | 68% | 12,198 | 548,971 | ok | UW tags it Technology (solar) |
| 9 | NEE | 21,216 | 53% | 18,793 | 487,429 | ok |  |

Also in CSV: PLUG, GEV, FPS, FCEL, CEG, NRG, EIX

## Real Estate

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | AGNC | 55,472 | 36% | 39,905 | 731,765 | good |  |
| 2 | OPEN | 42,534 | 81% | 46,810 | 947,845 | good |  |
| 3 | FRMI | 23,397 | 72% | 28,247 | 777,479 | ok |  |
| 4 | MPT | 15,229 | 45% | 16,493 | 674,742 | thin |  |
| 5 | NLY | 14,496 | 54% | 15,608 | 173,220 | thin |  |
| 6 | GEO | 10,132 | 89% | 11,435 | 246,210 | thin |  |
| 7 | O | 8,521 | 58% | 6,051 | 148,312 | thin |  |

## Tech/software not in universe

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | NOK | 131,255 | 77% | 98,821 | 2,842,187 | deep |  |
| 2 | CRWD | 102,140 | 54% | 90,010 | 1,201,989 | deep |  |
| 3 | ONDS | 96,276 | 72% | 91,000 | 1,549,847 | good |  |
| 4 | NOW | 82,638 | 64% | 93,010 | 1,046,676 | good |  |
| 5 | IONQ | 78,177 | 67% | 92,961 | 689,918 | good |  |
| 6 | HPE | 62,776 | 70% | 50,989 | 587,422 | good |  |
| 7 | CRM | 58,280 | 63% | 46,187 | 637,305 | good |  |
| 8 | SHOP | 51,336 | 60% | 42,125 | 526,294 | good |  |
| 9 | IBM | 50,138 | 70% | 38,472 | 535,829 | good |  |
| 10 | CSCO | 49,887 | 68% | 50,179 | 797,009 | good |  |

Also in CSV: AI, U, RGTI, BB, ADBE, PANW, QBTS, APP, TTD, SNOW, NVTS, SOUN, POET, KEEL, QUBT, PATH, FIG, AXTI, MDB, HPQ, ZS, FSLY, ACN, MCHP

## Sector & thematic ETFs

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | XLF | 271,473 | 39% | 266,316 | 5,472,475 | deep |  |
| 2 | XLE | 152,298 | 47% | 139,258 | 3,624,031 | deep |  |
| 3 | GDX | 137,654 | 61% | 140,218 | 2,392,880 | deep |  |
| 4 | XLU | 130,302 | 75% | 97,709 | 2,687,609 | deep |  |
| 5 | KRE | 90,737 | 35% | 52,712 | 2,053,594 | good |  |
| 6 | XBI | 40,563 | 36% | 50,938 | 631,019 | good |  |
| 7 | XLK | 36,826 | 37% | 28,908 | 776,531 | ok |  |
| 8 | XLP | 33,514 | 26% | 75,741 | 719,649 | ok |  |
| 9 | XLI | 26,279 | 34% | 26,750 | 521,627 | ok |  |
| 10 | JETS | 22,334 | 79% | 6,953 | 189,618 | ok |  |

Also in CSV: XLV, COPX, URA, XLY, XOP, GDXJ, XRT, IYR, XLB, XHB, ITA

## Macro/commodity/intl ETFs

| # | Ticker | 30d avg opt vol | Call % | 7d avg | Total OI | Liquidity | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 1 | TLT | 1,086,837 | 66% | 1,051,848 | 13,536,660 | deep |  |
| 2 | EWZ | 665,370 | 74% | 765,681 | 11,384,322 | deep |  |
| 3 | IBIT | 662,644 | 60% | 489,100 | 6,914,841 | deep |  |
| 4 | HYG | 602,626 | 20% | 512,923 | 9,521,605 | deep |  |
| 5 | GLD | 404,333 | 60% | 363,479 | 4,817,166 | deep |  |
| 6 | SLV | 362,889 | 67% | 330,229 | 5,145,920 | deep |  |
| 7 | USO | 239,706 | 48% | 176,934 | 1,475,336 | deep | UW tags it Financial Services |
| 8 | ETHA | 145,509 | 68% | 33,373 | 127,295 | good |  |
| 9 | LQD | 141,960 | 41% | 143,123 | 2,806,714 | deep |  |
| 10 | IEF | 116,706 | 47% | 62,249 | 1,476,731 | deep |  |

Also in CSV: EEM, FXI, KWEB, EFA, UNG, ARKK, SILJ, BNO
