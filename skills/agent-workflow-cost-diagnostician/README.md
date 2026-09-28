# Agent Workflow Cost Diagnostician

A workflow for mapping an Agent task end to end, locating measured and suspected bottlenecks, and planning experiments that account for cost, latency, quality, and reliability together.

## What it analyzes

- Model calls, tools, context, routing, retries, and human review
- Cost and latency per accepted task, where measurements exist
- Completion, acceptance, rework, and failure modes
- Reversible optimization experiments and rollback criteria

It does not claim savings from token counts or anecdotal observations alone. Missing measurements are called out explicitly.

## Use

Provide a task example, workflow or trace, acceptance criteria, and any available cost, latency, quality, and rework data. The Skill produces an evidence-based map and prioritizes experiments. If no baseline exists, it recommends what to measure before estimating impact.

## Contents

- `SKILL.md` — workflow, evidence standards, and optimization guardrails.
- `references/diagnosis-template.md` — reusable analysis and experiment format.

## Privacy

Do not add private traces, prompts, customer data, credentials, or confidential system details to this public Skill package.
