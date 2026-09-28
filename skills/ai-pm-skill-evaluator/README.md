# AI PM Skill Evaluator

A personal-workflow Skill for evaluating and improving Skills used in AI product management. It focuses on trigger accuracy, workflow adherence, evidence quality, deliverable quality, and regression behavior.

## Contents

- `SKILL.md` — evaluation workflow and report format.
- `references/evaluation-rubric.md` — behavior-based assessment criteria.
- `references/test-case-templates.md` — reusable case schema and sample prompts.
- `references/personal-project-cases.md` — case seeds based on AI product evaluation, Xiaoyunque, AI Product Factory, and AI Avatar Twin workflows.

## Use

Point the compatible agent at this Skill and a target Skill directory, then ask it to evaluate the target. For example:

> Evaluate the Skill at `path/to/skill` for my AI product workflow. Create positive, boundary, negative, and workflow cases. Run them with and without the Skill if the runtime is available; otherwise label the result static-only.

The evaluation must state what was actually run. A static review is not a runtime benchmark.

## Privacy

The package contains no project code, credentials, local file paths, or user data. Add only sanitized, shareable examples before publishing it.
