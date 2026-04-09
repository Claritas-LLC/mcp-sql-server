---
goal: Execute Phase 1 startup configuration alignment for FastMCP server runtime
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: Completed
tags: [architecture, fastmcp, startup, configuration, phase-1]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines the exact Phase 1 implementation sequence for introducing deterministic FastMCP constructor and run configuration builders, then wiring them into current startup paths without changing tool contracts.

## 1. Requirements & Constraints

- **REQ-001**: Implement build_mcp_run_config in mcp_sqlserver/server.py and use it as the canonical source for runtime transport arguments.
- **REQ-002**: Implement build_mcp_constructor_config in mcp_sqlserver/server.py and use it as the canonical source for FastMCP initialization arguments.
- **REQ-003**: Preserve all existing tool decorators and tool names currently bound to the global mcp object.
- **REQ-004**: Preserve validation behavior from _validate_runtime_guards and existing Settings parsing in _load_settings.
- **SEC-001**: Keep write safety checks unchanged for transport and auth guard logic.
- **SEC-002**: Do not weaken current handling for FASTMCP_AUTH_TYPE and FASTMCP_API_KEY.
- **OPS-001**: Maintain compatibility with Windows runtime and existing startup via module execution and server_startup.py.
- **CON-001**: Do not rename existing environment variables in .env.example.
- **CON-002**: Do not split mcp_sqlserver/server.py in this phase.
- **GUD-001**: Add deterministic tests for new builder functions.
- **PAT-001**: One function owns constructor args; one function owns run args; no duplicated startup argument assembly.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Introduce deterministic startup configuration builders in mcp_sqlserver/server.py with full test coverage.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Insert function build_mcp_constructor_config directly below current MCP_SERVER_NAME declaration in mcp_sqlserver/server.py. Function returns dict with key name set to MCP_SERVER_NAME and optional keys for instructions, version, list_page_size when values are configured. | Yes | 2026-04-09 |
| TASK-002 | Replace direct mcp = FastMCP(name=MCP_SERVER_NAME) assignment with mcp = FastMCP(**build_mcp_constructor_config()). Keep current banner print logic unchanged. | Yes | 2026-04-09 |
| TASK-003 | Insert function build_mcp_run_config near module tail before if __name__ == "__main__" block. Function returns dict with transport from SETTINGS.transport and for http transport includes host and port from SETTINGS.host and SETTINGS.port. | Yes | 2026-04-09 |
| TASK-004 | Add run_server_entrypoint function near module tail to call mcp.run(**build_mcp_run_config()) and replace direct mcp.run() in if __name__ == "__main__" block with run_server_entrypoint(). | Yes | 2026-04-09 |
| TASK-005 | Update server_startup.py to call run_server_entrypoint from mcp_sqlserver.server instead of invoking mcp.run directly or duplicating transport args. | Yes | 2026-04-09 |

### Implementation Phase 2

- GOAL-002: Add and validate startup configuration tests for deterministic behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-006 | Create tests/test_server_startup_config.py with unit tests for build_mcp_constructor_config default case and configured case using monkeypatch for environment variables consumed by _load_settings. | Yes | 2026-04-09 |
| TASK-007 | Add tests in tests/test_server_startup_config.py to validate build_mcp_run_config returns transport only for stdio and transport plus host and port for http. | Yes | 2026-04-09 |
| TASK-008 | Add test in tests/test_server_startup_config.py ensuring run_server_entrypoint calls mcp.run exactly once with dict returned by build_mcp_run_config via monkeypatch or mock patching. | Yes | 2026-04-09 |

### Implementation Phase 3

- GOAL-003: Update operator documentation for canonical startup path and environment variable ownership.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-009 | Update README.md startup section to state canonical startup methods are python server_startup.py and python -m mcp_sqlserver.server with transport selected by MCP_TRANSPORT. | Yes | 2026-04-09 |
| TASK-010 | Update DEPLOYMENT.md transport section to show deterministic argument mapping from MCP_TRANSPORT, MCP_HOST, and MCP_PORT into run_server_entrypoint behavior. | Yes | 2026-04-09 |
| TASK-011 | Update .env.example comments to mark MCP_TRANSPORT, MCP_HOST, and MCP_PORT as startup-owned settings and avoid duplicate explanations across files. | Yes | 2026-04-09 |

## 3. Alternatives

- **ALT-001**: Leave startup argument construction inline where mcp.run is called. Rejected due duplication and regression risk.
- **ALT-002**: Build startup args in server_startup.py only. Rejected because module execution path would diverge.
- **ALT-003**: Implement full auth and middleware refactor in same phase. Rejected to keep Phase 1 atomic and verifiable.

## 4. Dependencies

- **DEP-001**: Existing Settings object in mcp_sqlserver/server.py remains the source of transport, host, and port values.
- **DEP-002**: pytest and unittest.mock availability for new tests.
- **DEP-003**: Existing server_startup.py entrypoint remains present and importable.

## 5. Files

- **FILE-001**: mcp_sqlserver/server.py - add constructor/run config builders and run_server_entrypoint wiring.
- **FILE-002**: server_startup.py - consume run_server_entrypoint.
- **FILE-003**: tests/test_server_startup_config.py - new startup configuration unit tests.
- **FILE-004**: README.md - startup path update.
- **FILE-005**: DEPLOYMENT.md - transport mapping update.
- **FILE-006**: .env.example - startup settings ownership comments.

## 6. Testing

- **TEST-001**: Run pytest tests/test_server_startup_config.py and verify all startup configuration tests pass.
- **TEST-002**: Run pytest tests/test_blackbox_http.py with MCP_TRANSPORT=http and verify endpoint behavior unaffected.
- **TEST-003**: Run pytest tests/test_hardening_controls.py and verify auth and caller-identity behavior remains intact.
- **TEST-004**: Run pytest tests/test_readonly_sql.py and verify readonly protections are unchanged.

## 7. Risks & Assumptions

- **RISK-001**: Import-time initialization may cache settings before monkeypatch in tests if tests import module too early.
- **RISK-002**: Existing external scripts may rely on direct mcp.run behavior and require minor adaptation.
- **ASSUMPTION-001**: server_startup.py is used as the main production startup path.
- **ASSUMPTION-002**: New tests can run without a live SQL Server because they target startup config assembly only.

## 8. Related Specifications / Further Reading

https://gofastmcp.com/servers/server
https://gofastmcp.com/deployment/running-server
plan/architecture-fastmcp-plan-index-1.md
plan/process-fastmcp-execution-checklist-1.md
plan/architecture-fastmcp-server-alignment-1.md
plan/architecture-fastmcp-auth-phase2-1.md
plan/architecture-fastmcp-transforms-routes-phase3-1.md
plan/architecture-fastmcp-release-validation-phase4-1.md
README.md
DEPLOYMENT.md
