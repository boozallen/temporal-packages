---
name: openspec-verify-change
description: Verify implementation matches change artifacts before archiving. Use when the user wants to validate that code fulfills specs, design, and tasks.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.1.1"
---

Verify that an implementation matches the change artifacts (specs, tasks, design).

**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **If no change name provided, prompt for selection**

   Run `openspec list --json`. Use **AskUserQuestion tool** to let the user select.

   Show changes that have implementation tasks. Include schema. Mark changes with incomplete tasks as "(In Progress)".

   **IMPORTANT**: Do NOT guess or auto-select a change.

2. **Check status**  
   `openspec status --change "<name>" --json` → schemaName, which artifacts exist.

3. **Load artifacts**  
   `openspec instructions apply --change "<name>" --json` → read all files in contextFiles.

4. **Initialize verification report**

   Three dimensions: **Completeness** (tasks + spec coverage), **Correctness** (requirement implementation + scenario coverage), **Coherence** (design adherence + pattern consistency). Each can have CRITICAL, WARNING, or SUGGESTION issues.

5. **Verify Completeness**

   - **Task completion:** If tasks.md exists, parse `- [ ]` vs `- [x]`. If incomplete, add CRITICAL per incomplete task with recommendation.
   - **Spec coverage:** If delta specs exist in `openspec/changes/<name>/specs/`, extract requirements (### Requirement:). For each, search codebase for implementation evidence. If unimplemented, add CRITICAL with recommendation.

6. **Verify Correctness**

   - For each requirement: search codebase, note file paths, assess match to intent. If divergence, add WARNING with recommendation.
   - For each scenario (#### Scenario:): check conditions handled in code and tests. If uncovered, add WARNING with recommendation.

7. **Verify Coherence**

   - If design.md exists: extract decisions, verify implementation follows them. If contradiction, add WARNING with recommendation.
   - Review new code for pattern consistency (naming, structure, style). If significant deviations, add SUGGESTION.

8. **Generate report**

   Summary scorecard (Completeness / Correctness / Coherence). Issues by priority: CRITICAL (must fix before archive), WARNING (should fix), SUGGESTION (nice to fix). Final assessment: "X critical issue(s). Fix before archiving." / "No critical issues. Y warning(s). Ready for archive (with noted improvements)." / "All checks passed. Ready for archive."

**Verification heuristics**

- Completeness: Objective checklist (checkboxes, requirements list)
- Correctness: Keyword search, file path analysis, reasonable inference - not perfect certainty
- Coherence: Glaring inconsistencies only, not style nitpicks
- When uncertain: Prefer SUGGESTION over WARNING, WARNING over CRITICAL
- Every issue must have a specific recommendation and file/line references where applicable

**Graceful degradation**

- Only tasks.md: verify task completion only
- Tasks + specs: verify completeness and correctness; skip design if needed
- Full artifacts: verify all three dimensions
- Always note which checks were skipped and why

**Guardrails**
- Do not block archive; verify surfaces issues for user to address
- Use codebase search and artifact content; don't assume
- Prefer actionable, specific recommendations

**Edge cases**
- No tasks.md: Report and skip task verification; still verify spec/design if present
- Spec format doesn't use ### Requirement:/#### Scenario:: Adapt to actual structure or note "Could not parse requirements"
