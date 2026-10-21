# OID per-bot model plan (local-first), 2026-10-21

Hardware note before anything else: Research 2 flags that the current M4 Mac mini starts at 16 GB, so the four "8 GB" minis are most likely M1/M2-class (~68–100 GB/s), not base M4. Every 8 GB number below assumes the slower chip. UNVERIFIED until you read `sysctl machdep.cpu.brand_string` on one of them.

## 1. Per-bot plan

Serving stack (Research 2): **llama-server** (GGUF, `--jinja`, `json_schema`/GBNF, `--temp 0 --seed N -np 1`) for every feature-grade call; **mlx_lm.server** or **vllm-mlx** (continuous batching, prefix cache; vllm-mlx adds lm-format-enforcer schemas) for narrative traffic; **not** Ollama's MLX runner while issues #17280/#17317 stay open. Four resident instances:

- **A1** (64 GB, llama-server, `-np 1`): Qwen3.5-9B Q8_0 (~10 GB) — First-Seen.
- **A2** (64 GB, llama-server, `-np 1`): Qwen3.5-4B Q8_0 (~4.5 GB) — Peanut/News, X Summarizer, Chart feature text.
- **B** (64 GB, mlx_lm.server `--decode-concurrency 8`): Qwen3.6-35B-A3B 4-bit (~21 GB) — Rose, Macro, Hal intraday, Data Ops, Earnings/IV, Gate Keeper drafts.
- **C** (128 GB, vllm-mlx or llama-server): gpt-oss-120b MXFP4 (~60 GB peak, 75 tok/s measured on M4 Max 128 GB) — Hal open/close/EOD, Owner Mirror, Post-Mortem draft, open-weight research fallback (swapped for Qwen3-Coder-Next 80B-A3B 4-bit when the research loop needs it; the two do not co-reside).

Throughput inputs (Research 1 and 2): dense 27B 4-bit on M4 Pro 64 GB 13.8–15.4 tok/s decode, ~118 tok/s prefill; 30B-A3B MoE on M4 Pro ≈ 52 tok/s (llama.cpp), prefill assumed ≈ 650 tok/s (half of the M4 Max 1,300 figure, UNVERIFIED scaling); gpt-oss-120b on M4 Max 128 GB 75 tok/s decode, 650 tok/s prefill; Llama-2 7B Q8 on M4 Pro 30.7 tok/s decode / 450 prefill, so a 9B Q8 ≈ 24 / ~350 and a 4B Q8 ≈ 45 / ~700 (UNVERIFIED extrapolation).

| Bot | LLM job | Calls/day | Context/call (in/out) | Open-weight model, quant, instance | Proprietary | Machine | Latency need | Why |
|---|---|---|---|---|---|---|---|---|
| Chart | None in the feature path (deterministic producer). Optional nightly one-paragraph description of each feature family for the Owner Mirror | 0–5 | 4K / 300 | Qwen3.5-4B Q8 (A2), temp 0, GBNF | Haiku 5.5 | 64 GB | hours | Narration only; the numbers come from Python. Keeping Chart LLM-free is the report's intent |
| Rose | Rationale, candidate list, REJECT log every 5 min; tool calls read features only | 80–100 | 8K / 600 (6K shared preamble cached) | Qwen3.6-35B-A3B 4-bit MLX (B); native tool parser; `seed` set so it runs single-sequence | Sonnet 5.5 | 64 GB | < 60 s | 2K fresh prefill ≈ 3 s + 600 tok ≈ 11 s ≈ **14 s/call**, 100 calls ≈ 23 min of server time per day. SWE-bench V 73.4 and structured-output support (EXTRACT); dense 27B at 45–60 s per call is the quality upgrade if the loop tolerates it |
| Hal | Premarket brief, open/close passes, 15-min marks when positions open, EOD review, X scan every 2 h | ~30 | marks 8K / 600; EOD 30K / 1.5K | Intraday marks: Qwen3.6-35B-A3B (B). Open/close/EOD: gpt-oss-120b MXFP4 (C), native Structured Outputs, Apache-2.0 | Opus 5.5 for open/close/EOD, Sonnet 5.5 for marks | 64 GB + 128 GB | marks < 60 s; EOD < 5 min | gpt-oss-120b EOD: 30K/650 ≈ 46 s + 1.5K/75 ≈ 20 s ≈ **66 s**. Longer-horizon reasoning benefits from the 100B class; this is one of two places the 128 GB Mac is actually needed |
| Research | Autoresearch loop: writes feature code and study specs in `editable/`, reviews results | 3–5 sessions, 10–20 turns each | 40K / 4K per turn (mostly cached) | Fallback only: Qwen3-Coder-Next 80B-A3B 4-bit (~48 GB, SWE-bench V 70.6) loaded on C in place of gpt-oss-120b; Qwen3.6-27B 4-bit on B's slot as last resort | **Opus 5.5** (default for coding/agentic work); Fable 5.1 for code review | 128 GB sandbox; model via API | minutes per turn OK | The report reserves the large model for research; open coders that match Opus-class (GLM-5.2, Kimi K3) do not fit any Mac here. Local fallback keeps the loop alive during an API outage at lower quality |
| Data Ops | Hourly feed-health, quota and archive-integrity summary from deterministic checks | 24 | 3K / 300 | Qwen3.6-35B-A3B (B), temp 0 | Haiku 5.5 | 64 GB | < 2 min | Trivial load (≈ 8 s/call). Summary is advisory; alerts themselves are Python thresholds |
| X Summarizer | Score 25–200 posts -2..+2 with a one-line reason | 25–200 | 1K / 60 | Qwen3.5-4B Q8 (A2), GBNF enum {-2..2}, temp 0, seed | Haiku 5.5 | 64 GB | minutes | ≈ 2 s/post, 200 posts ≈ 7 min/day. Shadow copy of the same model on an 8 GB mini for A/B only |
| Macro | Morning macro pack, econ-calendar card, hourly macro-X scan | 10–20 | scans 6K / 400; morning pack 30K / 2K | Scans: Qwen3.6-35B-A3B (B). Morning pack: gpt-oss-120b (C) if present, else B | Sonnet 5.5 | 64 GB (+128 GB) | pack < 5 min; scans < 2 min | Pack on C ≈ 46 s prefill + 27 s decode; on B ≈ 2.5 min. Both fine |
| Peanut/News | Score ~770 wire + X-news items -2..+2 with reason | 770 | 1.2K / 60 | Keep **FinBERT as the baseline feature** (110M, CPU). Add Qwen3.5-4B Q8 (A2) GBNF score as a second feature; ranker chooses | Haiku 5.5 | 64 GB (FinBERT on an 8 GB mini with the labeler) | < 30 s per item at open | ≈ 2 s/item, 770 ≈ 26 min/day. FinBERT zero-shot on live 2025 headlines scored only 0.64 acc (EXTRACT), so neither source is trusted until the gold set says so |
| First-Seen | Typed gate flags (earnings, guidance, halt, macro print) + confidence + evidence quote | ~800 | 1.5K / 120 | Qwen3.5-9B Q8_0 (A1), `json_schema` with enum flags and quote field; temp 0, seed; Qwen3.6-27B 4-bit as arbiter when confidence < threshold (loaded on demand, UNVERIFIED fit alongside B) | **Haiku 5.5** with `output_config.format` as gold-set judge and hot fallback | 64 GB | < 20 s per item; burst at open | ≈ 4.3 s prefill + 5 s decode ≈ **9.5 s/item**, 800 ≈ 2.1 h/day serial; 100 items in 10 min at the open queue to ~16 min, so a deterministic pre-filter (universe membership, source type) must run first. Gemma 4 E4B τ2 57.5 vs E2B 29.4 (EXTRACT) is why nothing under 4B-effective is used here |
| Post-Mortem | Weekly narrative over the week's labeled trades and stats | 1/week (+ 2 code reviews) | 100K / 5K | gpt-oss-120b (C) draft | **Fable 5.1** (final) or Opus 5.5 | 128 GB + API | hours | The report puts post-mortems on the large model. 100K prefill on C ≈ 2.5 min; local draft, hosted final |
| Owner Mirror | Nightly narrative over deterministic daily stats | 1 | 20K / 1.5K | gpt-oss-120b (C); Qwen3.6-35B-A3B (B) if C absent | Sonnet 5.5 via Batch API | 128 GB | overnight | Batch halves cost; no latency need, so local is free and fine |
| Gate Keeper | Proposes config changes (thresholds, allow-lists) with evidence; never applies them | 1–5 | 20K / 1K | gpt-oss-120b (C) draft; Qwen3.8-27B 4-bit (Terminal-Bench 2.1 73.0) if you want a dense model | **Opus 5.5** reviews before the proposal enters the promotion ladder | 128 GB + API | hours | A config change is a code change; proposals go through the same gate as model swaps (section 4) |
| Earnings/IV | Small narrative next to deterministic IV-crush and expected-move numbers | 5–20 (earnings weeks) | 3K / 300 | Qwen3.6-35B-A3B (B), temp 0 | Haiku 5.5 | 64 GB | < 2 min | Numbers are deterministic; the LLM only phrases them |

Event Gate and Replay/Practice stay LLM-free; Replay explanations, when enabled, use B at temp 0 and are labeled as commentary, not features.

**Where open weights fall short (say it plainly).** (1) Tool use and long-horizon agentic work: the largest comparable number in the sheets is Terminal-Bench 2.1, where Qwen3.8-27B scores 73.0 and GLM-5.2 81.0 versus Claude Opus 4.8 85.0 (VERIFIED in the GLM README); nothing that fits a Mac matches hosted frontier on this, which is why Research and Gate Keeper review stay on Opus. (2) Knowledge recall: AA notes Qwen3.5-27B and Gemma 4 31B are weak on AA-Omniscience (EXTRACT), so macro context must come from the prompt, not the model. (3) Finance text: no 2025–2026 independent headline benchmark exists for any model; the only live-headline study gives FinBERT 0.64 accuracy, and FinGPT/phi-3 LoRA numbers are self-reported on FPB. (4) Determinism: no batch-invariant kernels on Metal/MLX (VERIFIED absence for vLLM; UNVERIFIED for others). (5) No SLA on anything local, and only Vertex (99.5%) and OpenAI Enterprise (99.9%) offer one hosted.

## 2. Machine assignment and memory budget

All usable-memory and wired-limit figures are UNVERIFIED planning numbers from Research 1/2; apply `sysctl iogpu.wired_limit_mb` from a LaunchDaemon and keep wired < 88% of RAM (the mlx-lm #883 panic occurred at 83.5% wired with 0 GB free).

| Machine | Wired limit | OS + services reserve | Model weights | KV / prompt cache | Total | What else runs there |
|---|---|---|---|---|---|---|
| **64 GB Mac mini M4 Pro** ("LLM mini") | 56 GB (57,344 MB) | 8 GB (macOS, Python agents, MCP shim, log shipper) | A1 Qwen3.5-9B Q8 10 GB; A2 Qwen3.5-4B Q8 4.5 GB; B Qwen3.6-35B-A3B 4-bit 21 GB = **35.5 GB** | A1 `-c 8192` 2 GB; A2 `-c 4096` 1 GB; B `--prompt-cache-bytes 8G` + 8-way decode ≈ 10 GB = **13 GB** | **56.5 GB** | Nothing else. The research sandbox and sealed holdout move to the 128 GB Mac; if the 128 GB Mac is not deployed, drop A1 to the 4B (saves 7 GB) and cap research jobs at the remaining ~10 GB |
| **128 GB Mac (M4 Max class)** ("research Mac") | 110 GB | 10 GB | C gpt-oss-120b MXFP4 ≈ 60 GB peak **or** Qwen3-Coder-Next 80B-A3B 4-bit 48 GB (LRU, one at a time) | 12 GB (`-c 65536` for EOD/Post-Mortem) | 82 GB | Research sandbox users, `editable/`, sealed holdout directory (never mounted on the LLM server's user), study runners (reserve 25 GB), weekly Post-Mortem job. Total ≈ 107 GB |
| **8 GB mini #1** | default | 4 GB | FinBERT/SetFit encoder ≤ 1 GB (CPU) | — | 5 GB | Labeler and archive-integrity checks (if not already on the data mini), Peanut baseline scorer |
| **8 GB mini #2** | default | 4 GB | none | — | 4 GB | Data Ops probes, Event Gate, Replay/Practice runner, econ-calendar fetcher |
| **8 GB mini #3** | default | 4 GB | Shadow Qwen3.5-4B Q4 2.5 GB, `-c 4096` 0.5 GB | 0.5 GB | 7 GB | Gold-set harness, A/B shadow scoring, re-run agreement checks. Expect ~15 tok/s and swap risk (UNVERIFIED); nothing depends on it |
| **8 GB mini #4** | default | 4 GB | none | — | 4 GB | Prometheus scraping llama-server `/metrics`, Grafana, launchd watchdog, cold spare for #1/#2 |
| **Data mini** (RAM unknown) | — | all | **none** | — | — | Collector, SIP/OPRA streams, archiver, surge engine, ranker, contract selector, risk sentinel, execution gateway, reconciler, live page. LLM-free by design |
| **Linux box** (8 vCPU, 0.8–5.4 GiB free) | n/a | — | none | — | — | MCP connectors, scheduler, API clients, secrets; cannot host a model |

Where the 128 GB Mac is needed: (a) to host anything above the 35B-A3B class (gpt-oss-120b, Qwen3.5-122B-A10B, Coder-Next at 8-bit) and (b) to get the research sandbox off the serving box so the 64 GB mini's memory is not shared with pandas jobs. Where the 64 GB mini suffices: every classifier, Rose, Macro scans, Hal intraday marks, Data Ops, Earnings/IV, X Summarizer. If you never buy the 128 GB Mac, the desk still works: Hal EOD, Owner Mirror and Gate Keeper drafts run on B at lower quality, and research fallback is Qwen3.6-27B at 4-bit on the 64 GB mini only when B is stopped.

Daily token arithmetic across the fleet (local path): classifiers ≈ 800×1.6K + 770×1.3K + 200×1.1K ≈ 2.5M tokens/day on A1/A2 ≈ 2.8 h of single-slot time; narrative ≈ 150×8.6K + 24×3.3K + 20×3.5K ≈ 1.5M tokens/day on B ≈ 40 min; C ≈ 15 calls × 10–30K ≈ 0.4M tokens ≈ 20 min. The fleet is under 15% busy; prefill, not decode, is the binding constraint on Apple silicon, so cache the shared preamble and pre-filter items deterministically.

## 3. Cost

**Proprietary path, Anthropic prices as given (30-day month).** Assumptions: Rose/Hal/Macro calls are 8K in / 600 out with 75% of input served from cache at $0.20/MTok; classifier calls 1.5K in / 150 out with no cache credit (the $0.20 cache-read price cannot apply at Haiku's $0.10 input, so Haiku is an upper bound); research turns 40K in / 4K out.

| Bot | Model | Calc | $/month |
|---|---|---|---|
| First-Seen | Haiku 5.5 | 800/day × (1.5K×$0.10 + 150×$0.50)/M = $0.18/day | 5.4 |
| Peanut/News | Haiku 5.5 | 770/day × same | 5.2 |
| X Summarizer | Haiku 5.5 | 200/day × (1K in, 60 out) | 0.8 |
| Data Ops + Earnings/IV + Chart | Haiku 5.5 | ~45/day × (3K in, 300 out) | 0.6 |
| Rose | Sonnet 5.5 | 100/day × (6K×$0.20 + 2K×$2 + 600×$10)/M = $1.12/day | 33.6 |
| Hal | Opus 5.5 | 30/day × (6K×$0.20 + 2K×$4 + 600×$20)/M = $0.64/day | 19.1 |
| Macro | Sonnet 5.5 | 15 scans × $0.0112 + 1 pack (30K/2K uncached $0.08) | 7.5 |
| Research | Opus 5.5 | single-shot: 5/day × $0.24 = $36; agentic: 5 sessions × 20 turns × (36K cached + 4K fresh + 1K out ≈ $0.043) = $4.30/day | 36–130 |
| Post-Mortem + 2 code reviews/week | Fable 5.1 | (100K×$10 + 5K×$50)/M = $1.25 + 2×(40K×$10 + 3K×$50)/M = $1.10 per week | 10.2 |
| Owner Mirror | Sonnet 5.5 Batch | (20K×$2 + 1.5K×$10)/M × 0.5 = $0.0275/day | 0.8 |
| Gate Keeper | Opus 5.5 | 3/day × (20K×$4 + 1K×$20)/M = $0.30/day | 9.0 |
| **Total all-proprietary** | | | **≈ $130–$225** |

**Local-first path** keeps only Research (Opus), Post-Mortem and code review (Fable), Gate Keeper review (Opus) and a Haiku gold-set judge (200 items/week, < $0.10) on the API: **≈ $55–$150/month**, dominated by the research loop's turn count, which the report lists as the unmeasured run rate. Batch API halves every non-latency-bound item (Owner Mirror, Post-Mortem, back-fill labeling).

**Local path, running cost (UNVERIFIED; no power measurements in the research sheets).** Assume the 64 GB mini averages 40 W with models resident and ~15% duty (≈ 29 kWh/month), the 128 GB Mac 60 W (≈ 43 kWh), four 8 GB minis 8 W each (≈ 23 kWh): ≈ 95 kWh/month ≈ $15–$25 at typical US rates. One-time: all machines are already owned; the only new spend is SSD space for GGUF/MLX files (~100 GB) and owner time to build the LaunchDaemons and the gold-set harness. The local path's real cost is quality and determinism risk, not dollars.

## 4. Determinism and governance

**Every LLM feature row** carries: `model_id` (local: file name + sha256 of the GGUF/safetensors + quant + server binary version + `-c` context size; API: the exact pinned id such as `claude-haiku-5-5`, never an alias, plus the `model` field echoed in the response), `prompt_hash` (sha256 of rendered system + user template + schema + tool definitions), `temperature=0`, `seed`, `source` (local/api), `latency_ms`, `tokens_in/out`, and the full raw output. Prompt hash and model hash together form the `feature_version`; any change bumps it and the feature is re-scored from scratch, exactly like a numeric feature with a new formula.

**Making local calls reproducible.** Research 2 shows greedy decoding still drifts with batch composition (Thinking Machines: ~80 distinct completions of 1,000 at temp 0 on default kernels; EXTRACT) and no batch-invariant mode exists for Metal or MLX. So feature-grade instances run single-sequence: llama-server `-np 1 --temp 0 --seed N`; on mlx_lm.server send `seed` (VERIFIED: routes to `_serve_single`). Narrative calls on B may batch because they are not features. Each feature declares a **re-run agreement metric** (fraction of identical outputs over a 50-item replay, run weekly on mini #3) and a floor (99% for enum scores, 95% for free-text fields); below floor the feature is quarantined.

**Model swap = code change.** A new model file, quant, server version, prompt or API id enters the same promotion ladder as a code commit: (1) shadow run on mini #3 or the API for ≥ 5 trading days producing a parallel feature column; (2) gold-set precision at or above floor and re-run agreement at floor; (3) correlation and label-drift report against the incumbent column; (4) promotion flips the `feature_version` the ranker reads, with the old column retained for 30 days for rollback; (5) the swap is recorded in the config repo with the sha256 and the gold-set report attached. Gate Keeper proposals follow the identical path with Opus review at step 3.

**Gold-set evaluation for classifiers (First-Seen, Peanut/News, X Summarizer).** A 200-item stratified set per classifier (First-Seen: ≥ 30 per gate flag plus 60 negatives) is labeled by two independent judges (owner plus Haiku 5.5 at temp 0, disagreements adjudicated by the owner; the Pugnola dual-judge template, UNVERIFIED) and stored in the sealed directory, readable only by the harness user, never by the research loop. Reported per model: per-class precision and recall, confidence calibration (ECE in 5 bins), and the deterministic check that every `evidence_quote` is a verbatim substring of the input. Floors: First-Seen per-flag precision ≥ 0.95 (gate flags feed the deterministic Event Gate); Peanut/X macro-F1 ≥ 0.70 and no worse than FinBERT on the same set. Refresh 40 items per quarter from live traffic, keeping the old 200 as a regression set. No precision, no promotion.

## 5. Fallback matrix

| Failure | Detection | Action | Feature marking |
|---|---|---|---|
| A1/A2/B process dies | launchd `KeepAlive` restart; `/metrics` scrape gap > 60 s | Auto-restart; if down > 5 min, the client routes the same JSON schema to Haiku 5.5 (classifiers) or Sonnet 5.5 (narrative) | `source=api_fallback`, feature_version suffixed; rows excluded from re-run agreement stats |
| 64 GB mini offline | Ping + `/v1/models` fail | 128 GB Mac loads Qwen3.6-35B-A3B 4-bit alongside gpt-oss-120b (21 + 60 + KV fits 110 GB) and serves B; classifiers go to Haiku | as above |
| 128 GB Mac offline | same | Hal EOD, Macro pack, Owner Mirror, Gate Keeper drafts run on B at reduced quality; Post-Mortem goes straight to Fable; research loop uses Opus only | `quality=degraded` flag in narrative header |
| Memory pressure yellow/red on a Mac | `memory_pressure` poll every 30 s | Stop lowest-priority instance (A2 first, then C), shrink `--prompt-cache-bytes`; never let wired exceed 88% | — |
| Anthropic API outage | 5xx or timeout > 30 s on 3 consecutive calls | Classifiers already local; narrative already local; research loop pauses (no destructive fallback); Post-Mortem waits | — |
| Anthropic rate limit (429) | header-driven backoff | Exponential backoff with jitter; Owner Mirror and back-fill move to Batch API; research turns queue | — |
| Both local and API unavailable | both detectors | LLM features emit NULL with `reason=unavailable`; ranker uses its no-LLM feature subset; data and execution planes continue unchanged | NULL rows logged |
| Gold-set precision drops below floor on the weekly check | harness report | Feature quarantined; Haiku column promoted if it passes; swap ticket opened | `quarantined=true` |
| Optional cross-vendor backup | manual | OpenRouter (5.5% fee, ZDR routing) with Gemini 3.5 Flash-Lite or GPT-5.4 mini for classifiers; only after the data-policy toggles (Together stores by default, Mistral free mode trains, Google unpaid tier trains) are set | separate feature_version |

## 6. What not to do

- **No LLM in the order path.** Surge engine, ranker, contract selector, sizing, exits, risk sentinel and execution gateway consume features and configs only; a First-Seen flag is an input to the deterministic Event Gate, never an order trigger by itself.
- **No 8 GB machine hosts a model the desk depends on.** The 8 GB minis run deterministic Python, the ≤ 1 GB FinBERT/SetFit encoder, monitoring, and the shadow 4B used only for A/B and agreement checks. Gemma 4 E4B under Ollama already needs 7–8 GB on a 16 GB mini (EXTRACT); on 8 GB the swap risk is real.
- **No model without a measured precision on the gold set**, including the hosted ones: Haiku's precision floor is tested the same way as Qwen's, and FinBERT's 0.64 on live headlines is the cautionary number.
- **No Ollama MLX runner behind bots** while concurrent requests serialize (open issues #17280/#17317), and no `mlx_lm.server` exposed beyond localhost (its docs say it is not production-grade).
- **No wired limit above ~88% of RAM**, no unbounded `--prompt-cache-bytes`, no research pandas jobs on the serving box.
- **No model aliases in config** (`claude-sonnet-5-5` not "latest"; a GGUF by sha256, not by file name), no temperature above 0 on any feature call, no prompt edits outside the promotion ladder.
- **No DeepSeek direct API** for anything carrying desk data (PRC residency, no ZDR); if those weights are ever wanted, use Fireworks/Together with ZDR on.
- **No reliance on Gemini Flash intro pricing** past 2026-12-31 or on OpenAI/Mistral fine-tuning (both winding down); if a classifier needs tuning, use local `mlx_lm.lora` or SetFit on the 64 GB mini.
- **No model licensed non-commercially** (MiniMax M2.7) or with conditions you have not recorded (Devstral 2, Kimi K3, Llama 4) in the fleet; every model in sections 1–2 is Apache-2.0 except gpt-oss (Apache-2.0 plus usage policy).

Items the research could not verify and that gate this plan: the 8 GB minis' actual chip and bandwidth; any measured tok/s for Qwen3.5-122B-A10B or Coder-Next-plus-sandbox co-residency on 128 GB; the default macOS wireable fraction; M4 Pro prefill speed for the 35B-A3B (scaled from M4 Max); power draw under sustained inference; whether Ollama/LM Studio enforce JSON schemas on MLX. Run `llama-bench -p 2048 -n 300` and `mlx_lm.benchmark` on your own units before locking the latency column.