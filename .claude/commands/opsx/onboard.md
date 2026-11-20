---
name: "OPSX: Onboard"
description: Guided onboarding - walk through a complete OpenSpec workflow cycle with narration
category: Workflow
tags: [workflow, onboarding, tutorial, learning]
---

Guide the user through their first complete OpenSpec workflow cycle. This is a teaching experience—you'll do real work in their codebase while explaining each step.

---

## Preflight

Before starting, check if OpenSpec is initialized:

```bash
openspec status --json 2>&1 || echo "NOT_INITIALIZED"
```

**If not initialized:**
> OpenSpec isn't set up in this project yet. Run `openspec init` first, then come back to `/opsx:onboard`.

Stop here if not initialized.

---

## Phase 1: Welcome

Display a welcome that explains you'll walk through a complete change cycle—from idea to implementation—using a real task. What we'll do: (1) Pick a small real task, (2) Explore briefly, (3) Create a change, (4) Build artifacts: proposal → specs → design → tasks, (5) Implement tasks, (6) Archive. Time: ~15–20 minutes. Start by finding something to work on.

---

## Phase 2: Task Selection

**Codebase Analysis:** Scan for small improvement opportunities: TODO/FIXME comments, missing error handling, functions without tests, type issues, debug artifacts, missing validation. Optionally check recent git activity.

**Present Suggestions:** From your analysis, present 3–4 specific suggestions (location, scope, why it's good). Include "Something else?" so they can describe their own. If nothing found, ask what they'd like to add or fix.

**Scope Guardrail:** If the user picks something too large (major feature, multi-day work), suggest slicing smaller or picking one of the other options; allow override if they insist.

---

## Phase 3: Explore Demo

Briefly demonstrate explore mode: spend 1–2 minutes investigating the relevant code (read files, optional ASCII diagram, note considerations). Explain that `/opsx:explore` is for this kind of thinking. **PAUSE** for acknowledgment.

---

## Phase 4: Create the Change

**EXPLAIN:** A "change" is a container for thinking and planning; it lives in `openspec/changes/<name>/` and holds proposal, specs, design, tasks.

**DO:** Create the change with a derived kebab-case name: `openspec new change "<derived-name>"`. Show the folder structure (proposal.md, design.md, specs/, tasks.md). Say we'll fill the first artifact—the proposal.

---

## Phase 5: Proposal

**EXPLAIN:** The proposal captures WHY and WHAT at a high level.

**DO:** Draft proposal content (Why, What Changes, Capabilities, Impact). **PAUSE** for approval/feedback. After approval, write to `openspec/changes/<name>/proposal.md`. Next: specs.

---

## Phase 6: Specs

**EXPLAIN:** Specs define WHAT in precise, testable terms (requirement/scenario format).

**DO:** Create `openspec/changes/<name>/specs/<capability>/spec.md`. Draft ADDED requirements with scenarios (WHEN/THEN). Save. Explain WHEN/THEN makes requirements testable.

---

## Phase 7: Design

**EXPLAIN:** Design captures HOW—technical decisions, tradeoffs. For small changes it can be brief.

**DO:** Draft design.md (Context, Goals/Non-Goals, Decisions). Save.

---

## Phase 8: Tasks

**EXPLAIN:** Tasks break work into implementation checkboxes that drive the apply phase.

**DO:** Generate tasks from specs and design (numbered groups, `- [ ] X.Y` format). **PAUSE** for confirmation. Save to `openspec/changes/<name>/tasks.md`.

---

## Phase 9: Apply (Implementation)

**EXPLAIN:** We implement each task, checking them off. You'll note how specs/design inform the approach.

**DO:** For each task: announce it, implement, reference specs/design naturally, mark complete in tasks.md, brief status. After all tasks: show completion summary.

---

## Phase 10: Archive

**EXPLAIN:** When complete, we archive: move change to `openspec/changes/archive/YYYY-MM-DD-<name>/`. Archived changes become decision history.

**DO:** Run archive (e.g. move directory, prompt for sync if delta specs exist). Show archive location.

---

## Phase 11: Recap & Next Steps

Summarize what we did (Explore → New → Proposal → Specs → Design → Tasks → Apply → Archive). Provide command reference table (e.g. `/opsx:explore`, `/opsx:new`, `/opsx:ff`, `/opsx:continue`, `/opsx:apply`, `/opsx:verify`, `/opsx:archive`). Suggest trying `/opsx:new` or `/opsx:ff` on something they want to build.

---

## Graceful Exit Handling

**User wants to stop mid-way:** Tell them the change is saved at `openspec/changes/<name>/`. To resume: `/opsx:continue <name>` or `/opsx:apply <name>`. Exit without pressure.

**User just wants command reference:** Show the quick reference table and exit.

---

## Guardrails

- Follow EXPLAIN → DO → SHOW → PAUSE at key transitions
- Keep narration light during implementation
- Don't skip phases (goal is teaching the workflow)
- Pause for acknowledgment at marked points
- Handle exits gracefully; use real codebase tasks
- Gently guide toward smaller tasks but respect user choice

**Skill**: Use openspec-onboard skill for full onboarding flow and wording.
