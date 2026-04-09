---
goal: Align MCP SQL Server runtime with FastMCP server patterns for transport, auth, startup, transforms, and HTTP operability
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: Completed
tags: [architecture, fastmcp, server, transport, auth, testing]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines deterministic steps to align the MCP SQL Server server runtime with documented FastMCP server behavior, with explicit updates to transport startup, HTTP auth handling, transform wiring, and test coverage.

## 1. Requirements & Constraints

- **REQ-001**: Preserve existing tool behavior and signatures in mcp_sqlserver/server.py while improving server wiring and runtime configuration handling.
- **REQ-002**: Keep read-only default behavior enforced by existing guards in _validate_runtime_guards and _ensure_write_enabled.
- **REQ-003**: Support documented transports with explicit behavior for stdio and http in startup entrypoints.
- **REQ-004**: Expose deterministic startup behavior through one canonical startup path and one module execution path.
- **REQ-005**: Keep existing environment variables functional, including MCP_TRANSPORT, FASTMCP_AUTH_TYPE, FASTMCP_API_KEY, MCP_TOOL_SEARCH_ENABLED, and MCP_LIST_PAGE_SIZE.
- **SEC-001**: Keep write-mode over network transports blocked unless auth type is configured.
- **SEC-002**: Ensure API key and auth identity behavior remains covered by test_hardening_controls.py and test_blackbox_http.py.
- **OPS-001**: Preserve Windows compatibility behavior and avoid import-time side effects where possible.
- **CON-001**: Do not remove dual-instance database routing behavior driven by DB_01_* and DB_02_* settings.
- **CON-002**: Maintain compatibility with existing deployment documentation and docker-compose-n8n.yml.
- **GUD-001**: All runtime wiring changes must include corresponding tests or explicit test updates.
- **PAT-001**: Use FastMCP constructor and run parameters as the single source of truth for transport and HTTP server behavior.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Build an explicit runtime configuration map for FastMCP server startup with measurable completion criteria: all required startup settings are resolved from environment in one function, validated in tests, and consumed by startup path.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Add function build_mcp_run_config in mcp_sqlserver/server.py that returns deterministic transport and network run options derived from SETTINGS.transport, SETTINGS.host, SETTINGS.port, SETTINGS.ssl_cert, SETTINGS.ssl_key, and SETTINGS.ssl_strict. | Yes | 2026-04-09 |
| TASK-002 | Add function build_mcp_constructor_config in mcp_sqlserver/server.py that returns deterministic FastMCP constructor options including name, instructions, version, and behavior toggles such as list_page_size where available. | Yes | 2026-04-09 |
| TASK-003 | Refactor current global mcp initialization in mcp_sqlserver/server.py to consume build_mcp_constructor_config while preserving existing tool registration decorators. | Yes | 2026-04-09 |

### Implementation Phase 2

- GOAL-002: Align HTTP auth and middleware startup behavior with explicit completion criteria: HTTP transport has deterministic auth gate behavior, identity propagation is unchanged, and regression tests pass.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-004 | Implement function configure_http_auth in mcp_sqlserver/server.py that maps SETTINGS.auth_type and SETTINGS.api_key to FastMCP auth provider wiring for HTTP transport only. | Yes | 2026-04-09 |
| TASK-005 | Ensure existing caller-identity middleware path in mcp_sqlserver/server.py remains active for HTTP requests and retains API caller projection used by audit logging assertions in tests/test_hardening_controls.py. | Yes | 2026-04-09 |
| TASK-006 | Add or update tests in tests/test_blackbox_http.py to assert expected response behavior for unauthenticated and authenticated requests under FASTMCP_AUTH_TYPE values apikey and none. | Yes | 2026-04-09 |

### Implementation Phase 3

- GOAL-003: Complete server capability wiring with measurable completion criteria: transforms, route behavior, and startup entrypoints are deterministic and documented.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-007 | Complete _configure_tool_search_transform in mcp_sqlserver/server.py by applying the selected transform object to mcp when MCP_TOOL_SEARCH_ENABLED is true and no runtime import error occurs. | Yes | 2026-04-09 |
| TASK-008 | Implement _resolve_http_app in mcp_sqlserver/server.py to return an HTTP app object when transport is http and to expose a health endpoint behavior for operational checks. | Yes | 2026-04-09 |
| TASK-009 | Replace direct mcp.run call under module main block in mcp_sqlserver/server.py with run_server_entrypoint function that consumes build_mcp_run_config and invokes mcp.run with explicit parameters. | Yes | 2026-04-09 |

### Implementation Phase 4

- GOAL-004: Validate and document behavior with measurable completion criteria: tests pass for affected areas and docs fully describe startup and transport/auth matrices.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-010 | Add targeted unit tests in tests/test_execute_in_database.py or a new tests/test_server_startup_config.py to validate build_mcp_run_config output for stdio and http settings. | Yes | 2026-04-09 |
| TASK-011 | Update README.md and DEPLOYMENT.md with a transport-auth matrix covering stdio, http, sse legacy status, and required auth behavior for write mode. | Yes | 2026-04-09 |
| TASK-012 | Update .env.example defaults and comments so each startup-related variable has one canonical explanation and no conflicting defaults. | Yes | 2026-04-09 |

## 3. Alternatives

- **ALT-001**: Keep current implicit startup flow and only patch tests. Rejected because runtime ambiguity remains in transport and auth wiring.
- **ALT-002**: Split mcp_sqlserver/server.py into multiple modules before startup alignment. Rejected for this iteration to avoid broad refactor risk while introducing runtime behavior changes.
- **ALT-003**: Add FastAPI wrapper first and mount FastMCP later. Rejected because immediate objective is to stabilize native FastMCP server behavior.

## 4. Dependencies

- **DEP-001**: fastmcp package version in requirements.txt must support server transforms and configured auth providers used in this plan.
- **DEP-002**: Existing tests in tests/test_blackbox_http.py and tests/test_hardening_controls.py must remain executable against local HTTP runtime.
- **DEP-003**: Environment-driven configuration in .env.example must stay synchronized with Settings model in mcp_sqlserver/server.py.

## 5. Files

- **FILE-001**: mcp_sqlserver/server.py - implement startup config builders, auth wiring, transform application, and run entrypoint.
- **FILE-002**: server_startup.py - align runtime startup call to new entrypoint function.
- **FILE-003**: tests/test_blackbox_http.py - validate HTTP auth and endpoint behavior.
- **FILE-004**: tests/test_hardening_controls.py - preserve and extend auth identity assertions if behavior changes.
- **FILE-005**: tests/test_execute_in_database.py or tests/test_server_startup_config.py - add startup config unit tests.
- **FILE-006**: README.md - document canonical startup and transport/auth behavior.
- **FILE-007**: DEPLOYMENT.md - add operator-focused transport/auth deployment matrix and constraints.
- **FILE-008**: .env.example - normalize startup and auth variable descriptions.

## 6. Testing

- **TEST-001**: Run pytest tests/test_blackbox_http.py with FASTMCP_AUTH_TYPE none and confirm expected open endpoint behavior in read-only mode.
- **TEST-002**: Run pytest tests/test_blackbox_http.py with FASTMCP_AUTH_TYPE apikey and FASTMCP_API_KEY set; confirm unauthorized requests fail and authorized requests pass.
- **TEST-003**: Run pytest tests/test_hardening_controls.py to verify caller identity projection and audit behavior remain correct.
- **TEST-004**: Run pytest tests/test_execute_in_database.py and new startup-config tests to verify no regression in database selection helpers and new run config builders.
- **TEST-005**: Run pytest tests/test_readonly_sql.py to verify read-only SQL guard behavior remains unchanged.

## 7. Risks & Assumptions

- **RISK-001**: FastMCP auth provider APIs may differ by installed version and require compatibility shims.
- **RISK-002**: Existing SSE-oriented tests may fail when transport behavior is made stricter for HTTP mode.
- **RISK-003**: Refactoring startup paths may introduce import order side effects if tool decorators are executed before final mcp configuration.
- **ASSUMPTION-001**: Existing CI or local test workflow can run pytest against the selected test files.
- **ASSUMPTION-002**: The repository intends to keep HTTP transport available for remote integrations while preserving stdio support.
- **ASSUMPTION-003**: Documentation updates are acceptable in the same delivery as runtime alignment changes.

## 8. Final Acceptance Criteria

Alignment work is considered complete only when all of the following are true:

- Phase artifacts `phase1`, `phase2`, `phase3`, and `phase4` are marked completed with dated task entries.
- Release gates `GATE-STARTUP`, `GATE-AUTH`, `GATE-TRANSFORM`, and `GATE-INTEGRATION` have passing evidence.
- No open critical or high defects remain in startup, auth, transform, or route behavior.
- Post-release verification steps pass: `GET /health` is healthy and sample authenticated MCP endpoint access behaves as expected.

## 9. Related Specifications / Further Reading

https://gofastmcp.com/servers/server
https://gofastmcp.com/deployment/running-server
plan/architecture-fastmcp-plan-index-1.md
plan/process-fastmcp-execution-checklist-1.md
plan/architecture-fastmcp-startup-phase1-1.md
plan/architecture-fastmcp-auth-phase2-1.md
plan/architecture-fastmcp-transforms-routes-phase3-1.md
plan/architecture-fastmcp-transforms-phase3b-1.md
plan/architecture-fastmcp-transforms-suite-phase3c-1.md
plan/architecture-fastmcp-release-validation-phase4-1.md
README.md
DEPLOYMENT.md
.env.example
