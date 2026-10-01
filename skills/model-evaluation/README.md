# 模型测评

An independent workflow for evaluating a newly released or user-provided AI model. It uses task-based evidence to describe the model's strengths, weaknesses, suitable use cases, and evaluation limits.

## What it does

- Checks whether the model can be accessed and run through the available endpoint, model repository, or local runtime.
- Builds a small, balanced set of tasks around the intended use case.
- Scores outputs with explicit criteria and preserves evidence for conclusions.
- Reports model/version, test conditions, observed strengths and weaknesses, practical fit, and uncertainty.

## Use

Provide the model identifier, endpoint, repository reference, or accessible local model files, along with the intended use case if known. The Skill checks access and runtime compatibility before testing. It does not assume every uploaded model can run in the current environment.

## Contents

- `SKILL.md` — evaluation workflow and guardrails.
- `agents/openai.yaml` — Chinese display name and UI description for compatible skill interfaces.

## Privacy

Do not add credentials, private prompts, customer data, or model files to this public Skill package. Do not send private evaluation inputs to third-party endpoints without the user's direction.
