OID support levels watch (Rose desk, routine folder oid-support-levels-watch). Fires every 15 min on weekdays, about 6:05 AM to 1:50 PM PT. Research and paper only. Zero Robinhood orders: never place, modify, cancel, review, or exercise any order, and never call any RH order or exercise tool.

GOAL
Rebuild the universe support / good-low map from FlashAlpha put walls plus RH equity quotes. Notify only when a PRIMARY name newly enters GOOD_LOW or THRU_PUT, or its put wall hard-rolls while it is near, compared with the prior snapshot. Soft color only. Support alone never elevates anything to PAPER_CANDIDATE. Soft C never elevates on its own.

DESK ROOT
/workspace/options-intelligence-desk (symlink to /workspace/oid-trading-desk; either path works). Run every command from this root.

UNIVERSE (defined in the builder; do not hand-edit)
PRIMARY: SPY, QQQ, NVDA, TSLA, PLTR, GOOGL, NFLX, META, AMZN, AMD, CBRS, INTC, TSM
EXTENDED (soft color when walls exist, never notify alone): MU, BE, MRVL, NBIS, IREN, CRWV, SNDK, AVGO, ASML, GOOG

HARD RULE: THIS ROUTINE NEVER WRITES rh-quotes
- Rose's refresh_marks.py / live_refresh.py is the only writer of market-data/latest/rh-quotes.json (see hal/DUPLICATE-RH-QUOTES.md and CUTOVER-20261005.md).
- Never call write_feed("rh-quotes", ...) and never write rh-quotes.json directly. Never stamp writer=oid-support-levels-watch on rh-quotes. Never run refresh_marks.py or live_refresh.py from this routine, because both of them write rh-quotes.
- Do not create per-run tmp/support_rh_pull_*.py or tmp/support_rebuild_*.py scripts. The old copy-and-edit pattern is retired. The builder below replaces it.

STEPS

1) Check freshness (query dedup)
- python3 market-data/cache_io.py age fa-levels
- python3 market-data/cache_io.py age rh-quotes
- python3 dashboard/refresh_support_map.py --check-piggyback  (prints rh-quotes coverage for the support symbols; makes no RH call and writes nothing; exits 0 when fresh)

2) FA walls (existing soft-support rules, unchanged)
- The builder reads fa-levels with read_fresh. On a miss it falls back to STALE_CARRY from market-data/latest/fa-levels.json. Never invent walls. A name without walls shows as WALLS_DATA_INSUFFICIENT.
- FlashAlpha free-tier caution: do not burn FA quota. After the 1:00 PM PT close, during AH or pre-market, or whenever FA quota is low or exhausted, do NOT call FlashAlpha; use STALE_CARRY and label it. Pull FA levels only within the existing RTH rules for this routine, only for missing or stale PRIMARY walls, and at most once per run.

3) RH quotes: piggyback first, never become a writer
a. If --check-piggyback reports fresh with no primary_missing, run the builder with the cache only (step 4). Make no RH quote call.
b. If rh-quotes is stale or partial, first look for a Rose/live_refresh equity-quotes JSON that is 120 seconds old or less (a get_equity_quotes dump that Rose's live book pulse just fed to live_refresh.py --equity-quotes-file, under tmp/). If one exists, pass it with --equity-quotes-file. It only fills the missing symbols.
c. If there is no such file, you may make one read-only RH equity-quote pull. Look up the Robinhood quote tool with the dynamic-tool discovery tool first; it is read-only and never an order tool. Pull only the missing symbols (primary_missing first, then extended). Save the raw JSON to tmp/support-eq-quotes-YYYYMMDD-HHMM.json and pass that file to the builder with --equity-quotes-file. Do not feed the file into refresh_marks.py, live_refresh.py, or write_feed. The builder uses it in memory only.
d. If quotes still can't be resolved (the pull fails, or the builder exits 1 saying primary quotes are incomplete), do not fabricate or carry old quotes. Report: "rh-quotes stale — Rose sole writer (refresh_marks.py / live_refresh.py) must refresh", set notify=false, and stop.
- In AH or pre-market the builder prefers last_non_reg. Label quote source and age (cache, file, or cache+file).

4) Build or update the support map (new piggyback builder)
- Normal run (writes the support-map feeds):
  python3 /workspace/options-intelligence-desk/dashboard/refresh_support_map.py [--equity-quotes-file tmp/support-eq-quotes-YYYYMMDD-HHMM.json]
  This writes market-data/latest/support-map.json (writer refresh_support_map.py, ttl 300), paper-trades/universe-support-watch.json, the dashboard copy, and paper-trades/nvda-support-watch.json plus its dashboard copy. It never writes rh-quotes (its summary shows wrote_rh_quotes=false).
- Use --dry-run only when checking or debugging. It writes nothing and must not be followed by the notify step.
- Do not pass --writer oid-support-levels-watch. Leave the builder's default writer stamp alone.

5) Notify diff (dedup state, journal, NVDA doc)
  python3 /workspace/options-intelligence-desk/dashboard/support_notify_diff.py
  This compares PRIMARY statusHint and put walls with tmp/support-levels-last.json (on first use after the cutover it seeds that file from the 2026-10-05 backup). It then writes tmp/support-levels-last.json, tmp/support-levels-notify-this-run.json, and tmp/support-levels-desk-ping.txt. Only when notify is true, it journals to journal/runs/ and journals/runs/ as OID-SUPPORT-YYYYMMDD-HHMM.md. It also updates the "Last support-levels run" line in NVDA-SUPPORT-WATCH.md. It writes no market-data feed and makes no RH call.
  Notify policy (unchanged):
  - Only PRIMARY names in GOOD_LOW or THRU_PUT. Reasons: new_entry, reenter, hard_roll (put wall changed while near), hint_change.
  - A given symbol+hint notifies at most once per RTH half-day (AM before 12:30 PM PT, PM after) unless it leaves the band and re-enters.
  - EXTENDED names, ABOVE_PUT, flip-testing, and WALLS_DATA_INSUFFICIENT are soft color only and never trigger a notify. Soft C never elevates alone.
  - No spam: when notify=false, send nothing to the user.

6) Report (required)
1. as_of_pt and session (PRE/RTH/AH)
2. FA freshness, age, and writer; RH quote source (cache / file / cache+file), age, and writer
3. nearSupportNow (primary and extended)
4. statusBySymbol for PRIMARY
5. notify true/false
6. If notify=true: the exact short desk ping text from tmp/support-levels-desk-ping.txt (PRIMARY tagged names with spot, put wall, % vs put, call wall, day %, soft note, reason tag; hard rolls if any). Deliver that ping to the user as a soft take-look only. If notify=false, say so clearly and send nothing.
7. Paths written, confirming rh-quotes was not written
8. Any errors, including any Rose-must-refresh message

Never invent walls. Never elevate. Never place orders. Give all user-facing times in PT.
