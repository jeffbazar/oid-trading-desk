# OID mini desk (`oid-mini-desk`): all OID data collection on the Mac mini

Research / paper only. No broker, order or trading code is here. Plan: `docs/MINI-MIGRATION-PLAN.md`. Deploy: `docs/MINI-DEPLOY-RUNBOOK.md`.

This package installs **next to** the existing quote collector (`~/oid-quote`, launchd `com.oid.quote-collector`, :8787). It does not modify the collector.

## Layout on the mini (`~/oid-desk`)
```
app/       oid_desk/ (data API, status, marks adapter, EDGAR, public macro, VIX plug, oidctl), tests/, vendor/, jobs.json
bin/       oidctl · run-job.sh (launchd entry) · enter-keys.sh (Jeffrey types keys, hidden)
desk/      desk tree, same relative layout as the box (/workspace/oid-trading-desk), so the box scripts run unchanged
flags/     <job>.disabled: EVERY job ships disabled
env/       non-secret per-job switches (shadow: option-subs.env -> OID_OPTION_SUBS_PUSH=0)
overrides/ shadow-only config overlays deep-merged on desk-state pushes (focus-watch.json FA budget, uw-refresh.json)
launchd/   rendered plists (copied to ~/Library/LaunchAgents only by `oidctl enable`)
logs/ state/ venv/
```
Secrets live in `~/oid-quote/secrets` (same 700 dir as the Alpaca keys): `FLASHALPHA_API_KEY`, `UW_API_KEY`, `HERENOW_API_KEY`, optional `EIA_API_KEY`, generated `OID_DESK_WRITE_TOKEN`. `desk/secrets/flashalpha-api-key` is a symlink to the FA file. Values are never copied, printed or logged.

## Jobs (`oidctl list`)
| job | group | what |
|---|---|---|
| data-api | core | :8788 `/v1/health` (open) · `/v1/feeds` · `/v1/feed?name=` · `/v1/walls` `/v1/flow` `/v1/marks` `/v1/macro` `/v1/filings` `/v1/status` `/v1/bars-summary` (read token = OID_QUOTE_TOKEN) · `POST /v1/desk-state` (write token) · one-shot `/v1/desk-write-token` handoff |
| status | status | mini job heartbeats + launchd + collector health → `mini-status.json` (alarm) |
| option-subs | marks | `quotes/mini_poller.py` against 127.0.0.1:8787 (subs push off in shadow) |
| marks | marks | SIP quotes + Alpaca snapshot prev close → `live_refresh.py --equity-quotes-file --options-from-mini --skip-rebuild` |
| fa-focus | fa | `quotes/focus_watch.py` + in-process FA focus refresh |
| uw-refresh / whale-flow | uw | UW tide / net prem / flow alerts; whale flow 60 s |
| bars | bars | `quotes/mini_bars.py loop` |
| edgar | edgar | SEC EDGAR submissions JSON (needs `edgar.sec_user_agent` email) |
| macro-public | macro | FRED + EIA (if key) + VIX provider (default `agent_rh`) |
| publish | publish | rebuild + here.now every 5 min, all sessions (phase 5 only) |
| benzinga | news | **hook only, on hold** until X Summarizer agrees (`oidctl enable` refuses without `--force`) |

`:8788` is a sidecar because the collector's `:8787` was being changed by the `/v1/bars` deploy at the same time. Folding these routes into :8787 later is optional. The box mirror only needs the base URL in `config/mirror.json`.

## Commands
```
~/oid-desk/bin/oidctl list | status | selfcheck
~/oid-desk/bin/oidctl enable data-api status          # bootstrap into launchd
~/oid-desk/bin/oidctl disable <job> | all-off          # rollback: flag + bootout + remove plist
~/oid-desk/bin/oidctl run <job>                        # foreground, same env as launchd
~/oid-desk/bin/oidctl token-handoff --minutes 30       # box mirror fetches the write token once
```
Build on the box: `python3 minihost/build_dist.py [--profile full]` → `minihost/dist/oid-mini-desk*.tar.gz`. Tests: `cd minihost && python3 -m unittest discover -s tests -t .`.
