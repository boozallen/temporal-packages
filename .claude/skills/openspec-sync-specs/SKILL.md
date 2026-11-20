---
name: openspec-sync-specs
description: Sync delta specs from a change to main specs. Use when the user wants to merge change-level spec deltas into the canonical openspec/specs/ directory (e.g. before or during archive).
license: MIT
compatibility: Requires openspec CLI (optional; can be done by reading/writing files).
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.1.1"
---

Sync delta specs from a change to main specs. This is an **agent-driven** operation: read delta specs and edit main specs to apply changes (intelligent merge, e.g. add a scenario without copying the whole requirement).

**Input**: Optionally specify a change name. If omitted, infer from context or prompt for selection.

**Steps**

1. **If no change name provided, prompt for selection**

   Run `openspec list --json`. Use **AskUserQuestion tool** to let the user select. Show changes that have delta specs under `specs/`. Do NOT auto-select.

2. **Find delta specs**

   Look for `openspec/changes/<name>/specs/*/spec.md`.

   Delta sections: `## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`, `## RENAMED Requirements` (FROM:/TO:).

   If none found, inform user and stop.

3. **For each delta spec, apply to main specs**

   For each `openspec/changes/<name>/specs/<capability>/spec.md`:

   a. Read the delta spec to understand intended changes.

   b. Read the main spec at `openspec/specs/<capability>/spec.md` (may not exist).

   c. **Apply intelligently:**
      - **ADDED:** If requirement not in main spec → add it. If already exists → update to match (implicit MODIFIED).
      - **MODIFIED:** Find requirement in main spec; apply changes (new scenarios, edits, description). Preserve content not mentioned in delta.
      - **REMOVED:** Remove the entire requirement block from main spec.
      - **RENAMED:** Find FROM, rename to TO.

   d. **Create new main spec** if capability doesn't exist: Create `openspec/specs/<capability>/spec.md` with Purpose (brief/TBD) and Requirements with ADDED requirements.

4. **Show summary**

   List which capabilities were updated and what changed (added/modified/removed/renamed).

**Key principle: Intelligent merging**

- Apply partial updates (e.g. add one scenario under MODIFIED without copying existing scenarios).
- Delta represents intent, not full replacement.
- Use judgment to merge sensibly.

**Output on success**

```
## Specs Synced: <change-name>

Updated main specs:

**<capability-1>**: Added requirement "X"; Modified requirement "Y" (added 1 scenario).
**<capability-2>**: Created new spec file; Added requirement "Z".

Main specs are now updated. The change remains active - archive when implementation is complete.
```

**Guardrails**

- Read both delta and main spec before editing
- Preserve existing content not mentioned in delta
- If unclear, ask for clarification
- Show what you're changing as you go
- Operation should be idempotent (running twice yields same result)

**Edge cases**

- Main spec missing: Create new file with capability name; add Purpose and ADDED requirements
- Conflicting MODIFIED and REMOVED: Prefer MODIFIED if both exist for same requirement; otherwise follow REMOVED when explicitly stated
- RENAMED and MODIFIED for same requirement: Apply RENAMED first, then MODIFIED to the new name
