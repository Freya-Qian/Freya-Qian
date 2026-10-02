# 模型选型

A provider-aware workflow for choosing models for a concrete task. It compares current capabilities and costs, gives three suitable recommendations, and clearly marks the top pick.

## What it does

- Lets the user choose balanced, quality-first, cost-first, speed-first, or a custom priority; balanced is the default.
- Compares three verified candidates across relevant providers and explains why one is the best fit.
- Checks current provider documentation and pricing rather than relying on a fixed model list.
- Estimates workload cost when usage is known and considers price in the recommendation itself.
- Distinguishes evidence, provider claims, and uncertainty; suggests a task-specific bake-off when needed.

## Use

Provide a task or workload and any known constraints, such as usage volume, latency, deployment region, data handling, or budget. If you do not specify a priority, the Skill presents selectable options when the interface supports them and accepts a custom text response; balanced is the default. If use volume is unknown, it compares unit prices rather than inventing a monthly estimate.

This Skill chooses among models for a task. Use [模型测评](../model-evaluation/README.md) when you want to test and profile a particular model.

## Contents

- `SKILL.md` — selection workflow, current-source requirements, cost comparison, and response format.
- `agents/openai.yaml` — Chinese display name and UI metadata for compatible skill interfaces.

## Privacy

Do not add credentials, private prompts, customer data, or confidential workloads to this public Skill package.
