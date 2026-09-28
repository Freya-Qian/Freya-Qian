# AI PM Skill Evaluator

A personal-workflow Skill for evaluating and improving Skills used in AI product management. It covers package hygiene and static safety signals, trigger accuracy, workflow adherence, evidence quality, deliverable quality, regression behavior, and measured efficiency tradeoffs.

## Contents

- `SKILL.md` — evaluation workflow and report format.
- `references/evaluation-rubric.md` — behavior-based assessment criteria.
- `references/skill-static-audit.md` — package, capability, data-boundary, and static safety review checklist.
- `references/test-case-templates.md` — reusable case schema and sample prompts.
- `references/personal-project-cases.md` — case seeds based on AI product evaluation, Xiaoyunque, AI Product Factory, and AI Avatar Twin workflows.

## Use

Point the compatible agent at this Skill and a target Skill directory, then ask it to evaluate the target. For example:

> Evaluate the Skill at `path/to/skill` for my AI product workflow. Create positive, boundary, negative, and workflow cases. Run them with and without the Skill if the runtime is available; otherwise label the result static-only.

The evaluation must state what was actually run. A static review is not a runtime benchmark or a security certification. Potentially unsafe scripts are not executed by default. Efficiency comparisons require comparable runtime conditions and measured outcomes.

## Privacy

The package contains no project code, credentials, local file paths, or user data. Add only sanitized, shareable examples before publishing it.
