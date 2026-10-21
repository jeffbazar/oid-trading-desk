# Open-weight model fact sheet for the OID desk — checked 2026-10-21

**Method and caveats.** WebSearch extracts were the main source. The sandbox proxy refused DNS for huggingface.co, artificialanalysis.ai, mistral.ai, nvidia.com, deepmind.google, wikipedia.org, gorilla.cs.berkeley.edu, omlx.ai, lambda.ai, datanorth.ai, rits.shanghai.nyu.edu, orcarouter.ai, markaicode.com; only github.com fetched. So **VERIFIED** = GitHub README read by me; **EXTRACT** = search-engine excerpt of an official or primary page (model card mirror, vendor docs, vendor blog); **UNVERIFIED** = secondary blog/aggregator or my own rule-of-thumb. Benchmark numbers are vendor-reported unless marked otherwise. Nothing below is invented; where no 2026 figure was found I say so.

**Memory formula (UNVERIFIED rule of thumb, consistent with observed MLX peaks).** Weights GB ≈ total params (B) × 0.6 at 4-bit (0.5 B/param + ~15% for scales, embeddings, norms, lm_head) and ≈ total params (B) × 1.1 at 8-bit. MoE models are sized by *total* params (all experts must be resident) but run at the speed of *active* params. Add KV cache: roughly 0.5 to 2 GB per 32K tokens of context for 27B-class models (varies by GQA/attention type; hybrid Mamba/linear-attention models like Nemotron 3, Qwen3.5 (Gated DeltaNet), GLM-5.3-Flash use far less). macOS keeps a slice of unified memory: assume usable for model+KV ≈ 5–6 GB on 8 GB, ≈ 48 GB default / ≈ 58 GB with `iogpu.wired_limit_mb` raised on 64 GB, ≈ 96 GB default / ≈ 115 GB raised on 128 GB (UNVERIFIED). Decode speed is memory-bandwidth-bound: M4 Pro 273 GB/s per [bestllmfor guide, UNVERIFIED](https://bestllmfor.com/guides/best-llm-macbook-pro-m4-pro-max/); M4 Max ≈ 546 GB/s and base M4 ≈ 120 GB/s (my training data, UNVERIFIED). Observed: Qwen3.5-27B 4-bit on M4 Pro 64 GB peaks at 17.0 GB and 13.8–15.4 tok/s, which matches 17 GB / 273 GB/s ≈ 16 tok/s ceiling [oMLX community table, EXTRACT](https://omlx.ai/benchmarks).

**Structured output note (applies to every row).** For a temperature-0 classifier you do not need the model's "native" JSON support: llama.cpp (GBNF / `json_schema`), vLLM/SGLang structured outputs, and mlx-lm with Outlines constrain decoding to a schema for any model. "Native tool calling" below means the chat template has tool tokens and a parser exists (vLLM `--tool-call-parser`, LM Studio, Ollama).

---

## 1. Qwen (Alibaba) — Apache-2.0 throughout

| Model | Released | Total / active | Context | License | Tools / JSON | 4-bit / 8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B | 2026-08-14 | 27B dense (one source says 28B incl. vision encoder) | 262K native, 1M YaRN | Apache-2.0 (weights license lives on HF per README) | Native; vLLM `--tool-call-parser qwen3_coder --enable-auto-tool-choice` | ~16–17 / ~30 | 64, 128 | VERIFIED [QwenLM/Qwen3.8 README](https://github.com/QwenLM/Qwen3.8); EXTRACT [orcarouter](https://www.orcarouter.ai/blog/qwen-3-8-27b-release-date), [benchlm](https://benchlm.ai/models/qwen3.8-27b) |
| Qwen3.8-2.4T-A95B (Qwen3.8-Max open release) | 2026-08-12 | 2.4T / 95B | — | Apache-2.0 repo | Native | ~1.4 TB / 2.6 TB | none | VERIFIED README |
| Qwen3.6-27B | 2026-04-22 | 27.8B dense | 262K | Apache-2.0 | Native + structured output | ~17 / ~30 | 64, 128 | VERIFIED README (date); EXTRACT [openrouter](https://openrouter.ai/qwen/qwen3.6-27b-20260422) |
| Qwen3.6-35B-A3B | 2026-04-16 | 35B / 3B | 262K (1M YaRN) | Apache-2.0 | Native, thinking + function calling + structured output | ~21 / ~38 | 64, 128 | VERIFIED README; EXTRACT [openrouter](https://openrouter.ai/qwen/qwen3.6-35b-a3b) |
| Qwen3.5-27B | 2026-02-24 | 27B dense | 262K | Apache-2.0 | Native | ~17 / ~30 | 64, 128 | VERIFIED README; EXTRACT [HF mirror](https://huggingface.co/unsloth/Qwen3.5-27B) |
| Qwen3.5-35B-A3B | 2026-02-24 | 35B / 3B | 262K | Apache-2.0 | Native | ~21 / ~38 | 64, 128 | same |
| Qwen3.5-122B-A10B | 2026-02-24 | 122B / 10B | 262K | Apache-2.0 | Native | ~73 / ~134 | 128 (4-bit only) | same |
| Qwen3.5-397B-A17B | 2026-02-16 | 397B / 17B | 262K | Apache-2.0 | Native | ~240 / ~440 | none | same; EXTRACT [getdeploying](https://getdeploying.com/llms/qwen3.5-397b-a17b) |
| Qwen3.5-9B / 4B / 2B / 0.8B ("Qwen3.5 Small", native multimodal) | 2026-03-02 | dense | 256K reported for 2B (UNVERIFIED) | Apache-2.0 (per quant card, UNVERIFIED) | Native | 9B ≈ 5.5/10; 4B ≈ 2.5/4.5; 2B ≈ 1.3/2.3; 0.8B ≈ 0.6/1 | 4B and below: 8 GB; 9B: 64 GB (8 GB too tight) | VERIFIED README (dates); EXTRACT [gigazine](https://gigazine.net/gsc_news/en/20260303-qwen-3-5-small), [HF quant card](https://huggingface.co/ariacompute/qwen3.5-2b_q4) |
| Qwen3-Coder-Next 80B-A3B | 2026-02-04 | 80B / 3B (hybrid attention MoE) | 262K | Apache-2.0 | Native (coder parser) | ~48 / ~88 | 64 (4-bit, tight), 128 | EXTRACT [technews.tw](https://technews.tw/2026/02/04/qwen3-coder-next-significantly-cuts-inference-costs/), [Azure catalog](https://ai.azure.com/catalog/models/qwen--qwen3-coder-next) |
| Qwen3 (Apr 2025) 0.6B…32B dense, 30B-A3B, 235B-A22B; 2507 refresh 262K ctx | 2025-04-29 / 2025-07 | — | 32K (0.6/1.7B), 131K YaRN (4B+), 262K (2507) | Apache-2.0 | Native | 30B-A3B ≈ 18/33; 4B ≈ 2.5/4.5; 1.7B ≈ 1.1/1.9 | 4B/1.7B: 8 GB; 30B-A3B: 64 | EXTRACT [simonwillison](https://simonwillison.net/2025/Apr/29/qwen-3/) |
| Qwen3.7 (May 2026) | API-only, no weights | — | — | — | — | — | — | EXTRACT [search summary of Qwen wiki/guides]; Qwen3.7 absent from the GitHub README (VERIFIED absence) |

**Benchmarks (Qwen model cards, EXTRACT [HF mirror / benchlm](https://benchlm.ai/md/models/qwen3-5-27b.md)):** Qwen3.5-27B SWE-bench Verified 72.4, BFCL-V4 68.5, TAU2-Bench 79.0; 35B-A3B 69.2 / 67.3 / 81.2; 122B-A10B 72.0 / 72.2 / 79.5. Qwen3.6-35B-A3B SWE-bench V 73.4; Qwen3.6-27B SWE-bench V 77.2, Terminal-Bench 2.0 59.3 (EXTRACT, secondary). Qwen3.8-27B Terminal-Bench 2.1 73.0 (vs 63.4 prior 27B), SWE-bench Pro 61.7, OSWorld-Verified 84.3; runs used the Claude Code harness; no independent eval as of Aug 15 (EXTRACT [orcarouter DE](https://www.orcarouter.ai/de/blog/qwen-3-8-27b-benchmarks)). Qwen3-Coder-Next SWE-bench V 70.6 (EXTRACT). Artificial Analysis (2026-04-14): Qwen3.5-27B (Reasoning) Intelligence Index 42 ≈ GPT-5 (medium), on the Pareto frontier for intelligence vs params under 32B [EXTRACT](https://artificialanalysis.ai/articles/sub-32b-open-weights); AA Aug 2026: Qwen3.6-27B 38 vs Muse Glimmer 35 [EXTRACT](https://artificialanalysis.ai/articles/muse-glimmer) (index versions differ between dates; do not compare across articles).

**Apple-silicon speed (community, EXTRACT [oMLX](https://omlx.ai/benchmarks)):** Qwen3.5-27B 4-bit MLX, M4 Pro 16-core 64 GB: 15.4 tok/s @1K ctx, 13.8 @4K, peak 17.0 GB (2026-04-24); 6-bit on M4 Pro 20-core: 11.6–11.9 tok/s, prompt ~118 tok/s (2026-03-10). Qwen3.6-35B-A3B 4-bit on M4 Max 64 GB: 98.6–108 tok/s. Qwen3.5-27B 4-bit on M4 Max 36 GB: 21.2 tok/s. Qwen3-Coder-Next 4-bit on M4 Max 128 GB: 83.9 tok/s @4K, 58.3 @32K. 30B-A3B-class MoE via llama.cpp on M4 Pro 48 GB ≈ 52 tok/s [EXTRACT, medium](https://medium.com/@andreask_75652/apples-m4-pro-is-faster-than-an-m2-max-for-nemotron-3-nano-with-mlx-2f19efbc5e50). MTP speculative decoding lifted a 27B on M4 Pro 48 GB to 18.3 tok/s [UNVERIFIED blog](https://medium.com/@vinoth.lingam333/i-got-18-tok-s-from-a-27b-model-on-a-macbook-mlx-native-mtp-speculative-decoding-on-apple-5e1211a06d0c); Unsloth ships Qwen3.6-35B-A3B-MTP GGUFs [EXTRACT](https://dell.huggingface.co/models/unsloth/Qwen3.6-35B-A3B-MTP-GGUF). Qwen3.5-4B on base M4: 25–35 tok/s (blog estimate, UNVERIFIED [insiderllm](https://insiderllm.com/guides/best-local-llms-mac-2026/)). No 2026 figure found for Qwen3.5-122B-A10B on M4 Max.

## 2. OpenAI gpt-oss — Apache-2.0

| Model | Released | Total / active | Context | Tools / JSON | Memory | Fits | Source |
|---|---|---|---|---|---|---|---|
| gpt-oss-120b | 2025-08-05 | 117B / 5.1B | 128K (training knowledge, UNVERIFIED; README silent) | Native function calling, browsing, Python, Structured Outputs (harmony format) | MXFP4 native ≈ 63.4 GB; 8-bit ≈ 125 GB | 128 only | VERIFIED [openai/gpt-oss README](https://github.com/openai/gpt-oss); EXTRACT [frame.work thread: "MXFP4 (63.39GB)"](https://community.frame.work/t/tracking-will-the-ai-max-395-128gb-be-able-to-run-gpt-oss-120b/73280) |
| gpt-oss-20b | 2025-08-05 | 21B / 3.6B | 128K (UNVERIFIED) | same | MXFP4 ≈ 12–13 GB ("runs within 16GB"); 8-bit ≈ 22 GB | 64, 128 (not 8 GB) | VERIFIED README |

**No successor found.** Searches for gpt-oss-2 / -mini / -safeguard and 2026 releases returned nothing from OpenAI; README lists only the two models (VERIFIED absence as of 2026-10-21). Apple-silicon: Metal reference implementation exists but "not production-ready" (VERIFIED README). Speed: gpt-oss-20b on Mac mini M4 16 GB via llama.cpp GGUF ≈ 26 tok/s measured, MLX MXFP4-Q8 build failed on 16 GB (12.9 GB used + swap) [EXTRACT, mlx-lm issue #644](https://github.com/ml-explore/mlx-lm/issues/644). gpt-oss-120b on M4 Max 128 GB: no measured 2026 figure found; estimator sites give 5.7–9.2 tok/s, which is implausibly low for a 5.1B-active MoE and is UNVERIFIED [willitrunai](https://willitrunai.com/zh/can-run/gpt-oss-120b-on-m4-max-128gb). Benchmarks: AA lists gpt-oss-20B among top "small" open models behind Qwen3-30B-A3B-2507 (undated page, EXTRACT [AA small](https://artificialanalysis.ai/models/open-source/small)); Qwen's card uses GPT-OSS-120B as a comparison column (EXTRACT).

## 3. Google Gemma 4 — Apache-2.0 (new), plus Gemma 3 / 3n

| Model | Released | Params | Context | License | Tools | 4/8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|---|
| Gemma 4 31B | 2026-04-02 | 31B dense | 256K | Apache-2.0 | Native function calling, thinking modes, vision | ~19 / ~34 | 64, 128 | EXTRACT [Google OSS blog](https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html), [deepmind.google/gemma-4](https://www.deepmind.google/models/gemma/gemma-4) |
| Gemma 4 26B-A4B | 2026-04-02 | 26B / ~3.8–4B | 256K | Apache-2.0 | same | ~16 / ~29 | 64, 128 | same |
| Gemma 4 E4B | 2026-04-02 | "effective 4B" edge model, audio+vision in | 128K | Apache-2.0 | same | ≈4–5 GB on LM Studio MLX, 7–8 GB under Ollama (measured on 16 GB mini) | 8 GB tight (MLX only), 64, 128 | EXTRACT [ansonbiggs](https://brain.ansonbiggs.com/Gemma-4-on-M4-Mac-Mini) |
| Gemma 4 E2B | 2026-04-02 | "effective 2B" | 128K | Apache-2.0 | function calling + structured outputs per 3rd-party listing (UNVERIFIED) | ≈3 GB Q4 | 8 GB | EXTRACT [bestllmfor 8GB](https://bestllmfor.com/meilleur-llm/mac-8gb/), [cloudprice](https://cloudprice.net/models/google-gemma-4-e2b-non-reasoning) |
| Gemma 3 1B/4B/12B/27B | 2025-03 | dense | 128K (4B+) | Gemma Terms of Use (custom; commercial allowed with restrictions, "Built with Gemma" notice) | yes | 27B ≈ 16/29; 4B ≈ 2.5/4.5 | 4B: 8 GB; 27B: 64 | EXTRACT [canirun license summary](https://canirun.ai/license/gemma/) |
| Gemma 3n E2B/E4B | 2025-06 (UNVERIFIED date) | effective 2B/4B | 32K | Gemma Terms of Use (2025-03-24 version) | yes | ≈3 / ≈4.5 | 8 GB | EXTRACT [ollama license blob](https://ollama.com/library/gemma3n:e4b/blobs/1adbfec9dcf0) |

**Benchmarks (Google's Gemma 4 page, EXTRACT):** LiveCodeBench v6: 31B 80.0, 26B-A4B 77.1, E4B 52.0, E2B 44.0; τ2-bench (tool use): 86.4 / 85.5 / 57.5 / 29.4; 31B GPQA Diamond 84.3, MMMLU 85.2. AA (2026-04-14): Gemma 4 31B (Reasoning) index 39 ≈ GPT-5 (low), more token-efficient than Qwen3.5-27B; both weak on AA-Omniscience (knowledge recall) [EXTRACT](https://artificialanalysis.ai/articles/sub-32b-open-weights). No BFCL score found. **Speed:** 26B-A4B 6-bit on M4 Max 128 GB 78.8 tok/s @4K (oMLX 2026-04-06); 31B on M4 Pro 64 GB 12.5 tok/s @1K, 6.5 @4K; M4 Pro 48 GB 11.5 @4K (oMLX, quant unstated, EXTRACT); 31B via Ollama on M4 Max 18–26 tok/s (UNVERIFIED [markaicode](https://markaicode.com/benchmarks/hugging-face-gemma-4-m4-max-latency-benchmark/)); E4B on M4 Max 47.2 tok/s @32K, 17.6 @128K (oMLX); E4B on base M4 35–45 tok/s and E2B 30–45 (blog estimates, UNVERIFIED [modelfit](https://modelfit.io/blog/best-llm-macbook-air-m4-16gb/)).

## 4. Meta — Llama 4, Llama 3.2, Muse

| Model | Released | Total / active | Context | License | 4/8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|
| Llama 4 Scout | 2025-04-05 | 109B / 17B (16 experts) | 10M claimed; providers 128K–328K | Llama 4 Community License: 700M-MAU clause (measured at release date, Meta's discretion); multimodal models not licensed to EU-domiciled entities (FAQ + commentary, partly UNVERIFIED) | ~65 / ~120 | 128 (4-bit) | EXTRACT [simonwillison](https://simonwillison.net/2025/Apr/5/llama-4-notes), [HF license text](https://huggingface.co/meta-llama/Llama-4-Maverick-17B-128E-Original), [llama.com FAQ](https://www.llama.com/faq/) |
| Llama 4 Maverick | 2025-04-05 | 400B / 17B (128 experts) | 1M | same | ~240 / ~440 | none | same |
| Llama 3.2 3B Instruct | 2024-09-25 | 3.21B | 128K | Llama 3.2 Community License | ~2 / ~3.5 | 8 GB | EXTRACT [portkey](https://models.portkey.ai/models/llama-3-2-3b-instruct) |
| Muse Glimmer 30B | 2026-08-10 | 30B dense (2B vision encoder + 28B decoder, distilled from Muse Spark) | not found | **Apache-2.0** | ~18 / ~33 (BF16 >55 GB; Meta ships Q4_K_M GGUF + drafter) | 64, 128 | EXTRACT [AA Muse Glimmer](https://artificialanalysis.ai/articles/muse-glimmer), [aiweekly](https://aiweekly.co/node/9634) |
| Muse Spark Open | 2026-10-15 | 816B / 42B, text+image+video+audio | 1M | Muse Model License (conditional commercial; $20M threshold reported, UNVERIFIED) | ~490 / ~900 | none | EXTRACT [thenewstack](https://thenewstack.io/meta-muse-spark-open/), [itdaily](https://itdaily.com/news/innovation/meta-muse-spark-open-weigh/) |
| "Llama 5" | **not released**; claims of April/June 2026 releases are aggregator noise; tracker puts "Avocado" at 2027 or folded into closed Muse Spark | — | — | — | — | — | EXTRACT [orcarouter](https://www.orcarouter.ai/blog/llama-5-leak) (secondary, UNVERIFIED) |

Benchmarks: Muse Glimmer AA index 35 (behind Qwen3.6-27B 38); Meta claims leads on MCP Atlas, SWE-Bench Pro, AIME 2026 vs Gemma 4 31B and Qwen3.6-27B (vendor, EXTRACT). Llama 4 Maverick BFCL v4 appears on benchmarklist (score not captured). No Apple-silicon speed figures found for Glimmer.

## 5. DeepSeek — MIT

| Model | Released | Total / active | Context | License | 4/8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|
| DeepSeek-V4-Pro | 2026-04-24 (preview) | 1.6T / 49B | 1M | MIT | ~960 / ~1,760 | none | EXTRACT [letsdatascience](https://letsdatascience.com/news/deepseek-v4-preview-adds-open-weight-1m-context-models-4a8f21c6), [cometapi](https://www.cometapi.com/how-to-use-deepseek-v4-api/) |
| DeepSeek-V4-Flash | 2026-04-24; "0731" GA checkpoint 2026-07-31 reported (name UNVERIFIED) | 284B / 13B, native FP4+FP8 mixed | 1M | MIT | ~170 / ~310 (native mixed ≈ 190 GB) | none (exceeds 128 GB) | EXTRACT [HF mirror table](https://huggingface.co/mart66/DeepSeek-V4-Flash), [aicybr](https://aicybr.com/blog/deepseek-v4-flash-complete-guide) |
| DeepSeek-V4-Flash-Vision-Exp | 2026 (date not found) | ~305B | — | MIT | ~183 | none | EXTRACT [runtimewire](https://runtimewire.com/article/deepseek-publishes-v4-flash-vision-open-weights) |
| DeepSeek-V3.2 / V3.2-Speciale | 2025-12-01 | 671B / 37B (one source 685B) | 128K–163K | MIT | ~400 / ~740 | none | EXTRACT [letsdatascience](https://letsdatascience.com/news/deepseek-releases-v32-open-weight-models-suite-e627edad) |
| DeepSeek-R1-0528 | 2025-05-28 | 671B / 37B | 128K | MIT | ~400 | none | EXTRACT [techcrunch](https://techcrunch.com/2025/05/29/deepseeks-distilled-new-r1-ai-model-can-run-on-a-single-gpu) |
| DeepSeek-R1-0528-Qwen3-8B | 2025-05-28 | 8B dense | 64K–131K (sources disagree) | MIT | ~5 / ~9 | 64, 128 (8 GB too tight) | same |

Tool calling: V4 exposes OpenAI-style `tools`, works in thinking mode, strict mode and `response_format` JSON reported by 3rd-party guides (UNVERIFIED [deepseekai.guide](https://deepseekai.guide/api/deepseek-api-function-calling/), [runware](https://runware.ai/models/deepseek-v4-flash)). github.com/deepseek-ai/DeepSeek-V4 returned 404 (VERIFIED), so the repo is named differently. No SWE-bench/τ2 numbers for V4 found; AA April 2026: DeepSeek V4 Pro (Reasoning, max) index 52, behind Kimi K2.6 and MiMo V2.5 Pro at 54 (EXTRACT). **Nothing in the DeepSeek line fits any Mac here; the desk would use it via API only.** API price reported $0.14/$0.28 per MTok for Flash, $1.74/$3.48 for Pro (EXTRACT, secondary).

## 6. Mistral — mixed licenses

| Model | Released | Total / active | Context | License | Commercial | 4/8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|---|
| Mistral Small 4 (119B-A6B; merges Instruct, Magistral reasoning, Pixtral vision, Devstral coding) | 2026-03-16 | 119B / 6B (128 experts, 4 active; 8B incl. embeddings) | 256K | Apache-2.0 | yes | ~72 / ~130 | 128 (4-bit) | EXTRACT [mistral.ai news](https://mistral.ai/news/mistral-small-4/), [NVIDIA NIM](https://docs.api.nvidia.com/nim/reference/mistralai-mistral-small-4-119b-2603) |
| Mistral Medium 3.5 | 2026-04 | 128B dense (multimodal) | 256K | Modified MIT (revenue cap) | conditional | ~77 / ~140 | 128 (4-bit) | EXTRACT [beam.ai](https://beam.ai/llm/mistral/) (secondary) |
| Mistral Large 3 | 2025-12 | 675B / 41B | 256K | Apache-2.0 | yes | ~400 | none | EXTRACT [intuitionlabs](https://intuitionlabs.ai/articles/mistral-large-3-moe-llm-explained) |
| Mistral Large 4 | preview API 2026-10-06; weights promised "by end of October", custom (non-Apache) license expected | ~1.05T / 49–52B | 1M | TBD | TBD | none | EXTRACT [thenewstack](https://thenewstack.io/mistral-large-4-weights/) |
| Devstral 2 | 2025-12-09 | 123B dense | 256K | Modified MIT: companies >$20M monthly revenue need a separate license | conditional | ~74 / ~135 | 128 (4-bit) | EXTRACT [venturebeat](https://venturebeat.com/ai/mistral-launches-powerful-devstral-2-coding-model-including-open-source), [mistral.ai](https://mistral.ai/fr/news/devstral-2-vibe-cli) |
| Devstral Small 2 | 2025-12-09 | 24B dense | 256K (one host says 128K) | Apache-2.0 | yes | ~14 / ~26 | 64, 128 | same; [vercel](https://vercel.com/ai-gateway/models/devstral-small-2/about) |
| Ministral 3 (3B / 8B / 14B; base, instruct, reasoning) | 2025-12 | dense | not captured | Apache-2.0 | yes | 3B ≈ 2/3.5; 8B ≈ 5/9; 14B ≈ 8.5/15 | 3B: 8 GB; 8B/14B: 64 | EXTRACT [heise](https://heise.de/-11101058), [letsdatascience](https://letsdatascience.com/news/mistral-unveils-open-weight-mistral-3-models-d866c1d4) |
| Magistral Small 1.2 | 2025-09 (training data; no 2026 search hit) | 24B | 128K | Apache-2.0 | yes | ~14 / ~26 | 64 | UNVERIFIED; AA "small" page lists Magistral Small 1.2 4th [EXTRACT](https://artificialanalysis.ai/models/open-source/small). Magistral is now folded into Small 4 (EXTRACT mistral.ai) |

Benchmarks: Devstral 2 SWE-bench Verified 72.2; Devstral Small 2 68.0 (vendor, EXTRACT). Mistral Large 4 AA ≈ 38 per a secondary Oct 2026 article (UNVERIFIED). No Apple-silicon speed figures for Small 4 found; at 6B active it should decode like a 6–8B dense model once the 72 GB of weights are resident (my inference).

## 7. Zhipu / Z.ai GLM — MIT

| Model | Released | Total / active | Context | License | 4/8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|
| GLM-5 | 2026-02-11 | 744B / 40B (DeepSeek Sparse Attention) | 200K+ (not stated in README) | MIT (repo shows Apache-2.0 link; HF weights MIT per coverage) | ~450 / ~820 | none | VERIFIED [zai-org/GLM-5 README](https://github.com/zai-org/GLM-5); EXTRACT [AA GLM-5](https://artificialanalysis.ai/articles/glm-5-everything-you-need-to-know) |
| GLM-5.1 | 2026 (date not in README) | 744B / 40B | — | MIT | same | none | VERIFIED README |
| GLM-5.2 | 2026-06-16 (NIST CAISI) | 744B / 40B | 1M | MIT | same | none | VERIFIED README; EXTRACT [nist.gov](https://www.nist.gov/node/1916756) |
| GLM-5.3 (flagship) | 2026-08-14, weights held for safety review | — | — | — | — | none | EXTRACT [smol.ai](https://news.smol.ai/issues/26-08-26-not-much) |
| GLM-5.3-Flash | 2026-08-25/26 | 320B / 18B, hybrid sparse+linear attention, native multimodal | 1M (one host 256K) | MIT | ~190 / ~350 | none | VERIFIED README (name/size); EXTRACT [featherless](https://featherless.ai/blog/glm-5-3-flash-is-live-on-featherless) |
| GLM-4.7 | 2025-12-22 | 355B / 32B | 200K | MIT | ~213 / ~390 | none | EXTRACT [AA GLM-5](https://artificialanalysis.ai/articles/glm-5-everything-you-need-to-know) |
| GLM-4.5-Air | 2025-07 | 106B / 12B | 128K | MIT | ~64 / ~117 | 128 (4-bit); 64 only at ~3-bit | EXTRACT [morphllm](https://www.morphllm.com/glm-4-6) |

No GLM-5 "Air" exists (VERIFIED README lists none). Benchmarks: GLM-5 SWE-bench V 77.8, AIME 2026 92.7 (EXTRACT); GLM-5.2 Terminal-Bench 2.1 81.0 (vs 62.0 for 5.1; Claude Opus 4.8 85.0), SWE-bench Pro 62.1 (VERIFIED README); BFCL v4 GLM-5 70.8 (third-party BenchLM snapshot Mar 2026, UNVERIFIED [benchlm](https://benchlm.ai/benchmarks/bfclV4)); AA Oct 2026: GLM-5.3 ≈ 45 (secondary, UNVERIFIED [pasqualepillitteri](https://pasqualepillitteri.it/en/news/24368/best-open-weight-models-october-2026-compared)). **Nothing in GLM fits the desk's Macs except GLM-4.5-Air at 4-bit on the 128 GB box.**

## 8. Moonshot Kimi

| Model | Released | Total / active | Context | License | Fits | Source |
|---|---|---|---|---|---|---|
| Kimi K2.5 | 2026-01-27 | 1T / 32B | 256K | Modified MIT | none (~600 GB 4-bit) | EXTRACT [epoch.ai](https://epoch.ai/models/kimi-k2-5), [NVIDIA NIM](https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k2-5) |
| Kimi K2.6 | 2026-04-20 | 1T / 32B | 256K | Modified MIT | none | EXTRACT [theneuron](https://theneuron.ai/explainer-articles/kimi-k26-just-shipped-open-weight-claude-level-coding-at-76-the-cost-with-a-300-agent-swarm-as-the-real-story/) |
| Kimi K3 | API 2026-07-16; weights ~2026-07-27 | 2.8T / 104B | 1,048,576 | "Kimi K3 License" (not MIT): MaaS operators >$20M revenue/12 mo need agreement; >100M MAU or >$20M monthly revenue must display "Kimi K3" | none (~1.7 TB 4-bit; 1.56 TB download) | VERIFIED [MoonshotAI/Kimi-K3 README](https://github.com/MoonshotAI/Kimi-K3); EXTRACT [venturebeat](https://venturebeat.com/technology/kimi-k3s-full-weights-are-here-but-theyre-open-with-a-caveat-what-enterprises-should-know) |

Benchmarks: K3 Terminal-Bench 2.1 88.3, DeepSWE 67.5, τ³-Banking 33.4 (VERIFIED README, vendor, max effort, as of 2026-07-23); K2.6 SWE-bench V 80.2, SWE-bench Pro 58.6, Terminal-Bench 2.0 66.7 (EXTRACT, vendor); AA Oct 2026 K3 ≈ 44 (UNVERIFIED secondary). API-only for this desk.

## 9. MiniMax

| Model | Released | Total / active | Context | License | Commercial | Fits | Source |
|---|---|---|---|---|---|---|---|
| MiniMax-M2.5 | 2026-02-12 | 229.9B / 9.8B | 204.8K | Modified MIT (MiniMax Model License: attribution + prohibited uses) | yes with attribution | none at 4-bit (~138 GB); ~3-bit ≈ 100 GB on 128 GB is UNVERIFIED | EXTRACT [epoch.ai](https://epoch.ai/models/minimax-m2-5), [NVIDIA modelcard](https://build.nvidia.com/minimaxai/minimax-m2.5/modelcard) |
| MiniMax-M2.7 | 2026-03 (weights ~April) | ~229B / 10B | 204.8K | **Non-commercial** without written authorization ("Built with MiniMax M2.7") | no | none | EXTRACT [HF discussion](https://huggingface.co/MiniMaxAI/MiniMax-M2.7/discussions/5), [MiniMax docs](https://platform.minimax.io/docs/guides/local-deploy-m2-7.md) |
| MiniMax-M3 | 2026-06-01 | ~428B / ~23B, native multimodal | 1M | MiniMax Community License (`license: other`): attribution, >$20M/yr revenue needs authorization; reading of base grant disputed | conditional | none (BF16 854 GB) | VERIFIED [MiniMax-AI/MiniMax-M3 README](https://github.com/MiniMax-AI/MiniMax-M3); EXTRACT [howaiworks](https://howaiworks.ai/models/minimax-m3) |

Benchmarks: M3 SWE-Bench Pro 59.0 (vendor); AA M2.5 ECI 147, M3 ECI 146 (Epoch); BFCL v4 M2.7 70.6 (BenchLM, UNVERIFIED). API-only.

## 10. NVIDIA Nemotron — Nemotron Open Model License → OpenMDW-1.1

| Model | Released | Total / active | Context | License | 4/8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|
| Nemotron 3 Nano 30B-A3B | 2025-12-15 | 31.6B / 3B hybrid Mamba-2 + MoE | 1M (HF default 256K) | NVIDIA Nemotron Open Model License (commercial OK) | ~19 / ~35 | 64, 128 | EXTRACT [NVIDIA NIM](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-nano-30b-a3b), [vLLM blog](https://blog.vllm.ai/2025/12/15/run-nvidia-nemotron-3-nano.html) |
| Nemotron 3 Super 120B-A12B | 2026-03-11 | 120B / 12B, LatentMoE, MTP, NVFP4-pretrained | 1M | Nemotron Open Model License | ~72 / ~132 (NVFP4 checkpoint ≈ 65–70 GB) | 128 | EXTRACT [NVIDIA NIM](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b) |
| Nemotron 3 Ultra | 2026-06-04 | 550B / 55B | 1M | OpenMDW-1.1 | ~330 | none | EXTRACT [Docker Hub](https://hub.docker.com/r/ai/nemotron-3-ultra), [NVIDIA llm-info](https://www.nvidia.com/en-us/ai-data-science/foundation-models/nemotron/llm-info/) |
| Nemotron 3.5 Lightning | 2026-08-11 | 30B / ~3B | — | OpenMDW-1.1 | ~19 / ~35 | 64, 128 | EXTRACT [guru3d](https://guru3d.com/story/nvidia-nemotron-35-lightning-runs-locally-on-a-single-gpu/) |
| Nemotron 3.5 Super VL | 2026-10-15 | 120B / 12B, text+image+video | 1M | OpenMDW-1.1 (per llm-info; UNVERIFIED for this SKU) | ~72 / ~132 | 128 | EXTRACT [AA](https://artificialanalysis.ai/zh/articles/nemotron-3-5-super-and-bolt), [hpcwire](https://www.hpcwire.com/aiwire/2026/10/15/nvidia-expands-nemotron-family-with-highest-efficiency-super-vl-and-bolt-models/) |
| Nemotron 3.5 Bolt 74B-A9B | 2026-10-15 | 74B / 9B | — | OpenMDW-1.1 (UNVERIFIED) | ~44 / ~81 | 64 (4-bit), 128 | EXTRACT AA article only |

Benchmarks: AA Oct 2026 — Super VL 26 (26.5 in one version), "highest-scoring US open-weights model"; Bolt 21 (EXTRACT AA). Tool calling: Nano RL-trained on tool calling; hosts list function calling and JSON output (EXTRACT). Speed: Nano via llama.cpp on M4 Pro 48 GB ≈ 52 tok/s, M2 Max ≈ 63 (EXTRACT medium); oMLX M3 Max 64 GB 79–124 tok/s (inconsistent). A 120B Nemotron ran at 27 tok/s on a 48 GB MacBook with "TurboQuant hybrid" sub-4-bit MLX quant (UNVERIFIED [medium](https://medium.com/data-science-collective/nemotron-120b-on-a-48-gb-macbook-27-tok-s-with-turboquant-hybrid-quantization-mlx-529d93cbc960)).

## 11. Microsoft Phi — MIT

| Model | Released | Params | Context | Tools | 4/8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|
| Phi-4-mini-instruct | 2025-02 | 3.8B | 128K | function calling (3rd-party claim, UNVERIFIED) | ~2.3 / ~4.2 | 8 GB | EXTRACT [promptlayer](https://www.promptlayer.com/models/phi-4-mini-instruct) |
| Phi-4-mini-flash-reasoning | 2025-07 | 3.8B SambaY hybrid | 64K | math-only tuning | ~2.3 | 8 GB | EXTRACT [Azure blog](https://azure.microsoft.com/en-us/blog/reasoning-reimagined-introducing-phi-4-mini-flash-reasoning/) |
| Phi-4-reasoning-vision-15B | 2026-03-04 | 15B VLM | — | — | ~9 / ~16.5 | 64, 128 | EXTRACT [MSR blog](https://www.microsoft.com/en-us/research/blog/phi-4-reasoning-vision/), [arXiv 2603.03975](https://arxiv.org/pdf/2603.03975) |
| Phi-5 | **not found** as of 2026-10-21 | — | — | — | — | — | EXTRACT (search returned nothing) |

No 2026 tool-use or coding leaderboard standing found for Phi; BFCL v4 lists Qwen3-4B-Instruct-2507 at ~35.7% overall as a reference point for 4B-class function calling (BenchListed May 2026, UNVERIFIED).

## 12. IBM Granite — Apache-2.0

| Model | Released | Params | Context | Tools | 4/8-bit GB | Fits | Source |
|---|---|---|---|---|---|---|---|
| Granite 4.1 3B / 8B / 30B (dense; base + instruct) | 2026-04-29 | dense | 131,072 in config; IBM marketing says 512K | RL-tuned tool calling, tool-call example on card | 3B ≈ 2/3.5; 8B ≈ 5/9; 30B ≈ 18/33 | 3B: 8 GB; 8B, 30B: 64 | EXTRACT [HF granite-4.1-3b](https://huggingface.co/ibm-granite/granite-4.1-3b), [granite-4.1-30b-base](https://huggingface.co/ibm-granite/granite-4.1-30b-base) |
| Granite Vision 4.1 | 2026-04-29 | — | — | documents/tables | — | — | EXTRACT [datanorth](https://datanorth.ai/news/ibm-releases-granite-4-1) |
| Granite 4.0 H-Small (32B-A9B hybrid Mamba) etc. | 2025-10 | — | — | — | ~19 / ~35 | 64 | EXTRACT [storagereview](https://www.storagereview.com/news/ibm-granite-4-0-efficient-open-weight-llms-target-enterprise-grade-performance-cost-and-governance) |

AA Intelligence Index for Granite 4.1 30B (non-reasoning): 9 — far below Qwen/Gemma peers (EXTRACT). Useful mainly for its clean license and enterprise RAG/tool-call tuning, not frontier ability.

## 13. Other sub-5B candidates for the 8 GB minis

| Model | Released | Params | Context | License | 4-bit GB | Source |
|---|---|---|---|---|---|---|
| SmolLM3-3B | 2025-07 | 3B dense, switchable reasoning | 64K native, 128K YaRN | Apache-2.0, full recipe published | ~2 | EXTRACT [osai-index](https://osai-index.eu/model/smollm), [HF README](https://huggingface.co/HuggingFaceTB/SmolLM3-3B-Base/blob/refs%2Fpr%2F4/README.md) |
| LFM2.5-8B-A1B (Liquid) | 2026-05-28 | 8.3B / 1.5B MoE (Together: 8.5B/1B) | 128K | LFM Open License v1.0 (custom) | ~5 (tight on 8 GB) | EXTRACT [marktechpost](https://www.marktechpost.com/2026/05/28/liquid-ai-releases-lfm2-5-8b-a1b-an-on-device-moe-model-with-8-3b-total-and-1-5b-active-parameters/), [lambda](https://lambda.ai/inference-models/liquidai/lfm2.5-8b-a1b); BFCL v4 49.7% = top open-weight entry in BenchLM July 2026 snapshot (UNVERIFIED) |
| Qwen3.5-4B / 2B / 0.8B, Gemma 4 E2B/E4B, Ministral 3 3B, Granite 4.1 3B, Phi-4-mini, Llama 3.2 3B | see above | | | | | |

---

## What fits where (weights + working KV; MLX or llama.cpp)

| Machine | Usable for model+KV (UNVERIFIED) | Comfortable | Tight / needs sub-4-bit | Does not fit |
|---|---|---|---|---|
| **8 GB Mac mini (base M4, ~120 GB/s)** | ~5–6 GB | Qwen3.5-4B/2B/0.8B 4-bit (2.5/1.3/0.6 GB); Gemma 4 E2B (~3 GB); Phi-4-mini 4-bit (2.3); Ministral 3 3B; Granite 4.1 3B; SmolLM3-3B; Llama 3.2 3B; Qwen3-4B-2507 | Gemma 4 E4B (4–5 GB on MLX only; 7–8 GB under Ollama); LFM2.5-8B-A1B (~5 GB); Qwen3.5-9B 4-bit (5.5 GB + KV: no) | gpt-oss-20b (12–13 GB), anything ≥9B |
| **64 GB Mac mini (M4 Pro, 273 GB/s)** | ~48 GB default, ~58 GB raised | Qwen3.8-27B / 3.6-27B / 3.5-27B at 8-bit (~30 GB) with long context; Gemma 4 31B 8-bit (~34); Gemma 4 26B-A4B 8-bit (~29); Qwen3.6-35B-A3B 8-bit (~38); Nemotron 3 Nano / 3.5 Lightning 8-bit (~35); Muse Glimmer 30B 8-bit (~33); Granite 4.1 30B 8-bit; Devstral Small 2 / Magistral Small 8-bit (~26); gpt-oss-20b (13); Qwen3-Coder-Next 80B-A3B 4-bit (~48, raise wired limit); Nemotron 3.5 Bolt 74B-A9B 4-bit (~44) | GLM-4.5-Air 4-bit (64 GB: no; ~3-bit ≈ 48 GB); Llama 4 Scout 4-bit (65: no); Nemotron 3 Super / 3.5 Super VL (72 GB at 4-bit; 27 tok/s reported at sub-4-bit on 48 GB); Qwen3.5-122B-A10B (73: no, ~3-bit ≈ 55 GB tight) | gpt-oss-120b (63.4 GB MXFP4 leaves no KV headroom), Mistral Small 4, Devstral 2, Medium 3.5, anything ≥230B |
| **128 GB Mac (M4 Max class, ~546 GB/s)** | ~96 GB default, ~115 GB raised | Everything above at 8-bit; gpt-oss-120b MXFP4 (63); Qwen3.5-122B-A10B 4-bit (73); Mistral Small 4 4-bit (72); Nemotron 3 Super / 3.5 Super VL 4-bit (72, NVFP4 checkpoint native); Llama 4 Scout 4-bit (65); GLM-4.5-Air 4-bit (64); Devstral 2 4-bit (74); Medium 3.5 4-bit (77); Nemotron Bolt 8-bit (81); Coder-Next 8-bit (88) | Qwen3-235B-A22B (140 at 4-bit; ~3-bit 105 tight); MiniMax M2.5/M2.7 (138 at 4-bit; ~3-bit ≈ 100) | DeepSeek V4-Flash (170), GLM-5.3-Flash (190), Qwen3.5-397B (240), Llama 4 Maverick (240), MiniMax M3 (257), Nemotron Ultra (330), GLM-5.x, Kimi K2.x/K3, V4-Pro, Muse Spark Open, Mistral Large 3/4 |

Speed reference points on the 64 GB M4 Pro: dense 27B 4-bit ≈ 14–15 tok/s (≈ 7–12 at 6/8-bit or long context); 35B-A3B / 30B-A3B MoE ≈ 50–100 tok/s; gpt-oss-20b ≈ 26–40 tok/s. On the 128 GB M4 Max: 35B-A3B ≈ 100 tok/s, 26B-A4B ≈ 79, Coder-Next 80B-A3B ≈ 84 @4K / 58 @32K, dense 27–31B ≈ 20–26. All from oMLX community rows or blogs cited above; no vendor-grade benchmark exists.

---

## Best candidates for the four jobs

**(1) Temperature-0 classifier for headlines/filings, ~800 items/day, precision floor on a 200-item gold set.** Open: **Qwen3.5-9B** (8-bit, ~10 GB) or **Qwen3.6-27B** (4-bit) on the 64 GB mini for the accuracy-critical First-Seen gate; **Qwen3.5-4B** or **Gemma 4 E4B (MLX)** on an 8 GB mini as the cheap shadow/second opinion; run through llama.cpp or vLLM grammar-constrained JSON so the schema is enforced regardless of the model. Load is trivial: 800 items × ~1.5K input tokens ≈ 1.2M tokens/day ≈ 1.5 min of 4B inference per hour. Proprietary: **Claude Haiku 5.5** with `output_config.format` structured outputs ≈ 1.2M in + 0.1M out ≈ $0.17/day at $0.10/$0.50 (≈ $0.09 with Batch API, prompt-cached system prompt cheaper still); use it as the gold-set judge and as the fallback when local precision drops below floor. Gemma 4 E4B τ2-bench 57.5 vs E2B 29.4 says do not go below 4B-effective for typed extraction with an evidence quote.

**(2) X-post scorer (-2..+2, 25–200/day).** Open: **Qwen3.5-4B** on an 8 GB mini (2.5 GB, 25–35 tok/s) — the whole day's load is seconds of compute; **Gemma 4 E2B** as the ultra-light alternative; SmolLM3-3B / Phi-4-mini only if license homogeneity matters more than quality. Proprietary: **Haiku 5.5** (<$0.05/day). Keep finbert as a baseline feature; score both and let the ranker pick.

**(3) Narrative/rationale writer with tool use (Rose ~100 calls/day at 5-min cadence, Hal ~30, Macro ~20).** Open on 64 GB: **Qwen3.8-27B** (Terminal-Bench 2.1 73.0, native tool parser) or **Qwen3.6-27B** at 4-bit ≈ 14 tok/s → a 600-token rationale ≈ 45–60 s, fine for a 5-minute loop; **Gemma 4 26B-A4B** (τ2-bench 85.5, ~5× faster at ~50–80 tok/s) when latency matters more than depth; **Gemma 4 31B** (τ2 86.4) for Hal end-of-day. On the 128 GB box: **Qwen3.5-122B-A10B** 4-bit, **gpt-oss-120b** (native Structured Outputs, Apache), **Nemotron 3.5 Super VL** (best US-licensed), **Mistral Small 4**. Proprietary: **Claude Sonnet 5.5** ($2/$10, 1M context, strict tool schemas) as default for Rose/Macro; **Opus 5.5** for Hal's open/close passes; Haiku 5.5 for Rose's 15-minute marks. Rough proprietary cost: 150 calls/day × 6K in / 0.6K out ≈ 0.9M in + 0.09M out ≈ $2.7/day on Sonnet, ≈ $0.9/day with cache reads at $0.20.

**(4) Coding/research assistant for the bounded experiment loop (bursty, few long sessions/day, edits only `editable/`).** Proprietary first: **Claude Opus 5.5** (the default for coding/agentic work; $4/$20, cache reads $0.20) for the loop, **Fable 5.1** for weekly post-mortems and code review. Open fallback on 64 GB: **Qwen3-Coder-Next 80B-A3B** 4-bit (SWE-bench V 70.6, 48 GB, ~50–80 tok/s class) or **Qwen3.6-27B** (SWE-bench V 77.2 vendor) / **Devstral Small 2** (68.0, Apache). On 128 GB: **gpt-oss-120b**, **Qwen3.5-122B-A10B**, **Devstral 2** (72.2, but Modified-MIT $20M/month revenue cap — fine for a small desk, record it). Frontier open coders (GLM-5.2 Terminal-Bench 81.0, Kimi K3 88.3, K2.6 SWE-bench V 80.2, DeepSeek V4) do not fit any Mac here and would be API-only; their licenses range from MIT (GLM, DeepSeek) to conditional (Kimi K3, MiniMax M3) to non-commercial (MiniMax M2.7).

**License flags for the desk (commercial use):** clean — Apache-2.0 (Qwen, Gemma 4, gpt-oss, Mistral Small 4 / Ministral 3 / Devstral Small 2 / Large 3, Muse Glimmer, Granite, SmolLM3), MIT (DeepSeek, GLM, Phi), OpenMDW-1.1 / Nemotron Open Model License (NVIDIA); conditional — Modified MIT with revenue caps (Kimi K2.5/K2.6, Devstral 2, Mistral Medium 3.5, MiniMax M2.5), Kimi K3 License, MiniMax Community License (M3), Muse Model License (Spark Open), Llama 4 Community (700M MAU + EU multimodal exclusion), Gemma 3/3n Terms of Use, LFM Open License; non-commercial — MiniMax M2.7.

**Gaps I could not close on 2026-10-21:** no primary Hugging Face model cards or Artificial Analysis pages were readable (DNS blocked); no measured M4 Max tok/s for gpt-oss-120b or Qwen3.5-122B-A10B; no 2026 BFCL leaderboard read directly (Epoch rates BFCL v4 "Flawed", 48% of sampled tasks defective [EXTRACT](https://epoch.ai/benchmarks/berkeley-function-calling-leaderboard/review)); Qwen3.7 has no open weights; no Phi-5, no gpt-oss successor, no Llama 5; Mistral Large 4 weights and license pending end of October.