---
name: model-selector
description: Recommend three suitable current AI models for a workload across major providers, compare cost and tradeoffs, and mark a top pick. Use for model selection; use model-evaluation to test a specified model.
---

# Model selector

Help the user choose models for a concrete workload. Treat model availability, capabilities, and prices as time-sensitive; do not rely on memory for current facts.

## Understand the workload

Use the details already provided. If a missing detail would materially change the recommendation, ask one concise question at a time. Focus on the task, input and output types, quality bar, volume, latency needs, context size, tools or structured output, deployment/API requirements, data handling constraints, and budget. Do not ask for details that are unnecessary for a useful first recommendation.

Let the user choose an optimization priority. If they have not specified one, ask before researching candidates and present these four choices: **综合平衡（默认）**, **效果优先**, **成本优先**, and **速度优先**. Allow a custom priority as free text (for example, long-context performance, coding, multimodality, privacy, or on-device use). Use a structured choice control with a free-text option when the current interface supports it; otherwise show the choices in the chat and invite the user to type a custom priority. If the user accepts the default or declines to choose, use balanced. Do not ask again when a priority is already clear from the request.

Always report cost information, regardless of the selected priority.

## Research current candidates

Compare appropriate current offerings from major providers, such as OpenAI, Anthropic, Google, and other providers relevant to the workload. When geography, data residency, or local access matters, include providers available in that market (for example, relevant Chinese providers for deployments in mainland China). Do not force a provider into the shortlist when it has no suitable option. Distinguish hosted chat products, API models, and self-hosted/open-weight models; their access and pricing are not interchangeable.

Browse for current information whenever web search is available. Prefer each provider's official model documentation, pricing pages, release notes, and API documentation for names, capabilities, availability, limits, and prices. Use independent benchmarks or evaluations only as supporting evidence, cite their methodology and date, and avoid treating unlike benchmark scores as directly comparable. If official sources do not establish a claim, mark it as uncertain instead of presenting it as fact.

Give exactly three recommended candidates when three suitable current options can be verified. Match them to the actual workload and note relevant tradeoffs such as quality, latency, context window, modality, tool use, structured output, reliability evidence, access restrictions, and deployment options. Mark one as **Most recommended** and explain why it best fits the workload and the user's selected priority. Explain the tradeoff for the other two. Separate measured evidence from provider claims and reasoned inference. If fewer than three suitable options can be verified, give the available options and state why the list is shorter rather than padding it with poor fits.

Price is part of the recommendation decision, not just a table column. For the default balanced priority, weigh expected task quality and reliability against the estimated total cost at the user's workload, plus latency and operational constraints when relevant. Prefer a less expensive model when available evidence suggests it is likely to meet the quality bar. Recommend a more expensive model only when its expected quality, reliability, or capability gain is relevant enough to justify the added cost; state that tradeoff plainly. Do not infer a quality-per-dollar winner from vendor claims alone. If evidence is insufficient, mark the top pick as provisional and recommend a representative bake-off before committing to higher spend.

## Compare cost fairly

For every shortlisted API model, show the current input and output price in the provider's billing unit (usually per million tokens), with currency and source. Include cache, image/audio/video, tool, batch, or other charges when relevant. State when a price or capability depends on region, tier, or contract. If recommending a hosted chat product, distinguish its subscription price and access limits from API costs. If recommending a self-hosted model, estimate serving costs only when hardware, utilization, and traffic assumptions are available; otherwise state the main cost drivers and what is needed to estimate them.

When workload volume is known, estimate cost using explicit input/output volume and usage assumptions. Show the arithmetic or a compact monthly estimate. If volume is unknown, show unit prices and say what information is needed for a meaningful estimate; do not invent usage. Keep subscription plan fees distinct from API token costs, and do not equate a consumer chat subscription with API access.

## Recommend

Give three recommended options and clearly mark the single most recommended option. Explain how it fits the workload and selected priority, then summarize why each alternative may be preferable under a different tradeoff. Under the default balanced priority, use estimated task cost in the ranking itself: explain why the top choice's expected performance is worth its price compared with cheaper candidates, or choose a cheaper candidate when higher-priced alternatives have no demonstrated benefit relevant to the workload. Include a cost-optimized option when one is credible.

State the main uncertainty and suggest a small task-specific bake-off when the evidence cannot settle an important quality or reliability difference. Use representative user inputs and success criteria; do not claim to have run tests that were not performed.

## Response format

1. **Workload and priority** — brief summary, noting any assumptions; priority defaults to balanced.
2. **Recommendation** — the best-fit option and why.
3. **Three recommendations** — compact table with provider/model, fit, key tradeoff, and current cost; mark the top pick as **Most recommended**.
4. **Cost estimate** — explicit scenario estimate if usage is known, otherwise unit prices and missing inputs.
5. **Sources and checked date** — direct links to current primary sources, plus any supporting independent evidence.
6. **Next step** — only if a benchmark, missing constraint, or access check would materially change the choice.

Keep the result decision-oriented. Clearly flag unverified pricing or availability, and avoid false precision when vendors use different billing units or counting rules.
