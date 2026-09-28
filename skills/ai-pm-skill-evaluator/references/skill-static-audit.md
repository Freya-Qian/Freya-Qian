# Skill Package and Static Safety Audit

Use this checklist before running test cases. Record findings with file paths and evidence. This is triage, not a security certification.

## Package integrity

- Confirm the folder contains the intended `SKILL.md` and only relevant supporting files.
- Check that `name` is valid and unique within the collection; `description` states both capability and trigger conditions.
- Verify every relative reference resolves and that examples match the current workflow.
- Identify scripts, binaries, generated files, hidden files, and declared dependencies.

## Capability and boundary review

Read scripts and instructions without executing them. Note whether they:

- read or write files outside the skill or user-selected workspace;
- access network services, browsers, accounts, or external APIs;
- request, print, store, or transmit credentials or personal data;
- install packages or run shell commands with broad effects;
- overwrite, delete, publish, or deploy data;
- accept retrieved pages, documents, or tool output as instructions rather than untrusted content.

Describe what the code appears to do and what could not be determined from static inspection. Do not label a Skill safe merely because no issue was noticed.

## Optional tooling

If a compatible linter or scanner is already available, it may be run when the user requests tool-based validation. Record its name, version if available, command, output, and scope. Do not install tools or execute bundled scripts by default. A clean scan does not replace review of the Skill's actual instructions and capabilities.

## Finding record

| Severity | File / line | Observed capability or issue | Evidence | User impact | Limitation |
|---|---|---|---|---|---|
| | | | | | |
