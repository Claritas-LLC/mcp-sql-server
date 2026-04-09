---
goal: Execute Phase 3 transform activation and HTTP route integration for FastMCP server runtime
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: Completed
tags: [architecture, fastmcp, transforms, routes, http, phase-3]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines the exact Phase 3 implementation sequence for activating tool-search transforms, resolving HTTP app behavior, and exposing deterministic operational routes without changing existing tool contracts.

## 1. Requirements & Constraints

- **REQ-001**: Complete _configure_tool_search_transform in mcp_sqlserver/server.py so it applies a transform object to the FastMCP server when MCP_TOOL_SEARCH_ENABLED is true.
- **REQ-002**: Implement _resolve_http_app in mcp_sqlserver/server.py so HTTP app resolution is deterministic and usable by startup workflows.
- **REQ-003**: Expose an HTTP health route with stable response semantics for operational probes.
- **REQ-004**: Preserve existing tool registration and execution behavior under both transformed and non-transformed modes.
- **REQ-005**: Keep transform strategy behavior deterministic for regex and bm25 values from MCP_TOOL_SEARCH_STRATEGY.
- **SEC-001**: Ensure health endpoint does not expose sensitive configuration, secrets, or connection details.
- **SEC-002**: Keep current auth behavior unchanged for protected endpoints when auth is enabled.
- **OPS-001**: Preserve compatibility with current tests expecting /mcp and /sse behavior.
- **CON-001**: Do not rename existing environment variables MCP_TOOL_SEARCH_ENABLED, MCP_TOOL_SEARCH_STRATEGY, MCP_TOOL_SEARCH_MAX_RESULTS, MCP_TOOL_SEARCH_ALWAYS_VISIBLE, MCP_TOOL_SEARCH_TOOL_NAME, and MCP_TOOL_CALL_TOOL_NAME.
- **CON-002**: Do not require external web framework migration in this phase.
- **GUD-001**: Every route and transform change must be covered by unit tests or blackbox HTTP tests.
- **PAT-001**: Transform and route setup occur in explicit setup functions called once during startup.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Activate deterministic tool-search transform wiring.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Update _configure_tool_search_transform in mcp_sqlserver/server.py to instantiate the selected transform class and apply it to the FastMCP server object with the prepared kwargs. | Yes | 2026-04-09 |
| TASK-002 | Add explicit no-op branch and structured log output when MCP_TOOL_SEARCH_ENABLED is false or transform imports are unavailable. | Yes | 2026-04-09 |
| TASK-003 | Add validation branch that raises deterministic runtime error when MCP_TOOL_SEARCH_STRATEGY is not regex or bm25, aligned with _validate_runtime_guards behavior. | Yes | 2026-04-09 |

### Implementation Phase 2

- GOAL-002: Implement deterministic HTTP app resolution and health route behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-004 | Implement _resolve_http_app in mcp_sqlserver/server.py to return the HTTP app instance when transport is http and return None for non-http transports. | Yes | 2026-04-09 |
| TASK-005 | Add custom route registration in mcp_sqlserver/server.py for path /health using mcp.custom_route with method GET and a constant OK response payload. | Yes | 2026-04-09 |
| TASK-006 | Ensure health route response includes only non-sensitive fields such as status and service name, excluding auth keys and DB credentials. | Yes | 2026-04-09 |

### Implementation Phase 3

- GOAL-003: Add and align transform and route tests for deterministic runtime verification.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-007 | Create or update tests/test_server_startup_config.py with unit tests validating transform setup call path for regex strategy and bm25 strategy with mocked transform classes. | Yes | 2026-04-09 |
| TASK-008 | Add unit tests in tests/test_server_startup_config.py for _resolve_http_app return behavior under MCP_TRANSPORT=http and MCP_TRANSPORT=stdio conditions. | Yes | 2026-04-09 |
| TASK-009 | Extend tests/test_blackbox_http.py with health endpoint checks verifying status code 200 and non-sensitive response content. | Yes | 2026-04-09 |

### Implementation Phase 4

- GOAL-004: Update deployment and operator documentation for transforms and health checks.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-010 | Update README.md with a tool-search section that documents strategy options, required FastMCP support level, and behavior when transform backend is unavailable. | Yes | 2026-04-09 |
| TASK-011 | Update DEPLOYMENT.md with health-check endpoint guidance for container probes and external monitors. | Yes | 2026-04-09 |
| TASK-012 | Update .env.example comments to clarify defaults and safe usage for all MCP_TOOL_SEARCH_* variables. | Yes | 2026-04-09 |

## 3. Alternatives

- **ALT-001**: Keep _configure_tool_search_transform as a stub and rely on external tooling for discovery. Rejected due mismatch with configured environment flags.
- **ALT-002**: Expose health checks through external reverse proxy only. Rejected because internal application-level health endpoint is needed for direct container probe use.
- **ALT-003**: Defer route integration until full FastAPI migration. Rejected because lightweight custom routes are already supported by FastMCP.

## 4. Dependencies

- **DEP-001**: FastMCP version in requirements.txt must include transform classes for regex or bm25 when enabled.
- **DEP-002**: Existing HTTP blackbox tests in tests/test_blackbox_http.py remain available for route verification.
- **DEP-003**: Existing startup configuration scaffolding from Phase 1 is in place or implemented concurrently.

## 5. Files

- **FILE-001**: mcp_sqlserver/server.py - complete transform setup, implement HTTP app resolver, and register health route.
- **FILE-002**: tests/test_server_startup_config.py - add transform and HTTP app resolution tests.
- **FILE-003**: tests/test_blackbox_http.py - add health endpoint and content assertions.
- **FILE-004**: README.md - add tool-search and health-check usage documentation.
- **FILE-005**: DEPLOYMENT.md - document operational health probe integration.
- **FILE-006**: .env.example - clarify MCP_TOOL_SEARCH configuration comments.

## 6. Testing

- **TEST-001**: Run pytest tests/test_server_startup_config.py and verify transform setup and HTTP app resolution tests pass.
- **TEST-002**: Run pytest tests/test_blackbox_http.py and verify /health, /mcp, and /sse behavior remains compatible.
- **TEST-003**: Run pytest tests/test_hardening_controls.py to verify auth and caller-context behavior remains unchanged after route additions.
- **TEST-004**: Run pytest tests/test_readonly_sql.py to confirm query safety protections remain unaffected.

## 7. Risks & Assumptions

- **RISK-001**: Transform class availability can differ by FastMCP version and may require guarded fallback behavior.
- **RISK-002**: Route path conflicts with existing mounted endpoints may require path adjustment.
- **RISK-003**: Health endpoint payload growth can accidentally leak operational metadata if not constrained.
- **ASSUMPTION-001**: Current deployment model can consume a simple GET health endpoint for liveness checks.
- **ASSUMPTION-002**: Existing route middleware does not block health endpoint access unless explicitly configured.

## 8. Related Specifications / Further Reading

https://gofastmcp.com/servers/transforms/transforms
https://gofastmcp.com/servers/transforms/tool-search
https://gofastmcp.com/servers/server
https://gofastmcp.com/deployment/http
plan/architecture-fastmcp-plan-index-1.md
plan/process-fastmcp-execution-checklist-1.md
plan/architecture-fastmcp-server-alignment-1.md
plan/architecture-fastmcp-startup-phase1-1.md
plan/architecture-fastmcp-auth-phase2-1.md
plan/architecture-fastmcp-release-validation-phase4-1.md
README.md
DEPLOYMENT.md
