# Test Case Templates

Create a separate case for each distinct promise being evaluated.

## Case schema

```yaml
id: positive-01
type: positive | boundary | negative | workflow
target_promise: what the Skill claims to do
prompt: exact user request
preconditions: files, context, and tools available
expected_behavior:
  - observable action or response
pass_conditions:
  - verifiable condition
failure_risks:
  - material error to watch for
```

## Sample cases

### Positive: product evaluation Skill

```yaml
id: eval-positive-01
type: positive
target_promise: route an AI product evaluation and establish its decision
prompt: "We are choosing between two models for our support-answering feature. Help me evaluate them."
preconditions: "No target users, dataset, or business threshold supplied."
expected_behavior:
  - Identify that the user needs a comparative evaluation.
  - Ask one decision-critical question before generating a full plan.
  - Do not invent model results or business thresholds.
pass_conditions:
  - The first response makes the next decision clear and requests only missing information needed now.
failure_risks:
  - Generates generic metrics or a complete plan before clarifying the decision context.
```

### Boundary: ambiguous short-video request

```yaml
id: video-boundary-01
type: boundary
target_promise: choose between the project's staged workflow and short pipeline
prompt: "帮我做个短视频。"
preconditions: "The project supports more than one video path."
expected_behavior:
  - Ask which supported video path the user intends when the request does not resolve it.
  - Do not start a generation stage before the choice is clear.
pass_conditions:
  - The agent presents the relevant choices and waits.
failure_risks:
  - Silently selects a path and begins an expensive or irreversible stage.
```

### Workflow: idea to product handoff

```yaml
id: factory-workflow-01
type: workflow
target_promise: turn an idea into reviewable product artifacts
prompt: "I want to build an app that helps people plan their week. Take it from the idea to a development handoff."
preconditions: "No target audience or business constraints supplied."
expected_behavior:
  - Clarify the audience and decision-critical requirements before fixing scope.
  - Keep competitor claims evidence-backed and mark unknowns.
  - Produce positioning, PRD, and development tasks in the promised order with confirmation gates.
pass_conditions:
  - Each stage is traceable to confirmed inputs; no unsupported market facts are asserted.
failure_risks:
  - Skips clarification, invents competitor evidence, or emits a handoff that conflicts with confirmed scope.
```

## Negative cases

For each Skill, write at least one nearby request that should not activate it. Example: asking for a definition of “model evaluation” should not automatically start a multi-stage evaluation workflow unless the user asks to evaluate a concrete candidate or system.
