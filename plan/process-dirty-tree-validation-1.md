---
goal: Validate and triage unexpected working-tree changes while continuing plan-only execution
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: Completed
tags: [process, validation, git, working-tree, risk]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan captures deterministic review and validation of unexpected working-tree changes and defines a safe continuation policy: proceed with plan/status updates only under the plan directory.

## 1. Requirements & Constraints

- **REQ-001**: Review all unexpected non-plan changed files before any further progression.
- **REQ-002**: Record risk findings with explicit file references and impact summaries.
- **REQ-003**: Continue implementation progress without modifying non-plan files.
- **SEC-001**: Treat ad hoc file-modifying scripts as high-risk until explicitly approved.
- **CON-001**: Touch only files under `plan/` for this continuation step.
- **CON-002**: Do not revert, amend, or rewrite unrelated working-tree changes.
- **GUD-001**: Keep findings deterministic and reproducible from current git diff.
- **PAT-001**: Separate validation status tracking from code-change execution.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Enumerate and classify unexpected changes.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Collect full changed-file diff snapshot and classify non-plan files as expected or unexpected. | Yes | 2026-04-09 |
| TASK-002 | Read helper scripts and validate whether they perform meaningful or no-op replacements. | Yes | 2026-04-09 |
| TASK-003 | Review newly added non-plan module files for API compatibility risk and import-path correctness. | Yes | 2026-04-09 |

### Implementation Phase 2

- GOAL-002: Record findings and enforce safe continuation policy.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-004 | Mark `fix_schem-name.py`, `fix_fragmentation.py`, and `fix_fragmentation_robust.py` as high-risk/no-value scripts due no-op replacements and unsafe direct file rewrite behavior. | Yes | 2026-04-09 |
| TASK-005 | Mark `mcp_sqlserver/resources.py` as compatibility-risk change pending explicit approval because it introduces unverified FastMCP API usage (`from fastmcp import mcp`). | Yes | 2026-04-09 |
| TASK-006 | Set continuation mode to plan-only/status-only updates under `plan/` while preserving all unrelated tree state. | Yes | 2026-04-09 |

## 3. Alternatives

- **ALT-001**: Revert unexpected files immediately. Rejected due instruction to avoid touching unrelated changes without explicit request.
- **ALT-002**: Continue coding in runtime files despite uncertainty. Rejected because risk classification is unresolved for several unexpected edits.
- **ALT-003**: Halt all progress. Rejected because plan-only progression remains safe and requested.

## 4. Dependencies

- **DEP-001**: Current git working-tree diff state.
- **DEP-002**: plan/architecture-fastmcp-plan-index-1.md
- **DEP-003**: plan/process-fastmcp-execution-checklist-1.md

## 5. Files

- **FILE-001**: plan/process-dirty-tree-validation-1.md - records validation outcome and continuation policy.
- **FILE-002**: plan/architecture-fastmcp-plan-index-1.md - links this validation artifact.

## 6. Testing

- **TEST-001**: Confirm changed-file inventory includes all unexpected non-plan files.
- **TEST-002**: Confirm continuation edits are restricted to `plan/` files only.

## 7. Risks & Assumptions

- **RISK-001**: Unexpected runtime-file edits may still contain latent regressions outside tested paths.
- **RISK-002**: Ad hoc fix scripts could be executed later and corrupt files if misused.
- **ASSUMPTION-001**: User-approved continuation mode remains plan-only until explicit direction changes.

## 8. Related Specifications / Further Reading

plan/architecture-fastmcp-plan-index-1.md
plan/process-fastmcp-execution-checklist-1.md
plan/architecture-fastmcp-server-alignment-1.md
