# mini-oid-collector

Source snapshot of every OID job running on Jeffrey's Mac mini (`jake@Jakes-Mac-mini.local`):
the Alpaca quote/volume collector, the mini desk job runner, the trigger engine (vol-surge / news-surge),
X-on-surge, option flow, the live volume page and its Field Guide, plus the launchd agents that run them.
Research / paper only: there is no broker or order-placing code here.

**Code, config and docs only.** Secrets, market data, caches, logs, sqlite/parquet/jsonl, runtime state,
venvs and `*.bak*` backups are deliberately excluded (see `.gitignore`). The tree mirrors the mini's home
directory layout, so `oid-desk/app` here is `~/oid-desk/app` on the mini, and so on.

## Folders

| folder | mini path | what it is |
|---|---|---|
| `oid-quote/app/` | `~/oid-quote/app` | `oid_quote` collector: Alpaca SIP stock + OPRA option streams, 5-second volume (`volume5s.py`), live volume (`livevol.py`), bars, HTTP API on :8787. Tests in `tests/`. |
| `oid-quote/config.json` | `~/oid-quote/config.json` | collector runtime config (feeds, port, caps). No keys. |
| `oid-desk/app/` | `~/oid-desk/app` | `oid_desk` package (data API :8788, status, marks, alerts, selfheal, position trigger, futures_live, vix_live, macro_public, EDGAR Form 4, short borrow, read tokens, `oidctl` backend), `oid_archive` (bars/volume/X archive compaction + integrity), `jobs.json` (job catalog), tests, `vendor/herenow-publish.sh`. |
| `oid-desk/bin/` | `~/oid-desk/bin` | `oidctl` (job control CLI), `run-job.sh` (launchd entry wrapper), `enter-keys.sh` (hidden key entry prompt; stores keys in the secrets dir, contains none). |
| `oid-desk/triggers/` | `~/oid-desk/triggers` | trigger engine: `oid_triggers.py` (scheduled triggers + `--vol-surge-loop`), `oid_surges.py`, `config.json`, tests. |
| `oid-desk/x-on-surge/` | `~/oid-desk/x-on-surge` | X search on volume/news surge: `oid_x_on_surge.py`, `lib/` (budget guard, query builder, prefilter, query map, credibility tiers, blocklist). |
| `oid-desk/overrides/` | `~/oid-desk/overrides` | shadow config overlays incl. `mini-desk.json`, `focus-watch.json`. |
| `oid-desk/flags/` | `~/oid-desk/flags` | `<job>.disabled` flag files (which jobs are held off). |
| `oid-desk/launchd/` | `~/oid-desk/launchd` | rendered plist templates that `oidctl enable` copies into LaunchAgents. |
| `oid-desk/desk/` | `~/oid-desk/desk` | desk tree (same layout as the box's `oid-trading-desk`): `Makefile`, `dashboard/` (page builders + docs + published html), `quotes/` (mini poller, bars, FA focus watch, UW refresh, option marks, mirror poller, live gate), `scripts/` (pollers, cutover, publishers, automation prompts), `config/` (mini-desk.json, live-gate, mirror, stream allowlist, uw-refresh, focus-watch), `public/`, `dist-prod/`, `market-data/*.py` + schema docs, `paper-trades/*.py`, `chart-bot/whale-flow/` code. |
| `oid-live-page/` | `~/oid-live-page` | live volume page server `livepage.py` + `index.html` (tiles, C/P chips, momentum arrows, wall/flip marks, ladder dry-run), `sectors.json`, `serve.sh`, `install.sh`, `build_guide.sh`, its plist. |
| `oid-live-page/guide/` | `~/oid-live-page/guide` | the Field Guide: `index.html`, `docs/*.md` + `docs/img/*.png`, vendored `marked.min.js` / `mermaid.min.js`. |
| `oid-optflow/` | `~/oid-optflow` | option flow collector `optflow.py` (C/P chips, momentum) + the `patch_*.py` scripts used to roll its features into the live page; its plist. |
| `oid-data/config/` | `~/oid-data/config` | `x-on-surge-config.json` (X phase switches + spend cap). |
| `launchd/` | `~/Library/LaunchAgents/com.oid.*.plist` | the agents actually installed on the mini (source of truth for what runs). |
| `tools/secret_scan.py`, `sync.sh` | `~/mini-oid-collector` | snapshot tooling (below). |

Not on the mini: `minihost/` (the box-side builder of the `oid-mini-desk` package) lives in the box repo.
Staging/package dirs on the mini (`~/oid-*-stage*`, `~/oid-desk-pkg`, `~/oid-staging`, `oid-optflow/stage`, `*.tgz`) are not live and are not included.

## launchd jobs (`~/Library/LaunchAgents`)

| label | runs | schedule |
|---|---|---|
| com.oid.quote-collector | `~/oid-quote/venv/bin/python -m oid_quote --root ~/oid-quote` (cwd `oid-quote/app`) | KeepAlive |
| com.oid.tailscaled | `/opt/homebrew/bin/tailscaled --tun=userspace-networking` (state in `~/oid-quote/tailscale`) | KeepAlive |
| com.oid.desk.data-api | `run-job.sh data-api … -m oid_desk.api` (:8788) | KeepAlive |
| com.oid.desk.status | `-m oid_desk.status --write` | every 60 s |
| com.oid.desk.alerts | `-m oid_desk.alerts` | every 60 s |
| com.oid.desk.selfheal | `-m oid_desk.selfheal` | every 60 s |
| com.oid.desk.futures-live | `-m oid_desk.futures_live` | every 60 s |
| com.oid.desk.vix-live | `-m oid_desk.vix_live` | every 120 s |
| com.oid.desk.position-trigger | `-m oid_desk.position_trigger` | every 30 s |
| com.oid.desk.macro-public | `-m oid_desk.macro_public` | every 900 s |
| com.oid.desk.edgar | `-m oid_desk.edgar_form4 --if-due` | hourly |
| com.oid.desk.short-borrow | `-m oid_desk.short_borrow --if-due` | hourly |
| com.oid.desk.marks | `-m oid_desk.marks loop` | KeepAlive (SuccessfulExit) |
| com.oid.desk.bars | `desk/quotes/mini_bars.py loop` | KeepAlive (SuccessfulExit) |
| com.oid.desk.option-subs | `desk/quotes/mini_poller.py` | KeepAlive (SuccessfulExit) |
| com.oid.desk.fa-focus | `desk/quotes/focus_watch.py` | KeepAlive (SuccessfulExit) |
| com.oid.desk.uw-refresh | `desk/quotes/uw_refresh.py` | KeepAlive (SuccessfulExit) |
| com.oid.desk.whale-flow | `desk/chart-bot/whale-flow/whale_flow.py --loop` | KeepAlive (SuccessfulExit) |
| com.oid.desk.triggers | `/usr/bin/python3 ~/oid-desk/triggers/oid_triggers.py` | every 60 s |
| com.oid.desk.volsurge | `/usr/bin/python3 ~/oid-desk/triggers/oid_triggers.py --vol-surge-loop` | KeepAlive |
| com.oid.desk.x-on-surge | `/usr/bin/python3 ~/oid-desk/x-on-surge/oid_x_on_surge.py` | KeepAlive |
| com.oid.desk.optflow | `~/oid-quote/venv/bin/python ~/oid-optflow/optflow.py` | KeepAlive |
| com.oid.desk.livepage | `/usr/bin/python3 ~/oid-live-page/livepage.py` | KeepAlive |
| com.oid.archive.main | `-m oid_archive.compact --pass main --weekdays-only` (cwd `~/oid-data`) | weekdays 14:00 |
| com.oid.archive.post | `-m oid_archive.compact --pass post --weekdays-only` | weekdays 17:15 |
| com.oid.archive.weekly | `-m oid_archive.integrity --delete` | Saturday 10:00 |

`run-job.sh` jobs use `~/oid-desk/venv/bin/python` with cwd `~/oid-desk/app` or `~/oid-desk/desk`. Times are mini-local (America/Los_Angeles).

## Where secrets and data live on the mini (paths only, never in this repo)

- Secrets: `~/oid-quote/secrets/` (Alpaca `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`, `FLASHALPHA_API_KEY`, `UW_API_KEY`, `HERENOW_API_KEY`, `OID_QUOTE_TOKEN`, `OID_DESK_WRITE_TOKEN`, `OID_ALERT_WEBHOOK_KEY`, `read-tokens/`), `~/oid-data/secrets/` (`X_BEARER_TOKEN`), `~/oid-live-page/secrets/` (`LADDER_PUSH_TOKEN`), `~/oid-desk/desk/secrets/` (symlink to the FA key), `~/.oid/webhook.env`, `~/oid-quote/tailscale/` (node state/keys).
- Per-job env switches: `~/oid-desk/env/*.env` (excluded as `.env` files).
- Data: `~/oid-data/{archive,state,spool,logs}`, `~/oid-desk/{state,logs}`, `~/oid-desk/desk/{cache,data,market-data/latest,paper-trades/*.json,tmp,chart-bot/*/<date>}`, `~/oid-quote/{cache,logs}`, `~/oid-live-page/{data,logs}` (incl. `fa-walls-pulse.json`, `wall-weights.json`, `ladder.jsonl`), `~/oid-optflow/{data,logs}`.
- Code reads secrets from those files or from env vars of the same name (e.g. `APCA_API_KEY_ID`, `FLASHALPHA_API_KEY`, `X_BEARER_TOKEN`); nothing is hardcoded.

## Deploy (to a mini with the same layout)

```bash
# from a checkout of this folder; never --delete into the live dirs (it would wipe data/secrets)
M=jake@Jakes-Mac-mini.local
rsync -av oid-quote/app/            $M:oid-quote/app/
rsync -av oid-desk/                 $M:oid-desk/
rsync -av oid-live-page/            $M:oid-live-page/
rsync -av oid-optflow/              $M:oid-optflow/
rsync -av oid-data/config/          $M:oid-data/config/
rsync -av launchd/                  $M:Library/LaunchAgents/
# restart only what changed, e.g.
ssh $M 'launchctl kickstart -k gui/$(id -u)/com.oid.desk.livepage'
# first install of an agent:
ssh $M 'launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.oid.desk.optflow.plist'
# desk jobs can also be managed with ~/oid-desk/bin/oidctl enable|disable|run <job>
```
Fresh machine: create the venvs (`python3 -m venv ~/oid-quote/venv && ~/oid-quote/venv/bin/pip install -r oid-quote/app/requirements.txt`; same for `~/oid-desk/venv`), create the secret files (`~/oid-desk/bin/enter-keys.sh`), then bootstrap the agents.

## Keeping it in sync: `sync.sh`

On the mini the repo is `~/mini-oid-collector` (local git, no remote yet). The live dirs are never edited:

```bash
~/mini-oid-collector/sync.sh             # copy live code -> repo, scrub+scan secrets, commit if changed
~/mini-oid-collector/sync.sh --dry-run   # same, but no commit
~/mini-oid-collector/sync.sh --tar /tmp/mini-oid-collector.tgz   # also export HEAD as a tarball
```
Steps: rsync each live dir into a temp stage with the exclude list; `tools/secret_scan.py --scrub`
replaces any known secret value (loaded in memory from the secret stores above, never printed) with a `${NAME}`
placeholder and regex-scans for Bearer tokens, `APCA*` assignments, `sk-` keys, key/token/secret assignments,
`?key=` URL params, private-key blocks, and long hex/base64 strings; any hard finding aborts the sync.
The stage is mirrored into the repo, re-checked, a path guard refuses to stage secret/data-like paths,
and then it commits as `Rose (OID desk) <jb@jbv.com>`. The latest scan summary is in `SCAN-REPORT.txt`.

## Publishing to GitHub (push.sh)

`sync.sh` ends by running `push.sh`, which mirrors this repo's committed tree (`git archive HEAD`, so only tracked files) into `mini-oid-collector/` of a working clone at `~/oid-trading-desk-clone` (remote `git@github-oid:jeffbazar/oid-trading-desk.git`, deploy key `~/.ssh/oid_deploy_ed25519` via the `github-oid` alias in `~/.ssh/config`), re-runs the secret scan on that copy, commits with the list of mini commits covered, and pushes to branch `mini-sync` (override with `OID_PUSH_BRANCH`). It fails soft: if GitHub is unreachable or the key is not authorized it logs to `~/oid-data/logs/mini-push.log` and sync carries on.
