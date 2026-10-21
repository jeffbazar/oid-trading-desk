# Model and hardware plan for the OID bots

Prepared 2026-10-21 as a companion to `SCALING-STRATEGY-20261021.md` (section 5, "Language models: should and should not", and section 10, the bot roster). It answers one question: which open-weight model and which proprietary model each bot should run on, given the hardware already owned (one 64 GB Mac mini, four 8 GB Mac minis, one 128 GB Mac if necessary) and the rule that no language model sits in the order path.

Research and paper only. Every claim below is marked VERIFIED (read from a primary source on 2026-10-21), EXTRACT (read from a search extract or a community benchmark, not the primary page), or UNVERIFIED (arithmetic or a rule of thumb). Eight load-bearing claims from the first draft went to independent checkers; four were corrected and the corrections are already applied here. The list is in section 11.

## 1. The rule, and the answer in one table

**The stakes of the output and its latency need pick the primary model. The other path is the fallback, kept warm and measured, never assumed.**

- Narrative and agentic work (Rose, Hal, Macro, Research, Post-Mortem, Gate Keeper) runs on the Anthropic lineup. Nothing that fits a Mac matches it on tool use or long-horizon reasoning (Terminal-Bench 2.1: Qwen3.8-27B 73.0 against Claude Opus 4.8 85.0, VERIFIED in the GLM README; the gap to Opus 5.5 is larger).
- Feature-grade classification (Peanut/News, X Summarizer) and low-stakes summaries (Data Ops, Earnings/IV, Chart captions) move to the 64 GB mini once they pass a gold set. A sha256-pinned GGUF file on one slot with a fixed seed and the prompt cache off is as reproducible as the desk can get, and the price difference between local and API on this tier is a rounding error either way.
- First-Seen is the exception and stays on Haiku 5.5. Its gate flags need an answer inside 60 seconds at the open, and a single-slot local 9B queues a 100-item burst to about 16 minutes (UNVERIFIED arithmetic, section 4).

| Bot | Primary | Fallback | Runs on |
|---|---|---|---|
| Chart (captions only) | Local B (Qwen3.6-35B-A3B) | Haiku 5.5 | 64 GB mini |
| Rose | Sonnet 5.5, prompt-cached | Local B, header `degraded=true` | API client on the Linux box; B on the 64 GB mini |
| Hal | Opus 5.5 for the four big passes, Sonnet 5.5 for marks and X scans | Local B for marks; big passes skipped in Phase 1, gpt-oss-120b (C) in Phase 2 | API; B on 64 GB; C on 128 GB |
| Research | Opus 5.5 loop; Fable 5.1 for code review of promotable diffs | Pause in Phase 1; Qwen3-Coder-Next on C in Phase 2, flagged lower quality | API; sandbox on 64 GB (Phase 1) then 128 GB |
| Data Ops | Local B | Haiku 5.5 | 64 GB mini |
| X Summarizer | Haiku 5.5 at launch; local A2 (Qwen3.5-4B) once the gold-set gate passes | A1 shadow at launch; Haiku after migration | 64 GB mini |
| Macro | Sonnet 5.5 for the pack and the calendar card; Haiku 5.5 for the hourly scan | Local B | API; B on 64 GB |
| Peanut/News | Haiku 5.5 at launch; local A2 once the gate passes; FinBERT stays a baseline column | A1 shadow; Haiku after migration | 64 GB mini; FinBERT on 8 GB mini 1 |
| First-Seen | Haiku 5.5 with strict structured output | Local A1 (Qwen3.5-9B), only for feature ids that passed the gate, tagged `source=local_fallback` | API; A1 on 64 GB |
| Post-Mortem | Fable 5.1 on the Batch API | Opus 5.5, then wait | API |
| Owner Mirror | Sonnet 5.5 on the Batch API | Local B (Phase 1) or C (Phase 2) | API |
| Gate Keeper | Opus 5.5 | Defer a day | API |
| Earnings/IV | Local B | Haiku 5.5 | 64 GB mini |
| Event Gate, Replay/Practice, Surge Engine, Ranker, Contract Selector, Risk Sentinel, Gateway, Reconciler | No model | No model | Data mini |

Phase 1 is the launch configuration on the hardware you have today, with the 128 GB Mac switched off. Phase 2 starts the first time a research job is refused for memory on the 64 GB mini, or when you want Hal's big passes to survive an API outage; that trigger, not a date, brings the 128 GB Mac online.

Expected bill: about $140 to $320 a month, of which the research loop is 60 to 80 percent. Everything else on the desk costs about $55 to $65 a month. The local path costs electricity, roughly $15 to $25 a month (UNVERIFIED, no power measurements).

## 2. Per-bot detail

Throughput inputs are community rows or extrapolations unless marked VERIFIED. Dense 27B 4-bit on an M4 Pro 64 GB: 13.8 to 15.4 tok/s decode, about 118 tok/s prefill (oMLX, EXTRACT). Llama-2 7B Q8 on an M4 Pro: 30.7 tok/s decode, 450 tok/s prefill (llama-bench, VERIFIED), from which a 9B Q8 at about 24 decode and 350 prefill, and a 4B Q8 at about 45 decode and 700 prefill, are extrapolated. Qwen3.6-35B-A3B on an M4 Pro via llama.cpp has no measured figure; published estimates for Q4_K_M on an M4 Pro 64 GB range from 27 to 86 tok/s (EXTRACT), so the fallback latencies below use the low end until `llama-bench` on the actual mini replaces them. gpt-oss-120b MXFP4 on an M4 Max 128 GB: about 75 tok/s decode at 1K context, about 30 tok/s at 16K to 32K, 59.5 to 60.5 GB peak (oMLX community rows, EXTRACT).

| Bot | Model job | Calls per day | In / out per call | Open-weight pick (instance, machine) | Proprietary pick | Latency need | Why this way |
|---|---|---|---|---|---|---|---|
| Chart | None in the feature path; optional caption of a feature pack for the live page | 0 to 20 | 2K / 100 | Qwen3.6-35B-A3B Q4, instance B, 64 GB | Haiku 5.5 | minutes | Cosmetic. The report makes Chart a deterministic feature producer; captions are never read back as features |
| Rose | Rationale, candidate list and REJECT log over ranker output; strict tool schema | 80 to 100 | 8K / 600, 6K of it a cacheable preamble | Instance B | Sonnet 5.5 prompt-cached; Haiku 5.5 for 15-minute marks | 60 s per 5-minute loop | Sonnet is $2/$10 with $0.20 cache reads and strict tool schemas. Fallback on B: 2K fresh prefill plus 600 tokens out at 27 tok/s is about 25 to 30 s a call, inside the loop |
| Hal | Premarket, open, close and EOD theses; 15-minute marks while positions are open; X scan every 2 h | about 30 | 12K / 800 on the four big passes; 8K / 600 otherwise | B for marks and X scans; gpt-oss-120b MXFP4, instance C, 128 GB, Phase 2 for big passes | Opus 5.5 for the four big passes; Sonnet 5.5 for the other 26 | big passes 2 min; marks 60 s | A big pass on a weaker model is worse than a skipped pass with a timestamped last-good thesis |
| Research | Bounded autoresearch loop: edits `editable/`, writes study specs, reads results; code review of promotable diffs | 3 to 5 sessions of 20 to 30 turns | 40K to 80K / 1.5K per turn, about 80 percent cacheable | Qwen3-Coder-Next 80B-A3B Q4 (about 48 GB, SWE-bench Verified 70.6, EXTRACT), loaded on C in place of gpt-oss-120b, Phase 2 only | Opus 5.5 for the loop; Fable 5.1 for code review | minutes per turn | No model under 128 GB reaches Opus-class on agentic coding; the GLM-5.2 and Kimi K3 class does not fit any Mac here |
| Data Ops | Hourly feed-health, quota and archive-integrity summary over deterministic checks | 24 | 4K / 300 | Instance B | Haiku 5.5 | 2 min | A summary of numbers Python already computed. This is the work that keeps B warm, so the failover path is exercised every hour |
| X Summarizer | Score 25 to 200 posts from minus 2 to plus 2 with a one-line reason; typed JSON | 25 to 200 items, batched 10 per API call | 1K to 1.5K / 60 to 100 per item | Phase 1: Qwen3.5-9B Q8_0, instance A1, 64 GB, shadow. Phase 2: Qwen3.5-4B Q8_0, instance A2, primary | Haiku 5.5 with `output_config.format` | minutes | About 2 s a post on the 4B; 200 posts is about 7 minutes a day. Below the 4B class is excluded: Gemma 4 E4B scores 57.5 on tau2 against 29.4 for E2B (EXTRACT) |
| Macro | Morning macro pack, econ-calendar card, hourly macro-X scan | 10 to 20 | pack 30K / 2K; scans 6K / 400 | B for scans; C for the pack in Phase 2 | Sonnet 5.5 for the pack and card; Haiku 5.5 for the hourly scan | pack 5 min; scans 2 min | Knowledge recall is weak in 27B to 35B open models (AA-Omniscience, EXTRACT), so macro context must arrive in the prompt whatever the model |
| Peanut/News | Score about 770 Benzinga and X-news items from minus 2 to plus 2 with a reason | 770 items | 1.2K to 1.5K / 60 to 100 | Phase 1: A1 shadow. Phase 2: A2 primary. FinBERT 110M on 8 GB mini 1, CPU | Haiku 5.5, structured output | 30 s per item at the open | FinBERT zero-shot scored 0.64 accuracy on live 2025 headlines (EXTRACT), so no scorer is trusted until the gold set says so; the ranker reads one named column |
| First-Seen | Typed gate flags (earnings, guidance, halt, macro print) with confidence and a verbatim evidence quote; precision floor on a 200-item gold set | about 800 items | 1.5K / 120 to 150 | Qwen3.5-9B Q8_0, instance A1, `json_schema` with enum flags and a quote field, fixed seed, 64 GB; Qwen3.6-27B Q4 (about 17 GB) is the upgrade if the 9B misses the floor | Haiku 5.5 strict structured output; Sonnet 5.5 as the second gold-set judge | 60 s, it feeds the deterministic Event Gate | The highest-stakes classifier. A local 9B is about 9.5 s an item on one slot; a 100-item open burst queues to about 16 minutes, which breaks the SLO. A deterministic pre-filter (universe membership, source type) runs first either way |
| Post-Mortem | Weekly narrative over labelled trades and stats | 1 a week | 100K to 150K / 5K to 8K | gpt-oss-120b on C as an optional draft, Phase 2 | Fable 5.1 via the Batch API | hours | The report reserves the large model for post-mortems; weekly and batchable, so the most capable model costs about $1 a week |
| Owner Mirror | Nightly narrative over deterministic daily stats | 1 a night | 20K / 1.5K, 10K cacheable | B (Phase 1) or C (Phase 2) as fallback | Sonnet 5.5 via the Batch API | overnight | About $0.02 a night; no reason to spend local capacity |
| Gate Keeper | Proposes config diffs with evidence; never applies them | about 1 a week plus ad hoc | 20K to 60K / 1K to 3K | C draft, optional, Phase 2 | Opus 5.5 | hours | A config change is a code change and needs the strongest reviewer short of Fable |
| Earnings/IV | Short narrative beside deterministic IV-crush and expected-move numbers | 5 to 20 | 3K / 300 | Instance B | Haiku 5.5 | 2 min | The numbers are deterministic; the model only phrases them |

Event Gate and Replay/Practice stay model-free. Replay explanations, when enabled, run on B and are labelled commentary, not features.

**Where open weights fall short, stated plainly.** Agentic tool use (the Terminal-Bench gap above). Knowledge recall (AA-Omniscience, EXTRACT). Finance text, where no independent 2025 to 2026 headline benchmark exists for any model, open or proprietary. Batch-invariant decoding, which does not exist on Metal or MLX (VERIFIED absent for vLLM, UNVERIFIED for llama.cpp Metal). And service levels: there is no SLA locally, and the hosted SLAs that exist (Vertex Gemini 99.5 percent, OpenAI Enterprise 99.9 percent) are not for anything this plan uses.

## 3. The models

### Open weights (all Apache-2.0, all GGUF through llama.cpp)

| Instance | Model | Quant and file size | Memory to budget | Role | Notes |
|---|---|---|---|---|---|
| A1 | Qwen3.5-9B (released 2026-03-02, VERIFIED in the QwenLM README; licence Apache-2.0 from the repo LICENSE and HF card extracts) | Q8_0, 9.5 to 9.8 GB (EXTRACT) | 12 to 14 GB with KV cache | Classifier shadow for all three text bots in Phase 1; First-Seen local fallback | Non-MoE hybrid Gated DeltaNet plus full attention, multimodal; tool calling documented (BFCL-V4 66.1, EXTRACT); JSON is enforced by the server grammar, not a model feature |
| A2 | Qwen3.5-4B | Q8_0, about 4.5 GB | 5.5 GB | Peanut/X local primary in Phase 2 | Added when Peanut/X go local-primary and need about 2 s an item at the open |
| B | Qwen3.6-35B-A3B (released 2026-04-16, VERIFIED; 35B total, 3B active; Apache-2.0) | Q4_K_M, about 21 GB (EXTRACT) | 25 to 29 GB with KV | Narrative instance: Rose fallback, Hal marks, Macro scans, Data Ops, Earnings/IV, Chart captions | Emits Qwen3-Coder-style XML tool calls that the engine must parse; llama.cpp has an open regression (#30118, 2026-10-07) where about 9 percent of tool calls leak into content, so pin a build that passes the tool-call test and keep a content-fallback parser. Multi-token prediction (llama.cpp PR #22673, 2026-05-16) adds roughly 10 to 30 percent decode speed |
| B-up | Qwen3.6-27B dense | Q4, about 17 GB | 21 GB | First-Seen upgrade if the 9B misses the precision floor | Slower (about 14 tok/s dense on the M4 Pro, EXTRACT), so fallback-only |
| C | gpt-oss-120b (117B total, 5.1B active, Apache-2.0 plus usage policy) | MXFP4, about 63 GB file; 59.5 to 60.5 GB measured peak at 1K to 32K context (EXTRACT) | 72 GB with a 65K context | Hal big passes, Macro pack, Post-Mortem draft when the API is down, Phase 2 | Native structured outputs. Size the throughput for long-context decode, about 30 tok/s at 16K to 32K, not the 75 tok/s headline at 1K |
| C-alt | Qwen3-Coder-Next 80B-A3B | Q4, about 48 GB | 60 GB | Research loop fallback, Phase 2 | Loaded in place of gpt-oss-120b, one at a time, a few seconds to swap from SSD |

Models deliberately left out: MiniMax M2.7 (non-commercial licence), Devstral 2, Kimi K3 and Llama 4 (conditional licences), anything served from a DeepSeek direct API (PRC residency, no zero-data-retention), and any model under the 4B-effective class.

### Proprietary (Anthropic; prices from the desk's Claude API reference, per million tokens)

| Model | Id to pin | Input / output | Cache read | Batch | Used for |
|---|---|---|---|---|---|
| Fable 5.1 | `claude-fable-5-1` | $10 / $50 | $0.25 (0.025x) | $5 / $25 | Post-Mortem (Batch), code review of promotable diffs |
| Opus 5.5 | `claude-opus-5-5` | $4 / $20 | $0.20 (0.05x) | half | Research loop, Hal big passes, Gate Keeper |
| Sonnet 5.5 | `claude-sonnet-5-5` | $2 / $10 | $0.20 (0.1x) | half | Rose, Hal marks and scans, Macro pack and card, Owner Mirror (Batch), second gold-set judge |
| Haiku 5.5 | `claude-haiku-5-5` | $0.10 / $0.50 at 100K tokens or less; $0.50 / $2.50 above | $0.01 (0.1x); 5-minute cache writes $0.125, 1-hour writes $0.20 | $0.05 / $0.25 | First-Seen, Peanut/News and X Summarizer at launch, hourly Macro scan, every local-instance fallback |

Three API facts that change how the classifier calls are written (from the fact-check): Haiku 5.5 rejects non-default `temperature`, `top_p` and `top_k`, so a classifier is made deterministic with a strict `output_config.format` schema or an enum tool rather than a sampling parameter; Haiku 5.5 has no server-side `fallbacks`, so refusals are handled by the client; and Fable 5.1 takes no sampling parameters at all and returns a 400 on forced `tool_choice`. Prompt caching on Haiku is real and cheap, so a stable system prompt and tool prefix is costed below at $0.01 a million, not $0.10.

## 4. Machine assignment and memory budget

**Wired memory.** macOS lets the GPU wire two thirds of unified memory up to 32 GiB and three quarters above that (a driver constant, not Apple-documented; VERIFIED by the fact-check). That is 49,152 MB on the 64 GB mini and 98,304 MB on the 128 GB Mac. `sudo sysctl iogpu.wired_limit_mb=N` raises it and is lost at reboot unless a LaunchDaemon re-applies it. The first draft budgeted above the default (53,248 and 57,344 MB on the 64 GB mini, 110,000 MB on the 128 GB Mac) and called 85 to 88 percent a safety ceiling; the checker found no source for that ceiling. The one documented kernel panic (mlx-lm issue #883) happened at 83.5 percent wired with the sysctl at its default, because mlx-lm's KV cache grew past the limit mlx-lm sets for itself, since fixed in PR #906. So this plan budgets to the default three quarters and leaves the sysctl alone. Both phases fit.

**Serving stack, all phases.** One `llama-server` per model instance (GGUF, `--jinja`, `response_format` and `json_schema` or GBNF, `--metrics` passed explicitly, `/slots`). Feature-grade instances run `-np 1` explicitly (the default is now auto), `--seed N`, and `--no-cache-prompt`. The narrative instance runs `-np 4 -cb` with the prompt cache on. Everything runs as a LaunchDaemon (`RunAtLoad`, `KeepAlive`, `EnvironmentVariables`), not a LaunchAgent, because the minis are headless (VERIFIED, Apple docs). Ollama's MLX runner is excluded while requests still serialise regardless of `OLLAMA_NUM_PARALLEL` (issue #17280 and PR #17317 open as of 2026-10-21, VERIFIED); `mlx_lm.server` is excluded for schema-bound calls because 0.32.2 and main ignore `response_format` (issue #1007 open, VERIFIED). Move narrative traffic to vllm-mlx only if a measured Rose failover call exceeds 60 seconds.

| Machine | Phase | Wired limit | Model weights | KV and cache | Wired total | What else runs there |
|---|---|---|---|---|---|---|
| 64 GB Mac mini, M4 Pro, 273 GB/s | 1, launch | default 49,152 MB | A1 Qwen3.5-9B Q8_0 about 10 GB (`-np 1 -c 8192`); B Qwen3.6-35B-A3B Q4 about 21 GB (`-np 4 -cb -c 32768`) | A1 3 GB; B 8 GB | about 42 GB | Research sandbox users, `editable/`, the sealed holdout (read-only to the sandbox UID, never on the model daemon's path), the gold-set harness. Research jobs capped at about 12 GB; a `memory_pressure` watchdog stops the lowest-priority job on yellow |
| same | 2, 128 GB online | default 49,152 MB | A1 10 GB; A2 Qwen3.5-4B Q8_0 about 4.5 GB (`-np 1 -c 4096`); B 21 GB with `-c 16384` | A1 3; A2 1; B 5 | about 44.5 GB | Nothing else: the sandbox and the holdout move to the 128 GB Mac. If B needs its 32K context back, drop A1 once A2 has passed the First-Seen gate as well |
| 128 GB Mac, chip unconfirmed | 2 | default 98,304 MB | C gpt-oss-120b MXFP4 about 60 GB measured peak, or Qwen3-Coder-Next Q4 about 48 GB, one at a time | 12 GB (`-c 65536` for EOD and Post-Mortem) | about 72 GB; 93 GB with B's GGUF loaded beside C when the 64 GB mini is down | Research sandbox, `editable/`, the sealed holdout under the same mount rules, study runners, in the roughly 30 GB of non-wired memory |
| 8 GB mini 1 | all | default | FinBERT or a SetFit ModernBERT encoder, 1 GB or less, CPU | none | about 5 GB used | Benzinga and X ingest, dedupe, the FinBERT baseline column, labeler mirror |
| 8 GB mini 2 | all | default | none | none | 4 GB | Data Ops probes, Event Gate, Replay/Practice runner, econ-calendar fetcher |
| 8 GB mini 3 | all | default | Shadow Qwen3.5-4B Q4, about 2.5 GB, `-c 4096` | 0.5 GB | about 7 GB | Gold-set harness, weekly re-run agreement replay, A/B shadow scoring. Expect about 15 tok/s and swap risk (UNVERIFIED). Nothing downstream reads from it |
| 8 GB mini 4 | all | default | none | none | 4 GB | Prometheus scraping every `/metrics`, Grafana, launchd watchdog, cold spare for 1 and 2 |
| Data mini, RAM unknown | all | n/a | none | none | n/a | Alpaca SIP and OPRA collector, archiver, surge engine, ranker, contract selector, risk sentinel, execution gateway, reconciler, live page. Model-free by design |
| Linux box, 8 vCPU, under 6 GiB free | all | n/a | none, it cannot host a model | n/a | n/a | MCP connectors, scheduler, Anthropic API clients, prompt and feature registry, cost meter, secrets |

**Confirm the 8 GB minis' chips before assigning anything to them.** If they are Apple silicon they are M1 (2020, about 68 GB/s) or M2 (2023, 100 GB/s), because 8 GB was the base configuration for only those two generations; the M4 and later minis start at 16 GB. But the Late 2018 Intel mini also shipped with 8 GB, with no useful Metal offload, and on one of those even the shadow 4B runs CPU-only well below 15 tok/s. `sysctl machdep.cpu.brand_string` or About This Mac settles it. On an 8 GB M1 the Metal working-set default is about 5.5 GB (llama.cpp logs `recommendedMaxWorkingSetSize` at 5.46 to 5.73 GB), which is why no 8 GB mini hosts a model the desk depends on.

**Why the 128 GB Mac is "if necessary".** The 64 GB mini alone runs every classifier, Rose, Macro scans, Hal marks, Data Ops and Earnings/IV with about 22 GB of unwired memory left for the sandbox in Phase 1. The bigger box earns its place for two things: anything above the 35B-A3B class (gpt-oss-120b, Coder-Next, Qwen3.5-122B-A10B at about 73 GB 4-bit), and getting pandas jobs off the serving box.

**Daily token arithmetic for the local path (UNVERIFIED extrapolations).** Classifiers: 800 items at 1.6K plus 770 at 1.3K plus 200 at 1.1K is about 2.5M tokens a day; on one 9B Q8 slot that is about 3.7 hours a day serial, fine for shadow, not for a latency SLO, which is why First-Seen stays on Haiku and Phase 2 adds the 4B for Peanut/X. Narrative on B: 150 calls at 8.6K plus 24 at 3.3K plus 20 at 3.5K is about 1.5M tokens, under an hour a day even at the low throughput estimate. The fleet is under 20 percent busy. Prefill, not decode, is the binding constraint on Apple silicon, so the shared preamble is kept short on feature calls (the prompt cache is off there) and items are pre-filtered deterministically before any model sees them.

## 5. Determinism and governance

**Every model output used as a feature is a versioned, scored numeric feature.** A feature call is identified by

`feature_id = sha256(prompt_template || json_schema || tool_defs || model_pin || decode_params || server_pin)`

For API calls `model_pin` is the exact id (`claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-1`, never an alias) plus the `model` string echoed in every response, so a silent server-side change surfaces as a diff. For local calls it is the sha256 of the GGUF file, the quant tag, the llama.cpp build hash, the chip, and the `-c` context size. `decode_params` is `max_tokens` plus, for local calls, `--seed`, `-np 1` and `cache_prompt: false`; for Haiku and Fable it is empty because those models take no sampling parameters.

**What determinism actually buys on this hardware, with the caveats the checker found.** llama.cpp's own README says prompt caching can produce nondeterministic results because logits are not bit-identical across batch sizes, so feature-grade instances run with the prompt cache off and a single slot. Its maintainers say outputs are reproducible only on the same hardware, so a `feature_id` that includes the chip is a different feature on the 128 GB Mac than on the 64 GB mini, and a failover between them is a new column, not the same one. Greedy decoding still drifts with batch composition on default kernels (Thinking Machines measured about 80 distinct completions in 1,000 at temperature zero, EXTRACT), and no batch-invariant mode exists for Metal or MLX, so single-sequence execution is the only lever available on a Mac. Narrative calls on B may batch because they are not features.

**Schema enforcement and tool calling do not combine on one llama-server request.** The server refuses a custom grammar when tools are active ("Cannot use custom grammar constraints with tools") and, when tools are active, the template-generated tool grammar replaces any user `json_schema`. The classifiers therefore send schema-only requests with no tools, and Rose's fallback on B uses tool calling with no grammar, with the tool-call output validated by the client against the same schema the API path uses. One server can serve both kinds of request, just never both constraints on the same call.

**Every row logs** `feature_id`, `source` (api, local, local_fallback, api_fallback), the full rendered prompt, the raw response, `usage`, latency, and for the classifiers the deterministic check that `evidence_quote` is a verbatim substring of the input. API calls use `output_config.format` with a strict schema; local calls use `json_schema` or GBNF, so the schema is enforced regardless of model.

**Re-run agreement is a first-class metric.** A 50-item replay runs weekly on mini 3 (local) and against the API: target at least 0.99 for enum fields and 0.95 for free-text fields. Below the floor the feature is quarantined, not silently drifted. API agreement is measured, not assumed.

**A model swap is a code change.** A new model file, quant, server build, prompt wording, schema field or API id produces a new `feature_id` and enters the same promotion ladder as a commit: shadow for at least 5 trading days producing a parallel column the ranker does not read; gold-set precision at or above the floor and re-run agreement at the floor; a correlation and label-drift report against the incumbent column, reviewed by Opus 5.5 for Gate Keeper proposals; promotion flips the one `feature_version` named in config, with the old column retained 30 days for rollback; the swap is recorded in the config repo with the sha256 and the gold-set report attached. API deprecations follow the same path: the old id stays pinned until the new id passes. Gate Keeper can only propose the diff.

**Gold-set evaluation (First-Seen, Peanut/News, X Summarizer).** One 200-item stratified set per classifier (First-Seen: at least 30 per gate flag plus 60 negatives), labelled by two independent judges (the owner and Sonnet 5.5; disagreements adjudicated by the owner). Stored outside the sealed holdout, readable only by the harness user, never by the research loop. Reported per model: per-flag precision and recall, macro-F1, confidence calibration (expected calibration error in 5 bins), evidence-quote validity, re-run agreement, and p95 latency at the open. Floors: First-Seen per-flag precision at least 0.95, highest on `halt` and `earnings` because they feed Event Gate; Peanut/X macro-F1 at least 0.70 and no worse than FinBERT on the same set. Refresh 40 items a quarter from live traffic, keeping the old 200 as a regression set. This applies to Haiku 5.5 too: it is the launch primary because it is the small fast model in the reference, not because it is assumed to pass. Published benchmarks shortlist only; FinBERT's 0.64 on live headlines is the cautionary number.

## 6. Cost

**Proprietary path, monthly.** 22 trading days for market-hours bots, 30 days for nightly and all-day bots. Cache reads at the per-model rate above; the stable system prompt and schema prefix on every classifier call is modelled as a cached read. The Batch API (half price) applies to Post-Mortem and Owner Mirror.

| Bot | Model | Per-call arithmetic | $ a day | $ a month, Phase 1 | $ a month, Phase 2 |
|---|---|---|---|---|---|
| Rose | Sonnet 5.5 | 100 calls at (2K fresh at $2, 6K cached at $0.20, 600 out at $10) a million = $0.0112 | 1.12 | 24.6 | 24.6 |
| Hal | Opus 5.5 for 4 (3K fresh, 9K cached, 800 out = $0.030) plus Sonnet for 26 ($0.0112) | | 0.41 | 9.0 | 9.0 |
| Macro | Sonnet 5.5 | 15 scans at $0.0098 plus one pack (30K / 2K uncached, about $0.08) | 0.23 | 5.0 | 5.0 |
| First-Seen | Haiku 5.5 | 800 at (1.2K cached at $0.01, 300 fresh at $0.10, 150 out at $0.50) a million = $0.000117 | 0.09 | 2.1 | 2.1 |
| Peanut/News | Haiku 5.5 | 770 at $0.000117 | 0.09 | 2.0 | about 0 (local primary; Haiku fallback budget under $1) |
| X Summarizer | Haiku 5.5 | 200 at (1.2K cached, 300 fresh, 100 out) = $0.000092 | 0.02 | 0.4 | about 0 |
| Data Ops, Earnings/IV, Chart | Haiku 5.5 fallback only | upper bound, 45 calls at (3K, 300) | 0.02 | under 0.6 | under 0.6 |
| Research | Opus 5.5 | per turn: 10K fresh at $4, 40K cached at $0.20, 1.5K out at $20 = $0.078; 50 to 150 turns a day | 3.9 to 11.7 | 86 to 257 | 86 to 257 |
| Post-Mortem | Fable 5.1, Batch | (150K at $10 plus 8K at $50) a million = $1.90, $0.95 batched, weekly | | 4.1 | 4.1 |
| Code review | Fable 5.1 | about 10 a month at (40K at $10 plus 3K at $50) a million = $0.55 | | 5.5 | 5.5 |
| Owner Mirror | Sonnet 5.5, Batch | (10K fresh, 10K cached, 1.5K out) = $0.037, $0.019 batched | 0.02 | 0.6 | 0.6 |
| Gate Keeper | Opus 5.5 | 60K at $4 plus 3K at $20 = $0.30 a proposal; one a week to three a day | | 1.3 to 9.0 | 1.3 to 9.0 |
| Gold-set judging | Sonnet 5.5 | weekly, 200 items, 3 scorers | | about 1 | about 1 |
| Total | | | | about $140 to $320 | about $135 to $315 |

Research is 60 to 80 percent of the bill and is the number to measure first: the cost meter on the Linux box logs `usage` per call, per bot and per `feature_id` from day one, and the first month's figure replaces the range above. Sensitivity: one research session a day brings the total to about $90 to $120; moving Rose wholesale to Opus 5.5 adds about $22. The classifier tier costs $0.02 to $0.10 a day per bot on any vendor, so classifier choice is made on gold-set precision, structured-output strictness and data posture, never price.

**Local path, running cost (UNVERIFIED; no power measurements).** The 64 GB mini at about 40 W average with models resident at roughly 15 percent duty is about 29 kWh a month; the 128 GB Mac at about 60 W is 43 kWh; four 8 GB minis at about 8 W each are 23 kWh; roughly 95 kWh or $15 to $25 a month at typical US rates. All machines are owned; the only new spend is about 100 GB of SSD for GGUF files and the owner's time for the LaunchDaemons, the gold-set harness and the cost meter. The local path's real cost is quality and determinism risk, not dollars.

## 7. Fallback matrix

| Failure | Detection | Classifiers (First-Seen, Peanut, X) | Narrative (Rose, Hal, Macro, Data Ops, Earnings/IV) | Research, Post-Mortem, Gate Keeper | Order path |
|---|---|---|---|---|---|
| A1, A2 or B process dies | launchd `KeepAlive` restart count; `/metrics` scrape gap over 60 s | Phase 1: no impact, Haiku is primary; the shadow column logs `missing`. Phase 2: Peanut/X route the same JSON schema to Haiku after 5 min, rows tagged `source=api_fallback` and excluded from agreement stats | Data Ops and Earnings/IV route to Haiku; Rose, Hal and Macro unaffected | none | unaffected |
| 64 GB mini offline | ping and `/v1/models` fail | all three on Haiku | Phase 2: the 128 GB Mac loads B's GGUF beside gpt-oss-120b (60 plus 21 GB plus KV fits under the 96 GB default) and serves B. Phase 1: the local standby is gone; Rose and Macro run API-only | Phase 1: the sandbox is down too, research pauses | unaffected |
| 128 GB Mac offline, Phase 2 | same | none | Hal big passes and the Macro pack fall back to B at reduced quality, `quality=degraded` | Post-Mortem goes straight to Fable; research loop API-only | unaffected |
| Anthropic API outage (5xx or a 30 s timeout on 3 consecutive calls) | health probe every 60 s from the Linux box | First-Seen fails over to A1 only for feature ids that passed the gold-set gate, tagged `source=local_fallback` so the ranker can down-weight; Peanut/X already local in Phase 2 | Rose, Macro and Hal marks run on B with `degraded=true`; Hal big passes skipped (Phase 1) or run on C (Phase 2); the live page shows the last good rationale with its timestamp | research pauses (Phase 1) or runs Coder-Next on C flagged lower quality (Phase 2); Post-Mortem and Owner Mirror wait, they are already Batch | unaffected by design |
| Anthropic 429 rate limit | response headers, 429 count a minute | exponential backoff with jitter; batch 20 items a call instead of 10; if the backlog passes 15 min, the same local failover | Rose skips a 5-minute slot rather than queueing (a stale rationale is worse than none); Hal marks retry once | research turns queue; back-fill moves to Batch | unaffected |
| Memory pressure yellow or red on a Mac | `memory_pressure` poll every 30 s | stop A2 first, then shrink B's context; never raise the wired limit to make room | same | the research job is killed before any model daemon | unaffected |
| Both local and API down | both probes fail | model features emit NULL with `reason=unavailable`; Event Gate runs on deterministic inputs only (filings feed, halt feed) | no narrative | paused | unaffected |
| Gold-set precision or agreement below floor on the weekly check | harness report | the feature is quarantined automatically; the previous passing `feature_id` is restored; the Haiku column is promoted if it passes; alert | n/a | Gate Keeper proposes the fix | unaffected |
| Prolonged Anthropic outage, over a trading day | manual | a pre-qualified cross-vendor route (OpenRouter with zero-data-retention routing and the data-policy filter, 5.5 percent fee) over GPT-5.4 mini or Gemini 3.5 Flash-Lite (EXTRACT). This is a new `feature_id`, so one alternative is pre-qualified in shadow now or it is not usable then | same | not used | unaffected |

## 8. What not to do

1. **No model in the order path.** Surge engine, ranker, contract selector, sizing, exits, risk sentinel, gateway and reconciler consume logged, versioned feature columns and configs only. A First-Seen flag is an input to the deterministic Event Gate, never an order trigger. An outage changes feature values, never order logic.
2. **No 8 GB mini hosts a model the desk depends on.** Usable model plus KV on them is about 5 to 6 GB with swap risk; Gemma 4 E4B under Ollama already needs 7 to 8 GB on a 16 GB mini (EXTRACT). Minis 1 to 4 run deterministic Python, the encoder of 1 GB or less, monitoring, and the shadow 4B that nothing reads.
3. **No model without a measured precision on the gold set**, Haiku 5.5 included.
4. **No unpinned ids, no sampling above greedy where the API allows it, no shared-batch decoding, no prompt cache on feature calls, no prompt edits outside the promotion ladder.** A call that cannot be reproduced is not a feature.
5. **No schema grammar and tool calling on the same llama-server request.** They are mutually exclusive; the plan splits them by call type.
6. **No Ollama MLX runner or `mlx_lm.server` for schema-bound or concurrent calls** while the cited issues stay open; nothing exposed beyond localhost.
7. **No research-loop model reading the sealed holdout.** The sandbox UID cannot read the holdout directory; the model edits only `editable/`; when the sandbox moves to the 128 GB Mac the holdout moves with it under the same mount rules; gold sets live outside it.
8. **No 100B-class local model on the 64 GB mini, and no wired limit above the macOS default** until a measured reason exists. gpt-oss-120b peaks at about 60 GB and leaves no KV headroom there.
9. **No cost decisions on the classifier tier.** Spend the attention on the research loop's turn count.
10. **No DeepSeek direct API for anything carrying desk data, no reliance on Gemini Flash intro pricing past 2026-12-31, no OpenAI or Mistral fine-tuning (both winding down).** If a classifier needs tuning, use local `mlx_lm.lora` or SetFit on the 64 GB mini.
11. **No non-commercial or unrecorded-condition licences in the fleet.** Every model named above is Apache-2.0. MiniMax M2.7, Devstral 2, Kimi K3 and Llama 4 stay out unless their conditions are recorded in the config repo.

## 9. First-week checklist

Measurements that replace the UNVERIFIED numbers above, in the order they unblock decisions.

1. `sysctl machdep.cpu.brand_string` on each 8 GB mini, and About This Mac on the 128 GB Mac. Decides whether mini 3 can host the shadow 4B at all.
2. `sysctl iogpu.wired_limit_mb` on the 64 GB mini, to confirm the 49,152 MB default before any daemon starts.
3. `llama-bench -p 2048 -n 300` for Qwen3.5-9B Q8_0 and Qwen3.6-35B-A3B Q4_K_M on the 64 GB mini, with and without multi-token prediction. Replaces the 24 and 27 to 86 tok/s figures and sets the real Rose failover latency.
4. A 100-request tool-call test against B on the pinned llama.cpp build, counting tool calls that leak into content. Pins the build or adds the fallback parser before Rose's failover is enabled.
5. A 50-item re-run agreement test on A1 with the prompt cache off and on, and across two chips if the 128 GB Mac is available. Confirms the determinism settings and whether failover between machines must be a new column.
6. The cost meter on the Linux box, logging `usage` per call before the first research session. Replaces the $86 to $257 research range with a measured number inside a week.
7. A plug-in power meter on the 64 GB mini for one trading day. Replaces the $15 to $25 estimate.
8. The three 200-item gold sets, built and double-judged, before any classifier column is promoted out of shadow, Haiku included.

## 10. How this fits the main report

The report's section 5 rule stands: a small fast model for classification routines, a large model only for research, post-mortems and code review, every agent output used as a feature at greedy decoding, versioned by prompt hash, logged and scored like any numeric feature, and a 200-item gold set with a precision floor before any agent flag may reduce exposure. This plan names the models, puts each on a machine, prices the API side with the actual cache rates, and adds the three things the research turned up that the report did not say: schema enforcement and tool calling do not combine on one local request; local determinism is best effort, same-hardware only, with the prompt cache off; and the 8 GB minis need their chips confirmed before anything is assigned to them.

## 11. Verification notes

Eight claims from the first draft went to independent checkers on 2026-10-21. Four held, four were corrected, and the corrections are applied above.

| Claim | Verdict | What changed |
|---|---|---|
| Qwen3.5-9B: 2026-03-02 release, Apache-2.0, dense about 9B, about 10 GB at Q8_0 | Held, confidence 0.8 | Budget 12 to 14 GB with KV, not 10; "dense" means non-MoE (hybrid Gated DeltaNet plus attention, multimodal); JSON comes from the server grammar, not a documented model feature |
| Qwen3.6-35B-A3B: 2026-04-16, Apache-2.0, 35B/3B, about 21 GB at 4-bit, native tool parser, about 50 tok/s on an M4 Pro | Corrected, confidence 0.72 | Tool-call parsing is engine-side, with an open llama.cpp regression (#30118); no measured M4 Pro throughput exists, estimates run 27 to 86 tok/s, so the plan uses the low end until `llama-bench` says otherwise |
| llama-server supports schema JSON, continuous batching, `--jinja` tools, `--seed`, prompt cache and `/metrics` together with nothing disabled at `-np 1` | Corrected, confidence 0.8 | Grammar and tools are mutually exclusive per request; prompt caching is documented as a source of nondeterminism; determinism holds only on identical hardware; `-np 1` and `--metrics` must be explicit |
| Haiku 5.5 at $0.10/$0.50 up to 100K tokens, strict structured outputs, no cache credit | Corrected, confidence 0.92 | Cache reads are $0.01 a million (writes $0.125 for 5 minutes, $0.20 for 1 hour); a second rate card applies above 100K tokens; Haiku rejects non-default sampling parameters and has no server-side fallbacks |
| gpt-oss-120b on an M4 Max 128 GB: about 75 tok/s, 650 tok/s prefill, 59.5 to 63 GB peak, fits beside a 21 GB GGUF under a 110 GB wired limit | Held with conditions, confidence 0.6 | 75 tok/s only at 1K context, about 30 tok/s at 16K to 32K; 59.5 to 60.5 GB measured peak, 63 GB is the file size; the plan fits under the 96 GB default, so no non-default limit is needed |
| The 8 GB minis are M1 or M2 class with 5 to 6 GB usable | Corrected, confidence 0.6 | A Late 2018 Intel mini also shipped with 8 GB; confirm the chip first; the 5 to 6 GB figure is the Metal working-set default on an 8 GB M1 |
| Ollama's MLX runner serialises requests; `mlx_lm.server` has no `response_format` | Held, confidence 0.93 | Still true as of 2026-10-21 (Ollama #17280 and PR #17317 open; mlx-lm 0.32.2 and main, issue #1007 open) |
| macOS default wireable share is two thirds to three quarters; the sysctl does not persist; above 85 to 88 percent risks the #883 panic | Corrected, confidence 0.7 | The default (two thirds up to 32 GiB, three quarters above) and non-persistence hold; the 85 to 88 percent ceiling has no source; #883 was at the default limit and is fixed; the plan budgets to the default |

Sources are listed in `strategy-2026-10-21/model-plan-sources.md`.
