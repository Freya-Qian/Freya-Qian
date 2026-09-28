---
name: creative-image-production
description: Plan, generate, edit, review, and deliver image assets from a creative brief. Use when creating images, editing an existing image, producing variants, or preparing visual assets for a product, presentation, campaign, or social post.
---

# Creative Image Production

Turn a visual request into reviewable image assets. Route generation and editing as separate modes, preserve user-specified constraints, and verify outputs before delivery. Follow the active image tool's own operating instructions; do not invent provider capabilities.

## Workflow

### 1. Capture the image brief

Use [image-brief-template.md](references/image-brief-template.md) to identify the intended use, audience, subject, scene, style, composition, exact text, dimensions, aspect ratio, format, number of candidates, references, and constraints. Reuse details already provided. Ask only for missing information that would materially change the image; for a clear request, proceed without another confirmation round.

Separate:

- **Fixed requirements**: text that must stay exact, product/UI details, identity, logo, required objects, output dimensions, and elements that must not change.
- **Creative choices**: lighting, background, palette, camera, framing, texture, and other choices the agent may propose.
- **Avoid list**: artifacts or content that must not appear.

### 2. Choose generation or editing

- **Generate** when the user wants a new concept or references are guidance only.
- **Edit** when the user wants to change an existing image while preserving specified parts.
- **Composite** when the request combines multiple source images or transfers an element between them, if an available tool supports it.

For every reference image, record its role: edit target, style reference, composition reference, identity/product reference, or insert. Do not treat a style reference as permission to reproduce protected logos, characters, or exact artwork.

### 3. Select a capable tool and plan

Inspect the available image tools and their current capabilities. Match the tool to the task's primary constraint: edit fidelity, reference-image support, text rendering, transparency, aspect ratio, resolution, consistency, speed, or cost. Do not route to a paid provider or silently switch providers after failure without authorization. If a paid external call is needed and the user's budget or authorization is unclear, state the known cost or uncertainty and ask before making that call.

Create a concise structured prompt that describes the visible result in natural language: subject and action, setting, composition, camera/viewpoint, lighting, palette, material/style, exact copy, output format, and constraints. Give each reference image an explicit role. For precise lettering, preserve the exact text and consider adding it in post-production when the image model cannot reliably render it.

For ambiguous or consequential work, present the proposed prompt and generation/edit plan for approval. Skip this pause when the user explicitly asks for direct generation and the tool, scope, and cost are already clear.

### 4. Generate or edit candidates

Use the selected tool and requested parameters. For variants, change one meaningful variable at a time when the goal is comparison. Keep edit targets intact; make edits non-destructively and save new outputs rather than overwriting the source.

If a required tool or input is unavailable, provide the prepared prompt and explain the blocker. Never claim an image was generated or edited unless the output exists.

### 5. Review the visual result

Inspect each candidate at a useful size. Check the subject, composition, crop, aspect ratio, rendering artifacts, exact text, brand/product fidelity, and any preservation constraints. For transparent output, verify the alpha channel rather than judging only the preview background. Record defects and uncertainty; do not call a visual review successful if the file could not be inspected.

See [visual-qa-checklist.md](references/visual-qa-checklist.md).

### 6. Iterate surgically

Translate feedback into the smallest relevant change. Keep approved elements fixed and change one main variable per iteration when practical. Do not regenerate unrelated elements or silently replace a failed candidate with a different concept. Ask a focused question when feedback conflicts with a fixed requirement.

### 7. Deliver with provenance

Deliver the image path or accessible result, format, dimensions, selected direction, and any remaining limitation. When the workflow supports it, save a sidecar record with the prompt, tool/model, parameters, reference roles, date, and parent asset for edits. Keep private source images and credentials out of public metadata. Clearly distinguish final assets from drafts and variants.

## Boundaries

- Do not alter source images destructively or change product/UI facts, identity, logos, or exact copy beyond the user's request.
- Do not expose private source images, credentials, or personal data in public outputs or provenance records.
- Do not claim a provider is best without a current, task-specific comparison.
- Do not imply that generation alone verifies factual accuracy, brand compliance, usage rights, or platform readiness.
