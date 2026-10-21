# Sources for the model and hardware plan (2026-10-21)

Eight claims from the first draft of `../MODEL-AND-HARDWARE-PLAN-20261021.md` were sent to independent checkers on 2026-10-21. Each entry lists the claim as checked, the verdict, the correction applied, and the sources the checker read. Where a page could not be fetched through the session proxy the entry says so ("search extract"). The three research sheets and the two draft plans the synthesis was built from are in `model-plan/`.

## 1. Held (confidence 0.8)

**Claim.** Qwen3.5-9B exists as an open-weight release dated 2026-03-02 under Apache-2.0, is a dense ~9B model with native tool/JSON support, and fits in roughly 10 GB at 8-bit (Q8_0 GGUF) so it can run as the sole classifier instance on the 64 GB mini.

**Correction applied.** Not refuted; minor precision fixes: (a) Apache-2.0 and the 9B parameter count were confirmed only from search extracts of the HF card plus the GitHub LICENSE, not from a directly read HF page; (b) "dense" is correct in the non-MoE sense, but the model is a hybrid Gated DeltaNet + full-attention architecture and is multimodal (image-text-to-text), with some listings giving 9.7B total parameters; (c) the Q8_0 GGUF weight file is 9.5-9.8 GB, and runtime memory with KV cache will be a few GB above that, so budget ~12-14 GB rather than exactly 10 GB; (d) tool calling is documented (BFCL-V4 66.1, Qwen-Agent integration) but "native JSON" is not explicitly documented; rely on llama.cpp grammar / server JSON schema enforcement for the classifier output.

**Sources.**

- https://github.com/QwenLM/Qwen3.5 (README News line 2026-03-02; read directly)
- https://github.com/QwenLM/Qwen3.5/blob/main/LICENSE (Apache 2.0; read directly)
- https://huggingface.co/Qwen/Qwen3.5-9B (search extract only: license apache-2.0, base Qwen3.5-9B-Base, image-text-to-text)
- https://huggingface.co/Qwen/Qwen3.5-9B/blob/main/config.json (search extract: Qwen3_5ForConditionalGeneration, full_attention_interval 4)
- https://huggingface.co/bartowski/Qwen_Qwen3.5-9B-GGUF (search extract: Q8_0 9.80GB)
- https://www.developersdigest.tech/local-models/qwen3-5-9b (search extract: unsloth Q8_0 9.5 GB)
- https://docs.baseten.co/examples/models/llm/qwen3.5.md (search extract: 9B dense, tool calling enabled)
- https://together.ai/models/qwen3-5-9b (search extract: tool calling, BFCL-V4 66.1)
- https://artificialanalysis.ai/articles/qwen3-5-small-models (search extract: four dense models 0.8B/2B/4B/9B, Apache 2.0, March 2026)
- https://apxml.com/models/qwen35-9b (search extract: Dense, Apache 2.0)
- https://llm-stats.com/models/qwen3.5-9b (search extract: 9.0B, Apache 2.0)

## 2. Corrected (confidence 0.72)

**Claim.** Qwen3.6-35B-A3B was released 2026-04-16 under Apache-2.0, has 35B total / 3B active parameters, fits in ~21 GB at 4-bit, ships a native tool-call parser, and decodes at roughly 50 tok/s or better via llama.cpp on an M4 Pro 64 GB mini.

**Correction applied.** Release date (2026-04-16), 35B/3B MoE shape, Apache-2.0 license and ~21 GB at Q4 hold up. Two parts should be corrected: (a) the model does not "ship" a tool-call parser; it emits Qwen3-Coder-style XML tool calls that the serving engine must parse (vLLM/SGLang: --tool-call-parser qwen3_coder; llama.cpp: --jinja with its built-in qwen3-coder XML path), and llama.cpp currently has an open regression (#30118, Oct 2026) where ~9% of Qwen3.6 tool calls leak into content, so the planning doc should pin a llama.cpp build or add a content-fallback parser. (b) There is no measured llama.cpp throughput for Qwen3.6-35B-A3B on an M4 Pro; published estimates for an M4 Pro 64 GB at Q4_K_M range from ~27 tok/s (willitrunai, modeled) to ~86 tok/s (llmcheck, estimated), with measured MLX runs on M4 Pro 48 GB at 38-105 tok/s. Replace "roughly 50 tok/s or better" with "unmeasured; estimates 27-86 tok/s, measure with llama-bench before relying on the 15 s/call fallback latency", or benchmark on the actual mini. Enabling MTP (llama.cpp >= May 16, 2026) adds roughly 10-30% decode speed.

**Sources.**

- https://github.com/QwenLM/Qwen3.6 (README news: 2026-04-16 release; serving commands with --tool-call-parser qwen3_coder; license pointer to HF)
- https://github.com/ggml-org/llama.cpp/issues/30118 (Qwen3.6 tool calls leak into content, opened 2026-10-07)
- https://github.com/ggml-org/llama.cpp/pull/27679 (chat: scope qwen3-coder workarounds, merged 2026-08-25)
- https://github.com/ggml-org/llama.cpp/pull/22673 (MTP support, merged 2026-05-16; 35B-A3B benchmarks on NVIDIA)
- https://github.com/stared/benching-local-llms-on-apple-silicon (llama.cpp Q8 on M5 Max 128 GB: 93 tok/s, 105 with MTP)
- https://github.com/ggml-org/llama.cpp/discussions/4167 (M4 Pro 273 GB/s bandwidth reference)
- https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md (tool calling requires --jinja; no Qwen3.x native entry listed)
- https://willitrunai.com/can-run/qwen-3.6-35b-a3b-on-m4-pro-64gb (search extract: 26.7 tok/s modeled estimate, Q4_K_M)
- https://llmcheck.net/blog/qwen-36-35b-a3b-mac-new-number-one/ (search extract: M4 Pro ~86 tok/s 'estimated'; 32 tok/s Ollama table)
- https://omlx.ai/benchmarks/ivmnze5g and https://omlx.ai/benchmarks/gujo2ju6 (search extracts: MLX on M4 Pro 48 GB, 85.9 and 37.6 tok/s)
- https://modelfit.io/quant-compare/qwen3.6-35b-a3b/ (search extract: bartowski Q4_K_M 20.75 GB)
- https://allthings.how/qwen3-6-35b-a3b-gguf-quants-sizes-and-how-to-run-it/ (search extract: UD-Q4_K_XL ~21 GB)
- https://wandb.ai/site/inference-model/cw_qwen_qwen3.6-35b-a3b and https://openrouter.ai/qwen/qwen3.6-35b-a3b (search extracts: license apache-2.0, 35B/3B)
- https://huggingface.co/Qwen/Qwen3.6-35B-A3B/discussions/30 (search extract: shipped template tool-calling failure on vLLM; HF unreachable via proxy)

## 3. Corrected (confidence 0.8)

**Claim.** The current llama.cpp `llama-server` enforces schema-constrained JSON (`response_format` json_schema / GBNF `grammar`) on the Metal backend, supports continuous batching, `--jinja` tool calling, `--seed`, prompt caching and a Prometheus `/metrics` endpoint at the same time, with no feature disabled when `-np 1` is set.

**Correction applied.** All listed features exist in current llama-server and none is turned off by `-np 1`, but the claim is wrong in two load-bearing respects. (a) Schema enforcement and `--jinja` tool calling are mutually exclusive within one request: the server throws "Cannot use custom grammar constraints with tools." when `grammar` is sent alongside active tools, and when tools are active the template-generated tool grammar replaces any user `grammar`/`json_schema` (they are erased). You can enforce a schema on non-tool requests and use tool calling on other requests from the same server, but not both constraints on the same call. (b) Determinism is not "feature-grade": the README explicitly warns that prompt caching (default on) "can cause nondeterministic results" because logits are not bit-identical across batch sizes, so reproducibility requires `--no-cache-prompt` (or `cache_prompt: false`) and fixed batch sizes in addition to `--seed` and a single slot; and maintainers state determinism holds only "with some caveats, on the same hardware" — outputs will differ between the 8 GB/64 GB/128 GB Mac minis if they are different chip generations. Also note `-np` now defaults to -1 (auto) with unified KV, so `-np 1` must be set explicitly and changes KV-cache layout. The design should be restated as: one llama-server stack per node; schema-enforced JSON OR tool calling per request; determinism best-effort only on identical hardware with prompt cache disabled; `--metrics` must be passed explicitly.

**Sources.**

- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-common.cpp
- https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/chat.cpp
- https://github.com/ggml-org/llama.cpp/issues/23212

## 4. Corrected (confidence 0.92)

**Claim.** Claude Haiku 5.5 (claude-haiku-5-5) is priced at $0.10 input / $0.50 output per MTok for prompts up to 100K tokens, supports strict structured outputs via `output_config.format`, and has a documented prompt-cache read price (the plan assumes no cache credit because the $0.20/MTok figure cannot apply to a $0.10 input price).

**Correction applied.** Keep $0.10 input / $0.50 output per MTok for prompts ≤100K tokens and keep `output_config.format` structured outputs (Haiku 5.5 is officially supported). Replace the "no cache credit" assumption: Haiku 5.5 cache hits/refreshes are billed at $0.01/MTok (0.1x base input) for prompts ≤100K tokens, with 5-minute cache writes at $0.125/MTok and 1-hour cache writes at $0.20/MTok. The $0.20 figure the plan rejected is the 1h cache-write price, not a cache-read price. Classifier cost rows should model a stable system prompt/tool prefix as cached reads at $0.01/MTok (not $0.10), and should add the second rate card for any request whose total prompt (including cache reads and writes) exceeds 100K tokens: $0.50 input / $2.50 output / $0.05 cache read / $0.625 5m write / $1 1h write per MTok, applied per request. Batch API halves all of these ($0.05/$0.25 and $0.25/$1.25). Two related notes for the fallback path: Haiku 5.5 has no server-side `fallbacks` support (refusals must be handled client-side), and it rejects non-default `temperature`/`top_p`/`top_k` (so a `temperature=0` classifier must switch to structured outputs or an enum tool).

**Sources.**

- https://platform.claude.com/docs/en/about-claude/pricing (fetched directly via WebFetch; Model pricing table rows for Claude Haiku 5.5, footnotes 1-3, Batch processing table, Long context pricing section)
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs (fetched directly via WebFetch; supportedModels list includes claude-haiku-5-5; output_config.format is current, output_format deprecated)
- Bundled claude-api skill, shared/model-migration.md § Migrating to Claude Haiku 5.5 (local file: (bundled Claude API reference) shared/model-migration.md, lines 2234, 2292, 2349)
- WebSearch extracts (secondary, used only as corroboration): https://llmgateway.io/models/claude-haiku-5-5, https://braindetox.kr/en/posts/claude_haiku_5_5_release_pricing_2026.html, https://dev.to/hassann/claude-haiku-55-pricing-53cb, https://techenclave.com/news/items/claude-haiku-5-5-launches-with-0-10-input-pricing-for-shorter-prompts

## 5. Held (confidence 0.6)

**Claim.** gpt-oss-120b (OpenAI, Apache-2.0, 117B total / 5.1B active) runs on an M4 Max 128 GB Mac at about 75 tok/s decode and ~650 tok/s prefill with a peak memory footprint of about 59.5–63 GB in MXFP4, leaving room for the research sandbox and a second 21 GB GGUF beside it under a ~110 GB wired limit.

**Correction applied.** Not refuted, but should be restated with its conditions: per oMLX community rows (user-submitted, not vendor-verified), gpt-oss-120b-MXFP4-Q8 on an M4 Max 40-core/128 GB decodes at ~75 tok/s and prefills at ~650–730 tok/s only at 1k context; expect ~70 tok/s at 4k, ~55–65 tok/s on other submissions, ~30 tok/s at 16–32k and ~10–12 tok/s at 64k. Peak memory measured 59.5–60.5 GB (1k–32k context); '63 GB' is the checkpoint file size, not a measured peak. The 110 GB wired limit is a non-default sysctl (iogpu.wired_limit_mb) that must be set explicitly (default ~96 GB) and re-applied after reboot; with ~60 GB for the 120B model plus a 21 GB GGUF (~81 GB) the plan fits even under the 96 GB default, so the 110 GB assumption is unnecessary for the memory budget but the throughput assumption should be sized for long-context decode (~30 tok/s), not 75.

**Sources.**

- https://omlx.ai/benchmarks/yjj3dzhc
- https://omlx.ai/benchmarks/bljno9g0
- https://omlx.ai/benchmarks/ohfrl8hz
- https://omlx.ai/benchmarks/433vclar
- https://omlx.ai/benchmarks/performance/enyk9fi2
- https://omlx.ai/benchmarks?page=6759
- https://docs.nvidia.com/nemo/microservices/25.9.0/fine-tune/models/gpt-oss.html
- https://huggingface.co/the-qa-company/gpt-oss-120b/blame/main/README.md
- https://community.frame.work/t/tracking-will-the-ai-max-395-128gb-be-able-to-run-gpt-oss-120b/73280
- https://news.ycombinator.com/item?id=44822195
- https://mehmetbaykar.com/posts/increase-vram-apple-silicon-local-llm/
- https://llmconfigurator.com/en/guides/troubleshooting/increase-metal-vram-limit-apple-silicon
- https://markaicode.com/benchmarks/groq-mistral-large-m4-max-memory-benchmark/

## 6. Corrected (confidence 0.6)

**Claim.** The four 8 GB Mac minis are M1/M2-class machines (roughly 68–100 GB/s memory bandwidth) because the M4 Mac mini has never shipped with less than 16 GB, and their usable memory for model weights plus KV cache is only about 5–6 GB.

**Correction applied.** Rewrite the chip identification as a conditional, not a deduction: 'If the 8 GB minis are Apple silicon they must be M1 (2020, ~68 GB/s) or M2 (2023, 100 GB/s), since 8 GB was the base for those two generations and the M4 (2024) and M6/M5 Pro (2026) Mac minis start at 16 GB. However, the Late 2018 Intel Mac mini also shipped with 8 GB (DDR4-2666, Intel UHD 630, ~42 GB/s, no useful Metal GPU offload), so confirm via About This Mac before assigning any model to them; on an Intel 2018 mini even the shadow 4B would run CPU-only and well below 15 tok/s.' Keep the 5–6 GB usable-memory figure, but cite it as the macOS Metal default GPU working-set limit on an 8 GB M1 (recommendedMaxWorkingSetSize ≈ 5.46–5.73 GB per llama.cpp logs) rather than a community rule of thumb; the limit can be raised with sysctl iogpu.wired_limit_mb at the cost of starving macOS.

**Sources.**

- https://www.apple.com/mac-mini/specs (via WebSearch extract; direct fetch blocked)
- https://www.macworld.com/article/2504251/m4-mac-mini-is-smaller-mighter-and-can-connect-three-displays.html (via WebSearch extract)
- https://ifixit.com/Device/Mac_mini_%282024%29 (via WebSearch extract)
- https://support.apple.com/en-au/111912 (Apple Late 2018 Mac mini tech specs, via WebSearch extract; direct fetch blocked)
- https://everymac.com/systems/apple/mac_mini/specs/mac-mini-core-i5-3.0-late-2018-specs.html (via WebSearch extract)
- https://lowendmac.com/2018/mac-mini-late-2018/ (via WebSearch extract)
- https://www.trustedreviews.com/versus/mac-mini-m2-vs-mac-mini-m1-4296006 (via WebSearch extract)
- https://www.owc.com/blog/apple-updates-mac-mini-lineup-with-m5-pro-and-new-m6-chips (via WebSearch extract)
- https://www.mactrast.com/2026/08/apple-unveils-new-mac-mini-with-m6-and-m5-pro-mac-studio-with-m5-max-and-m5-ultra/ (via WebSearch extract)
- https://www.shacknews.com/article/150472/apple-mac-mini-studio-m5-m6-release-date (via WebSearch extract)
- https://github.com/ggml-org/llama.cpp/issues/2048 (fetched directly: recommendedMaxWorkingSetSize = 5461.34 MB on 8 GB M1)
- https://github.com/ggml-org/llama.cpp/issues/12574 (fetched directly: recommendedMaxWorkingSetSize = 5726.63 MB on Apple M1)
- https://github.com/ivanopcode/devnote-override-macos-metal-vram-cap (fetched directly)
- https://developer.apple.com/documentation/metal/mtldevice/recommendedmaxworkingsetsize (via WebSearch extract)

## 7. Held (confidence 0.93)

**Claim.** Ollama's MLX runner still processes requests strictly sequentially regardless of OLLAMA_NUM_PARALLEL (issue #17280 and PR #17317 open as of 2026-10-15), and mlx_lm.server (v0.32.2) still has no response_format / json_schema handling in handle_chat_completions.

**Correction applied.** No correction needed. Both findings remain true as of 2026-10-21: Ollama's MLX runner on main still has no parallel/continuous-batching path (issue #17280 and PR #17317 remain open; nothing in v0.40.5-v0.40.8 changes this), and mlx-lm 0.32.2 (still the latest release) and main both ignore response_format/json_schema in mlx_lm.server (issue #1007 open, unaddressed). The exclusion rationale for schema-bound and concurrent traffic still stands; the only stale detail is the "as of 2026-10-15" date, which can be updated to 2026-10-21.

**Sources.**

- https://github.com/ollama/ollama/issues/17280
- https://github.com/ollama/ollama/pull/17317
- https://github.com/ollama/ollama/pull/17317/files
- https://raw.githubusercontent.com/ollama/ollama/main/server/sched.go
- https://raw.githubusercontent.com/ollama/ollama/main/mlxrunner/client.go
- https://raw.githubusercontent.com/ollama/ollama/main/mlxrunner/server.go
- https://github.com/ollama/ollama/releases
- https://github.com/ollama/ollama/releases/tag/v0.40.8
- https://pypi.org/pypi/mlx-lm/json
- https://raw.githubusercontent.com/ml-explore/mlx-lm/v0.32.2/mlx_lm/server.py
- https://raw.githubusercontent.com/ml-explore/mlx-lm/main/mlx_lm/server.py
- https://github.com/ml-explore/mlx-lm/issues/1007
- https://github.com/ml-explore/mlx-lm/pulls?q=is%3Apr+response_format+OR+json_schema+OR+structured+output

## 8. Corrected (confidence 0.7)

**Claim.** On macOS 15+ the default GPU-wireable share of unified memory is roughly two-thirds to three-quarters of RAM (about 48 GB on a 64 GB mini), `sysctl iogpu.wired_limit_mb` raises it but does not persist across reboot, and wiring above roughly 85–88 % of RAM risks the IOGPUMemory kernel panic reported in mlx-lm issue #883 at 83.5 % wired.

**Correction applied.** Keep: default wireable share is 2/3 of RAM up to 32 GiB and 3/4 above (driver constant, not Apple-documented), so 48 GB on a 64 GB Mac mini; `sudo sysctl iogpu.wired_limit_mb=N` is lost at reboot unless re-applied via a LaunchDaemon (confirmed) or /etc/sysctl.conf (one Sonoma report, unconfirmed on Sequoia/Tahoe). Fix: do not present 85–88 % as a sourced safety ceiling. mlx-lm issue #883 shows an IOGPUMemory kernel panic at 83.5 % wired with the sysctl at its DEFAULT value, caused by mlx-lm's KV cache growing past the ~75 % wired limit it sets itself (fixed in PR #906 / mitigated by --kv-preallocate-size); it provides no threshold and the maintainer gave none. Any budget above the default 75 % (e.g. 53,248 / 57,344 MB on 64 GB, ~110,000 MB on 128 GB, "8 GB OS reserve") is an untested extrapolation; the only community guidance is "don't go to 100 %" and that exceeding the 3/4 default caused swapping on a 128 GB machine. The document should either budget to the default 75 % (49,152 MB on 64 GB, 98,304 MB on 128 GB) or label higher values as unsourced and keep mlx-lm updated past PR #906 / use KV preallocation.

**Sources.**

- https://github.com/ml-explore/mlx-lm/issues/883
- https://github.com/ggml-org/llama.cpp/discussions/2182
- https://github.com/ggml-org/llama.cpp/discussions/2182?page=2
- https://raw.githubusercontent.com/ml-explore/mlx/main/python/src/memory.cpp
- https://raw.githubusercontent.com/ml-explore/mlx/main/mlx/backend/metal/allocator.cpp
- https://raw.githubusercontent.com/ml-explore/mlx-lm/main/mlx_lm/utils.py
- https://raw.githubusercontent.com/ml-explore/mlx-lm/main/mlx_lm/server.py
- https://developer.apple.com/tutorials/data/documentation/metal/mtldevice/recommendedmaxworkingsetsize.json

