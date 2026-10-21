# Hosted-model fact sheet for the OID bots (non-Anthropic), checked 2026-10-21

**Method note.** Every direct fetch of a vendor page (developers.openai.com, ai.google.dev, docs.x.ai, api-docs.deepseek.com, mistral.ai, groq.com, cerebras.ai, together.ai, fireworks.ai, openrouter.ai, alibabacloud.com) failed with DNS `ENOTFOUND` behind the sandbox proxy, so **no fact below is VERIFIED (page read)**. Facts tagged **EXTRACT** come from search-engine excerpts of the vendor's own page (URL given); **UNVERIFIED** means a third-party aggregator or a figure I could not corroborate. Prices are USD per 1M tokens (MTok), standard tier, unless stated. Where current excerpts conflict, I say so rather than pick. Anthropic figures are taken as given in the task and not re-researched.

---

## 1. OpenAI

| Model | Input | Cached in | Output | Context / max out | Status | Source |
|---|---|---|---|---|---|---|
| gpt-5.5 (flagship) | $5.00 | $0.50 | $30.00 | ~1.05M / 128K; >272K input billed 2x in / 1.5x out | current (Apr-2026 release) | EXTRACT https://developers.openai.com/api/docs/models/gpt-5.5 , https://developers.openai.com/api/docs/changelog |
| gpt-5.4 | $2.50 | $0.25 | $15.00 | ~1.05M / 128K; same >272K surcharge | current | EXTRACT https://developers.openai.com/api/docs/models/gpt-5.4 |
| gpt-5.4-mini | $0.75 | $0.075 | $4.50 | 400K / 128K | current | EXTRACT https://openai.com/index/introducing-gpt-5-4-mini-and-nano/ , https://developers.openai.com/api/docs/models/gpt-5.4-mini |
| gpt-5.4-nano | $0.20 | $0.02 | $1.25 | 400K / 128K | current, but one excerpt of the model page shows a "Deprecated" badge; treat as unresolved | EXTRACT https://developers.openai.com/api/docs/models/gpt-5.4-nano |
| gpt-5-mini / gpt-5-nano | $0.25 / $0.05 | $0.025 / $0.005 | $2.00 / $0.40 | 400K | **deprecated**, pages point to 5.4 successors | EXTRACT https://developers.openai.com/api/docs/models/gpt-5-mini , https://developers.openai.com/api/docs/models/gpt-5-nano |
| gpt-5.5-pro | n/a in excerpts | | | | exists | EXTRACT https://developers.openai.com/api/docs/models/gpt-5.5-pro |

- **Batch / Flex / Fast.** Batch API = 50% off, 24-h turnaround, separate higher rate-limit pool. Flex (`service_tier: flex`) = 50% off, beta, slower, 429 "Resource Unavailable" possible and not charged. Priority was renamed **Fast mode** on 2026-07-30 at **2.5x** standard (GPT-5.5: $12.50 / $75.00); cached input keeps its discount. Regional endpoints +10%. EXTRACT https://openai.com/index/introducing-gpt-5-5/ , https://developers.openai.com/api/docs/guides/batch , https://developers.openai.com/api/docs/guides/flex-processing , https://openai.com/api-priority-processing/
- **Structured outputs & tools.** GPT-5.5, 5.4, 5.4-mini, 5.4-nano all list function calling + structured outputs (strict JSON schema, Responses API `text.format` / strict tool schemas). EXTRACT model pages above. Third-party claim of "100% schema compliance" is UNVERIFIED (https://www.codewords.ai/blog/openai-structured-outputs-json-schema).
- **Data.** API data not used for training since 2023-03-01 unless opt-in; abuse-monitoring logs retained up to 30 days; **ZDR** is approval-based (2026-08-19 post "Our commitment to zero data retention"), not default on pay-as-you-go, endpoint-dependent. EXTRACT https://openai.com/index/our-commitment-to-zero-data-retention ; UNVERIFIED detail https://vantagepoint.io/docs/openai-api-data-controls
- **Rate limits (what matters at ~1,000 calls/day).** OpenAI collapsed five paid tiers into three: **Build / Launch / Grow** (Grow at $500 cumulative). gpt-5.4-mini: Build 5,000 RPM / 2M TPM; Launch 10,000 RPM / 10M TPM; Grow 30,000 RPM / 180M TPM. 1,000 calls/day of 8K tokens is ~0.4% of Build's TPM; not a constraint. EXTRACT https://community.openai.com/t/update-to-openai-api-rate-limits/1403852 , https://developers.openai.com/api/docs/models/gpt-5.4-mini
- **SLA.** 99.9% uptime SLA exists only on **Scale Tier / Fast mode for Enterprise agreements** (p50 latency SLA in 5-min windows); nothing for self-serve. Scale Tier covers models before "GPT-5.6"; newer go to a Reserved Tier (name only, not looked up). Public status page shows frequent 2026 incidents (e.g., 2026-03-04 elevated API error rates from an internal scheduler; 2026-03-24 Realtime SIP, 2.9 h). EXTRACT https://openai.com/api-scale-tier/ , https://help.openai.com/en/articles/11647665-priority-processing-faq , https://status.openai.com/incidents/01KJXQDJ6P1CG5YNXKZRY2H6RX/write-up ; UNVERIFIED counts https://isdown.app/status/openai/outage-history
- **Fine-tuning: important.** OpenAI's pricing page says the **fine-tuning platform is being wound down**: closed to new users, existing users can create jobs "for the coming months", tuned models served until base deprecation. gpt-5.4-mini/nano pages list fine-tuning "Not supported". Only remaining training price in excerpts is RFT on o4-mini at $100/h. Older gpt-4.1-nano SFT ~ $1.50/M train with $0.20/$0.80 inference is UNVERIFIED aggregator data and probably unavailable to a new account anyway. EXTRACT https://developers.openai.com/api/docs/pricing , https://developers.openai.com/api/docs/models/gpt-5.4-mini ; UNVERIFIED https://aicostcheck.com/blog/ai-fine-tuning-costs-2026

## 2. Google Gemini (Gemini Developer API; Vertex "Gemini Enterprise Agent Platform" mirrors prices)

| Model | Input | Cached | Output | Context | Notes | Source |
|---|---|---|---|---|---|---|
| gemini-3.1-pro (preview) | $2.00 (≤200K) / $4.00 (>200K) | $0.20 / $0.40 + $4.50/M-tok-hour storage | $12.00 / $18.00 | 1,048,576 in / 65,536 out | batch $1.00 / $6.00 | EXTRACT https://ai.google.dev/gemini-api/docs/pricing , https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview |
| gemini-3.8-flash / 3.7-flash / 3.6-flash | **$0.75 intro through 2026-12-31**, then $1.50 from 2027-01-01 | ~90% discount on cache (not itemised for 3.8) | **$3.75 intro**, then $7.50 | 1M / 64K (3.6 Flash page) | batch 3.8 Flash $0.375 / $1.875 to year-end | EXTRACT https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing , https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6 |
| gemini-3.5-flash | $1.50 | | $9.00 | 1M | superseded by 3.6+ | EXTRACT https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6 |
| gemini-3.5-flash-lite | $0.30 | $0.03 (+storage) | $2.50 | 1,048,576 / 65,536; released 2026-07-21 | batch $0.15 / $1.25 | EXTRACT https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite , https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash-lite |
| gemini-3.1-flash-lite | $0.25 | | $1.50 | 1,048,576 | batch $0.125 / $0.75; cheapest current Google tier | EXTRACT https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/ , https://ai.google.dev/gemini-api/docs/pricing |
| gemini-2.5-flash / 2.5-flash-lite | $0.30 / $0.10 | | $2.50 / $0.40 | 1M | 2.5 Flash reportedly deprecates 2026-10-16 (UNVERIFIED https://www.cloudzero.com/blog/gemini-pricing/) | EXTRACT pricing page |

- A "Gemini 4 Argon" row appears in the structured-output support table excerpt; I could not corroborate it anywhere else. UNVERIFIED. (https://ai.google.dev/gemini-api/docs/structured-output)
- **Discounts.** Flex 50%, Batch 50%, context caching ~90% off plus prorated storage. Function declarations count toward input tokens from Gemini 3.5 onward. EXTRACT https://ai.google.dev/gemini-api/docs/optimization , Vertex pricing page.
- **Structured outputs & tools.** `response_json_schema` (legacy generateContent) or `response_format` (new Interactions API); function calling incl. parallel/compositional on 3.x and 2.5; function calling combinable with structured output on Gemini 3 series. EXTRACT https://ai.google.dev/gemini-api/docs/structured-output , https://ai.google.dev/gemini-api/docs/tools
- **Data.** Paid Services: prompts/responses **not** used to improve products, processed under DPA. Unpaid (free tier, and arguably AI Studio even on a billed project): used for product improvement and human review. Link a billing account → paid terms. EXTRACT https://ai.google.dev/gemini-api/terms ; interpretation caveat UNVERIFIED https://simonwillison.net/2024/Oct/17/gemini-terms-of-service
- **Rate limits.** Four dimensions (RPM, RPD, TPM, batch enqueued tokens), per project. Tier 1 = billing linked; Tier 2 = $250 spend + 30 days. Google no longer publishes a flat RPM/TPM table in excerpts; the only Tier-1 number found is 10,000,000 batch-enqueued tokens for 3.5 Flash-Lite (Tier 2: 500M, Tier 3: 1B). Forum reports of inconsistent paid-tier quotas. EXTRACT https://ai.google.dev/gemini-api/docs/rate-limits ; UNVERIFIED https://discuss.ai.google.dev/t/regarding-gemini-models-rate-limit-in-paid-tier/143557
- **SLA.** Vertex "Gemini Online Inference API" SLA = **99.5%** monthly uptime for generateContent/streamGenerateContent (95% for "shorter-availability" models); the Developer API (ai.google.dev) has no SLA. Third-party "99.95%" claims are UNVERIFIED. EXTRACT https://cloud.google.com/vertex-ai/generative-ai/sla
- **Tuning.** Supervised fine-tuning is a Vertex feature (not the Developer API). Pricing table lists **Gemini 3.5 Flash SFT/RFT at $0.01 per 1,000 "count"**, 2.5 Flash $0.005, 2.5 Flash-Lite $0.0015; if "count" = training tokens that is ~$10 / $5 / $1.50 per 1M training tokens (tokens × epochs), unit not stated in excerpt. Supported-model doc still lists 2.5 Pro/Flash/Flash-Lite and 2.0 Flash/Flash-Lite; 3.5 Flash limits page says tuning runs in us-central1 / europe-west4. Tuned-model inference billed separately. EXTRACT https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing , https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-supervised-tuning

## 3. xAI Grok

| Model | Input (<200K / ≥200K) | Cached | Output (<200K / ≥200K) | Context | Rate limit (model page) | Source |
|---|---|---|---|---|---|---|
| grok-4.7 (flagship) | $2.00 / $4.00 | $0.50 | $6.00 / $12.00 | 500K | 150 RPS, 50M TPM | EXTRACT https://docs.x.ai/developers/models/grok-4.7 , https://docs.x.ai/developers/pricing |
| grok-4.6 | $2.00 | | $6.00 | 500K | | EXTRACT https://docs.x.ai/developers/pricing |
| grok-4.5 | not in excerpt | | | 500K; batch "Not supported" on model page | | EXTRACT https://docs.x.ai/developers/models/grok-4.5 |
| grok-4.3 (cheapest general model with batch) | $1.25 | not in excerpt | $2.50 | 1M | 37 RPS, 10M TPM | EXTRACT https://docs.x.ai/developers/models/grok-4.3 |
| grok-build-0.1 | $1.00 | | $2.00 | | no batch discount | EXTRACT https://docs.x.ai/developers/pricing |
| grok-4-fast ($0.20 / $0.50, 2M ctx) | **retired**; "Grok 4.7 Fast" ($4/$12) is Cursor/Grok Build only, not public API | | | | | EXTRACT docs.x.ai pricing; UNVERIFIED https://guptadeepak.com/ai-models/xai/grok-4-fast-reasoning/ |

- Batch: 20% discount on grok-4.7/4.6/4.5/4.3/4.20 per pricing page, but the 4.7 and 4.5 model pages say "Batch API: Not supported" — unresolved conflict. US regional endpoint 1.1x (4.7 and 4.6 only). EXTRACT https://docs.x.ai/developers/pricing
- Structured outputs (`response_format` / Responses `text.format` json_schema strict) and function calling, web/X search, code execution on grok-4.7. EXTRACT https://docs.x.ai/developers/model-capabilities/text/structured-outputs , https://docs.x.ai/developers/tools/function-calling
- Data: no training on API data without permission; requests stored encrypted **30 days** for abuse review, then deleted; ZDR opt-in team-wide in console, disables stateful Responses, Files/Collections, Batch. EXTRACT https://docs.x.ai/developers/faq/security.md
- SLA: none found in excerpts. Note for a desk: xAI's X-search tool is the only first-party API with native X/Twitter search, relevant to X Summarizer/Macro Bot.

## 4. DeepSeek API

- Lineup after 2026-09-10: **`deepseek-flash` (DeepSeek-V4.1-Flash, upgraded to -1017 on 2026-10-17, pricing unchanged)** and `deepseek-v4-pro`. Legacy `deepseek-chat`/`deepseek-reasoner` aliases retired 2026-07-24 (UNVERIFIED https://www.morphllm.com/deepseek-api). Changelog says V4-Pro API continues after 2026-09-14, while the V4.1-Flash post says Pro requests route to V4.1-Flash at Flash rates from 2026-09-14 — unresolved. EXTRACT https://api-docs.deepseek.com/news/news260910/ , https://api-docs.deepseek.com/updates/
- **deepseek-flash price (reading of the two-column table, column mapping inferred):** cache-hit input $0.006 peak / $0.003 off-peak; cache-miss input $0.30 / $0.15; output $1.20 / $0.60; 1M context, 384K max output; off-peak = 50% of peak (hours not in excerpt). The homepage still shows older V4-Flash figures ($0.14 miss / $0.28 out) — stale. EXTRACT https://api-docs.deepseek.com/quick_start/pricing/ , https://www.deepseek.com/en/platform/
- Search & Fetch tools: $0.75 per 1,000 calls from 2026-10-31; Search 100 QPS, Fetch 25 QPS. EXTRACT https://api-docs.deepseek.com/guides/search/
- Structured output: `response_format: json_object` (JSON mode, not schema-enforced; docs warn to prompt for JSON and set max_tokens), Responses API text format, function calling up to 128 tools, parallel calls; docs warn of hallucinated parameters. EXTRACT https://api-docs.deepseek.com/guides/responses_api/ , https://api-docs.deepseek.com/api/create-response/
- Rate limits: documented on a "Rate Limit & Isolation" page not returned; 429 on concurrency/QPS. EXTRACT https://api-docs.deepseek.com/quick_start/error_codes/
- Data: privacy policy (dated 2024-05-15) — data stored in the PRC, retained for the life of the account, training opt-out exists but no API-specific ZDR, no SOC 2 excerpt found; Chinese jurisdiction. For a US options desk this is the weakest data posture of any vendor here. EXTRACT https://chat.deepseek.com/downloads/DeepSeek%20Privacy%20Policy.html ; UNVERIFIED https://www.kaspersky.com/blog/deepseek-privacy-and-security/54643/ . Mitigation: run DeepSeek weights via Fireworks/Together (same price, US-hosted, ZDR available).

## 5. Alibaba Cloud Model Studio (Qwen, Singapore/international region)

| Model | Input | Output | Tiers | Source |
|---|---|---|---|---|
| qwen3.7-plus | $0.40 (≤256K) / $1.20 (256K–1M) | $1.60 / $4.80 | pricing page labels these as list price with a limited-time 20% discount | EXTRACT https://www.alibabacloud.com/help/en/model-studio/qwen3-7-plus , https://www.alibabacloud.com/help/en/model-studio/model-pricing |
| qwen3.7-flash (snapshot 2026-07-15) | $0.03 (≤32K) / $0.10 (32–256K) / $0.20 (256K–1M) | $0.13 / $0.40 / $0.80 | cheapest hosted tier in this sheet | EXTRACT https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash |
| qwen-plus (=2025-12-01) | $0.40 | $1.20 ($4.00 thinking) | | EXTRACT https://www.alibabacloud.com/help/en/model-studio/qwen-plus |
| qwen-flash (=2025-07-28) | $0.05 | $0.40 | | EXTRACT https://www.alibabacloud.com/help/en/model-studio/qwen-flash |
| qwen3.8-flash | $0.15 / $0.47 (Together's hosted price, not Alibaba's) | | | EXTRACT https://docs.together.ai/docs/changelog |

- Batch 50% off, context-caching discount, free quotas per model. Data: "will not use your business data to train, fine-tune or improve any foundation model without separate consent"; default retention of prompts/responses **≤30 days**; ZDR for enterprise customers of the International site (24-h encrypted cache then deleted). Regions: Singapore, US-Virginia, Frankfurt, Beijing. EXTRACT https://www.alibabacloud.com/help/en/model-studio/data-retention-policy
- Rate limits / SLA: not in excerpts. Structured output / tool calling: OpenAI-compatible endpoint; not confirmed per model in excerpts (UNVERIFIED).

## 6. Mistral API

| Model | Input | Cached | Output | Notes | Source |
|---|---|---|---|---|---|
| mistral-large-4 | $1.36 | $0.14 | $4.18 | listed on API pricing page; relation to Large 3 unclear | EXTRACT https://docs.mistral.ai/inference/pricing |
| mistral-medium-3.5 | $1.50 | $0.15 | $7.50 | weights not open per one source (conflict) | EXTRACT https://mistral.ai/pricing/api/ |
| mistral-large-3 (675B MoE, 41B active) | $0.50 | $0.05 | $1.50 | | EXTRACT https://docs.mistral.ai/models/mistral-large-3-25-12 |
| mistral-small-4 | $0.15 | $0.015 | $0.60 | Apache-2.0 open weights | EXTRACT https://mistral.ai/pricing/api/ , https://mistral.ai/news/mistral-small-4/ |
| ministral-3-14b / 8b / 3b | $0.20 / $0.15 / $0.10 | $0.02 / $0.015 | $0.20 / $0.15 / $0.10 | 256K ctx (14B); Apache-2.0 | EXTRACT https://docs.mistral.ai/models/ministral-3-8b-25-12 , https://docs.mistral.ai/models/model-cards/ministral-3-14b-25-12 |

- Batch 50% off; cached input up to 90% off. EXTRACT https://mistral.ai/pricing/
- Rate limits: RPS + TPM + tokens/month, per org/workspace; Free mode default; Tier 2 >$20, Tier 3 >$100, Tier 4 >$500 cumulative billed; >$2,000 contact support. Exact RPS not published in excerpts. EXTRACT https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them , https://docs.mistral.ai/admin/billing-usage/usage-limits
- Data: **Free mode may train on inputs/outputs**; pay-as-you-go has an "Anonymous improvement data" toggle to disable (default state not stated in excerpts — treat as on until you flip it); inputs/outputs kept 30 rolling days for abuse monitoring; ZDR only on pay-as-you-go stateless calls, requested via support. EXTRACT https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training , https://legal.mistral.ai/terms/privacy-policy/ , https://docs.mistral.ai/admin/monitor-comply/zero-data-retention
- Fine-tuning: the docs page is marked **deprecated / no longer actively supported** (last pricing: $4 minimum per job + $2/model/month storage). EXTRACT https://docs.mistral.ai/resources/deprecated/finetuning
- SLA: Enterprise Priority Tier only (custom). EXTRACT https://docs.mistral.ai/inference/priority-tier

## 7. Groq (GroqCloud)

- Production models: **openai/gpt-oss-120b $0.15 / $0.60, ~500 tok/s; gpt-oss-20b $0.075 / $0.30, ~1,000 tok/s**; Llama 3.1 8B and 3.3 70B now "Contact Sales" (enterprise). Preview: qwen/qwen3.8-27b ~450 tok/s at $0.80 / $4.00 (name unusual; single excerpt). Changelog history: Qwen3-32B $0.29/$0.59 ~491 tok/s; Kimi K2-0905 $1.00/$3.00; Llama 4 Scout ~607 tok/s — may be retired. EXTRACT https://console.groq.com/docs/models , https://console.groq.com/docs/model/openai/gpt-oss-120b , https://console.groq.com/docs/changelog
- Batch 50% off, prompt caching 50% off, Flex tier = 10x rate limits when capacity allows (fast timeouts under load). Developer tier limit for gpt-oss: 250K TPM / 1K RPM — ample for 1,000 calls/day. Billing thresholds $1/$10/$100/$500/$1,000. EXTRACT https://console.groq.com/docs/batch , https://console.groq.com/docs/rate-limits , https://console.groq.com/docs/billing-faqs (rate-limit page excerpt is old; verify in console)
- Data: "By default, Groq does not retain customer data for inference requests"; batch files 30 days; no training on customer data (Services Agreement); ZDR eligible on inference endpoints. EXTRACT https://console.groq.com/docs/your-data , https://console.groq.com/docs/legal/services-agreement
- Structured outputs/tool calling: OpenAI-compatible; model-dependent (not itemised in excerpts). SLA: enterprise "Performance Tier" only, no public price. EXTRACT https://console.groq.com/docs/performance-tier

## 8. Cerebras

- Production: **gpt-oss-120b $0.35 / $0.75 at ~3,000 tok/s** (public models endpoint returns $0.00000035/$0.00000075 per token). Catalog also lists qwen-3.8-27b (64K free / 128K paid context; price not in excerpt; query `https://api.cerebras.ai/public/v1/models/qwen-3.8-27b`). Older listings: Qwen3-32B $0.40/$0.80 ~2,400 tok/s; zai-glm-4.7 preview $2.25/$2.75 deprecated 2026-08-17 (UNVERIFIED). EXTRACT https://inference-docs.cerebras.ai/api-reference/models/public-models , https://inference-docs.cerebras.ai/models/overview , https://www.cerebras.ai/blog/cerebras-launches-openai-s-gpt-oss-120b-at-a-blistering-3-000-tokens-sec
- Tiers: Free trial ($5 credit, 30K uncached TPM); Pay-as-you-go from $10 removes hourly/daily caps; developer limits gpt-oss-120b 1M uncached TPM / 3M total TPM / 1K RPM; qwen-3.8-27b 150K uncached / 750K total / 300 RPM. EXTRACT https://inference-docs.cerebras.ai/support/rate-limits , https://inference-docs.cerebras.ai/support/change-log
- Data: privacy policy "we do not retain inputs and outputs associated with ... inference"; batch files 7 days; no explicit training statement found. UNVERIFIED summary https://www.developersdigest.tech/models/data-retention/cerebras . Cerebras Code subscriptions ($50 Pro / $200 Max) are chat-coding plans, not API. SLA: none public. Catalog is small and churns; do not build a critical path on a single Cerebras model.

## 9. Together AI (hosted open weights)

- Serverless chat prices (changelog/docs vs pricing page disagree on some rows): gpt-oss-120B $0.15/$0.60; **GLM-5.3 Flash $0.15 / $0.50, cached $0.03**; Qwen3.8 Flash $0.15/$0.47; MiniMax M3 $0.30/$1.20 (cached $0.06); DeepSeek V4 Flash 0731 $0.14/$0.28; Kimi K3 $3.00/$15.00; GLM-5.1 $1.40/$4.40; Llama 3.3 70B $1.04/$1.04; DeepSeek V4 Pro quoted anywhere from $1.32–$2.10 in / $3.48–$4.40 out (conflicting). Turbo (FP8) / Lite (INT4) / Reference (FP16) endpoint variants priced differently. EXTRACT https://docs.together.ai/docs/serverless/models , https://docs.together.ai/docs/changelog , https://www.together.ai/pricing ; UNVERIFIED https://www.morphllm.com/together-ai-pricing
- Data: **default stores prompts/responses and may use them for product improvements**; ZDR is an org-level toggle ("Store prompts and model responses" = No), forward-only, disables passthrough models; no training without explicit consent regardless of ZDR. EXTRACT https://docs.together.ai/docs/zero-data-retention , https://www.together.ai/privacy
- Fine-tuning: LoRA SFT ~$0.34/M tokens (Qwen3.5 9B), $0.40 (gpt-oss-20B), $2.03 (Llama 3.3 70B), $15 (Kimi K2.6); $4 minimum; billed tokens × epochs (+ validation); DPO ~2.5x. Two tables on the page disagree slightly. EXTRACT https://www.together.ai/pricing , https://docs.together.ai/docs/fine-tuning/pricing , https://www.together.ai/blog/together-ai-expands-fine-tuning-service-with-more-models-live-metrics-and-finer-controls
- Rate limits / SLA: not in excerpts; dedicated endpoints for guaranteed capacity.

## 10. Fireworks AI (hosted open weights)

- Serverless: **DeepSeek V4.1 Flash $0.30 / cached $0.006 / $1.20**; GLM-5.3 $1.40 / $0.26 / $4.40; GLM-5.2 $1.40/$0.14/$4.40; Qwen 3.7 Plus $0.50/$0.10/$3.00; gpt-oss-120B $0.15/$0.015/$0.60; size-based fallback rates $0.10 (<4B), $0.20 (4–16B), $0.90 (>16B), $0.50–$1.20 MoE. Batch 50% off; Priority tier ~1.25–1.5x. Billing reportedly moved to prepaid on 2026-07-01 (UNVERIFIED https://flexprice.io/pricing-index/fireworks-ai). EXTRACT https://docs.fireworks.ai/serverless/pricing , https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash , https://fireworks.ai/models/fireworks/glm-5p3
- Data: **zero retention by default for open models** (volatile memory only), content not used to train; enforced account-wide ZDR is Enterprise and blocks batch/fine-tuning/stored responses. EXTRACT https://docs.fireworks.ai/guides/security_compliance/data_handling
- Fine-tuning: LoRA from $0.50/M training tokens (≤16B), full SFT from $1.00/M; tuned model served at base-model price; some models (Qwen 3.7 Plus) limited availability. EXTRACT https://fireworks.ai/blog/qwen-3p7-plus ; UNVERIFIED https://www.morphllm.com/fireworks-ai-pricing
- SLA / rate limits: not in excerpts.

## 11. OpenRouter (router)

- Passes through provider token prices with no markup; **platform fee 5.5% on Standard, 8% on Business, charged at credit purchase** ($0.80 minimum); BYOK: $25,000/month list-price allowance free, then 5% of list. Credits reportedly expire after 365 days (UNVERIFIED). EXTRACT https://openrouter.ai/pricing , https://openrouter.ai/docs/guides/overview/auth/byok
- Rate limits: none plan-based on paid models (provider limits apply); free models 20 RPM / 50 RPD (1,000 RPD after $10 credit). EXTRACT https://openrouter.ai/docs/api_reference/limits
- Data: prompts/completions **not logged by default** (metadata only); opt-in logging gives 1% discount and retains ≥3 months; data-policy filter blocks providers that retain/train; ZDR routing on every plan; applies to BYOK too. EXTRACT https://openrouter.ai/docs/faq , https://openrouter.ai/docs/guides/features/input-output-logging
- Reliability: provider routing deprioritizes any provider with outages in the last 30 s; `models: [...]` fallback list; failed attempts not charged. No published uptime SLA. EXTRACT https://openrouter.ai/pricing , https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/
- Relevance: one key + one schema for Rose/Hal fallback across OpenAI/Gemini/Grok/open models; cost = 5.5% tax.

## 12. Fine-tuning a small classifier (First-Seen Bot, Peanut/News, X Summarizer)

| Option | Cost | Status | Fit for a -2..+2 / gate-flag classifier |
|---|---|---|---|
| OpenAI SFT | n/a | **Platform winding down; closed to new users; 5.4-mini/nano not tunable** | Rule out. EXTRACT https://developers.openai.com/api/docs/pricing |
| Google Vertex SFT (Gemini 3.5 Flash / 2.5 Flash / 2.5 Flash-Lite) | $0.01 / $0.005 / $0.0015 per 1K "count" (≈$10 / $5 / $1.50 per M training tokens if count = tokens) + tuned inference | live; us-central1/europe-west4 | Viable; 200-item gold set × a few thousand training items ≈ <1M tokens ≈ $1–$10 per run. EXTRACT Vertex pricing page |
| Together LoRA | $0.34–$0.40/M tokens (Qwen3.5 9B, gpt-oss-20B), $4 min | live | Cheap; served at base price |
| Fireworks LoRA | $0.50/M (≤16B) | live | Cheap; served at base price |
| Mistral | deprecated | | Rule out |
| **Local SetFit** (sentence-transformer + logistic head) | $0 | mature; ModernBERT-base SetFit cards exist at 8K seq len | Best first move for 800 items/day: 8–64 labelled examples/class, trains in minutes on CPU/MPS, runs easily on an 8 GB mini. EXTRACT https://huggingface.co/blog/setfit , https://arxiv.org/pdf/2209.11055 ; ModernBERT cards UNVERIFIED (https://huggingface.co/juliusherzig/setfit-modernbert-studien3) |
| **Local mlx-lm LoRA** (Qwen3-0.6B / 1.7B / 4B, or Ministral-3-3B/8B, Apache-2.0) | $0 | `mlx_lm.lora` works with a YAML config; Qwen3-0.6B config example exists; batch size 1 recommended on 16 GB | 0.6B–1.7B fits an 8 GB mini for inference; train on the 64 GB mini. No published M4 throughput numbers were found (willitrunai 8.4 tok/s figure is a formula, UNVERIFIED) — benchmark prefill tok/s yourself. EXTRACT https://docs.swanlab.cn/en/guide_cloud/integration/integration-mlx-lm.html ; UNVERIFIED https://kdnuggets.com/fine-tuning-language-models-on-apple-silicon-with-mlx |

## 13. Finance-specific small models (headline sentiment)

| Model | Size | Reported result | Caveat | Source |
|---|---|---|---|---|
| FinBERT (ProsusAI, 2019) | 110M | 97% acc on Financial PhraseBank (FPB) 100%-agreement subset; 86% on full FPB | numbers depend on agreement subset | EXTRACT https://arxiv.org/pdf/1908.10063 |
| FinBERT zero-shot on 2025 tech headlines (jses-2026-0003, 894 pairs) | | **0.637 acc / 0.626 macro-F1**; fine-tuned 0.585 / 0.532 (n.s.) | the most relevant 2026 headline-level number; shows FPB scores do not transfer to live headlines | EXTRACT https://reference-global.com/article/10.2478/jses-2026-0003 |
| FinSense-ModernBERT (AnkitAI) | 149M | 0.8675 acc / 0.8589 macro-F1 on FPB vs FinBERT 0.8423 same harness | self-reported model card | UNVERIFIED https://huggingface.co/AnkitAI/FinSense-ModernBERT-Financial-News-Sentiment |
| FinBERT fine-tuned on 35–40K LLM-labelled headlines (Pugnola, 2026) | 110M | 0.847 acc / 0.810 macro-F1; judge agreement only 85% | label-noise ceiling; dual-LLM-judge pipeline is a useful template for your 200-item gold set | UNVERIFIED https://github.com/Pugnola/finance-news-sentiment |
| FinGPT v3.3 (Llama-2-13B LoRA) | 13B | weighted F1: FPB 0.882, FiQA-SA 0.874, TFNS 0.903; independent eval 87.62% FLARE-FPB acc | self-reported + one paper; too big for the 8 GB minis, fits 64 GB | EXTRACT https://arxiv.org/pdf/2307.10485 , https://arxiv.org/pdf/2507.08015 |
| phi-3-mini LoRA on FPB | 3.8B | ~88% acc vs FinBERT 88.93% | shows a generic 4B model + LoRA matches FinBERT | EXTRACT https://arxiv.org/pdf/2410.01987 |
| Fin-R1 (Qwen2.5-7B SFT+RL) | 7B | avg 75.2 on financial reasoning (FinQA 76.0, ConvFinQA 85.0); no FPB number in excerpts | reasoning, not sentiment | EXTRACT https://arxiv.org/abs/2503.16252v3 |
| Llama-3.1-8B QLoRA on FinGPT data (community) | 8B | 0.9748 acc FPB in-domain, 0.9402 FiQA-SA OOD | unverified upload | UNVERIFIED https://huggingface.co/jhon53/Llama3_1_8B_Finance_QLoRA-merged-16bit |
| GPT-4-class LLMs | | ~90–93% on FPB-type tasks, but ~300–500x cost and 20–40x latency vs FinBERT-class | | EXTRACT https://arxiv.org/pdf/2606.03457 |

Takeaway: no 2025–2026 "FinBERT successor" has an independent headline-level benchmark; the only headline study (0.64 acc) argues for building your own gold set and scoring any model (FinBERT, ModernBERT-SetFit, Haiku/nano/Flash-Lite at temperature 0) against it, exactly as the report's precision-floor rule requires.

## 14. Cost per 1,000 calls (standard tier; computed from the prices above; cache credit applied only where a cached-input price is published)

Assumptions: (a) 1,500 in + 150 out, no cache; (b) 8,000 in + 600 out with **75% of input served from cache** (6,000 cached / 2,000 fresh); (c) 40,000 in + 4,000 out, no cache. Batch halves OpenAI/Google/Groq/Fireworks/Mistral/Alibaba/Anthropic rows; xAI batch −20%. Anthropic Fable cache-read price not given, so no credit; Haiku computed without cache credit (the $0.20 cache-read figure cannot apply at $0.10 input; treat Haiku (b) as an upper bound).

| Model | (a) classifier | (b) rationale | (c) research |
|---|---|---|---|
| Anthropic Fable 5.1 ($10/$50) | $22.50 | $110.00 | $600.00 |
| Anthropic Opus 5.5 ($4/$0.20/$20) | $9.00 | $21.20 | $240.00 |
| Anthropic Sonnet 5.5 ($2/$0.20/$10) | $4.50 | $11.20 | $120.00 |
| Anthropic Haiku 5.5 ($0.10/$0.50) | $0.23 | ≤$1.10 | $6.00 |
| OpenAI GPT-5.5 | $12.00 | $31.00 | $320.00 |
| OpenAI GPT-5.4 | $6.00 | $15.50 | $160.00 |
| OpenAI GPT-5.4 mini | $1.80 | $4.65 | $48.00 |
| OpenAI GPT-5.4 nano | $0.49 | $1.27 | $13.00 |
| Google Gemini 3.1 Pro (≤200K) | $4.80 | $12.40 | $128.00 |
| Google Gemini 3.8 Flash (intro to 2026-12-31) | $1.69 | $4.20 | $45.00 |
| Google Gemini 3.6 Flash (standard $1.50/$7.50) | $3.38 | $8.40 | $90.00 |
| Google Gemini 3.5 Flash-Lite | $0.82 | $2.28 | $22.00 |
| Google Gemini 3.1 Flash-Lite | $0.60 | $1.55 | $16.00 |
| xAI Grok 4.7 | $3.90 | $10.60 | $104.00 |
| xAI Grok 4.3 (cache rate assumed 25% of input, UNVERIFIED) | $2.25 | $5.88 | $60.00 |
| DeepSeek V4.1-Flash, peak | $0.63 | $1.36 | $16.80 |
| DeepSeek V4.1-Flash, off-peak | $0.32 | $0.68 | $8.40 |
| Alibaba qwen3.7-plus (no cache credit) | $0.84 | $4.16 | $22.40 |
| Alibaba qwen3.7-flash (≤32K tier; (c) falls in 32–256K tier at $0.10/$0.40 → ~$5.60) | $0.06 | $0.32 | $1.72* |
| Mistral Medium 3.5 | $3.38 | $8.40 | $90.00 |
| Mistral Large 3 | $0.97 | $2.20 | $26.00 |
| Mistral Small 4 | $0.32 | $0.75 | $8.40 |
| Mistral Ministral 3 8B | $0.25 | $0.48 | $6.60 |
| Groq gpt-oss-120b (cache 50%) | $0.32 | $1.11 | $8.40 |
| Groq gpt-oss-20b (cache 50%) | $0.16 | $0.56 | $4.20 |
| Cerebras gpt-oss-120b (no cache credit) | $0.64 | $3.25 | $17.00 |
| Together GLM-5.3 Flash | $0.30 | $0.78 | $8.00 |
| Together MiniMax M3 | $0.63 | $1.68 | $16.80 |
| Fireworks DeepSeek V4.1 Flash | $0.63 | $1.36 | $16.80 |
| Fireworks GLM-5.3 | $2.76 | $7.00 | $73.60 |

*Alibaba (c) recomputed for the 32K–256K tier: 40M×$0.10 + 4M×$0.40 = $5.60.

**Reading the table against the desk's volumes.** First-Seen Bot (~800 items/day, case a): Haiku 5.5 ≈ $0.18/day, GPT-5.4 nano ≈ $0.39, Gemini 3.1 Flash-Lite ≈ $0.48, qwen3.7-flash ≈ $0.05, local SetFit/FinBERT ≈ $0 — the classifier tier is a rounding error on any vendor, so choose on precision against the 200-item gold set, data policy, and structured-output strictness (OpenAI strict schema, Gemini `response_json_schema`, Grok strict json_schema; DeepSeek only JSON mode). Rose (~100 calls/day, case b): Sonnet 5.5 ≈ $1.12/day, Gemini 3.8 Flash ≈ $0.42 (doubles in 2027), GPT-5.4 mini ≈ $0.47, Grok 4.7 ≈ $1.06; Opus 5.5 ≈ $2.12. Research Bot (a few case-c sessions/day, say 5): Opus 5.5 ≈ $1.20/day, GPT-5.5 ≈ $1.60, Gemini 3.1 Pro ≈ $0.64, Fable 5.1 ≈ $3.00 — even the top tier is cheap at this volume; batch halves everything that is not latency-bound (post-mortems, owner mirror, labeler back-fill).

**Cross-vendor cautions dated 2026-10-21.** (1) Gemini Flash intro pricing ends 2026-12-31 (×2 on 2027-01-01). (2) OpenAI's fine-tuning platform is closing and Mistral's is deprecated; the hosted tuning options that remain are Vertex, Together, Fireworks, or local MLX/SetFit. (3) DeepSeek direct = PRC data residency and no ZDR; the same weights on Fireworks/Together carry US ZDR. (4) Together stores prompts by default until you flip ZDR; Mistral free mode may train on you; Google unpaid tier trains on you — put a billing account on every project and flip the toggles on day one. (5) The only public uptime SLAs are OpenAI Scale/Fast (Enterprise, 99.9%) and Vertex Gemini (99.5%); everyone else is best-effort, which is another reason the order path must stay LLM-free as the report requires.