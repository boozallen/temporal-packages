---
name: openspec-document-codebase
description: Document existing codebase capabilities as OpenSpec specs. Use when the user wants to reverse-engineer current functionality into specification documents for future reference or regeneration.
license: MIT
compatibility: None required (file operations only).
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.1.1"
---

Document existing codebase capabilities by creating OpenSpec specification files that describe current functionality.

**Input**: Optional capability name (kebab-case). If provided, document only that capability. If omitted, analyze the entire codebase and document all major capabilities (e.g. foundry-temporal, foundry-strands-agents packages, workflows, activities, MCP in this repo).

**Steps**

1. **Determine scope**  
   Capability name given → that capability only. No input → identify all major capabilities (packages and their public APIs).

2. **Analyze the codebase**  
   For each capability: name (kebab-case), purpose, main file paths under packages/, key requirements (current behavior), dependencies/dependents, edge cases and error handling, configuration (pyproject.toml, env), public interfaces. Focus on: core business logic, public APIs/interfaces, key workflows or activities, integration capabilities, configuration/packaging.

3. **Create spec directories**  
   For each capability: `openspec/specs/<capability-name>/`. Kebab-case. Avoid conflicts with existing specs. Optionally use numbering (001-, 002-) for ordering.

4. **Create spec.md files**  
   For each capability, create `openspec/specs/<capability>/spec.md` with:
   - Overview, Problem Statement, User Stories (if applicable)
   - Technical Specification (current implementation)
   - Requirements with scenarios (WHEN/THEN)
   - Current Implementation (paths, components, dependencies)
   - Non-Functional Requirements (performance, security, reliability where relevant)
   - Dependencies, Edge Cases, Configuration, Public Interfaces
   - Notes (limitations, tech debt, future considerations)

5. **Regeneration test**  
   For each spec: Would implementing this spec recreate the same capability? Are all behaviors, edge cases, config, and interfaces documented? If no, add detail.

6. **Validate against code**  
   Verify paths exist; requirements match actual behavior; only existing behavior (no planned features).

**Output**

Summarize: capabilities identified and documented, spec directories created, key findings or gaps, next steps if documenting incrementally.

**Guardrails**

- Focus on WHAT (behavior), not HOW (implementation details)
- Be accurate: specs must match actual code
- Complete: use regeneration test
- No forward-looking: existing behavior only
- Reference implementation: include file paths
- Start with core capabilities (e.g. foundry-temporal, foundry-strands-agents)

**Error handling**

- Capability not found: Ask user to clarify or list capabilities
- Spec directory already exists: Ask whether to update or create new
- Code ambiguous: Ask for clarification
- Dependencies unclear: Document what's known, note what needs investigation

**Edge cases**

- Monorepo with packages: Scope by package (e.g. foundry-temporal, foundry-strands-agents) or document cross-package capabilities; clarify with user if needed
- Partial implementation: Document what exists and note gaps in Notes
- Generated or external API: Document the observable contract; note source in Notes
