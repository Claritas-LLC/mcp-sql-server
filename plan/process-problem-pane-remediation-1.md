---
goal: Resolve all current Problems pane issues for the MCP SQL Server workspace and clear transient non-workspace diagnostics
version: 1.0
date_created: 2026-04-13
last_updated: 2026-04-13
owner: Harry Valdez
status: 'In progress'
tags: [process, diagnostics, typing, fastmcp, pyright, bug]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

This plan defines the deterministic remediation sequence for all issues currently visible in the VS Code Problems pane as of 2026-04-13. The scope includes actionable workspace diagnostics in `mcp_sqlserver/server.py` and explicit handling of transient `vscode-chat-code-block:*` diagnostics that are not backed by repository files.

## 1. Requirements & Constraints

- **REQ-001**: Eliminate all workspace-backed Problems pane diagnostics reported for `mcp_sqlserver/server.py`.
- **REQ-002**: Resolve the incorrect FastMCP import split in `_configure_tool_transformation_transform` so runtime imports and static analysis agree.
- **REQ-003**: Remove the `ToolTransformConfig(**config_kwargs)` typing errors by replacing the untyped kwargs pattern with explicit constructor arguments that match the installed FastMCP model.
- **REQ-004**: Remove all `custom_route(...)(handler)` callable diagnostics in `_register_dashboard_routes` without changing runtime route behavior.
- **REQ-005**: Preserve existing HTTP route registration behavior for `/health`, `/sessions-monitor`, `/sessions-monitor/data`, `/data-model-analysis`, `/data-model-analysis/generate`, and `/data-model-analysis/stats`.
- **REQ-006**: Distinguish repository diagnostics from transient `vscode-chat-code-block:*` diagnostics and define the exact cleanup action for the latter.
- **REQ-007**: Verify the final Problems pane state with workspace diagnostics re-queried after implementation.
- **SEC-001**: Do not weaken existing auth, read-only, or route registration safeguards while changing typing or import code.
- **OPS-001**: Keep compatibility with the installed FastMCP package layout where `ToolTransform` is defined in `fastmcp.server.transforms.tool_transform` and `ToolTransformConfig` is defined in `fastmcp.tools.tool_transform`.
- **OPS-002**: Preserve startup behavior when optional transform APIs are unavailable.
- **CON-001**: Do not introduce `type: ignore`, blanket casts, or suppression-only fixes unless a code-level correction is impossible.
- **CON-002**: Do not create new markdown documentation outside `plan/` for this remediation.
- **CON-003**: Treat `vscode-chat-code-block:*` diagnostics as editor-buffer artifacts, not repository source files.
- **GUD-001**: Reuse the existing typed route registration pattern already present in `_register_health_route` instead of inventing a new FastMCP integration style.
- **PAT-001**: Prefer explicit constructor arguments and typed local helpers over broad `dict[str, str]` kwargs expansion for Pydantic/FastMCP models.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Freeze the diagnostic scope and separate repository issues from transient editor issues.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Re-run workspace diagnostics and record the exact actionable repository issues in `mcp_sqlserver/server.py`: incorrect `ToolTransformConfig` import at line 1326, incorrect `dict[str, str]` kwargs expansion at line 1335, and callable inference failures at lines 1806-1810. | ✅ | 2026-04-13 |
| TASK-002 | Record the two `vscode-chat-code-block:*` diagnostics as transient editor artifacts and exclude them from repository code changes. The remediation action for these artifacts is to close the chat scratch buffers or clear the corresponding chat code blocks after repository fixes are complete. | ✅ | 2026-04-13 |
| TASK-003 | Define success criteria: `get_errors` returns no diagnostics for any repository file under the workspace root after code changes and targeted verification are complete. | ✅ | 2026-04-13 |

### Implementation Phase 2

- **GOAL-002**: Correct the FastMCP tool transformation import and constructor typing in `mcp_sqlserver/server.py`.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-004 | Update `_configure_tool_transformation_transform` in `mcp_sqlserver/server.py` so imports match the installed FastMCP package layout: import `ToolTransform` from `fastmcp.server.transforms.tool_transform` and import `ToolTransformConfig` from `fastmcp.tools.tool_transform`. | ✅ | 2026-04-13 |
| TASK-005 | Replace `config_kwargs: dict[str, str] = {}` plus `ToolTransformConfig(**config_kwargs)` with explicit local values `mapped_name` and `mapped_description`, then construct `ToolTransformConfig(name=mapped_name, description=mapped_description)`. This removes false inference for `tags`, `meta`, `enabled`, and `arguments` while preserving runtime behavior. | ✅ | 2026-04-13 |
| TASK-006 | Keep `transforms_dict` typed as `dict[str, ToolTransformConfig]` or an equivalent precise type instead of `dict[str, Any]` so the tool transform pipeline is statically validated end to end. | ✅ | 2026-04-13 |

### Implementation Phase 3

- **GOAL-003**: Correct dashboard route registration typing without changing HTTP behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-007 | Refactor `_register_dashboard_routes` in `mcp_sqlserver/server.py` to mirror the `_register_health_route` pattern by storing each `custom_route(...)` result in a typed local `route_decorator` before applying it to the handler, or by introducing a small local helper that performs the same two-step registration for all dashboard routes. | ✅ | 2026-04-13 |
| TASK-008 | Ensure the selected route-registration helper or local variable pattern uses the callable shape documented by FastMCP transport mixin: `Callable[[Callable[[Request], Awaitable[Response]]], Callable[[Request], Awaitable[Response]]]`. Use imports from `collections.abc` and Starlette only if needed to satisfy static analysis. | ✅ | 2026-04-13 |
| TASK-009 | Verify that `_register_dashboard_routes` still registers exactly five dashboard routes: `/sessions-monitor`, `/sessions-monitor/data`, `/data-model-analysis`, `/data-model-analysis/generate`, and `/data-model-analysis/stats`. | ✅ | 2026-04-13 |

### Implementation Phase 4

- **GOAL-004**: Add regression coverage for the corrected typing and route-registration behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-010 | Extend `tests/test_server_startup_config.py` with a focused test for `_configure_tool_transformation_transform` that monkeypatches `SETTINGS` to enable the transform, supplies both name and description maps, and asserts the returned object is a `ToolTransform` configured for the expected tool keys. | ✅ | 2026-04-13 |
| TASK-011 | Extend `tests/test_server_startup_config.py` or the most relevant existing HTTP test file to assert `_register_dashboard_routes` calls `mcp.custom_route` five times and does not raise when using the fake FastMCP instance shape already used in the test suite. | ✅ | 2026-04-13 |
| TASK-012 | Keep existing `_resolve_http_app` and route-registration tests green by preserving the current `custom_route=Mock(side_effect=lambda **_kwargs: (lambda fn: fn))` contract used in tests. | ✅ | 2026-04-13 |

### Implementation Phase 5

- **GOAL-005**: Validate the remediation and clear non-repository diagnostics from the working session.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-013 | Run targeted validation with `get_errors` against the workspace root and confirm `mcp_sqlserver/server.py` no longer reports import or callable diagnostics. | ✅ | 2026-04-13 |
| TASK-014 | Run targeted tests covering the touched code paths, at minimum `pytest tests/test_server_startup_config.py`, and record pass/fail output. | ✅ | 2026-04-13 |
| TASK-015 | Clear the remaining `vscode-chat-code-block:*` Problems entries by closing the corresponding chat scratch editors or removing the temporary code blocks that generated those non-workspace diagnostics. |  |  |
| TASK-016 | Re-open the Problems pane and confirm the final state contains zero workspace diagnostics and zero remaining transient chat-buffer diagnostics for the current session. |  |  |

## 3. Alternatives

- **ALT-001**: Add `# type: ignore` to the import and route-registration lines. Rejected because it suppresses defects instead of aligning code with the installed FastMCP APIs.
- **ALT-002**: Broaden `config_kwargs` from `dict[str, str]` to `dict[str, Any]` and keep `ToolTransformConfig(**config_kwargs)`. Rejected because it weakens type checking and still hides the true model contract.
- **ALT-003**: Ignore `vscode-chat-code-block:*` diagnostics completely. Rejected because the user requested a plan for all Problems pane issues, so transient items must be explicitly triaged and cleared.

## 4. Dependencies

- **DEP-001**: `mcp_sqlserver/server.py` contains the active diagnostics and the production code paths to update.
- **DEP-002**: `tests/test_server_startup_config.py` already contains FastMCP mock patterns for `custom_route` and should be the primary regression harness.
- **DEP-003**: Installed FastMCP package layout in `.venv/Lib/site-packages/fastmcp/` defines `ToolTransform` in `server/transforms/tool_transform.py` and `ToolTransformConfig` in `tools/tool_transform.py`.
- **DEP-004**: VS Code Problems pane state must be re-queried after code and editor-buffer cleanup.

## 5. Files

- **FILE-001**: `mcp_sqlserver/server.py` - correct FastMCP imports, explicit `ToolTransformConfig` construction, and dashboard route registration typing.
- **FILE-002**: `tests/test_server_startup_config.py` - add regression coverage for tool transformation configuration and dashboard route registration.
- **FILE-003**: `plan/process-problem-pane-remediation-1.md` - execution plan and remediation record.

## 6. Testing

- **TEST-001**: `get_errors` for the workspace root returns no diagnostics for repository files after implementation.
- **TEST-002**: `pytest tests/test_server_startup_config.py` passes with new transform and dashboard-route assertions.
- **TEST-003**: Manual smoke of HTTP startup confirms `_resolve_http_app()` still registers the health route and dashboard routes without runtime exceptions.
- **TEST-004**: Manual editor validation confirms `vscode-chat-code-block:*` diagnostics disappear after closing the transient chat buffers.

## 7. Risks & Assumptions

- **RISK-001**: A future FastMCP upgrade could move `ToolTransform` or `ToolTransformConfig` again, requiring import updates beyond this plan.
- **RISK-002**: Over-tightening local callable annotations for `custom_route` could create unnecessary test friction if the fake MCP object in tests diverges from the runtime signature.
- **RISK-003**: The chat-buffer diagnostics may reappear if the same invalid scratch code is reopened later in the session.
- **ASSUMPTION-001**: The current Problems pane contains no additional workspace-backed diagnostics beyond `mcp_sqlserver/server.py`.
- **ASSUMPTION-002**: The repository should treat transient `vscode-chat-code-block:*` issues as session artifacts, not source-controlled defects.
- **ASSUMPTION-003**: Existing HTTP route behavior is correct; only static typing and registration shape require adjustment.

## 8. Related Specifications / Further Reading

plan/architecture-fastmcp-plan-index-1.md
plan/architecture-fastmcp-transforms-wildcard-1.md
tests/test_server_startup_config.py
.venv/Lib/site-packages/fastmcp/server/transforms/tool_transform.py
.venv/Lib/site-packages/fastmcp/tools/tool_transform.py
.venv/Lib/site-packages/fastmcp/server/mixins/transport.py