# OID per-bot model plan (API-first), 2026-10-21

Scope: every reasoning job defaults to the Anthropic lineup given in the desk context (Haiku 5.5 / Sonnet 5.5 / Opus 5.5 / Fable 5.1, 1M context, prompt caching, Batch API). Local open-weight models are reserved for three things: (a) a shadow/second-opinion path for the three high-volume classifiers, where determinism and a pinned sha256 matter more than cost; (b) a cold-standby narrative model for API outages; (c) nothing else. The order path stays LLM-free. Every open-weight figure below comes from Research 1 and 2; anything those sheets could not read from a primary page is marked UNVERIFIED.

## 1. Per-bot model table

| Bot | LLM job | Calls/day | Context/call (in / out) | Open-weight model + quant (role) | Proprietary model (primary) | Machine | Latency need | Why |
|---|---|---|---|---|---|---|---|---|
| Chart | None in steady state: deterministic feature producer. Optional one-line caption of a feature pack for the live page | 0 (optional ≤20) | 2K / 100 | none | Haiku 5.5 (captions only, not a feature) | box → API | minutes | The report moves Chart to deterministic features; a caption is cosmetic and must never be read back as a feature |
| Rose (short-term trader) | Rationale, candidate list, REJECT log over deterministic ranker output; strict tool schema | 80–100 | 8K / 600 (≈6K cacheable preamble) | Cold standby: Qwen3.6-35B-A3B 4-bit (~21 GB, Apache-2.0, native tool parser, 262K ctx); never primary | Sonnet 5.5, prompt-cached; 15-minute marks on Haiku 5.5 | box → API; standby on 64 GB mini | ≤60 s per 5-min loop | Sonnet is $2/$10 with $0.20 cache reads and strict tool schemas; 35B-A3B decodes ≈50–100 tok/s class on M4 Pro (Research 1, oMLX EXTRACT; M4 Pro figure scaled, UNVERIFIED), so a 600-token rationale lands in ~9 s if failover is needed |
| Hal (longer-term) | Premarket/open/close theses, 15-min marks when positions open, EOD review, X scan every 2 h | ~30 | 12K / 800 on the 4 big passes; 8K / 600 otherwise | Same cold standby as Rose | Opus 5.5 for premarket, open, close, EOD (4 passes); Sonnet 5.5 for marks and X scans | box → API | ≤2 min on big passes | Opus is the context's default for agentic reasoning at $4/$20; the 26 cheaper calls do not need it |
| Research | Bounded autoresearch loop: writes/edits feature code and study specs in `editable/`, reads results; code review of its own PRs | 3–5 sessions, ~30 turns each | 40–80K / 1.5K per turn, 80% cacheable | Fallback only: Qwen3-Coder-Next 80B-A3B 4-bit (~48 GB, SWE-bench V 70.6 EXTRACT) on 128 GB box if it is brought online; not on 64 GB alongside the sandbox | Opus 5.5 (loop); Fable 5.1 for code review of promotable diffs | sandbox on 64 GB mini (today) or 128 GB (phase 2); model via API | minutes per turn; bursty | Opus 5.5 is the stated default for coding/agentic work; no local model under 128 GB reaches it, and the sandbox already isolates `editable/` from sealed holdout |
| Data Ops | Hourly feed-health, quota, archive-integrity summary over deterministic checks | 24 | 4K / 300 | none (Qwen3.5-4B on an 8 GB mini was considered and rejected: nothing the desk depends on runs on 8 GB) | Haiku 5.5 | 8 GB mini B (checks) → API (summary) | minutes | Pure summarisation of numbers already computed; cheapest tier is right |
| X Summarizer | Score posts -2..+2, typed JSON, temperature 0 | 25–200 items (batched 10/call → 3–20 calls) | 1.5K / 100 per item | Shadow: Qwen3.5-9B 8-bit (~10 GB, Apache-2.0) via llama-server GBNF on the 64 GB mini; Gemma 4 E4B rejected for 8 GB hosting | Haiku 5.5 with `output_config.format` | box → API; shadow on 64 GB | ≤5 min | Feature-grade output; API primary, local shadow gives a re-run agreement metric and a sha256-pinned fallback |
| Macro | Morning macro pack, econ-calendar card, hourly macro-X scan | 10–20 | 6K / 500 (4K cacheable) | Cold standby shared with Rose | Sonnet 5.5 (pack, card); Haiku 5.5 (hourly scan) | box → API | ≤2 min | Narrative with light tool use; Sonnet default per lens |
| Peanut/News | Score Benzinga + X news items -2..+2 (replaces finbert as primary; finbert stays as baseline feature) | ~770 items (batched 10/call → ~77 calls) | 1.5K / 100 per item | Shadow: same Qwen3.5-9B 8-bit instance; finbert (110M, CPU) stays on an 8 GB mini as the deterministic baseline | Haiku 5.5, temperature 0, structured output | box → API; finbert on 8 GB mini C; shadow on 64 GB | ≤2 min | Research 3 shows finbert at 0.64 accuracy on live 2025 headlines (EXTRACT); the gold set decides who wins, not a benchmark |
| First-Seen | Typed classification of filings/headlines into gate flags (earnings, guidance, halt, macro print) with confidence + evidence quote; precision floor on 200-item gold set | ~800 items | 1.5K / 150 | Shadow and outage fallback: Qwen3.5-9B 8-bit with GBNF schema; promote to primary only if it passes the gold set (Qwen3.6-27B 4-bit as the upgrade if 9B misses the floor) | Haiku 5.5 strict structured output (primary); Sonnet 5.5 as gold-set judge | box → API; shadow on 64 GB | ≤60 s (gate flags feed Event Gate, which is deterministic) | Highest-stakes classifier; needs two independent scorers so disagreement is itself a feature |
| Post-Mortem | Weekly narrative over deterministic trade stats | 1/week | 150K / 8K | none | Fable 5.1 via Batch API (50% off) | box → API | hours | The lens reserves Fable for where capability is decisive; weekly, latency-free, batchable |
| Owner Mirror | Nightly narrative over deterministic stats | 1/night | 20K / 1.5K (10K cacheable) | none | Sonnet 5.5 via Batch API | box → API | hours | Narrative only; batch halves cost |
| Gate Keeper | Proposes config changes with evidence; never applies them | ~1/week (plus ad hoc) | 60K / 3K | none | Opus 5.5 | box → API | hours | Proposals go through the promotion ladder like code; needs the strongest reviewer short of Fable |
| Earnings/IV narrative | Small narrative on top of deterministic earnings/IV features | ~10 | 3K / 300 | none | Haiku 5.5 | box → API | minutes | Trivial volume, cosmetic narrative |

Event Gate and Replay/Practice are deterministic and get no row; Replay's optional explanations use Haiku 5.5 on demand.

Why Qwen3.5-9B rather than a 27B for the shadow classifiers: Research 1 sizes it at ~10 GB at 8-bit, Apache-2.0, with native tool/JSON support (VERIFIED README dates, EXTRACT card), and 800 + 770 + 200 items/day is ≈2.7M input tokens, trivial even at M4 Pro prefill (~118 tok/s measured for a dense 27B at 6-bit, oMLX EXTRACT; no 9B figure measured, UNVERIFIED). The 27B class is held in reserve if the 9B misses the precision floor.

## 2. Machine assignment and memory budget

Planning numbers use Research 1's rule of thumb (4-bit ≈ 0.6 GB/B params, 8-bit ≈ 1.1 GB/B; UNVERIFIED) and Research 2's headroom rule (OS + services ≥ 8 GB on big boxes, never wire above ~88% of RAM; UNVERIFIED). Apply `iogpu.wired_limit_mb` from a LaunchDaemon; it does not survive reboot.

| Machine | Role | Model weights | KV / prompt cache | OS + services headroom | What else runs there |
|---|---|---|---|---|---|
| **64 GB Mac mini (M4 Pro, 273 GB/s)** | Local LLM server + research sandbox | Steady state: llama-server instance A, Qwen3.5-9B Q8 GGUF ≈ 10 GB, `-np 1 --temp 0 --seed N -c 8192`. Failover: instance B, Qwen3.6-35B-A3B Q4 ≈ 21 GB, `-np 4 -cb -c 32768`, loaded only when the API is down (≈10 s from SSD) | A: 2 GB. B: 8 GB (`--prompt-cache` on the shared preamble) | 8 GB OS/services | Research sandbox users, sealed holdout directory (read-only to the sandbox UID, never mounted into any model's working dir), gold-set evaluator, llama-bench nightly. Steady-state wired ≈ 12 GB, leaving ~44 GB for research jobs; in failover ≈ 41 GB wired, research jobs capped at ~15 GB (wired limit set to 53,248 MB) |
| **8 GB mini A** (M1/M2-era per Research 2's note that M4 minis start at 16 GB; chip UNVERIFIED) | Deterministic only | none | none | 4 GB | Archiver + labeler mirror (write-behind copy of SIP/OPRA archive), archive-integrity hashes |
| **8 GB mini B** | Deterministic only | none | none | 4 GB | Data Ops checks (feed health, quotas), Event Gate, Replay/Practice engine |
| **8 GB mini C** | Deterministic only | finbert 110M (CPU, <1 GB) and optional SetFit/ModernBERT head (<1 GB) | n/a | 4 GB | Benzinga + X ingest, dedupe, finbert baseline scoring, item queue feeding the API scorers |
| **8 GB mini D** | Deterministic only; hot spare | none in production. An experimental Qwen3.5-4B Q4 (~2.5 GB) may be loaded for benchmarking only, and nothing downstream may read from it | ≤1 GB (experiment only) | 4 GB | Live-page mirror, gold-set runner, spare for A/B/C failover |
| **128 GB Mac (M4 Max class, UNVERIFIED chip)** | Not required for phase 1. Phase 2 options, in order: (1) move the research sandbox off the 64 GB mini; (2) host gpt-oss-120b MXFP4 (≈60–63 GB, Apache-2.0, native Structured Outputs; 75 tok/s and 59.5 GB peak on M4 Max 128 GB, oMLX EXTRACT) as a stronger outage fallback for Rose/Hal/Macro; (3) Qwen3-Coder-Next 80B-A3B 4-bit (≈48 GB) as a research-loop fallback | 60–63 GB (gpt-oss-120b) or 48 GB (Coder-Next) | 20–30 GB | 10 GB | Research sandbox + sealed holdout (if moved), post-mortem data pulls. Wired limit ≈ 110,000 MB |
| **Data mini (RAM unknown)** | LLM-free, by report | none | none | all | Alpaca SIP/OPRA collector, surge engine, ranker, contract selector, risk sentinel, execution gateway, reconciler, live page |
| **Linux box (8 vCPU, 0.8–5.4 GiB free)** | Orchestration | none (cannot host a model) | none | all | MCP connectors, Anthropic API clients for every bot, scheduler, prompt/feature registry, cost meter |

Serving choices follow Research 2: `llama-server` is the only stack where JSON-schema/GBNF, continuous batching, `--jinja` tools, `seed`, prompt cache and `/metrics` are all VERIFIED in the official README; Ollama's MLX runner serialises requests (issue #17280 open, VERIFIED) and mlx-lm's server has no `response_format` (VERIFIED), so neither is used for feature-grade calls. If MLX throughput is wanted for the failover narrative instance, vllm-mlx (lm-format-enforcer, VERIFIED) is the alternative, accepting a younger codebase.

## 3. Cost

### 3a. Proprietary path, monthly (Anthropic prices from the desk context)

Assumptions: 22 trading days for market-hours bots, 30 days for nightly/hourly bots; prompt caching applied only where the context lists a cache-read price ($0.20/MTok on Opus 5.5 and Sonnet 5.5). Haiku 5.5 is costed with no cache credit because the $0.20 cache-read figure cannot apply to a $0.10 input price (UNVERIFIED how Haiku caching is billed; treat Haiku rows as upper bounds). Batch API at 50% is applied only to Post-Mortem and Owner Mirror.

| Bot | Model | Calls/day × tokens | $/day | $/month |
|---|---|---|---|---|
| Rose | Sonnet 5.5 | 100 × (2K fresh + 6K cached in, 600 out) = $0.0112/call | 1.12 | 24.6 |
| Hal | Opus 5.5 ×4 (3K fresh + 9K cached, 800 out = $0.030) + Sonnet 5.5 ×26 ($0.0112) | | 0.41 | 9.0 |
| Macro | Sonnet 5.5 | 15 × (2K fresh + 4K cached, 500 out) = $0.0098 | 0.15 | 3.2 |
| X Summarizer | Haiku 5.5 | 200 items × 1.5K in / 100 out | 0.04 | 1.2 |
| Peanut/News | Haiku 5.5 | 770 × 1.5K / 100 | 0.15 | 4.6 |
| First-Seen | Haiku 5.5 | 800 × 1.5K / 150 | 0.18 | 5.4 |
| Data Ops | Haiku 5.5 | 24 × 4K / 300 | 0.01 | 0.4 |
| Research | Opus 5.5 | 3–5 sessions × 30 turns × (12K fresh + 48K cached, 1.5K out = $0.088/turn) | 7.9–13.2 | 175–290 |
| Post-Mortem | Fable 5.1, batch | 1/week × 150K in / 8K out = $1.90 → $0.95 batched | | 4.1 |
| Code review | Fable 5.1 | ~10/month × 40K in / 3K out = $0.55 | | 5.5 |
| Owner Mirror | Sonnet 5.5, batch | 1/night × (10K fresh + 10K cached, 1.5K out) = $0.037 → $0.019 | 0.02 | 0.6 |
| Gate Keeper | Opus 5.5 | 1/week × 60K in / 3K out = $0.30 | | 1.3 |
| Earnings/IV | Haiku 5.5 | 10 × 3K / 300 | 0.005 | 0.1 |
| Gold-set judging | Sonnet 5.5 | weekly 200 items × 3 scorers | | ~1 |
| **Total** | | | | **≈ $235–$350/month**, of which Research is 75–85%; everything else ≈ $60/month |

Sensitivity: if Research runs one session/day, total ≈ $120/month. If Rose moves wholesale to Opus 5.5 it adds ≈ $22/month. The classifier tier is a rounding error on any vendor (Research 3 reaches the same conclusion), so classifier choice is made on gold-set precision and data posture, never price. The daily token run rate remains an unknown to be measured: the cost meter on the box logs `usage` per call and per bot from day one.

### 3b. Local path: electricity and one-time cost

Hardware is already owned, so one-time cost is engineering time plus a few hundred GB of SSD for GGUF files. Power figures were not in the research sheets and are my estimates (UNVERIFIED): M4 Pro mini ≈ 5 W idle, 60–70 W at full GPU load; averaged over a day of shadow scoring plus idle it is ≈ 20–30 W, i.e. 15–22 kWh/month, ≈ $3–5 at $0.20/kWh. Four 8 GB minis ≈ 7–10 W each ≈ 25 kWh/month ≈ $5. A 128 GB M4 Max class box holding gpt-oss-120b resident ≈ 10 W idle / 100+ W load, ≈ $5–15/month. Electricity for the whole fleet is therefore under $25/month, comparable to Rose's API bill. The real local cost is operational: wired-limit management (mlx-lm #883 kernel panic at 83.5% wired, VERIFIED), the lack of any batch-invariant kernel on Metal (VERIFIED absence for vLLM; UNVERIFIED for llama.cpp Metal), and the fact that no local model under 128 GB matches Opus 5.5 for the research loop.

## 4. Determinism and governance

**Every LLM feature is a versioned, scored numeric feature.** A feature call is identified by `feature_id = sha256(prompt_template || json_schema || model_pin || decode_params || server_pin)`, where:

- `model_pin` is the exact API model id (`claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-1`) for proprietary calls, plus the `model` string echoed in each response, logged so that a silent server-side change shows up as a diff; for local calls it is the sha256 of the GGUF file, the quant tag (`Q8_0`), the llama.cpp commit and the `-c` context size.
- `decode_params` is `temperature=0`, `top_p=1`, `max_tokens`, and for local calls a fixed `--seed` with `-np 1` so the request never shares a batch (Research 2: batch composition changes numerics even at temperature 0; Thinking Machines EXTRACT). Proprietary calls use `output_config.format` with a strict schema; local calls use GBNF/`json_schema` so the schema is enforced regardless of model.
- The full prompt, the raw response, `usage`, latency, and `feature_id` are appended to the feature log. Re-running a 50-item sample nightly yields a **re-run agreement** metric per feature (target ≥ 0.99 local, measured not assumed for API). Agreement below target is an alert, not a silent drift.

**Model swap = code change.** A new model, quant, prompt wording, schema field, or server version produces a new `feature_id`, which enters the same promotion ladder as code: shadow (scored but unread by the ranker) → gold-set gate → paper (read by the paper ranker only) → live. Two feature ids may run in parallel in shadow; the ranker reads exactly one, named in config, and Gate Keeper can only *propose* the config diff. API model deprecations are handled the same way: the old id is pinned until the new id passes the ladder.

**Gold-set evaluation for classifiers (First-Seen, Peanut/News, X Summarizer).** A 200-item stratified gold set per classifier, labelled by two humans with disagreements adjudicated (the dual-judge template in Research 3 is the pattern, UNVERIFIED source). Metrics: per-flag precision and recall, macro-F1, calibration of the confidence field, evidence-quote span validity (must be a substring of the input), and re-run agreement. The precision floor for First-Seen is set per flag; `halt` and `earnings` carry the highest floors because they feed Event Gate. Every candidate scorer (Haiku 5.5, Sonnet 5.5 as judge, Qwen3.5-9B Q8, finbert baseline) is scored on the same set before it is allowed into shadow, and re-scored weekly on a 50-item rotating fresh slice so the set does not go stale. The sealed holdout stays sealed: gold sets live outside it and are never used for research-loop training.

## 5. Fallback matrix

| Failure | Detection | Classifiers (First-Seen, Peanut, X) | Narrative bots (Rose, Hal, Macro) | Research / Post-Mortem / Gate Keeper | Order path |
|---|---|---|---|---|---|
| Local llama-server down (64 GB mini) | `/metrics` scrape fails, launchd restart count | No impact on primary (API); shadow feature logged as `missing`, agreement metric paused | No impact unless already in API failover; then narrative bots degrade to "no rationale, candidate list only" | none | unaffected |
| Anthropic API outage (5xx, timeouts > 30 s) | Health probe every 60 s from the box | Fail over to Qwen3.5-9B Q8 on the 64 GB mini, but only for feature ids that have passed the gold-set gate; output tagged `source=local_fallback` so the ranker can down-weight | Load instance B (Qwen3.6-35B-A3B Q4) on the 64 GB mini; Rose/Macro run with `degraded=true`; Hal's big passes are skipped rather than run on a weaker model | Pause; resume on recovery | unaffected by design |
| Anthropic rate limit (429) | Response headers / 429 count per minute | Exponential backoff, queue items, batch 20 per call instead of 10, cache preamble; if backlog > 15 min, same local failover as above | Rose skips a 5-minute slot rather than queueing (stale rationale is worse than none); Hal marks retry once | Research sessions throttle themselves; Post-Mortem/Owner Mirror are already Batch | unaffected |
| Both API and local down | Both probes fail | Features marked missing; Event Gate runs on deterministic inputs only (filings feed, halt feed) | No narrative; live page shows last good rationale with timestamp | paused | unaffected |
| Gold-set precision drops below floor on weekly re-score | Weekly eval job | Feature demoted to shadow automatically; previous passing feature id (if any) restored; alert | n/a | Gate Keeper proposes the fix | unaffected |
| Third-vendor option (not default) | manual | If a prolonged Anthropic outage (>1 trading day) is ever hit, OpenRouter with a data-policy filter and ZDR routing gives one key over GPT-5.4 mini or Gemini 3.5 Flash-Lite (Research 3, EXTRACT) for the classifiers; the feature id changes, so it must pass the gold set first, which in practice means pre-qualifying one alternative in shadow now | same | not used | unaffected |

The 128 GB box, if brought online, replaces instance B with gpt-oss-120b MXFP4, which lifts narrative failover quality and speed (~7 s per 2K/300 call, UNVERIFIED arithmetic on oMLX EXTRACT) without touching the 64 GB mini's research budget.

## 6. What not to do

1. **No LLM in the order path.** Surge engine, ranker, contract selector, sizing, risk sentinel, gateway and reconciler read LLM outputs only as logged, versioned numeric features with a `source` tag; nothing they do waits on an API or a local model, and an outage changes feature values, never order logic.
2. **No 8 GB mini hosts a model the desk depends on.** Research 2 puts usable model+KV memory at ~5–6 GB with swap risk and ~15 tok/s for a 4B model (UNVERIFIED); minis A, B, C and D run deterministic Python planes and finbert/SetFit only. Mini D's optional 4B experiment has no consumers.
3. **No model without a measured precision on the gold set.** This applies to Haiku 5.5 too: it is primary because it is the context's small fast model, not because it is assumed to pass. Benchmarks in the research sheets (τ2-bench, BFCL, FPB) are for shortlisting only; Research 3's 0.64 finbert headline result shows published scores do not transfer.
4. **No unpinned model ids, no temperature above 0, no shared-batch decoding for feature calls.** A call that cannot be reproduced is not a feature.
5. **No Ollama MLX runner or mlx-lm server for schema-bound calls** while Ollama #17280 stays open and mlx-lm lacks `response_format` (both VERIFIED).
6. **No research-loop model reading sealed holdout.** The sandbox UID cannot read the holdout directory, and the LLM edits only `editable/`; if the sandbox moves to the 128 GB box, the holdout moves with it under the same mount rules.
7. **No 100B-class local model on the 64 GB mini.** gpt-oss-120b peaks at 59.5 GB at 1K context (EXTRACT) and leaves no KV headroom; Research 2's #883 panic was at 83.5% wired.
8. **No cost decisions on the classifier tier.** At $0.04–$0.18/day per classifier, every vendor is a rounding error; choose on precision, structured-output strictness and data posture, and spend the attention on the research loop, which is 75–85% of the bill.

**Open items the research could not close (all UNVERIFIED):** measured tok/s for Qwen3.5-9B and Qwen3.6-35B-A3B on an M4 Pro 64 GB; whether the 8 GB minis are M1 or M2 class; the macOS default wired-limit fraction; Haiku 5.5 prompt-cache billing; power draw per machine; any batch-invariant decode on Metal. Each is resolved by measurement on the desk's own units (`llama-bench -p 2048 -n 300`, nightly re-run agreement, `memory_pressure`) before the corresponding feature id is promoted past shadow.