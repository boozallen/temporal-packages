---
name: openspec-apply-change
description: Implement tasks from an OpenSpec change. Use when the user wants to start implementing, continue implementation, or work through tasks.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.1.1"
---

Implement tasks from an OpenSpec change.

**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **Select the change**

   If a name is provided, use it. Otherwise:
   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `openspec list --json` to get available changes and use the **AskUserQuestion tool** to let the user select

   Always announce: "Using change: <name>" and how to override (e.g., `/opsx:apply <other>`).

2. **Check status to understand the schema**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - Which artifact contains the tasks (typically "tasks" for spec-driven, check status for others)

3. **Get apply instructions**

   ```bash
   openspec instructions apply --change "<name>" --json
   ```

   This returns: context file paths, progress (total, complete, remaining), task list with status, dynamic instruction.

   **Handle states:**
   - If `state: "blocked"` (missing artifacts): show message, suggest using openspec-continue-change or `/opsx:continue`
   - If `state: "all_done"`: congratulate, suggest archive
   - Otherwise: proceed to implementation

4. **Read context files**

   Read the files listed in `contextFiles` from the apply instructions output.
   For **spec-driven**: proposal, specs, design, tasks. For other schemas follow contextFiles from CLI.

5. **Show current progress**

   Display schema, progress "N/M tasks complete", remaining tasks overview, dynamic instruction from CLI.

6. **Implement tasks (loop until done or blocked)**

   For each pending task:
   - Show which task is being worked on
   - Make the code changes required
   - Keep changes minimal and focused
   - Mark task complete in the tasks file: `- [ ]` → `- [x]`
   - Continue to next task

   **Pause if:** Task is unclear, implementation reveals a design issue, error or blocker, or user interrupts.

7. **On completion or pause, show status**

   Display tasks completed this session, overall progress, and if all done suggest archive; if paused explain why and wait for guidance.

**Output**

- During implementation: Show "Working on task N/M: <description>" and "✓ Task complete" as you go.
- On completion: Summary with change name, schema, progress 7/7, and suggestion to run `/opsx:archive`.
- On pause: Explain issue and options (e.g. clarify task, update artifacts, try different approach).

**Guardrails**
- Keep going through tasks until done or blocked
- Always read context files before starting (from apply instructions output)
- If task is ambiguous, pause and ask before implementing
- If implementation reveals issues, pause and suggest artifact updates
- Keep code changes minimal and scoped to each task
- Update task checkbox immediately after completing each task
- Pause on errors, blockers, or unclear requirements - don't guess
- Use contextFiles from CLI output, don't assume specific file names

**Edge cases**
- No tasks.md or tasks empty: Report and suggest creating tasks via `/opsx:continue` or editing tasks.md
- Context files missing: Report blocked state and list missing artifacts; suggest `/opsx:continue`
