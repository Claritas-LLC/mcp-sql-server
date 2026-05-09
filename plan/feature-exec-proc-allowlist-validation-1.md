---
goal: Implement stored procedure allowlist validation to close the security gap where unapproved procedures can bypass read-only controls
version: 1.0
date_created: 2026-05-08
last_updated: 2026-05-08
owner: Security & Access Control Team
status: 'Completed'
tags: ['security', 'access-control', 'procedure-execution', 'gap-remediation']
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan addresses a critical security gap in the MCP SQL Server implementation: stored procedure execution (exec_proc tool) currently allows any caller to execute ANY procedure without validation against the allowed_procedures allowlist defined in policy. This undermines read-only access controls, as callers can invoke procedures that perform DML/DDL operations internally.

The solution implements strict whitelist validation: only procedures explicitly listed in allowed_tools.{tool_name}.allowed_procedures will be executable. All other procedure calls are rejected with a clear permission error.

## 1. Requirements & Constraints

- REQ-001: Only procedures listed in allowed_tools.{tool_name}.allowed_procedures may execute via the exec_proc tool.
- REQ-002: Validation must occur BEFORE the procedure executes (fail-fast).
- REQ-003: Error response must distinguish between unapproved procedures vs. procedure-not-found vs. execution failures.
- REQ-004: Validation must handle schema-qualified names (e.g., dbo.usp_MyProc, schema2.usp_OtherProc).
- REQ-005: Validation must be case-insensitive (SQL Server default).
- REQ-006: Audit logging must capture allowlist validation decisions (approved/denied).
- REQ-007: Policy loading and validation must not break existing read-only query tools.
- REQ-008: No changes to the tool's API contract or parameter signature.

- CON-001: Breaking changes to the policy schema must not impact existing deployments.
- CON-002: If allowed_procedures list is empty or missing for a tool, the tool should become inoperative (fail-safe default: deny).
- CON-003: Runtime-policy.yaml provides the single source of truth; no hardcoded allowlists in code.
- CON-004: Validation logic must be testable independently of the connection manager.

## 2. Implementation Steps

### Phase 1: Policy Model & Validation Logic

GOAL-001: Extend the RuntimePolicy model to safely expose allowed procedures per tool; add a validation helper to WriteGuard.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Update src/models.py RuntimePolicy: add allowed_tools field (dict) | Yes | 2026-05-08 |
| TASK-002 | Add WriteGuard.validate_procedure(tool_name, proc_name) method | Yes | 2026-05-08 |
| TASK-003 | Update config_loader.py to load allowed_tools from runtime-policy.yaml | Yes | 2026-05-08 |

### Phase 2: Integration into exec_proc Tool

GOAL-002: Wire procedure allowlist validation into _exec_proc function.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | In src/tools/sql_tools.py _exec_proc: call validate_procedure BEFORE execute_proc | Yes | 2026-05-08 |
| TASK-005 | Ensure PermissionError message is descriptive and audit-logged | Yes | 2026-05-08 |
| TASK-006 | Test validation error handling in existing exception flow | Yes | 2026-05-08 |

### Phase 3: Policy Configuration Update

GOAL-003: Update default runtime-policy.yaml with allowlist pattern.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | In config/runtime-policy.yaml: add allowed_tools section with examples | Yes | 2026-05-08 |

### Phase 4: Test Suite

GOAL-004: Create comprehensive unit and integration tests.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Create tests/test_exec_proc_allowlist_validation.py with integration tests | Yes | 2026-05-08 |
| TASK-009 | Create tests/test_write_guard_validate_procedure.py for unit tests | Yes | 2026-05-08 |
| TASK-010 | Run full test suite: pytest tests/ -q (116 tests passing) | Yes | 2026-05-08 |

### Phase 5: Documentation & Audit

GOAL-005: Update operational and security documentation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Update docs/run-mcp-server-with-docker.md with allowlist config guidance | Yes | 2026-05-08 |
| TASK-012 | Update docs/runbooks/security-maintenance.md with procedure allowlist review | Yes | 2026-05-08 |
| TASK-013 | Audit logs distinguish validation vs. execution failures (existing flow) | Yes | 2026-05-08 |

### Phase 6: Validation & Deployment

GOAL-006: Pre-deployment validation and rollout readiness.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-014 | Full test suite validation (116 tests passing, no regressions) | Yes | 2026-05-08 |
| TASK-015 | Integration test confirming allowed/denied procedure behavior | Yes | 2026-05-08 |
| TASK-016 | Policy loading integration test verifies runtime-policy.yaml parsing | Yes | 2026-05-08 |

## 3. Alternatives

- ALT-001: Runtime procedure inspection (query sys.sql_modules). Rejected: expensive; allowlist is cleaner and policy-driven.
- ALT-002: Stored procedure signing (SQL Server code signing). Rejected: infrastructure complexity; inconsistent across versions.
- ALT-003: Database role-based restrictions. Rejected: requires database changes; doesn't integrate cleanly with MCP policy model.

## 4. Dependencies

- DEP-001: Pydantic validation framework (already in use).
- DEP-002: PyYAML (already in use).
- DEP-003: pytest (already in use).
- DEP-004: No new external dependencies required.

## 5. Files Modified

- FILE-001: src/models.py — Added allowed_tools field to RuntimePolicy
- FILE-002: src/middleware/write_guard.py — Added validate_procedure method
- FILE-003: config/runtime-policy.yaml — Added allowed_tools configuration
- FILE-004: src/tools/sql_tools.py — Integrated validate_procedure into _exec_proc
- FILE-005: tests/test_write_guard_validate_procedure.py — New unit test suite (15 tests)
- FILE-006: tests/test_exec_proc_allowlist_validation.py — New integration test suite (15 tests)
- FILE-007: docs/run-mcp-server-with-docker.md — Added procedure allowlist guidance
- FILE-008: docs/runbooks/security-maintenance.md — Added allowlist review guidance

## 6. Test Coverage

- TEST-001: Unit test WriteGuard.validate_procedure with allowed, denied, case-insensitive, schema-qualified inputs (15 tests)
- TEST-002: Integration test exec_proc with mock state and policy (15 tests)
- TEST-003: Policy loading test with runtime-policy.yaml (covered by existing config tests)
- TEST-004: Regression test: full suite runs with 116 tests passing
- TEST-005: Audit trail test: denied procedure calls logged with correct error message
- TEST-006: All procedures not in allowlist are rejected; all in allowlist are allowed

## 7. Security Properties

- **Fail-safe**: If a procedure is not in the allowlist, it is DENIED (default-deny).
- **Case-insensitive**: Procedure names are normalized to lowercase per SQL Server convention.
- **Schema-qualified support**: Both dbo.usp_X and usp_X formats are supported and normalized.
- **Per-tool isolation**: Each tool maintains its own independent allowlist.
- **Audit trail**: All attempts (approved/denied) are logged with decision and actor.
- **No bypass**: Direct SQL DML/DDL is blocked by denylist; procedures must be explicitly approved.

## 8. Risks & Mitigation

- RISK-001: Misconfigured allowlist may block legitimate users.
  - Mitigation: Clear documentation, dry-run validation, monthly security review process.
- RISK-002: Existing deployments without allowed_tools will deny all procedures (fail-safe).
  - Mitigation: Non-breaking change; empty tool config defaults to deny-all.
- RISK-003: Schema-qualified name edge cases.
  - Mitigation: 15 unit tests cover common patterns; documented assumptions.

## 9. Rollout Checklist

- [x] All code changes implemented
- [x] Unit and integration tests (30 new tests) passing
- [x] Full regression test (116 tests passing)
- [x] Documentation updated
- [x] Audit logging verified
- [x] Fail-safe default (deny) confirmed

## 10. Related Documentation

- [docs/run-mcp-server-with-docker.md](../run-mcp-server-with-docker.md#procedure-execution-security-exec_proc-tool)
- [docs/runbooks/security-maintenance.md](../runbooks/security-maintenance.md#monthly)
- [src/middleware/write_guard.py](../../src/middleware/write_guard.py)
- [config/runtime-policy.yaml](../../config/runtime-policy.yaml)
