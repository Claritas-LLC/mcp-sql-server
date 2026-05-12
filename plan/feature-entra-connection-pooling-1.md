---
goal: Add SQL Connection Pooling and Azure Entra Group-Based Authorization to MCP Server
version: 1.0
date_created: 2026-05-09
last_updated: 2026-05-09
owner: Platform Engineering
status: Planned
tags: [feature, security, authentication, connection-pooling, azure-entra, mcp]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan defines deterministic implementation steps to add reusable SQL client connection pooling (default maximum pool size 10, configurable) and Azure Entra ID authentication/authorization with read/write privilege assignment based on group membership, including explicit feature toggles.

## 1. Requirements & Constraints

- **REQ-001**: Implement SQL connection pooling in `src/db/connection_manager.py` with reuse of existing live connections.
- **REQ-002**: Set default max SQL pool size to `10` and make it runtime-configurable.
- **REQ-003**: Add Azure Entra ID authentication provider with token verification for MCP HTTP requests.
- **REQ-004**: Add Azure Entra group-to-privilege mapping where group membership resolves to `read` or `write` privilege set.
- **REQ-005**: Add explicit runtime toggle to enable or disable Entra auth without code changes.
- **REQ-006**: When Entra auth toggle is disabled, preserve current non-Entra behavior and existing tool execution paths.
- **REQ-007**: Preserve existing deny-by-default write guard semantics in `src/middleware/write_guard.py`.
- **REQ-008**: Expose configuration via YAML and environment-variable overrides in `src/config_loader.py`.
- **SEC-001**: Validate JWT tokens against Azure issuer/JWKS and required audience/scope before request execution.
- **SEC-002**: Fail closed for invalid/missing token when Entra auth is enabled.
- **SEC-003**: Do not grant write access unless actor is in configured write-enabled Entra group.
- **SEC-004**: Log auth decision and resolved privilege level (`read` or `write`) in audit context.
- **CON-001**: Use existing repository runtime architecture in `src/server.py` and `AppState`.
- **CON-002**: Maintain compatibility with current tool naming and registry behavior in `src/tools/sql_tools.py`.
- **CON-003**: Keep SQL policy files (`config/runtime-policy.yaml`, `policy/sql-allowlist.yaml`) as enforcement source-of-truth.
- **GUD-001**: Use clear config toggle names with default-safe values (`false` for new security features unless explicitly enabled).
- **PAT-001**: Implement pooling with bounded resources and deterministic cleanup in app lifespan shutdown.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Establish configuration schema and toggles for SQL pooling and Azure Entra integration.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Add `AuthConfig` model (or reconcile missing model if absent) in `src/models.py` with fields: `auth_mode`, `azure_tenant_id`, `azure_client_id`, `azure_client_secret_ref`, `azure_required_scopes`, `azure_identifier_uri`, `azure_group_claim_name`, `azure_read_groups`, `azure_write_groups`, `azure_auth_enabled` (bool), and HTTP token-verification pool settings. |  |  |
| TASK-002 | Add SQL pooling config fields in `src/models.py` under `SqlInstanceConfig`: `pool_enabled` (default `true`), `pool_max` (default `10`), `pool_idle_timeout_sec` (default `300`), `pool_acquire_timeout_sec` (default `5`). |  |  |
| TASK-003 | Extend `apply_auth_env_overrides()` in `src/config_loader.py` with environment variables: `FASTMCP_AZURE_AUTH_ENABLED`, `FASTMCP_AZURE_READ_GROUPS`, `FASTMCP_AZURE_WRITE_GROUPS`, and parse CSV lists deterministically. |  |  |
| TASK-004 | Add environment overrides for SQL pooling in `src/config_loader.py`: `FASTMCP_SQL_POOL_ENABLED`, `FASTMCP_SQL_POOL_MAX`, `FASTMCP_SQL_POOL_IDLE_TIMEOUT_SEC`, `FASTMCP_SQL_POOL_ACQUIRE_TIMEOUT_SEC`; validate integer/boolean types. |  |  |
| TASK-005 | Update `config/instances.yaml` and `config/instances.runtime.example.yaml` with pool configuration examples showing default `pool_max: 10`. |  |  |
| TASK-006 | Update `config/runtime-policy.yaml` auth block example with Entra toggles and group mapping placeholders. |  |  |

### Implementation Phase 2

- GOAL-002: Implement SQL connection pooling and connection reuse lifecycle.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-007 | Refactor `ConnectionManager` in `src/db/connection_manager.py` to maintain per-instance pool registry: `dict[str, queue/LIFO structure of pyodbc.Connection wrappers]` guarded by `threading.RLock`. |  |  |
| TASK-008 | Implement `_acquire_connection(instance_id, database_override)` and `_release_connection(instance_id, conn)` methods with max pool cap and stale/closed connection checks. |  |  |
| TASK-009 | Modify `connect()` context manager in `src/db/connection_manager.py` to acquire from pool when `pool_enabled=true`, else preserve direct-connect fallback behavior. |  |  |
| TASK-010 | Ensure returned connections are reset to safe state before reuse (`autocommit`, transaction rollback on exception, and database context validation). |  |  |
| TASK-011 | Add `close_all_pools()` method and invoke it during app shutdown in `build_fastapi_app()` lifespan in `src/server.py`. |  |  |
| TASK-012 | Add pool diagnostics method in `ConnectionManager` returning per-instance metrics (`pool_size`, `in_use`, `available`, `created_total`, `reused_total`, `discarded_total`). |  |  |
| TASK-013 | Expose pool diagnostics via `src/diagnostics/routes.py` endpoint (for example `/diagnostics/pool`) with no sensitive data leakage. |  |  |

### Implementation Phase 3

- GOAL-003: Integrate Azure Entra token verification and request identity extraction.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-014 | Create missing module `src/security/auth_provider.py` with `build_auth_provider(auth_config, http_client, secret_resolver)` compatible with current import in `src/server.py`. |  |  |
| TASK-015 | Implement Azure JWT verification flow in `src/security/auth_provider.py` using Azure OpenID metadata/JWKS resolution per tenant, with cached key material and timeout-limited HTTP calls. |  |  |
| TASK-016 | Validate issuer, audience/client ID, required scopes, and token expiry claims; reject invalid tokens with deterministic auth error payload. |  |  |
| TASK-017 | Extract actor identity and group claims from token (`oid`, `preferred_username`, configured group claim name) and attach to request context. |  |  |
| TASK-018 | In `src/server.py`, wire auth toggle: if `azure_auth_enabled=false`, `build_auth_provider()` returns `None`; if `true`, require valid provider and fail startup on invalid Entra config. |  |  |

### Implementation Phase 4

- GOAL-004: Enforce group-based MCP privileges (`read`/`write`) with explicit toggle behavior.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-019 | Add privilege resolver in `src/security/auth_provider.py` (or new `src/security/privilege_mapper.py`) mapping token groups to privilege levels using configured `azure_read_groups` and `azure_write_groups`. |  |  |
| TASK-020 | Implement precedence rule: `write` supersedes `read` when user belongs to both; no matching group resolves to `none` and request denied when auth enabled. |  |  |
| TASK-021 | In `src/tools/sql_tools.py`, enforce privilege level before tool execution: all tools require at least `read`, and `exec_proc` tools require `write`. |  |  |
| TASK-022 | Preserve existing policy gates (`SessionManager`, `RateLimiter`, `WriteGuard`) after privilege check; do not bypass allowlist/denylist checks for write users. |  |  |
| TASK-023 | Extend audit logging payload in `src/middleware/audit_logger.py` call sites to include `auth_mode`, `auth_subject`, `privilege_level`, and `group_match_result`. |  |  |
| TASK-024 | Add config toggle `azure_group_authorization_enabled` to allow disabling group-based privilege checks while keeping token authentication enabled. |  |  |

### Implementation Phase 5

- GOAL-005: Validate behavior with deterministic tests, load checks, and rollback-safe deployment controls.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-025 | Add unit tests for pooling in `tests/test_connection_pooling.py`: acquire/release reuse, max-cap enforcement, stale connection discard, and shutdown close behavior. |  |  |
| TASK-026 | Add unit tests for auth in `tests/test_auth_provider_azure.py`: valid token, invalid issuer, invalid audience, missing scope, expired token, JWKS refresh behavior. |  |  |
| TASK-027 | Add unit tests for privilege mapping in `tests/test_group_privileges.py`: read-only group, write group, both groups, no group, toggle-off behavior. |  |  |
| TASK-028 | Add integration tests in `tests/test_tool_authorization.py` verifying read users denied on `exec_proc`, write users allowed only when procedure allowlisted. |  |  |
| TASK-029 | Add diagnostics tests in `tests/test_diagnostics_pool_metrics.py` for pool metrics endpoint shape and values. |  |  |
| TASK-030 | Execute full test suite and enforce pass gate (`pytest -q`) before merge; record evidence in `testing/artifacts/`. |  |  |
| TASK-031 | Add rollout runbook updates in `docs/runbooks/security-maintenance.md` and `docs/runbooks/scaling-strategy.md` with toggle-based rollback steps. |  |  |

## 3. Alternatives

- **ALT-001**: Use driver-level global pooling only (`pyodbc.pooling`) without app-managed pool telemetry. Not chosen because instance-level limits, deterministic lifecycle control, and observability are required.
- **ALT-002**: Enforce privileges solely from SQL credentials per instance instead of token group mapping. Not chosen because user-level MCP privilege assignment by Entra group is an explicit requirement.
- **ALT-003**: Use static API keys for MCP auth and keep Entra external. Not chosen because centralized identity and group-based authorization are required.
- **ALT-004**: Apply write privilege directly to SQL statements instead of tool-level authorization. Not chosen because existing design is tool-centric with allowlisted `exec_proc` enforcement.

## 4. Dependencies

- **DEP-001**: FastMCP auth integration points in `src/server.py`.
- **DEP-002**: Existing config parser and env-override system in `src/config_loader.py`.
- **DEP-003**: Existing policy enforcement stack (`WriteGuard`, `RateLimiter`, `SessionManager`).
- **DEP-004**: Azure Entra tenant app registration and client credentials secret source (`secret_resolver`).
- **DEP-005**: Token verification guidance: https://gofastmcp.com/servers/auth/token-verification#connection-pooling.
- **DEP-006**: Azure integration guidance: https://gofastmcp.com/integrations/azure.

## 5. Files

- **FILE-001**: `src/models.py` - Add/extend auth and pooling configuration models.
- **FILE-002**: `src/config_loader.py` - Add env overrides and config parsing for toggles/group mappings.
- **FILE-003**: `src/db/connection_manager.py` - Implement reusable SQL connection pool.
- **FILE-004**: `src/server.py` - Wire startup/shutdown lifecycle and auth toggle handling.
- **FILE-005**: `src/security/auth_provider.py` - Implement Azure Entra token verification and identity extraction.
- **FILE-006**: `src/security/privilege_mapper.py` (new, optional) - Group-to-privilege resolver.
- **FILE-007**: `src/tools/sql_tools.py` - Enforce privilege checks per tool category.
- **FILE-008**: `src/diagnostics/routes.py` - Add pool metrics endpoint.
- **FILE-009**: `config/instances.yaml` - Add SQL pool defaults/config options.
- **FILE-010**: `config/instances.runtime.example.yaml` - Add SQL pool runtime examples.
- **FILE-011**: `config/runtime-policy.yaml` - Add Entra/group toggle examples.
- **FILE-012**: `tests/test_connection_pooling.py` - Unit tests for pooling behavior.
- **FILE-013**: `tests/test_auth_provider_azure.py` - Unit tests for token verification.
- **FILE-014**: `tests/test_group_privileges.py` - Unit tests for group privilege mapping.
- **FILE-015**: `tests/test_tool_authorization.py` - Integration authz tests across tools.

## 6. Testing

- **TEST-001**: Pool reuse test proves same connection object is reused within configured max pool size.
- **TEST-002**: Pool saturation test proves acquisition blocks/fails deterministically when max size reached.
- **TEST-003**: Pool cleanup test proves `close_all_pools()` closes all idle/in-use tracked connections at shutdown.
- **TEST-004**: Token validation test suite verifies issuer/audience/scope/expiry checks.
- **TEST-005**: Group mapping test suite verifies read/write assignment and precedence.
- **TEST-006**: Authorization integration test verifies read group can call read tools but cannot call `exec_proc`.
- **TEST-007**: Authorization integration test verifies write group can call `exec_proc` only for allowlisted procedures.
- **TEST-008**: Toggle test verifies `azure_auth_enabled=false` bypasses Entra auth provider path.
- **TEST-009**: Toggle test verifies `azure_group_authorization_enabled=false` authenticates token but skips group privilege checks.
- **TEST-010**: End-to-end test verifies audit entries include auth subject and privilege level fields.

## 7. Risks & Assumptions

- **RISK-001**: Connection leak risk if pooled connections are not released on exceptional paths.
- **RISK-002**: Token verification outage (JWKS/metadata unavailable) may deny all requests when auth enabled.
- **RISK-003**: Incorrect group IDs in config can unintentionally deny write access to legitimate operators.
- **RISK-004**: Privilege check ordering bugs could bypass expected deny behavior if not tested.
- **ASSUMPTION-001**: Azure Entra app registration and group IDs are available before integration testing.
- **ASSUMPTION-002**: Current deployment environment can provide client secret through existing `secret_resolver` mechanism.
- **ASSUMPTION-003**: Existing SQL instance credentials remain valid while Entra auth governs MCP caller identity.

## 8. Related Specifications / Further Reading

- https://gofastmcp.com/servers/auth/token-verification#connection-pooling
- https://gofastmcp.com/integrations/azure
- `src/server.py`
- `src/db/connection_manager.py`
- `src/config_loader.py`
- `config/runtime-policy.yaml`

## 9. Phase 1 PR Checklist

- **GOAL-P1-001**: Deliver configuration and schema groundwork for SQL pooling + Azure Entra toggles with no runtime regressions.

### Scope for PR-1

- `src/models.py`
- `src/config_loader.py`
- `config/instances.yaml`
- `config/instances.runtime.example.yaml`
- `config/runtime-policy.yaml`
- `tests/test_policy_env_overrides.py`
- `tests/test_auth_config_overrides.py` (new)

### Atomic Execution Tasks

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-P1-001 | Add/verify `AuthConfig` model in `src/models.py` with Entra fields and toggles: `azure_auth_enabled`, `azure_group_authorization_enabled`, `azure_read_groups`, `azure_write_groups`, `azure_group_claim_name`. |  |  |
| TASK-P1-002 | Add SQL pooling config fields in `SqlInstanceConfig` in `src/models.py`: `pool_enabled`, `pool_max` (default `10`), `pool_idle_timeout_sec`, `pool_acquire_timeout_sec`. |  |  |
| TASK-P1-003 | Extend `apply_auth_env_overrides()` in `src/config_loader.py` to parse env toggles and group CSV values deterministically. |  |  |
| TASK-P1-004 | Add SQL pool env override parsing in `src/config_loader.py` and validation for integer/boolean conversion errors. |  |  |
| TASK-P1-005 | Update sample configs in `config/instances.yaml` and `config/instances.runtime.example.yaml` to include pool settings and comments. |  |  |
| TASK-P1-006 | Update auth example block in `config/runtime-policy.yaml` for Entra toggles and group mappings. |  |  |
| TASK-P1-007 | Add tests for new auth/pool env overrides and model validation edge cases. |  |  |

### Acceptance Criteria

- **AC-P1-001**: `pool_max` default resolves to `10` when omitted.
- **AC-P1-002**: Invalid numeric env overrides fail with deterministic `ValueError` messages.
- **AC-P1-003**: `FASTMCP_AZURE_READ_GROUPS` and `FASTMCP_AZURE_WRITE_GROUPS` parse into trimmed string lists with empty entries removed.
- **AC-P1-004**: `azure_auth_enabled=false` remains default-safe behavior unless explicitly enabled.
- **AC-P1-005**: Existing tests continue to pass with no behavior change in current runtime path.

### Verification Commands

- `python -m pytest -q tests/test_policy_env_overrides.py`
- `python -m pytest -q tests/test_auth_config_overrides.py`
- `python -m pytest -q`

### PR Metadata Template

- **Title**: `feat(config): add Entra auth toggles and SQL pool configuration scaffolding`
- **Summary bullets**:
	- Add Entra auth/group toggle fields in config model.
	- Add SQL connection pool config fields with default max size 10.
	- Add env override parsing and validation tests.
	- Update example configuration files.

## 10. Phase 2 PR Checklist

- **GOAL-P2-001**: Implement reusable SQL connection pooling with bounded capacity and deterministic lifecycle cleanup.

### Scope for PR-2

- `src/db/connection_manager.py`
- `src/server.py`
- `src/diagnostics/routes.py`
- `tests/test_connection_pooling.py` (new)
- `tests/test_diagnostics_pool_metrics.py` (new)

### Atomic Execution Tasks

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-P2-001 | Add per-instance pool structures in `src/db/connection_manager.py` with lock-protected state: available list/queue, in-use counter, created/reused/discarded counters. |  |  |
| TASK-P2-002 | Implement `_acquire_connection(instance_id, database_override)` with timeout and max-cap checks honoring `pool_enabled` and `pool_max`. |  |  |
| TASK-P2-003 | Implement `_release_connection(instance_id, conn, had_error)` to return clean connections to pool, and discard bad/stale connections. |  |  |
| TASK-P2-004 | Refactor `connect()` context manager to call acquire/release methods and ensure rollback on failure before release. |  |  |
| TASK-P2-005 | Add `close_all_pools()` in `ConnectionManager` and invoke it in `src/server.py` app lifespan shutdown path. |  |  |
| TASK-P2-006 | Add non-sensitive pool diagnostics payload method (`pool_size`, `in_use`, `available`, `created_total`, `reused_total`, `discarded_total`) and expose via `src/diagnostics/routes.py`. |  |  |
| TASK-P2-007 | Preserve backward compatibility by keeping direct-connect fallback when `pool_enabled=false`. |  |  |

### Acceptance Criteria

- **AC-P2-001**: With pooling enabled and repeated reads, `reused_total` increments above zero.
- **AC-P2-002**: With `pool_max=10`, concurrent acquisition beyond 10 is rejected or times out deterministically.
- **AC-P2-003**: On exception in DB execution path, transaction is rolled back before connection release.
- **AC-P2-004**: `close_all_pools()` closes all pooled connections and resets in-memory pool state.
- **AC-P2-005**: Diagnostics endpoint returns pool metrics with no secrets, SQL text, usernames, or passwords.
- **AC-P2-006**: Behavior remains unchanged when pooling toggle is disabled.

### Verification Commands

- `python -m pytest -q tests/test_connection_pooling.py`
- `python -m pytest -q tests/test_diagnostics_pool_metrics.py`
- `python -m pytest -q tests/test_diagnostics_tool_usage_summary.py`
- `python -m pytest -q`

### PR Metadata Template

- **Title**: `feat(db): implement bounded SQL connection pooling and diagnostics`
- **Summary bullets**:
	- Add per-instance reusable SQL connection pool with max cap and timeout handling.
	- Add app-shutdown pool cleanup integration.
	- Add diagnostics metrics for pool observability.
	- Add pooling and diagnostics tests with deterministic assertions.

## 11. Phase 3 PR Checklist

- **GOAL-P3-001**: Implement Azure Entra token verification and identity extraction with explicit auth toggle behavior.

### Scope for PR-3

- `src/security/auth_provider.py` (new)
- `src/server.py`
- `src/config_loader.py`
- `src/models.py`
- `tests/test_auth_provider_azure.py` (new)

### Atomic Execution Tasks

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-P3-001 | Create `src/security/auth_provider.py` implementing `build_auth_provider(auth_config, http_client, secret_resolver)` to satisfy existing import in server bootstrap. |  |  |
| TASK-P3-002 | Implement Azure OpenID discovery and JWKS retrieval with cached key material and bounded HTTP timeout behavior. |  |  |
| TASK-P3-003 | Validate token claims: issuer, audience/client ID, expiry (`exp`), not-before (`nbf` if present), and required scopes. |  |  |
| TASK-P3-004 | Implement deterministic error mapping for auth failures (missing token, invalid signature, invalid issuer, missing scope, expired token). |  |  |
| TASK-P3-005 | Extract and normalize request identity fields (`oid`, `sub`, `preferred_username`) and group claim values using configured claim name. |  |  |
| TASK-P3-006 | Wire server toggle behavior in `src/server.py`: when `azure_auth_enabled=false`, provider returns `None`; when true, startup must fail closed for invalid config. |  |  |
| TASK-P3-007 | Extend `apply_auth_env_overrides()` for any missing Entra options required by provider implementation and add validation tests. |  |  |

### Acceptance Criteria

- **AC-P3-001**: Valid Azure Entra bearer token is accepted and identity is attached to request context.
- **AC-P3-002**: Invalid issuer/audience/signature or expired token is rejected with deterministic auth error response.
- **AC-P3-003**: Missing required scope causes access denial when scope requirement is configured.
- **AC-P3-004**: With `azure_auth_enabled=false`, MCP server starts and behaves as current non-Entra mode.
- **AC-P3-005**: With `azure_auth_enabled=true` and incomplete config, startup fails closed with actionable error message.
- **AC-P3-006**: No secret values or raw tokens are written to logs/audit output.

### Verification Commands

- `python -m pytest -q tests/test_auth_provider_azure.py`
- `python -m pytest -q tests/test_policy_env_overrides.py`
- `python -m pytest -q`

### PR Metadata Template

- **Title**: `feat(auth): add Azure Entra token verification provider for MCP`
- **Summary bullets**:
	- Add Azure Entra token verification provider with JWKS/discovery integration.
	- Add strict claim validation and deterministic auth failure mapping.
	- Add auth toggle wiring in server bootstrap with fail-closed startup on invalid config.
	- Add focused auth verification tests.

## 12. Phase 4 PR Checklist

- **GOAL-P4-001**: Enforce Entra group-based MCP read/write privileges with explicit toggles and immutable audit context.

### Scope for PR-4

- `src/security/privilege_mapper.py` (new, or embedded in auth provider)
- `src/tools/sql_tools.py`
- `src/middleware/audit_logger.py` (or existing audit call sites)
- `src/config_loader.py`
- `src/models.py`
- `tests/test_group_privileges.py` (new)
- `tests/test_tool_authorization.py` (new)

### Atomic Execution Tasks

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-P4-001 | Implement privilege resolver for token groups: return `write`, `read`, or `none` based on configured `azure_write_groups` and `azure_read_groups`. |  |  |
| TASK-P4-002 | Implement precedence rule in resolver: `write` supersedes `read`; no match returns `none`. |  |  |
| TASK-P4-003 | Add `azure_group_authorization_enabled` toggle handling so group checks can be disabled while token auth remains enabled. |  |  |
| TASK-P4-004 | In `src/tools/sql_tools.py`, enforce minimum privilege before tool execution: read tools require `read` or `write`; `exec_proc` requires `write`. |  |  |
| TASK-P4-005 | Ensure existing policy gates still execute after privilege check: session limits, rate limits, write allowlist/denylist, procedure allowlist. |  |  |
| TASK-P4-006 | Add audit context fields to log payloads: `auth_mode`, `auth_subject`, `privilege_level`, `group_match_result`, and deterministic decision (`allow`/`deny`). |  |  |
| TASK-P4-007 | Add deterministic authorization error codes/messages for insufficient privilege that do not leak sensitive token internals. |  |  |

### Acceptance Criteria

- **AC-P4-001**: Token with read group can execute read-only tools and is denied on `exec_proc`.
- **AC-P4-002**: Token with write group can execute read-only tools and `exec_proc` (subject to existing write/procedure allowlists).
- **AC-P4-003**: Token with no mapped groups is denied when group authorization toggle is enabled.
- **AC-P4-004**: When `azure_group_authorization_enabled=false`, token-authenticated requests are not blocked by group mapping.
- **AC-P4-005**: Audit records include privilege-related fields for both allow and deny outcomes.

### Verification Commands

- `python -m pytest -q tests/test_group_privileges.py`
- `python -m pytest -q tests/test_tool_authorization.py`
- `python -m pytest -q tests/test_write_restrictions.py`
- `python -m pytest -q`

### PR Metadata Template

- **Title**: `feat(authz): enforce Entra group-based read/write privileges for MCP tools`
- **Summary bullets**:
	- Add group-to-privilege mapping resolver with deterministic precedence.
	- Enforce read/write privileges at MCP tool entry points.
	- Add toggle for group authorization behavior.
	- Add audit fields and authorization-focused tests.

## 13. Phase 5 PR Checklist

- **GOAL-P5-001**: Complete end-to-end validation, diagnostics hardening, and rollout/rollback readiness.

### Scope for PR-5

- `src/diagnostics/routes.py`
- `docs/runbooks/security-maintenance.md`
- `docs/runbooks/scaling-strategy.md`
- `testing/artifacts/` (generated evidence)
- `tests/test_diagnostics_pool_metrics.py`
- `tests/test_auth_provider_azure.py`
- `tests/test_tool_authorization.py`

### Atomic Execution Tasks

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-P5-001 | Finalize diagnostics endpoints for auth/pool observability with redaction-safe payloads and stable schema. |  |  |
| TASK-P5-002 | Add full end-to-end integration tests covering auth toggle ON/OFF, group authorization toggle ON/OFF, and pool metrics visibility. |  |  |
| TASK-P5-003 | Execute concurrency test to verify pool cap behavior at configured max (`10`) and document latency/throughput impact. |  |  |
| TASK-P5-004 | Execute regression suite to verify no behavior drift in existing tools and policy enforcement paths. |  |  |
| TASK-P5-005 | Update runbooks with deployment sequencing, required Entra config, and immediate rollback actions (toggle-off instructions). |  |  |
| TASK-P5-006 | Produce release evidence package in `testing/artifacts/` with test logs, config snapshots (sanitized), and diagnostics screenshots/output. |  |  |
| TASK-P5-007 | Define production acceptance gate checklist and sign-off criteria for promotion. |  |  |

### Acceptance Criteria

- **AC-P5-001**: Full test suite passes in CI and local execution paths.
- **AC-P5-002**: Pool and auth diagnostics endpoints expose required fields with no sensitive leakage.
- **AC-P5-003**: Rollback runbook proves service can return to non-Entra mode without code changes.
- **AC-P5-004**: Evidence bundle contains reproducible proof for pooling reuse and group-based authorization outcomes.

### Verification Commands

- `python -m pytest -q tests/test_diagnostics_pool_metrics.py`
- `python -m pytest -q tests/test_auth_provider_azure.py tests/test_group_privileges.py tests/test_tool_authorization.py`
- `python -m pytest -q`

### PR Metadata Template

- **Title**: `chore(release): validate and operationalize Entra auth + SQL pooling rollout`
- **Summary bullets**:
	- Finalize diagnostics and end-to-end validation coverage.
	- Add rollout and rollback runbook guidance.
	- Produce artifact evidence for production promotion.
	- Confirm full regression pass.

## 14. Execution Order and Merge Strategy

- **GOAL-EXEC-001**: Deliver all phases with deterministic branch order, CI gates, and rollback-safe releases.

### Branch and PR Sequence

| Sequence | Branch Name | PR Scope | Merge Prerequisites |
| -------- | ----------- | -------- | ------------------- |
| STEP-001 | `feature/entra-pooling-phase1-config` | Phase 1 checklist only | All AC-P1 pass, CI green, config review approved |
| STEP-002 | `feature/entra-pooling-phase2-dbpool` | Phase 2 checklist only | All AC-P2 pass, CI green, perf smoke evidence attached |
| STEP-003 | `feature/entra-pooling-phase3-auth` | Phase 3 checklist only | All AC-P3 pass, CI green, security review approved |
| STEP-004 | `feature/entra-pooling-phase4-authz` | Phase 4 checklist only | All AC-P4 pass, CI green, policy owner approval |
| STEP-005 | `feature/entra-pooling-phase5-release` | Phase 5 checklist only | All AC-P5 pass, CI green, runbook + evidence sign-off |

### Merge Policy

- **MERGE-001**: Merge each phase PR in sequence; do not open parallel merge candidates for later phases.
- **MERGE-002**: Do not squash cross-phase commits; keep phase boundaries traceable in git history.
- **MERGE-003**: Require at least one reviewer from security for phases 3-5.
- **MERGE-004**: Block merge if any acceptance criterion for that phase is unchecked.

### Release Gates

| Gate | Condition | Evidence Required |
| ---- | --------- | ----------------- |
| GATE-001 | Unit and integration test suite green | CI run URL and local `pytest -q` output |
| GATE-002 | Auth security checks pass | Token validation test logs and negative-case outputs |
| GATE-003 | Pooling behavior verified | Pool diagnostics output showing reuse and bounded cap behavior |
| GATE-004 | Operational readiness complete | Updated runbooks + rollback instructions |
| GATE-005 | Final promotion approval | Evidence bundle under `testing/artifacts/` |

### Rollback Strategy

- **RBK-001**: If Phase 3+ causes auth outage, set `azure_auth_enabled=false` and restart service.
- **RBK-002**: If group mapping misconfiguration causes authorization outage, set `azure_group_authorization_enabled=false`.
- **RBK-003**: If pool behavior regresses DB reliability, set `pool_enabled=false` and restart service.
- **RBK-004**: Revert only the most recent phase branch merge when rollback toggles are insufficient.