---
name: model-evaluation
description: Independently evaluate a newly released or user-provided AI model to characterize its strengths, weaknesses, and suitable use cases from task-based evidence.
---

# Model evaluation

Build an evidence-based, task-relevant picture of a single model's capabilities. This skill produces an independent profile; do not add baseline-model comparisons.

## Establish what can be evaluated

- Identify the model and version, provider or source, modality, intended use, and evaluation date. Do not assume a model name uniquely identifies a fixed version.
- Accept a user-supplied model in any accessible form: hosted API or endpoint, provider/model ID, repository reference, or local model files. First determine whether the current tools and runtime can actually access and run it.
- For hosted models, establish the endpoint, compatible API/protocol, model identifier, and required authentication. Do not ask the user to paste secrets into the chat; use an available secure credential mechanism. Never claim to have tested a model that was only described or linked.
- For local weights, inspect the format, architecture/runtime support, required dependencies, and available compute before attempting inference. File presence alone does not establish compatibility. If unsupported or too large for available hardware, explain the specific blocker and offer alternatives such as a compatible inference server, quantized checkpoint, hosted endpoint, or a narrower test. Do not silently install large dependencies, download large weights, or incur paid usage.
- Ask only for details that materially change the evaluation. If no task is specified, propose a compact general-purpose text evaluation and state its limits; if modality or intended use is clear, tailor the tasks accordingly.

## Run the evaluation

1. Define the questions the evaluation should answer: intended use cases, candidate failure modes, language/domain coverage, and cost, latency, privacy, or deployment constraints when relevant.
2. Create a small, balanced set of representative tasks. Include straightforward, challenging, and adversarial or ambiguous cases where appropriate. Prefer tasks with checkable answers or explicit scoring rubrics. Do not infer broad ability from one anecdote.
3. Record outputs and score them against task-specific criteria. Use exact checks for deterministic answers and a transparent rubric for open-ended work. For subjective judging, preserve examples that support the judgment. Treat automatic or LLM judging as fallible and spot-check it.
4. Track model/version, provider, date, endpoint/runtime, prompt and settings, task set, sample count, scoring method, failures, latency, and observed costs when available. Do not imply a benchmark score is comparable to a published score unless the benchmark version, protocol, and scoring match.
5. Report observed strengths, weaknesses, and suitable use cases with concrete evidence. Separate measured observations from hypotheses, mention uncertainty and sample limits, and avoid an unsupported single overall rating.

## Deliver the result

Give a concise report with:

- Model identity, version, access route, date, and test conditions.
- Evaluation scope and method, including task count and scoring approach.
- Strengths and weaknesses, each grounded in examples or scores.
- Practical fit: where it appears useful, where human review or another model is preferable, and what was not tested.
- Confidence and limitations, including compatibility or access problems that prevented testing.

Keep raw prompts, outputs, and per-task scores available or linked when the user needs an auditable report. Protect private inputs and do not send them to third-party endpoints without the user's direction.
