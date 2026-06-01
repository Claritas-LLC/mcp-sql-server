---
goal: Add db_sql2019_top_statements Analysis Tool for Dual SQL Server Instances
version: 1.0
date_created: 2026-05-28
last_updated: 2026-05-28
owner: MCP SQL Server Team
status: Planned
tags: [feature, analysis, sqlserver, performance, mcp]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan defines a deterministic implementation for a new MCP analysis tool family, `db_<instance #>_sql2019_top_statements`, available on instance 1 and 2, that identifies longest-running SQL statements, execution counts, and prescriptive recommendations for indexing, query rewrites, query hints, and partitioning strategy. The implementation is structured to create reusable sub-tools/helpers that can be consumed by future tools.

## 1. Requirements & Constraints

- **REQ-001**: Implement a new MCP tool family named `db_<instance #>_sql2019_top_statements` with concrete tool names `db_1_sql2019_top_statements` and `db_2_sql2019_top_statements`.
- **REQ-002**: Tool input must include `database_name` as a required parameter.
- **REQ-003**: Tool output must include longest-running SQL statements and execution count per statement.
- **REQ-004**: Tool output must include recommendation sections for index strategy, query rewrites, query hints, and partitioning strategy.
- **REQ-005**: Recommendations must be deterministic and reproducible from collected metrics and rule thresholds.
- **REQ-006**: Create reusable helper/sub-tool functions in shared modules so the logic can be reused by other tools.
- **REQ-007**: Tool must work for both SQL Server instances configured as instance 1 and instance 2.
- **REQ-008**: Tool must use existing report envelope conventions (`build_report_envelope`) and include severity counts/findings/recommendations.
- **REQ-009**: Tool must preserve existing audit logging, rate limiting, session controls, actor resolution, and authorization flow.
- **REQ-010**: Add or update documentation in tool catalog/spec docs with usage, schema, and failure code behavior.
- **SEC-001**: Maintain read-only execution posture; no write SQL execution is allowed.
- **SEC-002**: Apply existing write guard enforcement before any SQL execution path.
- **SEC-003**: Do not leak secrets, tokens, or sensitive SQL text fragments beyond existing redaction and output limits.
- **CON-001**: Follow current naming and registration patterns used in `src/tools/tool_registry.py` and `src/tools/sql_tools.py`.
- **CON-002**: Respect `max_result_rows` and existing policy constraints from `config/runtime-policy.yaml`.
- **CON-003**: Query Store dependencies must degrade gracefully when unsupported objects are unavailable; fallback behavior must be deterministic.
- **GUD-001**: Reuse `src/tools/query_catalog.py` for SQL text generation rather than embedding ad-hoc SQL literals.
- **GUD-002**: Encapsulate recommendation heuristics in dedicated helper functions with unit tests.
- **PAT-001**: Use the existing pattern of per-tool blocks in `register_remote_tools` with `_tool`, `_instance`, `_instance_number`, and audit markers.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Register new tool family and expose concrete names for both instance 1 and instance 2.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Update `src/tools/tool_registry.py` function `generate_tool_specs` to append `ToolSpec(instance=instance, toolname="top_statements")` after existing report tools. Completion criteria: `tests/test_tool_naming.py` asserts both `db_primary_sql2019_top_statements` and `db_secondary_sql2019_top_statements`. |  |  |
| TASK-002 | Add tool metadata entry in `src/tools/sql_tools.py` `tool_metadata_by_suffix` for key `top_statements` with required parameter `database_name` and optional parameters list. Completion criteria: list-tools output includes parameter schema for the new tool. |  |  |
| TASK-003 | Add registration block in `src/tools/sql_tools.py` within `register_remote_tools` for `spec.toolname == "top_statements"` that defines the MCP tool function and appends to `registered`. Completion criteria: runtime exposes tool names for enabled instances. |  |  |

### Implementation Phase 2

- GOAL-002: Implement reusable SQL collection sub-tools/helpers for statement runtime analysis.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-004 | Add SQL builder functions in `src/tools/query_catalog.py`: `top_statements_query_store_query(top_n: int, lookback_minutes: int)`, `top_statements_dmv_fallback_query(top_n: int)`, and `statement_object_stats_query(top_n: int)` with deterministic ordering by duration. |  |  |
| TASK-005 | Add reusable helper in `src/tools/sql_tools.py`: `_collect_top_statement_metrics(connection_manager, instance_id, database_name, top_n, lookback_minutes)` that attempts Query Store query first, then falls back to DMV query on `42S02`/unsupported object conditions. |  |  |
| TASK-006 | Add reusable helper in `src/tools/sql_tools.py`: `_normalize_statement_metrics_rows(rows)` to enforce stable output keys, numeric typing, and bounded SQL text length. |  |  |

### Implementation Phase 3

- GOAL-003: Implement recommendation engine for index strategy, rewrite guidance, query hints, and partitioning candidates.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-007 | Add reusable helper in `src/tools/sql_tools.py`: `_generate_top_statement_recommendations(statement_rows, object_stats_rows)` returning deterministic `findings` and `recommendations` arrays with codes grouped into `INDEX`, `REWRITE`, `HINT`, and `PARTITION` families. |  |  |
| TASK-008 | Implement explicit heuristic thresholds as module constants in `src/tools/sql_tools.py` (for example duration, execution-count, scan-heavy ratio, row-count partition thresholds). Completion criteria: no magic numbers inside recommendation logic. |  |  |
| TASK-009 | Ensure recommendation envelope uses `build_report_envelope` and existing DBA disclaimer behavior from `src/tools/analysis_contracts.py`. Completion criteria: response schema matches existing analysis tools. |  |  |

### Implementation Phase 4

- GOAL-004: Implement MCP tool execution flow with policy enforcement and deterministic response contract.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-010 | In `src/tools/sql_tools.py`, implement `async def _top_statements(...)` parameters: `database_name: str`, `top_n: int = 25`, `lookback_minutes: int = 1440`, `view_mode: str = "COMPACT"`, `actor: str = "system"`, `ctx: Context | None = None`. |  |  |
| TASK-011 | Enforce validation and controls in `_top_statements`: `validate_database_name`, `validate_positive_int`, actor authorization, `state.rate_limiter.allow`, `state.session_manager.touch`, and `state.write_guard.enforce(_tool, "SELECT 1")`. |  |  |
| TASK-012 | Return deterministic payload fields: `instance_number`, `database_name`, `tool`, `generated_at_utc`, `summary`, `severity_counts`, `findings`, `recommendations`, `top_statements`, `data_source` (`query_store` or `dmv_fallback`). |  |  |

### Implementation Phase 5

- GOAL-005: Add automated tests for naming, query builders, recommendation logic, and runtime behavior on both instances.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-013 | Update `tests/test_tool_naming.py` assertions for `db_primary_sql2019_top_statements` and `db_secondary_sql2019_top_statements`. |  |  |
| TASK-014 | Add query builder tests in `tests/test_advanced_analysis_tools.py` (or new `tests/test_top_statements_tool.py`) for `query_catalog.py` functions, including SQL fragments and deterministic ordering clauses. |  |  |
| TASK-015 | Add unit tests for `_generate_top_statement_recommendations` to verify each recommendation class (`index`, `rewrite`, `hint`, `partition`) is emitted under expected metric patterns. |  |  |
| TASK-016 | Add integration-style tests validating tool registration/invocation for both `db_1_sql2019_top_statements` and `db_2_sql2019_top_statements` via existing testing harness patterns in `testing/run_unit_phase.py`. |  |  |

### Implementation Phase 6

- GOAL-006: Update documentation and operational controls for rollout.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-017 | Update `docs/mcp-tool-catalog.md` with tool definition, input/output contract, category, and failure-code behavior for `top_statements`. |  |  |
| TASK-018 | Update `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` with endpoint section for `db_<instance #>_sql2019_top_statements`, including request/response example and Query Store fallback semantics. |  |  |
| TASK-019 | Update `config/runtime-policy.yaml` sample flags (`tool_enable_flags` / `instance_tool_enable_flags`) to include `top_statements: true` defaults where appropriate for explicit rollout control. |  |  |

## 3. Alternatives

- **ALT-001**: Implement logic only on top of Query Store views. Rejected because some SQL Server 2019 builds expose partial Query Store object sets and can fail with `42S02`.
- **ALT-002**: Add one monolithic SQL query inside `sql_tools.py` without shared helpers. Rejected because it prevents reuse by future tools and increases maintenance risk.
- **ALT-003**: Reuse existing `top_queries_report` output and infer recommendations externally. Rejected because requirements mandate recommendations from this tool and database-scoped analysis input.
- **ALT-004**: Build a write-capable tuning tool that applies hints/indexes automatically. Rejected because this repository enforces read-only defaults and controlled-write constraints.

## 4. Dependencies

- **DEP-001**: Existing helper contracts in `src/tools/analysis_contracts.py` (`build_report_envelope`, finding/recommendation builders).
- **DEP-002**: SQL execution and catalog access in `src/db/connection_manager.py` (`execute_catalog_query`, `execute_read_in_database`).
- **DEP-003**: Tool registration pipeline in `src/tools/sql_tools.py` and `src/tools/tool_registry.py`.
- **DEP-004**: Input validation utilities in `src/tools/input_validation.py`.
- **DEP-005**: Runtime policy and flag gating in `config/runtime-policy.yaml` and `src/tools/tool_flags.py`.

## 5. Files

- **FILE-001**: `src/tools/tool_registry.py` — register `top_statements` tool spec for both primary and secondary instances.
- **FILE-002**: `src/tools/sql_tools.py` — add MCP tool block, reusable metric collectors, recommendation engine, and metadata registration.
- **FILE-003**: `src/tools/query_catalog.py` — add reusable SQL query builder sub-functions for Query Store and DMV fallback.
- **FILE-004**: `tests/test_tool_naming.py` — validate new generated tool names.
- **FILE-005**: `tests/test_advanced_analysis_tools.py` and/or `tests/test_top_statements_tool.py` — validate query builders and recommendation heuristics.
- **FILE-006**: `testing/run_unit_phase.py` — include optional execution contract checks for new tool in automated run phase.
- **FILE-007**: `docs/mcp-tool-catalog.md` — document tool contract and usage.
- **FILE-008**: `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` — document request/response and fallback semantics.
- **FILE-009**: `config/runtime-policy.yaml` — explicit enablement examples for rollout governance.

## 6. Testing

- **TEST-001**: Naming contract test: `generate_tool_specs(["primary", "secondary"])` includes `top_statements` entries.
- **TEST-002**: Query builder tests verify generated SQL contains expected source objects and deterministic `ORDER BY` clauses.
- **TEST-003**: Recommendation engine unit tests cover all recommendation categories and no-recommendation baseline path.
- **TEST-004**: Tool invocation tests validate required `database_name` input and error contract for invalid parameters.
- **TEST-005**: Dual-instance behavior test validates both `db_1_sql2019_top_statements` and `db_2_sql2019_top_statements` invocation and envelope schema.
- **TEST-006**: Fallback behavior test simulates Query Store object absence and verifies deterministic `dmv_fallback` data source field.
- **TEST-007**: Non-regression validation: run `ruff check .` and `pytest -q` after implementation.

## 7. Risks & Assumptions

- **RISK-001**: Query Store object availability differs by SQL Server build; direct dependencies may fail with `42S02`.
- **RISK-002**: Statement text from DMVs can be truncated or parameterized, reducing recommendation precision.
- **RISK-003**: Overly aggressive recommendation heuristics could produce noisy findings without proper thresholds.
- **RISK-004**: Large query text payloads may increase response size and impact client rendering.
- **ASSUMPTION-001**: Service principals used by MCP have read permissions for required DMVs/Query Store views.
- **ASSUMPTION-002**: Existing report envelope and disclaimer behavior remain the standard for analysis output.
- **ASSUMPTION-003**: Instances `primary` and `secondary` continue mapping to numeric tool bindings 1 and 2 in deployed configuration.

## 8. Related Specifications / Further Reading

[MCP Tool Catalog](../docs/mcp-tool-catalog.md)
[Connectivity Discovery Diagnostics Spec](../docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md)
[Runtime Policy Configuration Guide](../docs/runtime-policy-configuration-guide.md)
[Access Levels and Controlled Write](../docs/access-levels-and-controlled-write.md)