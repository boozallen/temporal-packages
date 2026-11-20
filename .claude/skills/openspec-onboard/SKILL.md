---
name: openspec-onboard
description: Guided onboarding - walk through a complete OpenSpec workflow cycle with narration. Use when the user wants to learn OpenSpec by doing one full change with step-by-step explanation.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.1.1"
---

Guide the user through their first complete OpenSpec workflow cycle. Teaching experience: do real work in the codebase while explaining each step.

**Preflight**

Check OpenSpec is initialized: `openspec status --json 2>&1 || echo "NOT_INITIALIZED"`. If not initialized, tell user to run `openspec init` then return to `/opsx:onboard`. Stop.

**Phases (high level)**

1. **Welcome** – Explain: one full change cycle (idea → implementation) with a real task. Steps: pick small task, explore briefly, create change, build proposal → specs → design → tasks, implement, archive. Time ~15–20 min. Start by finding something to work on.

2. **Task selection** – Scan codebase for small improvements (TODO/FIXME, missing error handling, untested functions, type issues, debug artifacts, missing validation). Present 3–4 specific suggestions with location and scope. Include "Something else?". If nothing found, ask what they want to add or fix. **Scope guardrail:** If task too large, suggest slicing smaller or picking another option; allow override.

3. **Explore demo** – Spend 1–2 minutes on relevant code (read files, optional ASCII diagram). Explain `/opsx:explore` is for this. **PAUSE** for acknowledgment.

4. **Create change** – Explain change = container in `openspec/changes/<name>/`. Run `openspec new change "<derived-name>"`. Show folder structure. Next: fill proposal.

5. **Proposal** – Explain proposal = WHY and WHAT. Draft content (Why, What Changes, Capabilities, Impact). **PAUSE** for approval. Save to `openspec/changes/<name>/proposal.md`.

6. **Specs** – Explain specs = WHAT in testable terms. Create `openspec/changes/<name>/specs/<capability>/spec.md` with ADDED requirements and WHEN/THEN scenarios. Save.

7. **Design** – Explain design = HOW. Draft design.md (Context, Goals/Non-Goals, Decisions). Save.

8. **Tasks** – Explain tasks = implementation checkboxes. Generate from specs and design (`## N. Group`, `- [ ] X.Y`). **PAUSE** for confirmation. Save to `openspec/changes/<name>/tasks.md`.

9. **Apply** – Explain we implement each task and check off. For each task: announce, implement, reference specs/design, mark complete, brief status. After all: completion summary.

10. **Archive** – Explain archive = move to `openspec/changes/archive/YYYY-MM-DD-<name>/`. Optionally sync specs. Do archive. Show location.

11. **Recap** – Summarize: Explore → New → Proposal → Specs → Design → Tasks → Apply → Archive. Give command reference table. Suggest trying `/opsx:new` or `/opsx:ff` next.

**Graceful exit**

- User wants to stop: Change is saved; resume with `/opsx:continue <name>` or `/opsx:apply <name>`. No pressure.
- User only wants command reference: Show quick reference table and exit.

**Guardrails**

- EXPLAIN → DO → SHOW → PAUSE at key transitions
- Keep narration light during implementation
- Don't skip phases (teaching goal)
- Pause for acknowledgment at marked points
- Handle exits gracefully
- Use real codebase tasks only
- Gently guide toward smaller tasks; respect user choice

**Edge cases**

- openspec list returns no changes after create: Confirm directory exists under openspec/changes/<name>/ and continue
- User has no small tasks: Suggest adding a trivial improvement (e.g. a TODO or docstring) or use a minimal example and label it as for learning only
