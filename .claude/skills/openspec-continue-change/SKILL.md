---
name: openspec-continue-change
description: Continue working on an OpenSpec change by creating the next artifact. Use when the user wants to progress their change, create the next artifact, or continue their workflow.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.1.1"
---

Continue working on a change by creating the next artifact.

**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **If no change name provided, prompt for selection**

   Run `openspec list --json` to get available changes sorted by most recently modified. Use the **AskUserQuestion tool** to let the user select.

   Present the top 3-4 most recently modified changes as options, showing: change name, schema (e.g. "spec-driven"), status (e.g. "0/5 tasks", "complete"), lastModified.

   Mark the most recently modified as "(Recommended)".

   **IMPORTANT**: Do NOT guess or auto-select a change. Always let the user choose.

2. **Check current status**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse: schemaName, artifacts (done/ready/blocked), isComplete.

3. **Act based on status**:

   **If all artifacts are complete (`isComplete: true`):**
   - Congratulate the user
   - Suggest: "All artifacts created! You can now implement with `/opsx:apply` or archive with `/opsx:archive`."
   - STOP

   **If artifacts are ready to create** (status "ready"):
   - Pick the FIRST artifact with status "ready"
   - Get instructions: `openspec instructions <artifact-id> --change "<name>" --json`
   - Parse: context, rules, template, instruction, outputPath, dependencies
   - **Create the artifact file:** Read dependency files, use template as structure, apply context/rules as constraints (do NOT copy them into the file), write to outputPath
   - Show what was created and what's now unlocked
   - STOP after creating ONE artifact

   **If no artifacts are ready (all blocked):** Show status and suggest checking for issues.

4. **After creating an artifact, show progress**
   ```bash
   openspec status --change "<name>"
   ```

**Output**

After each invocation: which artifact was created, schema, current progress (N/M complete), what artifacts are now unlocked, prompt "Run `/opsx:continue` to create the next artifact".

**Artifact Creation Guidelines (spec-driven)**

- **proposal.md**: Why, What Changes, Capabilities, Impact. Capabilities section is critical - each capability needs a spec file.
- **specs/<capability>/spec.md**: One spec per capability in the proposal's Capabilities section (use capability name, not change name).
- **design.md**: Technical decisions, architecture, implementation approach.
- **tasks.md**: Checkboxed tasks; use `- [ ] X.Y` format so apply phase can track.

For other schemas, follow the `instruction` field from the CLI output.

**Guardrails**
- Create ONE artifact per invocation
- Always read dependency artifacts before creating a new one
- Never skip artifacts or create out of order
- If context is unclear, ask the user before creating
- Verify the artifact file exists after writing before marking progress
- Use the schema's artifact sequence, don't assume specific artifact names
- **IMPORTANT**: `context` and `rules` are constraints for YOU - do NOT copy them into the artifact

**Edge cases**
- Multiple artifacts ready: Create only the first one in dependency order
- instructions JSON missing outputPath: Infer from schema (e.g. proposal → proposal.md, specs → specs/<capability>/spec.md from proposal)
