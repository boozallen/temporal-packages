---
name: openspec-bulk-archive-change
description: Archive multiple completed changes at once, resolving spec conflicts by checking the codebase. Use when the user has several completed changes and wants to archive them in one operation.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.1.1"
---

Archive multiple completed changes in a single operation. Handles spec conflicts by checking the codebase to see what is actually implemented.

**Input**: None required; prompt for which changes to archive.

**Steps**

1. **Get active changes**  
   `openspec list --json`. If none, inform user and stop.

2. **Prompt for selection**  
   Use **AskUserQuestion tool** (multi-select): show each change with schema, include "All changes", allow 1+ (typically 2+). Do NOT auto-select.

3. **Batch validation**  
   For each selected change:
   - Artifact status: `openspec status --change "<name>" --json` → schemaName, artifacts
   - Task completion: read `openspec/changes/<name>/tasks.md`, count incomplete vs complete
   - Delta specs: list capabilities under `openspec/changes/<name>/specs/`, extract requirement names

4. **Detect spec conflicts**  
   Build map `capability -> [changes that touch it]`. Conflict = 2+ selected changes have delta specs for same capability.

5. **Resolve conflicts agentically**  
   For each conflict: read delta specs from each change; search codebase for implementation; decide: only one implemented → sync that one; both implemented → apply in chronological order (older first, newer overwrites); neither → skip sync, warn. Record resolution (which change's specs, order, rationale).

6. **Show consolidated status table**  
   Columns: Change | Artifacts | Tasks | Specs | Conflicts | Status. Show conflict resolutions. Show warnings for incomplete changes.

7. **Confirm batch**  
   **AskUserQuestion tool**: "Archive N changes?" with options (e.g. "Archive all N", "Archive only N ready (skip incomplete)", "Cancel"). If incomplete, state they will be archived with warnings.

8. **Execute**  
   For each confirmed change in resolved order:
   - Sync specs if delta specs exist (openspec-sync-specs style); for conflicts apply in resolved order
   - Archive: `mkdir -p openspec/changes/archive`, `mv openspec/changes/<name> openspec/changes/archive/YYYY-MM-DD-<name>`
   - Track: Success / Failed / Skipped

9. **Display summary**  
   Archived list with paths; Skipped (if any); Failed with reason (if any). Spec sync summary (how many synced, conflicts resolved).

**Output on success**

```
## Bulk Archive Complete

Archived N changes:
- <change-1> -> archive/YYYY-MM-DD-<change-1>/
- <change-2> -> archive/YYYY-MM-DD-<change-2>/

Spec sync summary: N delta specs synced; no conflicts (or M conflicts resolved).
```

**Guardrails**

- Allow 1+ changes (2+ typical for bulk)
- Always prompt for selection
- Detect conflicts early; resolve via codebase check
- When both implemented, apply specs in chronological order
- Skip spec sync only when implementation missing (warn)
- Show per-change status before confirm
- Single confirmation for whole batch
- Report all outcomes (success/skip/fail)
- Preserve .openspec.yaml when moving
- Archive target YYYY-MM-DD-<name>; if exists, fail that change but continue others

**Edge cases**

- One change selected: Same workflow; still check for conflicts with other active changes if they touch same capability (optional; can keep simple and only consider selected set)
- Archive target exists: Fail that change, report, continue with rest
- Sync fails for one change: Record failure, continue archiving others; report in summary
