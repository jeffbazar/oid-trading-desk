# 37 · Company credit (CDS and bonds per name)
[← Index](README.md)

> Added **Wed 10/21/2026, 8:50 PM PT**. Shown as the **Company credit** section on the `/credit` tab ([36](36-credit-betas.md)). Data endpoint: `/name-credit.json`. Research only, not an order signal.

**What it is.** A free, daily log of company-level credit for the AI builders and their backers, built by the launchd job `com.oid.desk.name-credit` (Mon–Fri 13:40 PT, `~/oid-score/research/name_credit.py`), ten minutes after the market-wide credit job. Output goes to `~/oid-data/research/name-credit/`.

**Names and roles.** CRWV, NBIS, IREN, APLD, WULF, CIFR, CORZ = `neocloud`; ORCL, META, AMZN, MSFT = `hyperscaler`; **NVDA and GOOGL = `backer`**, so their CDS can be compared with CRWV's (NVDA holds about 10% of CRWV and backstops its capacity).

**Three sources, kept in separate files and separate fields of `latest.json`**

| File | Source | `source_quality` | What a row is |
|---|---|---|---|
| `cds_dtcc_trades.csv` | DTCC SBSDR public dissemination: SEC security-based-swap credit slices (free, no key) | `firsthand_dtcc` | One single-name CDS trade: time, maturity, coupon, notional (above $5M is shown as `5,000,000+`), quoted spread or upfront, and the spread derived from it |
| `cds_dtcc_daily.csv` | Built from the trades file | `firsthand_dtcc` | Per name per day: the on-the-run 5-year level in bp, the method, and trade counts |
| `cds_x_prints.csv` | X recent search (3 queries/day) | **`secondhand_x`** | A 5y CDS level quoted in a post: company, level, change, prior level, the date the level refers to, author, post link, approximate flags |
| `bond_yields.csv` | FINRA TRACE last prints, read from Kilambi News leverage pages | `firsthand_finra` | One bond per trade date: CUSIP, coupon, maturity, price, yield, yield type, spread to Treasury (CRWV) |

**How the DTCC 5y level is set.** Only new trades and corrections count. Trades later marked as errors are dropped, and so are portfolio or compression batches (one upfront shared by three or more names in the same minute). The level is the median **quoted spread** of on-the-run 5y trades that day (maturity 20 Dec 2031 since the 20 Sep roll). If no trade that day has a quoted spread, the job uses the median spread **implied from the upfront** (flat hazard, 4% rate, 40% recovery, about ±2%). Upfronts are used only when the notional is exact. The public record doesn't show which side paid, so both signs are tried. A sign is kept only if exactly one solves, or if one lands within 25% of a reference and clearly nearer than the other. The reference is that day's quoted median, then an earlier quoted DTCC level, then the median FINRA bond spread, then the X prints. Otherwise the trade is marked `upfront sign ambiguous` and left out.

**How X prints are parsed.** Each sentence that mentions CDS and a covered company is read. "To a record ~1,118 basis points" is the level, "+135 basis points" is the change, and "up from 260 bps a week earlier" is the prior level. "On Wednesday" and "on Oct 19" are turned into dates against the post's ET date; a sentence with no day takes the day named earlier in the post. `level_approx` / `change_approx` = 1 for "~", "as much as", "about", "above" and similar words. Nothing is filled in that the post doesn't say. Validated on the two GlobalMktObserv seed posts (CRWV ~1,118 bp, +135 on Wed 10/14; ORCL 288 bp, prior 260; CRWV 1,194.5 bp, as much as +74.5, on Thu 10/15): `research/test_name_credit.py`.

**X budget.** The job makes 3 recent-search calls per day at max_results 25/15/10, with `since_id` so only new posts come back. That's at most 50 post reads ($0.25) a day, typically much less. It also makes one batch user lookup ($0.01 per new author) for author handles. The job has its own $0.30/day ceiling, and x-on-surge now keeps `reserve_other_usd = 0.30` out of its own daily allowance, so the two together stay under the 95% line of the $5/day cap. Combined month spend is checked against $95. Ledger: `~/oid-data/state/x/name_credit_budget.json`. The kill file `~/oid-data/state/x/STOP` stops both jobs.

**Bonds.** CRWV rows come from each bond's own page: the last TRACE trade with its ET time, yield to worst and spread to Treasury. ORCL, IREN, APLD and WULF rows come from the issuer table, with a 30/360 yield to maturity computed here that ignores calls. Converts and low-coupon neocloud notes show the price only. **NBIS has no page there, so there's no NBIS bond series.** FINRA's own endpoints (`services-dynarep…/public/reporting` and `api.finra.org`) now require a FINRA login or API account, so they aren't used. Nothing was signed up for.

**On the tab.** One row per name: the DTCC 5y level and the prior day's level (firsthand), the latest X print with its refers-to date and author link (tagged **secondhand**), and bonds (CRWV's 9.25% 2030, 9% 2031 and 9.625% 2032 with price, yield and spread; other issuers show a bond count and median yield, or prices for converts). Values are raw and never smoothed.
