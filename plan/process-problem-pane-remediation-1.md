---
goal: Resolve all current Problems pane issues in workspace and transient chat buffers
version: 1.0
date_created: 2026-04-13
last_updated: 2026-04-13
owner: Harry Valdez
status: 'In progress'
tags: [process, diagnostics, pyright, fastmcp, bugfix]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

This plan defines deterministic remediation steps for all issues currently shown in the Problems pane. Scope includes workspace-backed diagnostics in `mcp_sqlserver/server.py` and transient diagnostics from `vscode-chat-code-block:*` buffers.

## 1. Requirements & Constraints

- **REQ-001**: Remove all diagnostics reported against `mcp_sqlserver/server.py`.
- **REQ-002**: Align imports in `_configure_tool_transformation_transform` with installed FastMCP module layout.
- **REQ-003**: Replace broad `ToolTransformConfig(**config_kwargs)` usage with explicit, type-safe argument construction.
- **REQ-004**: Keep existing runtime behavior for transform mapping while fixing static typing errors.
- **REQ-005**: Ensure post-fix Problems pane has no repository-file diagnostics.
- **REQ-006**: Include explicit cleanup steps for transient `vscode-chat-code-block:*` diagnostics.
- **SEC-001**: Do not broaden write capabilities or change auth/readonly safeguards while fixing typing/import issues.
- **OPS-001**: Preserve startup resilience when optional transform components are unavailable.
- **CON-001**: Avoid suppression-only fixes (`# type: ignore`) unless no code-level correction exists.
- **CON-002**: Keep changes minimal and localized to diagnostics-related code paths.
- **GUD-001**: Follow existing transform configurator patterns in `mcp_sqlserver/server.py`.
- **PAT-001**: Prefer explicit parameter passing and narrow types over untyped kwargs expansion.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Capture and classify all current Problems pane diagnostics.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Re-run diagnostics and capture current entries; confirm one actionable workspace cluster in `mcp_sqlserver/server.py` and transient entries under `vscode-chat-code-block:*`. | ✅ | 2026-04-13 |
| TASK-002 | Record root causes: incorrect `ToolTransformConfig` import location and overly broad `dict[str, str]` kwargs expansion into `ToolTransformConfig`. | ✅ | 2026-04-13 |
| TASK-003 | Define acceptance criteria: no diagnostics in repository files, plus explicit closure/cleanup of transient chat buffers. | ✅ | 2026-04-13 |

### Implementation Phase 2

- GOAL-002: Fix repository-backed diagnostics in transform configuration code.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Update import in `_configure_tool_transformation_transform` to import `ToolTransform` from `fastmcp.server.transforms.tool_transform` and `ToolTransformConfig` from `fastmcp.tools.tool_transform`. | ✅ | 2026-04-13 |
| TASK-005 | Change `transforms_dict` to a precise type (`dict[str, ToolTransformConfig]`) for static correctness. | ✅ | 2026-04-13 |
| TASK-006 | Replace `ToolTransformConfig(**config_kwargs)` with explicit constructor arguments (`name=...`, `description=...`) from parsed maps. | ✅ | 2026-04-13 |
| TASK-007 | Verify no behavioral change in mapping semantics for tool names and descriptions. | ✅ | 2026-04-13 |

### Implementation Phase 3

- GOAL-003: Validate changes and lock in regression coverage.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Run targeted diagnostics check for `mcp_sqlserver/server.py` and confirm zero errors. | ✅ | 2026-04-13 |
| TASK-009 | Add/adjust tests in `tests/test_server_startup_config.py` to validate transform config creation and type-correct construction paths. | ✅ | 2026-04-13 |
| TASK-010 | Run focused test suite (`tests/test_server_startup_config.py`) using workspace venv and repo PYTHONPATH. | ✅ | 2026-04-13 |

### Implementation Phase 4

- GOAL-004: Resolve non-repository transient diagnostics and close the plan.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Close or clear the `vscode-chat-code-block:*` editor buffers generating transient parser/type errors. |  |  |
| TASK-012 | Re-open Problems pane and confirm no remaining issues from repository files or transient chat code blocks. |  |  |
| TASK-013 | Update plan status to `Completed` once all checks pass. |  |  |

## 3. Alternatives

- **ALT-001**: Add suppression comments for Pylance diagnostics. Rejected because this hides real import/type mismatches.
- **ALT-002**: Use `dict[str, Any]` and keep kwargs expansion. Rejected because it weakens type safety and does not prevent future schema drift.
- **ALT-003**: Ignore transient chat-buffer diagnostics. Rejected because request scope is all issues currently shown in Problems pane.

## 4. Dependencies

- **DEP-001**: `mcp_sqlserver/server.py` transform configuration function.
- **DEP-002**: `tests/test_server_startup_config.py` for focused regression coverage.
- **DEP-003**: Installed FastMCP package layout in `.venv/Lib/site-packages/fastmcp`.
- **DEP-004**: VS Code Problems pane state including transient `vscode-chat-code-block:*` entries.

## 5. Files

- **FILE-001**: `mcp_sqlserver/server.py` - import/type-safe transform config fixes.
- **FILE-002**: `tests/test_server_startup_config.py` - regression tests for transform config behavior.
- **FILE-003**: `plan/process-problem-pane-remediation-1.md` - this execution plan.

## 6. Testing

- **TEST-001**: Diagnostics check for `mcp_sqlserver/server.py` returns zero errors.
- **TEST-002**: `pytest tests/test_server_startup_config.py` passes using the workspace venv command prefix.
- **TEST-003**: End-state Problems pane shows no repository-file diagnostics.
- **TEST-004**: End-state Problems pane shows no remaining `vscode-chat-code-block:*` diagnostics.

## 7. Risks & Assumptions

- **RISK-001**: Future FastMCP package updates may move transform classes again.
- **RISK-002**: Transient chat diagnostics can reappear if old scratch buffers are reopened.
- **ASSUMPTION-001**: Current repository diagnostics are limited to the transform import/typing cluster in `mcp_sqlserver/server.py`.
- **ASSUMPTION-002**: Existing runtime behavior should remain unchanged after typed-constructor refactor.

## 8. Related Specifications / Further Reading

- plan/architecture-fastmcp-transforms-wildcard-1.md
- plan/architecture-fastmcp-plan-index-1.md
- .venv/Lib/site-packages/fastmcp/server/transforms/tool_transform.py
- .venv/Lib/site-packages/fastmcp/tools/tool_transform.py
