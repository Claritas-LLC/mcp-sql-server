---
goal: Add advanced monitoring and analysis MCP tools for dual SQL Server 2019 instances with cross-database and cross-instance reporting
version: 1.0
date_created: 2026-05-07
last_updated: 2026-05-07
owner: MCP SQL Server Team
status: Completed
tags: [feature, sql-server, diagnostics, security, performance, fastmcp]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines the implementation of four advanced MCP tools per SQL instance for performance tuning, data model analysis, security/configuration analysis, and interactive sessions dashboard generation. The plan uses the existing FastMCP server architecture and extends current connection, diagnostics, and tool registration modules with deterministic outputs and cross-database query support through fully qualified object names.

## 1. Requirements & Constraints

- **REQ-001**: Implement concrete tool names for both instances: `db_1_sql2019_analyze_tab_health`, `db_2_sql2019_analyze_tab_health`, `db_1_sql2019_analyze_db_data_model`, `db_2_sql2019_analyze_db_data_model`, `db_1_sql2019_analyze_sec_config`, `db_2_sql2019_analyze_sec_config`, `db_1_sql2019_sessions_dashboard`, `db_2_sql2019_sessions_dashboard`.
- **REQ-002**: All tools must be hard-bound to one instance at registration time and must not accept runtime instance switching.
- **REQ-003**: All analysis tools must return deterministic JSON with `summary`, `findings`, `severity_counts`, `recommendations`, `evidence`, and `generated_at_utc`.
- **REQ-004**: Session dashboard tool must return web-ready payload (HTML fragment + JSON model) consumable by FastMCP interactive app clients.
- **REQ-005**: Support cross-database retrieval via fully qualified names (for example `[USGISPRO_800].[sys].[tables]`) without SQL rewriting.
- **REQ-006**: All tools must enforce session, rate-limit, write-policy, and audit logging before/after execution.
- **REQ-007**: Each tool must support `database_name` input where context is required; defaults must be explicit.
- **REQ-008**: Output findings must include prioritized severity values: `critical`, `high`, `medium`, `low`, `info`.
- **SEC-001**: Never execute write statements in analysis tools; use read-only catalog/DMV queries only.
- **SEC-002**: Redact sensitive values from output (`password`, `secret`, `token`, connection strings).
- **SEC-003**: Enforce existing SQL write guard and policy controls in `src/security/write_restrictions.py`.
- **SEC-004**: Enforce per-actor rate limits through existing middleware backend (`local` or `redis`).
- **CON-001**: Preserve existing public behavior for current tools in `src/tools/sql_tools.py`.
- **CON-002**: Maintain compatibility with n8n schema validation (all array schemas must define `items`).
- **CON-003**: Keep runtime compatible with Docker image flow and current diagnostics endpoints.
- **GUD-001**: Reuse shared execution wrappers and audit plumbing already used by `_run_read_tool` in `src/tools/sql_tools.py`.
- **PAT-001**: Add helper modules under `src/tools/` and `src/db/` for composable query generation and result normalization.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Add architecture scaffolding and deterministic contracts for new tool families.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-001 | Create `src/tools/analysis_contracts.py` defining typed output schema builders: `build_summary()`, `build_finding()`, `build_recommendation()`, `build_report_envelope()` with fixed keys and severity enum. | Yes | 2026-05-07 |
| TASK-002 | Create `src/tools/query_catalog.py` to store parameterized SQL snippets for table health, data model, security/configuration, and session diagnostics; enforce read-only query declarations. | Yes | 2026-05-07 |
| TASK-003 | Add query execution helper `execute_catalog_query(instance_id, database_name, sql, max_rows)` in `src/db/connection_manager.py` reusing existing connection/path methods and returning normalized rows + timing. | Yes | 2026-05-07 |
| TASK-004 | Add input validation helper module `src/tools/input_validation.py` with deterministic validators for `database_name`, `table_name`, `schema_name`, `top_n`, and `view_mode`. | Yes | 2026-05-07 |
| TASK-005 | Extend `src/tools/tool_registry.py` and `generate_tool_specs()` to include four new tool types for each enabled instance. | Yes | 2026-05-07 |

### Implementation Phase 2

- **GOAL-002**: Implement performance and tuning analysis tool: `analyze_tab_health`.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-006 | In `src/tools/sql_tools.py`, register `db_<n>_sql2019_analyze_tab_health` with inputs: `database_name`, `schema_name|None`, `table_name|None`, `include_indexes: bool`, `top_n: int`, `actor`. | Yes | 2026-05-07 |
| TASK-007 | Implement table/index checks using `src/tools/query_catalog.py` queries: fragmentation, heap usage, disabled/hypothetical indexes, missing PK/FK/UQ, duplicate candidate keys, stale stats age, rowcount and size by table. | Yes | 2026-05-07 |
| TASK-008 | Produce prioritized findings JSON with evidence rows and recommendations; include cross-database examples using fully qualified objects in evidence queries. | Yes | 2026-05-07 |
| TASK-009 | Add deterministic error mapping in tool function: `INVALID_INPUT`, `SQL_EXECUTION_ERROR`, `TIMEOUT`, `RATE_LIMIT_EXCEEDED`, `SESSION_LIMIT_EXCEEDED`, `SQL_BLOCKED_BY_POLICY`. | Yes | 2026-05-07 |

### Implementation Phase 3

- **GOAL-003**: Implement data model analysis tool: `analyze_db_data_model`.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-010 | In `src/tools/sql_tools.py`, register `db_<n>_sql2019_analyze_db_data_model` with inputs: `database_name`, `schema_filter|None`, `max_edges: int`, `actor`. | Yes | 2026-05-07 |
| TASK-011 | Implement model checks: orphan tables, cardinality anti-patterns, nullable FK anomalies, circular FK dependencies, missing relationship indexes, denormalization hints, naming convention drift. | Yes | 2026-05-07 |
| TASK-012 | Implement graph extraction helper `build_fk_graph()` in new file `src/tools/model_graph.py`; emit node/edge summaries for downstream visualization. | Yes | 2026-05-07 |
| TASK-013 | Return report JSON following REQ-003 standard envelope with `summary`, `findings`, `severity_counts`, `recommendations`, `evidence`, and `generated_at_utc`; require `findings` object to contain `model_overview`, `integrity_findings`, and `normalization_findings`, with actionable recommendations and estimated impact placed under `recommendations`. | Yes | 2026-05-07 |

### Implementation Phase 4

- **GOAL-004**: Implement security/configuration analysis tool: `analyze_sec_config`.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-014 | In `src/tools/sql_tools.py`, register `db_<n>_sql2019_analyze_sec_config` with inputs: `database_name`, `include_server_scope: bool`, `actor`. | Yes | 2026-05-07 |
| TASK-015 | Implement checks for excessive privileges, orphan users, weak role assignments, TRUSTWORTHY/cross-db ownership chain risks, xp_cmdshell state, CLR state, audit configuration coverage, backup recency and recovery model mismatches. | Yes | 2026-05-07 |
| TASK-016 | Redact sensitive output values before return using helper `redact_sensitive_fields()` in `src/tools/security_redaction.py`. | Yes | 2026-05-07 |
| TASK-017 | Return REQ-003-compliant envelope where `findings` explicitly nests `server_security`, `database_security`, and `audit_backup` (for example: `findings: { server_security: [...], database_security: [...], audit_backup: [...] }`) and `recommendations` nests `hardening_actions` (for example: `recommendations: { hardening_actions: [...] }`) so mapping is unambiguous. | Yes | 2026-05-07 |

### Implementation Phase 5

- **GOAL-005**: Implement interactive sessions dashboard tool using FastMCP interactive app payload pattern.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-018 | In `src/tools/sql_tools.py`, register `db_<n>_sql2019_sessions_dashboard` with inputs: `database_name|None`, `lookback_minutes: int`, `include_locks: bool`, `actor`. | Yes | 2026-05-07 |
| TASK-019 | Build session/lock collectors using DMVs (`sys.dm_exec_sessions`, `sys.dm_exec_requests`, `sys.dm_tran_locks`, `sys.dm_os_waiting_tasks`) with bounded row limits and deterministic sort order. | Yes | 2026-05-07 |
| TASK-020 | Create `src/tools/dashboard_payloads.py` to emit `{ "content_type": "text/html", "html": "...", "data": { ... } }` payload plus widget sections: active sessions, blockers, waits, top SQL, lock chains. | Yes | 2026-05-07 |
| TASK-021 | Add lock-chain prioritization algorithm (head blocker first, then depth, then cumulative wait time) and recommendations for immediate mitigation. | Yes | 2026-05-07 |

### Implementation Phase 6

- **GOAL-006**: Integrate, validate, and document usage with cross-database examples and operations guidance.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-022 | Update diagnostics in `src/diagnostics/routes.py` security payload to include count/list of new tool names and last execution status summary buckets. | Yes | 2026-05-07 |
| TASK-023 | Add/extend tests in `tests/test_tool_registration.py`, `tests/test_sql_tools.py`, and new `tests/test_advanced_analysis_tools.py` for schema validity, deterministic error codes, and cross-database queries. | Yes | 2026-05-07 |
| TASK-024 | Add integration tests in `testing/run_integration_phase.py` that execute each new tool against seeded SQL containers and verify findings payload shape. | Yes | 2026-05-07 |
| TASK-025 | Update docs in `docs/mcp-tool-catalog.md` and `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` with exact input/output contracts, sample invocations, and expected reports. | Yes | 2026-05-07 |
| TASK-026 | Update `plan/feature-remote-mcp-tools-1.md` execution notes and mark this plan status to `In progress` when coding starts, then `Completed` when validation gates pass. | Yes | 2026-05-07 |

## 3. Alternatives

- **ALT-001**: Single generic tool with mode flags for all analyses. Rejected because it increases schema complexity and reduces discoverability in n8n/MCP clients.
- **ALT-002**: Perform analysis in external ETL service and only expose results through MCP. Rejected because it adds latency, deployment complexity, and weakens real-time diagnostics.
- **ALT-003**: Build dashboard as separate web server endpoint only. Rejected because requirement mandates MCP tool-based session dashboard delivery.
- **ALT-004**: Use write-enabled temp tables for intermediate analysis. Rejected due to security/read-only constraints.

## 4. Dependencies

- **DEP-001**: Existing tool registration entrypoint `register_sql_tools()` in `src/tools/sql_tools.py`.
- **DEP-002**: Existing connection APIs in `src/db/connection_manager.py`.
- **DEP-003**: Existing policy and guard components loaded in `src/server.py` (`state.write_guard`, `state.rate_limiter`, `state.session_manager`, `state.audit_logger`).
- **DEP-004**: Existing diagnostics router in `src/diagnostics/routes.py`.
- **DEP-005**: SQL Server 2019 DMV/catalog access permissions for monitoring queries.
- **DEP-006**: FastMCP interactive app payload compatibility (HTML + JSON response contract).
- **DEP-007**: Runtime ODBC dependency availability in Docker image (`msodbcsql18`).

## 5. Files

- **FILE-001**: `src/tools/sql_tools.py` - register and implement 8 new instance-bound advanced tools.
- **FILE-002**: `src/tools/tool_registry.py` - extend generated tool specification catalog.
- **FILE-003**: `src/db/connection_manager.py` - add catalog-query helper and deterministic timeout/error mapping hooks.
- **FILE-004**: `src/diagnostics/routes.py` - extend security/usage diagnostics for new tools.
- **FILE-005**: `src/tools/analysis_contracts.py` - new deterministic JSON report builders.
- **FILE-006**: `src/tools/query_catalog.py` - new SQL query templates for all analyses.
- **FILE-007**: `src/tools/model_graph.py` - new FK graph and circular dependency analyzer.
- **FILE-008**: `src/tools/security_redaction.py` - new output redaction helpers.
- **FILE-009**: `src/tools/dashboard_payloads.py` - new sessions dashboard payload formatter.
- **FILE-010**: `tests/test_tool_registration.py` - schema and registration validation updates.
- **FILE-011**: `tests/test_sql_tools.py` - advanced tool behavior tests.
- **FILE-012**: `tests/test_advanced_analysis_tools.py` - new comprehensive analysis test suite.
- **FILE-013**: `testing/run_integration_phase.py` - integration execution for advanced tools.
- **FILE-014**: `docs/mcp-tool-catalog.md` - tool catalog additions.
- **FILE-015**: `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` - spec extension for new tools.

## 6. Testing

- **TEST-001**: Validate MCP schema generation for all new tool parameters; assert no array schema is missing `items`.
- **TEST-002**: Validate deterministic error code mapping for invalid inputs, blocked policy, and SQL runtime failures.
- **TEST-003**: Validate cross-database query execution by running from `master` and reading `[USGISPRO_800].[sys].[tables]`.
- **TEST-004**: Validate `analyze_tab_health` identifies known seeded issues (fragmentation, missing constraints) in integration DB.
- **TEST-005**: Validate `analyze_db_data_model` returns graph summary and flags circular dependencies when fixture creates loop.
- **TEST-006**: Validate `analyze_sec_config` flags unsafe configuration fixture (for example `xp_cmdshell` enabled) with `high` or `critical` severity.
- **TEST-007**: Validate sessions dashboard payload includes required widget keys and renders non-empty HTML.
- **TEST-008**: Validate audit logs include request metadata for all new tools.
- **TEST-009**: Validate rate limiting/session limiting behavior under concurrent requests.

## 7. Risks & Assumptions

- **RISK-001**: Some SQL security checks require server-level permissions not available in all environments.
- **RISK-002**: DMV-heavy queries can add measurable overhead on busy systems if limits are not enforced.
- **RISK-003**: Cross-database metadata visibility depends on login grants; missing grants can reduce finding completeness.
- **RISK-004**: Dashboard HTML payload shape may vary by client renderer; strict schema tests are required.
- **ASSUMPTION-001**: Both managed instances expose SQL Server 2019 compatible DMVs and system catalogs.
- **ASSUMPTION-002**: Existing write-policy and audit components remain unchanged and reusable for new tools.
- **ASSUMPTION-003**: Integration SQL fixtures can be extended with representative anti-patterns for deterministic testing.

## 8. Related Specifications / Further Reading

- `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md`
- `docs/mcp-tool-catalog.md`
- `plan/feature-remote-mcp-tools-1.md`
- `plan/remote-sql2019-fastmcp3-deployment-plan.md`
- https://gofastmcp.com/apps/interactive-apps