---
goal: Implement db_sql2019_top_statements with Strict Dependency Sequencing
version: 2.0
date_created: 2026-05-28
last_updated: 2026-05-28
owner: MCP SQL Server Team
status: Planned
tags: [feature, analysis, sqlserver, performance, mcp, execution-ordered]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan is an execution-ordered implementation specification for adding `db_<instance #>_sql2019_top_statements` to the MCP server for instance 1 and instance 2. Each phase has strict dependencies and machine-verifiable completion criteria.

## 1. Requirements & Constraints

- **REQ-001**: Expose `db_1_sql2019_top_statements` and `db_2_sql2019_top_statements` with required `database_name` input.
- **REQ-002**: Return longest-running SQL statements and execution counts from database-scoped telemetry.
- **REQ-003**: Return recommendations for index strategy, query rewrite, query hints, and partitioning.
- **REQ-004**: Use reusable sub-tools/helpers so logic can be reused by future tools.
- **REQ-005**: Preserve existing controls: auth, session, rate-limit, write-guard, and audit logging.
- **REQ-006**: Use deterministic report envelope (`summary`, `severity_counts`, `findings`, `recommendations`).
- **SEC-001**: Keep read-only behavior; no write-capable SQL pathways.
- **SEC-002**: Do not expose secrets or sensitive values in output payloads.
- **CON-001**: Follow naming/registration conventions from `src/tools/tool_registry.py` and `src/tools/sql_tools.py`.
- **CON-002**: Implement Query Store graceful fallback when objects are unavailable (`42S02` case).
- **GUD-001**: Place query text builders in `src/tools/query_catalog.py`.
- **PAT-001**: Implement as one tool block in `register_remote_tools` plus reusable helper functions.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Create registry and naming plumbing before runtime logic.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Update `src/tools/tool_registry.py` `generate_tool_specs` to include `ToolSpec(instance=instance, toolname="top_statements")`. |  |  |
| TASK-002 | Update `tests/test_tool_naming.py` to assert `db_primary_sql2019_top_statements` and `db_secondary_sql2019_top_statements`. |  |  |
| TASK-003 | Run `pytest -q tests/test_tool_naming.py` and verify all assertions pass. |  |  |

### Implementation Phase 2

- GOAL-002: Implement reusable SQL collection sub-tools/helpers.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-004 | Add `top_statements_query_store_query(top_n: int, lookback_minutes: int)` in `src/tools/query_catalog.py`. |  |  |
| TASK-005 | Add `top_statements_dmv_fallback_query(top_n: int)` in `src/tools/query_catalog.py`. |  |  |
| TASK-006 | Add `top_statements_object_pressure_query(top_n: int)` in `src/tools/query_catalog.py` for index/partition heuristics. |  |  |
| TASK-007 | Add unit tests for all new query builders in `tests/test_advanced_analysis_tools.py` or `tests/test_top_statements_tool.py`. |  |  |
| TASK-008 | Run query-builder tests and verify deterministic SQL output strings and order clauses. |  |  |

### Implementation Phase 3

- GOAL-003: Implement reusable analysis/recommendation engine.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-009 | Add helper `_collect_top_statement_metrics(...)` in `src/tools/sql_tools.py` that attempts Query Store first and falls back to DMV query on unsupported-object errors. |  |  |
| TASK-010 | Add helper `_normalize_top_statement_rows(rows)` for stable field names and numeric casting. |  |  |
| TASK-011 | Add helper `_recommend_top_statement_actions(statement_rows, object_rows)` that emits findings/recommendations for `INDEX`, `REWRITE`, `HINT`, `PARTITION`. |  |  |
| TASK-012 | Add explicit threshold constants in `src/tools/sql_tools.py` for duration, execution count, scan pressure, and object size cutoffs. |  |  |
| TASK-013 | Add unit tests for recommendation helper covering all four recommendation categories plus no-op baseline. |  |  |

### Implementation Phase 4

- GOAL-004: Implement MCP tool runtime block with policy controls.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-014 | Add metadata entry in `tool_metadata_by_suffix` for `top_statements` in `src/tools/sql_tools.py`. |  |  |
| TASK-015 | Add `elif spec.toolname == "top_statements"` MCP block in `register_remote_tools` with params `database_name`, `top_n`, `lookback_minutes`, `view_mode`, `actor`, `ctx`. |  |  |
| TASK-016 | Ensure tool enforces `validate_database_name`, positive-int validation, actor authorization, session/rate limits, and write guard before query execution. |  |  |
| TASK-017 | Ensure response uses `build_report_envelope` and includes `top_statements` and `data_source` (`query_store` or `dmv_fallback`). |  |  |
| TASK-018 | Ensure exception flow maps SQL errors to existing standardized contracts and includes actionable SQLSTATE details. |  |  |

### Implementation Phase 5

- GOAL-005: Validate end-to-end for both numeric instances.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-019 | Add integration-style tests to invoke `db_1_sql2019_top_statements` and `db_2_sql2019_top_statements` with valid `database_name`. |  |  |
| TASK-020 | Add fallback test simulating Query Store object absence and verify deterministic `dmv_fallback` output path. |  |  |
| TASK-021 | Run `ruff check .` and `pytest -q` for full regression validation. |  |  |

### Implementation Phase 6

- GOAL-006: Update docs and rollout controls.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-022 | Update `docs/mcp-tool-catalog.md` with contract, input/output, and failure behavior for `top_statements`. |  |  |
| TASK-023 | Update `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` with request/response and fallback examples. |  |  |
| TASK-024 | Update `config/runtime-policy.yaml` examples for explicit feature flags (if feature-gated rollout is required). |  |  |
| TASK-025 | Rebuild/push image and recreate runtime container after merge; verify `/diagnostics/health` and tool availability through list-tools. |  |  |

## 3. Alternatives

- **ALT-001**: Query Store only implementation without fallback. Rejected due to object availability variance across SQL Server builds.
- **ALT-002**: Reuse `top_queries_report` output and add recommendations externally. Rejected because requirement mandates new database-scoped tool contract.
- **ALT-003**: Implement write-capable auto-tuning actions. Rejected by read-only posture and controlled-write guardrails.

## 4. Dependencies

- **DEP-001**: `src/tools/tool_registry.py` for name generation.
- **DEP-002**: `src/tools/sql_tools.py` for MCP registration, auth, audit, and result envelopes.
- **DEP-003**: `src/tools/query_catalog.py` for reusable SQL builders.
- **DEP-004**: `src/tools/analysis_contracts.py` for report envelope and recommendation format.
- **DEP-005**: `src/tools/input_validation.py` and `src/tools/tool_flags.py` for validation/gating behavior.

## 5. Files

- **FILE-001**: `src/tools/tool_registry.py`
- **FILE-002**: `src/tools/sql_tools.py`
- **FILE-003**: `src/tools/query_catalog.py`
- **FILE-004**: `tests/test_tool_naming.py`
- **FILE-005**: `tests/test_advanced_analysis_tools.py`
- **FILE-006**: `tests/test_top_statements_tool.py` (new test file if needed)
- **FILE-007**: `docs/mcp-tool-catalog.md`
- **FILE-008**: `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md`
- **FILE-009**: `config/runtime-policy.yaml`

## 6. Testing

- **TEST-001**: Tool name generation includes `top_statements` for primary/secondary.
- **TEST-002**: Query builders generate deterministic SQL and valid ORDER BY for runtime ranking.
- **TEST-003**: Recommendation helper emits each recommendation family under expected metrics.
- **TEST-004**: `db_1_sql2019_top_statements` invocation succeeds with valid database input.
- **TEST-005**: `db_2_sql2019_top_statements` invocation succeeds with valid database input.
- **TEST-006**: Query Store missing-object scenario returns deterministic fallback path.
- **TEST-007**: Full lint/test regression pass.

## 7. Risks & Assumptions

- **RISK-001**: Query text truncation/parameterization may reduce recommendation precision.
- **RISK-002**: Heuristic thresholds may over/under-report recommendations on diverse workloads.
- **RISK-003**: Missing DMV permissions can reduce data completeness.
- **ASSUMPTION-001**: Required DMV/Query Store read permissions exist for both instances.
- **ASSUMPTION-002**: Existing envelope and disclaimer standards remain unchanged.
- **ASSUMPTION-003**: Numeric tool bindings (`db_1`, `db_2`) remain mapped to configured dual instances.

## 8. Related Specifications / Further Reading

[MCP Tool Catalog](../docs/mcp-tool-catalog.md)
[Connectivity Discovery Diagnostics Spec](../docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md)
[Runtime Policy Configuration Guide](../docs/runtime-policy-configuration-guide.md)
[Access Levels and Controlled Write](../docs/access-levels-and-controlled-write.md)