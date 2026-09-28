# Personal Project Case Seeds

These are starting points based on project workflows. Adapt them only when the corresponding Skill or project material is part of the evaluation. They are not claims that the projects pass.

## 1. AI product evaluation

Use the existing AI product evaluation Skill as a target or baseline. Test whether it:

- distinguishes the evaluation object (model, prompt, Skill, agent, or RAG) from the business task;
- identifies the decision before choosing metrics;
- asks only for missing decision-critical information;
- preserves confirmed thresholds and flags hard stop conditions;
- keeps each conclusion traceable to case IDs, versions, outputs, and rules.

Example negative case: a user asks “What is RAG?” The evaluator should not launch a full RAG benchmark unless the user requests an evaluation.

## 2. Xiaoyunque / short-video production

Test the target Skill against its documented routes and confirmation points:

- a vague “make me a video” request should resolve the supported production path before work begins;
- the staged workflow should respect its user-confirmation gates;
- a selected one-shot pipeline should follow that pipeline rather than silently entering the staged workflow;
- missing services, API credentials, or required references should be reported instead of treated as ready.

Do not include local API keys, localhost assumptions, or private implementation details in a public test package.

## 3. AI Product Factory

Test the promise from idea through handoff:

- requirements are clarified before scope is fixed;
- competitor and market claims have evidence or are marked unknown;
- positioning, PRD, and development tasks follow the agreed scope;
- confirmation gates are respected between stages;
- exported artifacts are usable outside the application.

## 4. AI Avatar Twin

When evaluating a content-production Skill for this project, check that it:

- grounds topics in supplied or retrieved source material;
- follows the chosen creator profile, voice, and prohibited terms;
- keeps source facts separate from generated script wording;
- produces the requested script or publishing package without claiming an unrun video-generation step is complete.

## Source boundary

Use the user's project files and course notes as evidence only when they are available in the current task. Do not publish private source material or cite local absolute paths in the generated Skill. If a test expectation comes from a user-provided rubric or class example, identify that source in the private evaluation report.
