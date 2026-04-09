---
goal: Execute Phase 2 HTTP authentication and middleware alignment for FastMCP runtime
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: Completed
tags: [architecture, fastmcp, auth, middleware, http, phase-2]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines the exact Phase 2 implementation sequence for deterministic HTTP authentication wiring, caller identity propagation, and auth regression coverage in the FastMCP SQL Server runtime.

## 1. Requirements & Constraints

- **REQ-001**: Implement configure_http_auth in mcp_sqlserver/server.py to map SETTINGS.auth_type and SETTINGS.api_key to FastMCP-compatible HTTP auth behavior.
- **REQ-002**: Keep authentication behavior transport-scoped so stdio remains unaffected when HTTP auth is configured.
- **REQ-003**: Preserve existing runtime guard behavior in _validate_runtime_guards for write mode over HTTP.
- **REQ-004**: Preserve audit log identity output semantics consumed by tests in tests/test_hardening_controls.py.
- **REQ-005**: Ensure API key auth behavior remains deterministic across Authorization header and allowed query token paths where configured.
- **SEC-001**: Maintain deny-by-default behavior for invalid or missing credentials on HTTP endpoints when auth is enabled.
- **SEC-002**: Prevent silent fallback to unauthenticated behavior when FASTMCP_AUTH_TYPE is configured.
- **OPS-001**: Keep backward compatibility with existing FASTMCP_AUTH_TYPE values already documented for operators.
- **CON-001**: Do not break existing endpoints expected by tests/test_blackbox_http.py.
- **CON-002**: Do not remove current middleware hooks that set API caller context for auditing.
- **GUD-001**: Any auth wiring change must include explicit tests for success and failure paths.
- **PAT-001**: Auth resolution occurs in one function and is consumed by one startup wiring path.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Build deterministic auth resolver and connect it to HTTP runtime setup.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Add configure_http_auth function in mcp_sqlserver/server.py that accepts current SETTINGS and returns a structured auth config object with fields auth_enabled, auth_type, provider, and validation_mode. | Yes | 2026-04-09 |
| TASK-002 | Implement auth_type normalization logic in configure_http_auth to handle none, apikey, oidc, jwt, azure-ad, github, and google with explicit unsupported-type error handling. | Yes | 2026-04-09 |
| TASK-003 | For apikey mode, implement deterministic validation path requiring non-empty SETTINGS.api_key and wire secure compare behavior for provided tokens. | Yes | 2026-04-09 |
| TASK-004 | Ensure configure_http_auth result is consumed only when build_mcp_run_config returns transport http, and bypassed for stdio transport. | Yes | 2026-04-09 |

### Implementation Phase 2

- GOAL-002: Preserve and harden API caller identity propagation through middleware and audit projection.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-005 | Keep or refactor existing middleware path in mcp_sqlserver/server.py so authenticated principal extraction continues to populate _API_CALLER_CONTEXT deterministically. | Yes | 2026-04-09 |
| TASK-006 | Verify query-token and header-token identity formatting remains stable in audit payload generation paths validated by tests in tests/test_hardening_controls.py. | Yes | 2026-04-09 |
| TASK-007 | Ensure failed auth requests do not mutate caller context and do not write misleading caller identities to audit logs. | Yes | 2026-04-09 |

### Implementation Phase 3

- GOAL-003: Expand and align auth regression tests for both blackbox HTTP and unit-level hardening behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-008 | Update tests/test_blackbox_http.py with explicit matrix tests for FASTMCP_AUTH_TYPE=none and FASTMCP_AUTH_TYPE=apikey covering 200, 401, and 403 expectations by endpoint and credential state. | Yes | 2026-04-09 |
| TASK-009 | Add targeted unit tests in tests/test_hardening_controls.py for configure_http_auth output and error paths including missing FASTMCP_API_KEY in apikey mode. | Yes | 2026-04-09 |
| TASK-010 | Add regression assertions that authenticated requests preserve expected api_caller values and unauthenticated requests never report authenticated identities. | Yes | 2026-04-09 |

### Implementation Phase 4

- GOAL-004: Update operator docs and environment guidance for deterministic auth configuration.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-011 | Update README.md auth section to document each supported FASTMCP_AUTH_TYPE value, required variables, and expected HTTP behavior when enabled. | Yes | 2026-04-09 |
| TASK-012 | Update DEPLOYMENT.md with production auth checklist including FASTMCP_AUTH_TYPE, FASTMCP_API_KEY management, and write-mode guard interaction. | Yes | 2026-04-09 |
| TASK-013 | Update .env.example comments for FASTMCP_AUTH_TYPE, FASTMCP_API_KEY, and MCP_ALLOW_QUERY_TOKEN_AUTH with deterministic precedence and security notes. | Yes | 2026-04-09 |

## 3. Alternatives

- **ALT-001**: Keep ad hoc auth checks inline in route handling without a resolver function. Rejected due drift and poor testability.
- **ALT-002**: Move auth handling into external reverse proxy only. Rejected because server-level enforcement is still required for defense in depth.
- **ALT-003**: Implement only API key mode and drop documented providers. Rejected because it conflicts with existing documented auth types.

## 4. Dependencies

- **DEP-001**: FastMCP runtime version in requirements.txt must support configured auth provider APIs used by this phase.
- **DEP-002**: Existing hardening middleware and audit projection functions in mcp_sqlserver/server.py remain available for extension.
- **DEP-003**: tests/test_blackbox_http.py and tests/test_hardening_controls.py remain part of the validation workflow.

## 5. Files

- **FILE-001**: mcp_sqlserver/server.py - implement configure_http_auth and integrate deterministic auth wiring.
- **FILE-002**: tests/test_blackbox_http.py - extend auth behavior matrix tests.
- **FILE-003**: tests/test_hardening_controls.py - add auth resolver and identity propagation assertions.
- **FILE-004**: README.md - update operator auth documentation.
- **FILE-005**: DEPLOYMENT.md - add production auth checklist and guard interactions.
- **FILE-006**: .env.example - normalize auth variable guidance and security notes.

## 6. Testing

- **TEST-001**: Run pytest tests/test_blackbox_http.py with FASTMCP_AUTH_TYPE=none and validate open endpoint behavior in read-only mode.
- **TEST-002**: Run pytest tests/test_blackbox_http.py with FASTMCP_AUTH_TYPE=apikey and FASTMCP_API_KEY configured; validate unauthorized and authorized paths.
- **TEST-003**: Run pytest tests/test_hardening_controls.py and validate api_caller projection, token-derived identity, and denied-request behavior.
- **TEST-004**: Run pytest tests/test_readonly_sql.py to confirm read-only SQL protections are unchanged by auth changes.
- **TEST-005**: Run pytest tests/test_execute_in_database.py to confirm no regression in helper functions unrelated to auth wiring.

## 7. Risks & Assumptions

- **RISK-001**: FastMCP provider API differences across versions may require compatibility branching.
- **RISK-002**: Existing blackbox expectations may vary by endpoint path mapping between /mcp and /sse in current runtime.
- **RISK-003**: Query-token auth paths can increase exposure if not explicitly constrained in production docs.
- **ASSUMPTION-001**: Existing deployment model continues to use HTTP transport for remote clients.
- **ASSUMPTION-002**: API key remains an accepted baseline auth mode for environments without OIDC integration.

## 8. Related Specifications / Further Reading

https://gofastmcp.com/servers/auth/authentication
https://gofastmcp.com/servers/server
https://gofastmcp.com/deployment/running-server
plan/architecture-fastmcp-plan-index-1.md
plan/process-fastmcp-execution-checklist-1.md
plan/architecture-fastmcp-server-alignment-1.md
plan/architecture-fastmcp-startup-phase1-1.md
plan/architecture-fastmcp-transforms-routes-phase3-1.md
plan/architecture-fastmcp-release-validation-phase4-1.md
README.md
DEPLOYMENT.md
