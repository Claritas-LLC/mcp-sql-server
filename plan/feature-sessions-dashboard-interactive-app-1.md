---
goal: Interactive Sessions Dashboard App For db_{instance_number}_sql2019_sessions_dashboard
version: 1.0
date_created: 2026-05-07
last_updated: 2026-05-07
owner: Database Platform Team
status: Completed
tags: [feature, architecture, mcp, interactive-app, dashboard]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines the exact implementation steps to evolve the existing sessions dashboard tool into an interactive FastMCP app that renders and updates a web-based dashboard using FastMCPApp, Prefab UI components, and app-scoped backend tools. The plan follows guidance from https://gofastmcp.com/apps/interactive-apps, including entry-point UI tools, app backend tools, CallTool action wiring, state management, and composition-safe tool references.

## 1. Requirements & Constraints

- REQ-001: Preserve compatibility with the existing registered tool naming convention, including db_{instance_number}_sql2019_sessions_dashboard.
- REQ-002: Provide a model-visible app entry point that opens an interactive dashboard webpage.
- REQ-003: Move server work to app backend tools callable from UI actions via CallTool.
- REQ-004: Support interactive filtering controls for database_name, lookback_minutes, and include_locks.
- REQ-005: Display lock chains, head blockers, and recommendation summaries in reactive UI sections.
- REQ-006: Keep session, rate-limit, write-guard, metrics, and audit behavior equivalent to current tool semantics.
- REQ-007: Return deterministic, typed payloads for UI state updates and error handling.
- SEC-001: All backend queries must remain read-only and pass write guard policy enforcement.
- SEC-002: No sensitive values may be rendered unredacted in the dashboard view.
- SEC-003: Preserve request tracing with request_id in both server logs and client context logs.
- CON-001: Existing tool contracts in [src/tools/sql_tools.py](src/tools/sql_tools.py) must continue to work for non-app clients.
- CON-002: No breaking changes to existing diagnostics routes or metrics labels.
- CON-003: Interactive app dependencies must be pinned to stable versions, including prefab-ui.
- GUD-001: Use FastMCPApp decorators: app.ui for entry points and app.tool for backend tools.
- GUD-002: Use CallTool with function references where possible for composition safety.
- GUD-003: Use RESULT and SetState callbacks for post-call state updates; use ShowToast for errors.
- PAT-001: Separate UI layout construction from data-fetching backend tools.
- PAT-002: Keep backend tools app-visible by default and expose model-visible tools only when required.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Define architecture and dependencies for interactive sessions dashboard app.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Create architecture decision note in [docs/runbooks/scaling-strategy.md](docs/runbooks/scaling-strategy.md) addendum describing FastMCPApp entry tool, app backend tools, and state model for sessions dashboard. | Yes | 2026-05-07 |
| TASK-002 | Update dependencies in [pyproject.toml](pyproject.toml) to include prefab-ui and required FastMCP app packages with pinned versions. | Yes | 2026-05-07 |
| TASK-003 | Define typed dashboard state schema and payload contract in [src/tools/dashboard_payloads.py](src/tools/dashboard_payloads.py) for sections sessions, locks, blockers, recommendations, and ui_meta. | Yes | 2026-05-07 |
| TASK-004 | Add a development usage note for interactive app testing in [docs/run-mcp-server-with-docker.md](docs/run-mcp-server-with-docker.md) with standalone and mounted modes. | Yes | 2026-05-07 |

### Implementation Phase 2

- GOAL-002: Implement FastMCPApp provider and UI entry point for sessions dashboard.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-005 | Add a new module [src/tools/sessions_dashboard_app.py](src/tools/sessions_dashboard_app.py) containing app = FastMCPApp("Sessions Dashboard"). | Yes | 2026-05-07 |
| TASK-006 | Implement app.ui entry function named open_sessions_dashboard_app with title and description aligned to db_{instance_number}_sql2019_sessions_dashboard semantics. | Yes | 2026-05-07 |
| TASK-007 | Build Prefab UI view with controls for database_name, lookback_minutes, include_locks, refresh button, and sections for active sessions and lock chains. | Yes | 2026-05-07 |
| TASK-008 | Initialize PrefabApp state with defaults: loading false, error null, sessions empty list, lock_chains empty list, head_blockers empty list, recommendations empty list. | Yes | 2026-05-07 |

### Implementation Phase 3

- GOAL-003: Implement app backend tools and UI action wiring.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-009 | Implement app.tool backend function fetch_sessions_dashboard_data that reuses existing query logic from [src/tools/sql_tools.py](src/tools/sql_tools.py) and [src/tools/query_catalog.py](src/tools/query_catalog.py). | Yes | 2026-05-07 |
| TASK-010 | Implement app.tool backend function fetch_lock_chains_data with include_locks guard and normalized return payload for UI rendering. | Yes | 2026-05-07 |
| TASK-011 | Wire UI actions using CallTool with on_success SetState updates and ShowToast success or error messages, including loading-state toggling. | Yes | 2026-05-07 |
| TASK-012 | Use function-reference CallTool bindings for backend tools to remain namespace-safe during composition and mounting. | Yes | 2026-05-07 |

### Implementation Phase 4

- GOAL-004: Integrate app provider into server registration while preserving existing tool compatibility.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-013 | Register new FastMCPApp provider in [src/server.py](src/server.py) through providers list or add_provider without removing current tools. | Yes | 2026-05-07 |
| TASK-014 | Keep current db_{instance_number}_sql2019_sessions_dashboard tool in [src/tools/sql_tools.py](src/tools/sql_tools.py) and add optional link metadata to launch interactive app when client supports apps. | Yes | 2026-05-07 |
| TASK-015 | Ensure audit, metrics, and request lifecycle instrumentation parity by reusing existing request_id generation and REQUEST_COUNT or REQUEST_LATENCY labels. | Yes | 2026-05-07 |
| TASK-016 | Add explicit fallback behavior: if app transport is unavailable, return existing payload path from build_sessions_dashboard unchanged. | Yes | 2026-05-07 |

### Implementation Phase 5

- GOAL-005: Validate behavior, performance, and operational readiness.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-017 | Add unit tests in [tests/test_diagnostics_tool_usage_summary.py](tests/test_diagnostics_tool_usage_summary.py) or a new app test file to validate app state transitions and CallTool result mapping. | Yes | 2026-05-07 |
| TASK-018 | Add integration tests in [tests/test_advanced_analysis_tools.py](tests/test_advanced_analysis_tools.py) or a new sessions app test file to validate end-to-end app rendering and data refresh. | Yes | 2026-05-07 |
| TASK-019 | Run syntax and tests via existing scripts and commands documented in [testing/run_unit_phase.py](testing/run_unit_phase.py) and [testing/run_integration_phase.py](testing/run_integration_phase.py). | Yes | 2026-05-07 |
| TASK-020 | Validate Docker runtime behavior with app enabled using [docker/docker-compose.runtime.yml](docker/docker-compose.runtime.yml) and publish updated runbook notes. | Yes | 2026-05-07 |

## 3. Alternatives

- ALT-001: Continue using only app=True display tools without FastMCPApp decorators. Rejected because backend tool visibility and namespacing become brittle as tool count grows.
- ALT-002: Implement a separate external web frontend outside FastMCP. Rejected because it duplicates transport, auth, and server-tool orchestration already provided by FastMCP interactive apps.
- ALT-003: Replace existing sessions dashboard tool entirely with app-only entry point. Rejected to avoid breaking non-app clients and existing automation consumers.

## 4. Dependencies

- DEP-001: FastMCP version supporting FastMCPApp and interactive app providers.
- DEP-002: Prefab UI package pinned to a stable version compatible with selected FastMCP version.
- DEP-003: Existing database access layer in [src/db/connection_manager.py](src/db/connection_manager.py).
- DEP-004: Existing diagnostics payload builder in [src/tools/dashboard_payloads.py](src/tools/dashboard_payloads.py).
- DEP-005: Existing catalog queries in [src/tools/query_catalog.py](src/tools/query_catalog.py).

## 5. Files

- FILE-001: [src/tools/sessions_dashboard_app.py](src/tools/sessions_dashboard_app.py) create app provider, app.ui entry point, app.tool backend functions.
- FILE-002: [src/server.py](src/server.py) register FastMCPApp provider.
- FILE-003: [src/tools/sql_tools.py](src/tools/sql_tools.py) preserve compatibility path and optional app-launch metadata.
- FILE-004: [src/tools/dashboard_payloads.py](src/tools/dashboard_payloads.py) align payload keys to interactive state model.
- FILE-005: [pyproject.toml](pyproject.toml) add and pin interactive app dependencies.
- FILE-006: [docs/run-mcp-server-with-docker.md](docs/run-mcp-server-with-docker.md) document interactive app run and debug workflow.
- FILE-007: [tests/test_diagnostics_tool_usage_summary.py](tests/test_diagnostics_tool_usage_summary.py) add behavioral validation.

## 6. Testing

- TEST-001: Unit test UI state initialization and default rendering structure.
- TEST-002: Unit test CallTool success path updates sessions and lock_chains state.
- TEST-003: Unit test CallTool error path sets error state and emits toast metadata.
- TEST-004: Integration test app entry point invocation from model-visible tool list.
- TEST-005: Integration test backend tool visibility is app-only and not model-visible unless explicitly enabled.
- TEST-006: Regression test existing db_{instance_number}_sql2019_sessions_dashboard output contract for non-app clients.
- TEST-007: Performance test refresh interaction under bounded lookback and lock-heavy scenarios.

## 7. Risks & Assumptions

- RISK-001: Interactive app dependency drift may break UI behavior if package versions are not pinned.
- RISK-002: UI state payload growth may increase latency for large session or lock sets.
- RISK-003: Mixed client support for interactive apps may create inconsistent UX unless fallback is explicit.
- ASSUMPTION-001: db_{instance_number}_sql2019_sessions_dashboard refers to the MCP tool name and not a physical SQL database name.
- ASSUMPTION-002: Existing transport and auth settings permit interactive app responses in target environment.
- ASSUMPTION-003: Current diagnostics query permissions are sufficient for backend app tool execution.

## 8. Related Specifications / Further Reading

https://gofastmcp.com/apps/interactive-apps
https://gofastmcp.com/apps/prefab
https://gofastmcp.com/apps/patterns
https://gofastmcp.com/apps/development
https://prefab.prefect.io/