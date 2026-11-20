---
name: "OPSX: Document"
description: Document existing codebase capabilities as OpenSpec specs
category: Workflow
tags: [workflow, documentation, reverse-engineering, specs]
---

Document existing codebase capabilities by creating OpenSpec specification files that describe current functionality.

**Input**: Optional capability name (kebab-case). If provided, documents only that capability. If omitted, analyzes the entire codebase and documents all major capabilities.

**Steps**

1. **Determine scope**

   - If capability name provided: Focus on documenting that specific capability
   - If no input: Analyze the entire codebase to identify all major capabilities (e.g., foundry-temporal, foundry-temporal-agents packages, workflows, activities, MCP integrations)

2. **Analyze the codebase**

   For each capability to document:
   - Identify the capability name (kebab-case)
   - Understand what it does (high-level purpose)
   - Locate where it's implemented (main file paths under packages/)
   - Identify key requirements (current behavior)
   - Find dependencies and dependents
   - Identify edge cases and error handling
   - Document configuration options (pyproject.toml, env)
   - Identify public interfaces

   Focus on: core business logic, public APIs/interfaces, key workflows or activities, integration capabilities, configuration or packaging.

3. **Create spec directories**

   For each capability, create a spec directory under `openspec/specs/<capability-name>/`. Use kebab-case. Check existing specs to avoid conflicts. Optionally use numbering (e.g. 001-, 002-) for ordering if desired.

4. **Create spec.md files**

   For each capability, create `openspec/specs/<capability>/spec.md` that documents:
   - Overview: What the capability does
   - Problem Statement: Why it exists
   - User Stories / Who uses it and how (if applicable)
   - Technical Specification: Current implementation details
   - Requirements: All behaviors as requirements with scenarios (WHEN/THEN)
   - Current Implementation: File paths, components, dependencies
   - Non-Functional Requirements: Performance, security, reliability where relevant
   - Dependencies: External libraries, services, internal components
   - Edge Cases: Error handling, boundary conditions
   - Configuration: Options and their effects
   - Public Interfaces: APIs, contracts, data structures
   - Notes: Limitations, technical debt, future considerations

5. **Apply the Regeneration Test**

   For each spec, verify: Would implementing this spec recreate the same capability? Are all behaviors, edge cases, configuration options, and public interfaces documented? If any answer is "no", add more detail.

6. **Validate against code**

   Verify file paths exist; ensure requirements match actual code behavior; confirm dependencies and that only existing behavior is documented (no planned features).

**Output**

Summarize: capabilities identified and documented, spec directories created, key findings or gaps, next steps if documenting incrementally.

**Guardrails**

- Focus on WHAT (behavior), not HOW (implementation details)
- Be accurate: specs must match actual code behavior
- Complete specifications: use the regeneration test
- No forward-looking: only document existing behavior
- Reference implementation: include file paths for traceability
- Start with core capabilities (e.g., foundry-temporal, foundry-temporal-agents)

**Error Handling**

- If capability not found: Ask user to clarify or list available capabilities
- If spec directory already exists: Ask if user wants to update or create new
- If code analysis unclear: Ask for clarification on ambiguous behavior
- If dependencies unclear: Document what's known and note what needs investigation

**Example Usage**

- `/opsx:document` — Analyze entire codebase and create specs for major capabilities (packages)
- `/opsx:document foundry-temporal-worker` — Document only the foundry-temporal worker capability

**Skill**: Use openspec-document-codebase skill for detailed documentation workflow.
