---
name: ai-product-opportunity-evaluator
description: Assess AI product ideas by examining target users, problem evidence, alternatives, incremental AI value, feasibility, business assumptions, and validation plans. Use when exploring, prioritizing, or challenging an AI product opportunity before committing to a build.
---

# AI Product Opportunity Evaluator

Turn an AI product idea into an evidence-based opportunity assessment and a small, testable next step. Distinguish observed evidence from assumptions; do not treat a polished demo, market-size claim, or model capability as proof of user demand.

## Workflow

### 1. Define the decision

Clarify the idea, target user, intended decision, stage, constraints, and what would count as a useful outcome. Reuse known context. Ask one focused question only when a missing answer would materially change the assessment; otherwise state assumptions and proceed.

### 2. Ground the problem in evidence

Identify the user's job, triggering situation, frequency, severity, current workaround, and consequences of the problem. Separate:

- **Observed evidence**: interviews, behavior, usage data, support cases, or existing workflow artifacts.
- **Reported belief**: what users say they want or might pay for.
- **Assumption**: what has not yet been checked.

Do not invent research, customer quotes, willingness to pay, market size, or adoption data. If evidence is thin, frame conclusions as hypotheses.

### 3. Examine alternatives and AI's contribution

Compare the proposed product with the user's current workaround, non-AI software, services, and doing nothing. Specify what AI changes in the workflow and whether that change improves an outcome users value. Consider quality, latency, cost, privacy, explainability, and human review where relevant.

Ask whether a simpler non-AI solution could deliver the same value. Do not assume that adding a model creates differentiation.

### 4. Check feasibility and business assumptions

List the main product, technical, operational, policy, and distribution constraints supported by available information. Identify dependencies such as data access, integrations, human operations, and model reliability. Separate known constraints from items requiring technical or commercial validation.

For business viability, state the likely beneficiary, buyer, budget or payment hypothesis, delivery and support costs, and route to reach users. Treat these as hypotheses unless evidence was supplied.

### 5. Identify decisive assumptions

Rank the few assumptions that could change the decision. For each, record:

- the assumption and why it matters;
- current evidence and confidence;
- the cheapest credible test;
- the signal that would support or weaken it;
- the next decision if the signal is positive, negative, or ambiguous.

Prefer tests of user behavior or real workflow outcomes over preference-only questions. Do not present arbitrary numeric thresholds as universal standards; label proposed thresholds as provisional and ask the user to set them when a decision depends on them.

### 6. Recommend a reversible next step

Choose among **continue discovery**, **run a focused validation**, **prototype**, **revise the target/problem**, or **pause**. Tie the recommendation to evidence, uncertainty, cost of learning, and reversibility. Do not recommend a full build when a smaller test can resolve the key uncertainty.

## Output

Use [assessment-template.md](references/assessment-template.md). Keep the summary concise and include:

- decision and confidence, with confidence described qualitatively;
- strongest supporting and opposing evidence;
- assumptions that remain unverified;
- next validation step, owner if known, and success/failure signals;
- material risks and what was not assessed.

If key inputs are missing, deliver a bounded preliminary assessment and list the missing evidence. Never manufacture a numerical score or imply that this framework guarantees product-market fit.

## Boundaries

- Do not conduct external research unless requested or appropriate tools are available; cite sources and dates for researched claims.
- Do not claim market size, demand, willingness to pay, or technical feasibility without evidence.
- Do not expose private user or company material in public outputs.
- Do not make irreversible product, spending, or launch decisions on the user's behalf.
