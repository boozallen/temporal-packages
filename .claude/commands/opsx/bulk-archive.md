---
name: "OPSX: Bulk Archive"
description: Archive multiple completed changes at once
category: Workflow
tags: [workflow, archive, experimental, bulk]
---

Archive multiple completed changes in a single operation.

This command allows you to batch-archive changes, handling spec conflicts intelligently by checking the codebase to determine what's actually implemented.

**Input**: None required (prompts for selection)

**Steps**

1. **Get active changes**

   Run `openspec list --json` to get all active changes.

   If no active changes exist, inform user and stop.

2. **Prompt for change selection**

   Use **AskUserQuestion tool** with multi-select to let user choose changes:
   - Show each change with its schema
   - Include an option for "All changes"
   - Allow any number of selections (1+ works, 2+ is typical for bulk)

   **IMPORTANT**: Do NOT auto-select. Always let the user choose.

3. **Batch validation - gather status for all selected changes**

   For each selected change, collect:
   - **Artifact status**: `openspec status --change "<name>" --json` → schemaName, artifacts (done vs other)
   - **Task completion**: Read `openspec/changes/<name>/tasks.md`, count incomplete vs complete; if no tasks file, note "No tasks"
   - **Delta specs**: List capabilities under `openspec/changes/<name>/specs/`, extract requirement names

4. **Detect spec conflicts**

   Build a map of `capability -> [changes that touch it]`. A conflict exists when 2+ selected changes have delta specs for the same capability.

5. **Resolve conflicts agentically**

   For each conflict: read delta specs from each conflicting change; search codebase for implementation evidence; determine resolution (only one implemented → sync that one; both implemented → apply in chronological order; neither → skip sync, warn). Record resolution (which change's specs to apply, order, rationale).

6. **Show consolidated status table**

   Display a table: Change | Artifacts | Tasks | Specs | Conflicts | Status. For conflicts show resolution. For incomplete changes show warnings.

7. **Confirm batch operation**

   Use **AskUserQuestion tool**: "Archive N changes?" with options (e.g. "Archive all N", "Archive only N ready (skip incomplete)", "Cancel"). If there are incomplete changes, make clear they'll be archived with warnings.

8. **Execute archive for each confirmed change**

   Process in determined order (respecting conflict resolution):
   - Sync specs if delta specs exist (agent-driven merge); for conflicts apply in resolved order
   - Perform archive: `mkdir -p openspec/changes/archive`, `mv openspec/changes/<name> openspec/changes/archive/YYYY-MM-DD-<name>`
   - Track outcome per change: Success / Failed / Skipped

9. **Display summary**

   Show: Archived N changes (with paths); Skipped M (if any); Failed K (if any with reason). Spec sync summary (how many synced, conflicts resolved).

**Output On Success**

```
## Bulk Archive Complete

Archived N changes:
- <change-1> -> archive/YYYY-MM-DD-<change-1>/
- <change-2> -> archive/YYYY-MM-DD-<change-2>/

Spec sync summary:
- N delta specs synced to main specs
- No conflicts (or: M conflicts resolved)
```

**Output On Partial Success**

Show archived list, skipped list, failed list with reasons.

**Output When No Changes**

"No active changes found. Use `/opsx:new` to create a new change."

**Guardrails**
- Allow 1+ changes (2+ is typical for bulk)
- Always prompt for selection, never auto-select
- Detect spec conflicts early; resolve by checking codebase
- When both changes implemented, apply specs in chronological order
- Skip spec sync only when implementation is missing (warn user)
- Show clear per-change status before confirming
- Single confirmation for entire batch
- Track and report all outcomes
- Preserve .openspec.yaml when moving to archive
- Archive target: YYYY-MM-DD-<name>; if target exists, fail that change but continue others

**Skill**: Use openspec-bulk-archive-change skill for conflict resolution and batch workflow.
