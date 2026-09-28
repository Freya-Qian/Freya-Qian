---
name: data-to-decision-brief
description: Analyze structured product or business data and turn verified findings into a concise decision brief with appropriate charts, caveats, and optional presentation outline. Use when answering questions from CSV, Excel, metrics, experiments, or operational datasets.
---

# Data to Decision Brief

Move from a decision question to a data-backed brief. Check the data before interpreting it, preserve the source, and make every important claim traceable to a calculation or cited source. A clean chart or report does not prove that the underlying data is valid.

## Workflow

### 1. Define the question and decision

Establish the question, intended decision, audience, metric definitions, unit of analysis, comparison, time window, and requested deliverable. Reuse known context. Ask one focused question when a missing detail would change the analysis; otherwise state assumptions and proceed with a bounded answer.

### 2. Inspect the data before analysis

Identify files, sheets, fields, types, row counts, date range, grain, keys, missing values, duplicates, outliers, and relevant filters. Check joins for row multiplication and time windows for incomplete periods. Preserve raw inputs; document cleaning and exclusions. Do not silently impute, remove, or recode values when the choice could change the result.

If the file cannot be read with available tools, explain what is missing and request an accessible format or tool. Do not pretend to have inspected data that was not available.

### 3. Choose an analysis that answers the question

Use the simplest suitable method. Define denominators and comparison groups. Distinguish descriptive trends from causal effects; observational differences alone do not establish causality. For experiments, inspect assignment, exposure, sample size, guardrail metrics, and relevant uncertainty before interpreting results. Avoid unsupported significance or ROI claims.

### 4. Build traceable findings

For each finding, record the calculation or source fields, comparison, period, and limitation. Separate:

- **Observed result**: directly calculated from the inspected data.
- **Interpretation**: a plausible explanation of the observed result.
- **Hypothesis**: a claim requiring additional evidence.

Use charts only when they clarify a comparison or trend. Label units, dates, denominators, and source; choose scales that do not distort the message.

### 5. Write the decision brief

Use [brief-template.md](references/brief-template.md). Lead with the decision-relevant answer, then show the evidence, method, caveats, and recommended next action. State what the data cannot answer. If the user asks for slides, provide a narrative outline or create a deck only with suitable tools and the requested format.

### 6. Verify the deliverable

Reconcile reported numbers against the analysis output. Check formulas, units, totals, chart labels, date ranges, and citations. Do not add recommendations that are disconnected from the evidence. Clearly mark estimates and unverified assumptions.

## Boundaries

- Do not change source data unless the user requests it; save transformed data separately and document transformations.
- Do not infer causality, population prevalence, or business impact beyond the analysis design and sample.
- Do not expose personal or confidential records in reports or charts; aggregate or redact where appropriate.
- Route product-opportunity decisions to a dedicated opportunity assessment when the main question is whether to build; this Skill supplies data evidence and does not substitute for that decision framework.
- Route Agent orchestration cost and reliability diagnosis to a workflow diagnostic when the dataset represents model/tool traces and the task is to optimize the Agent pipeline.
