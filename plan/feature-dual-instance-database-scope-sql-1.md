---
goal: Refactor dual-instance SQL tool execution to use database-scoped sp_executesql context switching and validate the change against two temporary SQL Server 2019 containers
version: 1.0
date_created: 2026-05-01
last_updated: 2026-05-01
owner: Platform Engineering
status: Completed
tags: [feature, refactor, sql, dual-instance, testing, mcp]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines the exact work required to replace ad hoc database scoping in the MCP SQL Server tools with deterministic database-scoped execution using `EXEC <db>.sys.sp_executesql ...`, then validate the refactor end-to-end against two disposable SQL Server 2019 instances configured through the repository's existing dual-instance harness.

## Implementation Outcome

- Status: Completed on 2026-05-01.
- Core execution path in [mcp_sqlserver/server.py](mcp_sqlserver/server.py) now routes named-database execution through database-scoped `sp_executesql` while keeping connection pools instance-local.
- Dual-instance validation completed against `test1` on instance 1 and `test2` on instance 2.
- Narrow helper regression suite passed: `tests/test_execute_in_database.py`, `tests/test_run_query_internal.py`, and `tests/test_get_connection_retry_cleanup.py` with 10 passing tests.
- End-to-end dual HTTP harness completed with 50 tools passed and 0 failed, recorded in [testing/tool_execution_summary.json](testing/tool_execution_summary.json).
- Per-pair artifacts were generated and validated under [testing/tool_results](testing/tool_results), with zero recorded validation errors in the final run.
- Final defect register state is empty in [testing/defect_register.json](testing/defect_register.json), indicating no open defects remained after remediation.

## 1. Requirements & Constraints

- **REQ-001**: Centralize database-context execution in [mcp_sqlserver/server.py](mcp_sqlserver/server.py) function `_execute_in_database()` so tool logic does not issue raw `USE [database]` statements directly.
- **REQ-002**: Implement database-scoped execution using the exact pattern `EXEC <db>.sys.sp_executesql N'<sql statement>'` with parameter support, rather than relying on session-level `USE` for tools that target a non-default database.
- **REQ-003**: Preserve existing read-only enforcement, table-scope enforcement, audit logging, pagination, and dual-instance registration behavior in [mcp_sqlserver/server.py](mcp_sqlserver/server.py).
- **REQ-004**: Update all dual-instance reachable tools registered by `_register_dual_instance_tools()` in [mcp_sqlserver/server.py](mcp_sqlserver/server.py#L2672) that currently depend on direct database connections or explicit `USE` switching.
- **REQ-005**: Keep `db_01_*` and `db_02_*` tool names unchanged and continue using the existing wrapper registration flow in [mcp_sqlserver/server.py](mcp_sqlserver/server.py#L2672).
- **REQ-006**: Add or update automated tests for the execution helper, direct tool behavior, and blackbox/end-to-end dual-instance validation.
- **REQ-007**: Perform functional validation by provisioning two temporary SQL Server 2019 containers, seeding dummy data, and executing the existing dual-instance tool matrix.
- **REQ-008**: Fix all defects encountered during implementation and rerun validation until the targeted regression suite passes.
- **REQ-009**: Configure instance-specific database targets so server 1 uses database `test1` and server 2 uses database `test2`; do not validate dual-instance behavior with the same database name on both servers.
- **REQ-010**: Execute each affected MCP tool sequentially, testing the `db_01_*` variant against `test1` on server 1 and the corresponding `db_02_*` variant against `test2` on server 2 before advancing to the next tool.
- **REQ-011**: Persist a test artifact for every per-tool execution pair and read the artifact contents immediately after each tool completes to verify there are no errors, schema mismatches, or unexpected payloads.
- **REQ-012**: If any per-tool artifact contains an error or failed assertion, stop the sequence, fix the defect, rerun that same tool pair, reread the updated artifacts, and only then proceed to the next tool.
- **REQ-013**: Preserve intended connection-pooling semantics in [mcp_sqlserver/server.py](mcp_sqlserver/server.py): pools remain keyed by instance, pooled sessions are reused within the same instance across tool calls, and the database-scope refactor must not convert routine operations into one-off connections.
- **REQ-014**: Optimize resource usage by avoiding pool fragmentation by database name; the refactor must not create separate effective pools for `master`, `test1`, and `test2` within the same instance unless a validated exception is documented.
- **REQ-015**: Validate that pooled connections returned by `get_connection()` remain safe to reuse after database-scoped execution, including preserved autocommit behavior, successful liveness checks, and clean return to the originating instance pool.
- **SEC-001**: Database names used in scoped execution must continue to pass identifier validation before being interpolated into `EXEC <db>.sys.sp_executesql` statements.
- **SEC-002**: SQL statement text and parameter payloads must remain parameterized through `pyodbc`; do not convert user SQL input into string-concatenated executable SQL beyond the validated database identifier.
- **SEC-003**: Write-enabled tool validation must run only with disposable containerized databases and explicit write-mode environment flags from [testing/dual_sql_env.ps1](testing/dual_sql_env.ps1).
- **CON-001**: Do not change MCP public tool signatures unless a signature mismatch is already broken and must be repaired to complete the database-scope refactor.
- **CON-002**: Reuse the existing dual-instance scripts in [testing/provision_dual_sql.ps1](testing/provision_dual_sql.ps1), [testing/seed_dual_sql.ps1](testing/seed_dual_sql.ps1), [testing/teardown_dual_sql.ps1](testing/teardown_dual_sql.ps1), and [testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py) instead of introducing parallel infrastructure.
- **CON-003**: Preserve compatibility with SQL Server 2019 system views, DMVs, and `INFORMATION_SCHEMA` queries already used by the tools.
- **CON-004**: The tool execution order must be deterministic and derived from [testing/tool_matrix.json](testing/tool_matrix.json), normalized so each logical suffix is tested as a pair: `db_01_<suffix>` first, then `db_02_<suffix>`.
- **CON-005**: Connection pooling must remain instance-local as implemented by `_CONN_POOLS` and `PooledConnection` in [mcp_sqlserver/server.py](mcp_sqlserver/server.py); no plan step may assume per-database pool keys unless the implementation is explicitly redesigned and revalidated.
- **GUD-001**: Apply the refactor at the smallest owning abstraction first: execution helpers before individual tool bodies.
- **GUD-002**: After the helper change, validate via the narrowest available tests before broadening to full dual-instance runs.
- **PAT-001**: Use a two-path execution model: direct execution for instance-level `master` operations that intentionally stay on `master`, and scoped execution for target-database work.
- **PAT-002**: Use deterministic, instance-specific seed databases by setting `DB_01_NAME=test1` and `DB_02_NAME=test2`, and update the seed flow in [testing/seed_dual_sql.ps1](testing/seed_dual_sql.ps1) and seed SQL assets as needed so both databases contain equivalent dummy data under different names.
- **PAT-003**: Use a strict serial validation loop per logical tool suffix: execute server 1 variant, execute server 2 variant, save both artifacts, read both artifacts, remediate defects if present, then unlock the next suffix.
- **PAT-004**: Prefer stable per-instance pooled sessions plus database-scoped `sp_executesql` over opening database-specific physical connections, so cross-database execution does not reduce pool hit rate or increase connection churn.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Establish the exact refactor surface and classify every affected tool by database-scope strategy.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Inspect `_execute_in_database()` in [mcp_sqlserver/server.py](mcp_sqlserver/server.py#L1090), `_run_query_internal()` in [mcp_sqlserver/server.py](mcp_sqlserver/server.py#L1334), and `_register_dual_instance_tools()` in [mcp_sqlserver/server.py](mcp_sqlserver/server.py#L2672) to define the single owning execution path for database-scoped SQL. | ✅ | 2026-05-01 |
| TASK-002 | Enumerate all tool functions in [mcp_sqlserver/server.py](mcp_sqlserver/server.py) that currently call `get_connection(db_name_str, instance=instance)`, explicitly execute `USE [database]`, or depend on the connection string database to set context: `db_sql2019_list_tables`, `db_sql2019_get_schema`, `_run_query_internal`, `db_sql2019_list_objects`, `_get_index_fragmentation_data`, `db_sql2019_analyze_table_health`, `db_sql2019_db_stats`, `_analyze_logical_data_model_internal`, `db_sql2019_show_top_queries`, `db_sql2019_db_sec_perf_metrics`, `db_sql2019_explain_query`, `db_sql2019_generate_ddl`, `db_sql2019_create_db_user`, `db_sql2019_drop_db_user`, `db_sql2019_create_object`, `db_sql2019_alter_object`, and `db_sql2019_drop_object`. | ✅ | 2026-05-01 |
| TASK-003 | Classify tools into three deterministic groups: `master_only` for `db_sql2019_list_databases`, `db_sql2019_server_info_mcp`, and `db_sql2019_kill_session`; `target_database_scoped` for database-local reads and writes; and `hybrid` for tools that connect to `master` but execute against a named database. | ✅ | 2026-05-01 |
| TASK-004 | Record the final affected-function inventory and the required instance-to-database mapping (`instance=1 -> test1`, `instance=2 -> test2`) in the plan execution notes or implementation PR description before writing code so no dual-instance tool is skipped. | ✅ | 2026-05-01 |
| TASK-005 | Derive a deterministic logical tool order from [testing/tool_matrix.json](testing/tool_matrix.json) by grouping `db_01_<suffix>` and `db_02_<suffix>` into ordered suffix pairs, and treat each suffix pair as one serial validation unit. | ✅ | 2026-05-01 |
| TASK-006 | Record the current pooling invariants from [mcp_sqlserver/server.py](mcp_sqlserver/server.py): pools are keyed only by instance, `PooledConnection.close()` returns sessions to the same instance pool, and pool exhaustion falls back to temporary direct connections. | ✅ | 2026-05-01 |

### Implementation Phase 2

- GOAL-002: Replace session-level context switching with a reusable database-scoped execution helper.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-007 | Redesign `_execute_in_database()` in [mcp_sqlserver/server.py](mcp_sqlserver/server.py#L1090) to build a validated statement of the form `EXEC [<database_name>].sys.sp_executesql N'<sql>', <param definition list>, <bound parameters>` and execute it through `_execute_safe()`. | ✅ | 2026-05-01 |
| TASK-008 | Add an internal helper in [mcp_sqlserver/server.py](mcp_sqlserver/server.py) that converts Python parameter lists into deterministic `sp_executesql` placeholders, for example `@p1`, `@p2`, and the matching declaration string, while preserving `pyodbc` parameter binding order. | ✅ | 2026-05-01 |
| TASK-009 | Define exact fallback rules in the helper: when `database_name` is empty or equals the active default database, execute the raw SQL directly; otherwise route through `EXEC [db].sys.sp_executesql`. | ✅ | 2026-05-01 |
| TASK-010 | Keep `_validate_identifier()` and `_quoted_ident()` as the only interpolation gate for database identifiers in the new helper and reject invalid database names before generating the scoped SQL. | ✅ | 2026-05-01 |
| TASK-011 | Ensure the new helper supports statements that return result sets, statements used by `SHOWPLAN_ALL`, DDL statements executed by write tools, and parameterless queries. | ✅ | 2026-05-01 |
| TASK-012 | Define the connection-acquisition strategy so pooled connections continue to come from an instance-stable path in `get_connection()`, rather than requiring a new physical connection for each target database name. | ✅ | 2026-05-01 |

### Implementation Phase 3

- GOAL-003: Migrate tool implementations to the new helper without changing public behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-013 | Update `db_sql2019_list_tables()` and `db_sql2019_get_schema()` in [mcp_sqlserver/server.py](mcp_sqlserver/server.py) to remove raw `USE [database]` statements and route database-specific SELECT statements through the refactored `_execute_in_database()`. | ✅ | 2026-05-01 |
| TASK-014 | Update `_run_query_internal()` in [mcp_sqlserver/server.py](mcp_sqlserver/server.py) so read and write query execution uses the database-scoped helper whenever `database_name` is supplied and the tool should execute against a target database from a stable session. | ✅ | 2026-05-01 |
| TASK-015 | Update metadata and analysis tools in [mcp_sqlserver/server.py](mcp_sqlserver/server.py) to use `_execute_in_database()` consistently for target-database queries: `db_sql2019_list_objects`, `_get_index_fragmentation_data`, `db_sql2019_analyze_table_health`, `db_sql2019_db_stats`, `_analyze_logical_data_model_internal`, `db_sql2019_show_top_queries`, `db_sql2019_db_sec_perf_metrics`, `db_sql2019_explain_query`, and `db_sql2019_generate_ddl`. | ✅ | 2026-05-01 |
| TASK-016 | Update write-path helpers in [mcp_sqlserver/server.py](mcp_sqlserver/server.py) to run database-targeted DDL and principal-management statements through `_execute_in_database()` where the operation is intended to affect the named database: `db_sql2019_create_db_user`, `db_sql2019_drop_db_user`, `db_sql2019_create_object`, `db_sql2019_alter_object`, and `db_sql2019_drop_object`. | ✅ | 2026-05-01 |
| TASK-017 | Leave `db_sql2019_list_databases`, `db_sql2019_server_info_mcp`, and `db_sql2019_kill_session` on `master` unless testing proves they also require a scoped execution wrapper. | ✅ | 2026-05-01 |
| TASK-018 | Remove no-longer-needed direct `USE` calls and any redundant connection-string database switching logic after the helper migration is complete. | ✅ | 2026-05-01 |
| TASK-019 | Verify that each migrated tool still acquires and releases connections through the existing per-instance pooling path, and document any deliberate exceptions that must bypass the pool. | ✅ | 2026-05-01 |

### Implementation Phase 4

- GOAL-004: Repair unit and integration expectations around the new scoped-execution behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-020 | Replace the current `USE [db]` assertions in [tests/test_execute_in_database.py](tests/test_execute_in_database.py) with assertions that verify `_execute_in_database()` emits `EXEC [db].sys.sp_executesql ...` and preserves parameter forwarding. | ✅ | 2026-05-01 |
| TASK-021 | Add helper-focused tests in [tests/test_execute_in_database.py](tests/test_execute_in_database.py) for parameterless SQL, multi-parameter SQL, invalid database names, and exception propagation from `_execute_safe()`. | ✅ | 2026-05-01 |
| TASK-022 | Add or update tests in [tests/test_run_query_internal.py](tests/test_run_query_internal.py) to verify `_run_query_internal()` routes named-database executions through the scoped helper and still preserves readonly/table-scope enforcement. | ✅ | 2026-05-01 |
| TASK-023 | Update or extend [tests/test_get_connection_retry_cleanup.py](tests/test_get_connection_retry_cleanup.py) so pooled replacement and cleanup logic remains correct when database-scoped execution is introduced. | ✅ | 2026-05-01 |
| TASK-024 | Add pooling regression tests proving that repeated calls on the same instance reuse pooled sessions even when alternating between `master`, `test1`, and `test2` scoped execution paths. | ✅ | 2026-05-01 |
| TASK-025 | Add resource-usage regression tests proving the refactor does not increase avoidable `pyodbc.connect()` calls for common read-tool sequences on the same instance. | ✅ | 2026-05-01 |
| TASK-026 | Update integration expectations in [tests/test_integration_tools.py](tests/test_integration_tools.py) where existing assertions no longer match the actual tool payload shape, but only when those failures block the database-scope change from reaching green. | ✅ | 2026-05-01 |
| TASK-027 | Add at least one regression test covering dual-instance database targeting, proving `instance=1` executes against `test1` and `instance=2` executes against `test2` for the same logical query shape, with no context bleed or accidental fallback to a shared database name. | ✅ | 2026-05-01 |
| TASK-028 | Add or update tests around the execution harness so a failing artifact for one tool suffix aborts the remaining suffix sequence until the defect is resolved and the same suffix pair passes. | ✅ | 2026-05-01 |

### Implementation Phase 5

- GOAL-005: Run targeted validation immediately after the first helper refactor, then execute full dual-instance functional testing in a strict per-tool serial loop.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-029 | Run the narrow helper tests first: `pytest tests/test_execute_in_database.py -q`, `pytest tests/test_run_query_internal.py -q`, and `pytest tests/test_get_connection_retry_cleanup.py -q`; fix any local helper or pooling defects before changing additional files. | ✅ | 2026-05-01 |
| TASK-030 | Provision two disposable SQL Server 2019 containers using [testing/provision_dual_sql.ps1](testing/provision_dual_sql.ps1) and configure the shell with [testing/dual_sql_env.ps1](testing/dual_sql_env.ps1), explicitly setting `DB_01_NAME=test1`, `DB_02_NAME=test2`, and non-trivial per-instance pool sizes for validation. | ✅ | 2026-05-01 |
| TASK-031 | Seed both containers with deterministic dummy data from [setup_test_database.sql](setup_test_database.sql) via [testing/seed_dual_sql.ps1](testing/seed_dual_sql.ps1), adapting the seed flow to create database `test1` on server 1 and database `test2` on server 2, then verify `sales.Customers` exists in both databases. | ✅ | 2026-05-01 |
| TASK-032 | Run focused integration checks against the changed slice: `pytest tests/test_integration_tools.py -q -k "run_query or execute_query or list_tables or get_schema or explain_query"`. | ✅ | 2026-05-01 |
| TASK-033 | Run HTTP blackbox validation with the dual-instance environment: `pytest tests/test_blackbox_http.py -q`. | ✅ | 2026-05-01 |
| TASK-034 | Update [testing/generate_tool_matrix.py](testing/generate_tool_matrix.py) and [testing/tool_matrix.json](testing/tool_matrix.json) so every generated args template uses `test1` for `db_01_*` tools and `test2` for `db_02_*` tools instead of a shared `TEST_DB` default. | ✅ | 2026-05-01 |
| TASK-035 | Refactor [testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py) to iterate one logical suffix pair at a time, execute `db_01_<suffix>` then `db_02_<suffix>`, and stop immediately if either execution fails. | ✅ | 2026-05-01 |
| TASK-036 | Instrument the serial runner to capture pooling evidence per suffix pair, including instance identifier, whether a pooled or replacement connection path was used, and whether the session returned cleanly to the pool. | ✅ | 2026-05-01 |
| TASK-037 | Persist per-tool-pair artifacts under [testing/tool_results](testing/tool_results) using deterministic names that preserve both instance results and the logical suffix, for example one pair summary plus one raw artifact per instance. | ✅ | 2026-05-01 |
| TASK-038 | After each suffix pair completes, read the just-written artifacts, validate that the payloads contain no errors and reference the expected database name (`test1` or `test2`), then mark the pair as passed before unlocking the next suffix. | ✅ | 2026-05-01 |
| TASK-039 | If any suffix pair artifact fails validation, log the defect, fix the root cause, rerun only that suffix pair first, reread its artifacts, and continue the serial sequence only after the repaired artifacts are clean. | ✅ | 2026-05-01 |
| TASK-040 | Execute `pytest tests/test_stress_tools.py -q` only after all suffix pairs pass the serial artifact-review loop, to confirm the refactor did not introduce concurrency or pooling regressions. | ✅ | 2026-05-01 |
| TASK-041 | Run an explicit pooling non-regression pass that compares connection creation counts and pooled-session reuse before and after the refactor for repeated read-tool sequences on each instance. | ✅ | 2026-05-01 |

### Implementation Phase 6

- GOAL-006: Resolve all discovered issues and publish deterministic completion evidence.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-042 | For every failing test or tool invocation, update [testing/defect_register.json](testing/defect_register.json) with `id`, `tool_suffix`, `tool_name`, `symptom`, `root_cause_file`, `root_cause_function`, `reproduction_step`, and `status`. | ✅ | 2026-05-01 |
| TASK-043 | Fix each defect in the smallest owning code path, rerun the narrowest failing validation first, then rerun the failed suffix pair and reread its artifacts before marking the defect resolved. | ✅ | 2026-05-01 |
| TASK-044 | Capture final execution evidence in [testing/tool_execution_summary.json](testing/tool_execution_summary.json), [testing/blackbox_results.txt](testing/blackbox_results.txt), [testing/e2e_results.txt](testing/e2e_results.txt), and [testing/TEST_REPORT.md](testing/TEST_REPORT.md). | ✅ | 2026-05-01 |
| TASK-045 | Confirm that both instances can execute representative database-scoped queries from `master`, with server 1 proving `EXEC test1.sys.sp_executesql ...` and server 2 proving `EXEC test2.sys.sp_executesql ...`, and persist the evidence in [testing/tool_results](testing/tool_results). | ✅ | 2026-05-01 |
| TASK-046 | Add a final artifact audit step that rereads every generated per-tool artifact and verifies zero recorded `error` fields, zero failed suffix pairs, correct database-name attribution across both instances, and no unexpected pool-growth or connection-churn signals. | ✅ | 2026-05-01 |
| TASK-047 | Tear down both temporary containers with [testing/teardown_dual_sql.ps1](testing/teardown_dual_sql.ps1) after all validations pass. | ✅ | 2026-05-01 |

## 3. Alternatives

- **ALT-001**: Keep the current mix of connection-string database selection plus ad hoc `USE [database]`. Rejected because pooled connections and mixed `master` versus target-database flows make session context harder to reason about under the dual-instance wrappers.
- **ALT-002**: Open a fresh connection directly to each requested database for every tool and avoid `sp_executesql`. Rejected because the requested implementation standard is database-scoped execution and a central helper yields a smaller, more testable change surface.
- **ALT-003**: Refactor each tool's SQL individually without a shared helper. Rejected because it duplicates escape, parameter, and scope logic across too many functions in [mcp_sqlserver/server.py](mcp_sqlserver/server.py).
- **ALT-004**: Validate only unit tests and skip the dual-container functional run. Rejected because the requirement explicitly includes provisioning two temporary SQL Server 2019 containers and exercising the dual-instance feature end-to-end.

## 4. Dependencies

- **DEP-001**: Python environment with repository dependencies from [requirements.txt](requirements.txt) and test dependencies from [testing/requirements-test.txt](testing/requirements-test.txt).
- **DEP-002**: Docker access capable of running `mcr.microsoft.com/mssql/server:2019-latest` containers.
- **DEP-003**: PowerShell execution support for [testing/provision_dual_sql.ps1](testing/provision_dual_sql.ps1), [testing/dual_sql_env.ps1](testing/dual_sql_env.ps1), [testing/seed_dual_sql.ps1](testing/seed_dual_sql.ps1), and [testing/teardown_dual_sql.ps1](testing/teardown_dual_sql.ps1).
- **DEP-004**: A local ODBC driver compatible with the `DB_01_DRIVER` and `DB_02_DRIVER` values set by [testing/dual_sql_env.ps1](testing/dual_sql_env.ps1).
- **DEP-005**: Seed data and Query Store configuration from [setup_test_database.sql](setup_test_database.sql), adjusted so the same schema/data can be created under database names `test1` and `test2`.

## 5. Files

- **FILE-001**: [mcp_sqlserver/server.py](mcp_sqlserver/server.py) - primary implementation target for helper and tool refactor.
- **FILE-001A**: [mcp_sqlserver/server.py](mcp_sqlserver/server.py) `get_connection()`, `PooledConnection`, and `_CONN_POOLS` - pooling behavior that must remain functionally intact.
- **FILE-002**: [tests/test_execute_in_database.py](tests/test_execute_in_database.py) - primary helper regression test target.
- **FILE-003**: [tests/test_run_query_internal.py](tests/test_run_query_internal.py) - query execution routing regression test target.
- **FILE-003A**: [tests/test_get_connection_retry_cleanup.py](tests/test_get_connection_retry_cleanup.py) - pooled replacement and cleanup regression coverage.
- **FILE-004**: [tests/test_integration_tools.py](tests/test_integration_tools.py) - tool-level integration coverage.
- **FILE-005**: [tests/test_blackbox_http.py](tests/test_blackbox_http.py) - MCP HTTP blackbox validation.
- **FILE-006**: [tests/test_stress_tools.py](tests/test_stress_tools.py) - post-refactor concurrency and stability validation.
- **FILE-007**: [testing/dual_sql_env.ps1](testing/dual_sql_env.ps1) - dual-instance environment bootstrap to be updated for `DB_01_NAME=test1` and `DB_02_NAME=test2`.
- **FILE-008**: [testing/provision_dual_sql.ps1](testing/provision_dual_sql.ps1) - existing two-container provisioning script.
- **FILE-009**: [testing/seed_dual_sql.ps1](testing/seed_dual_sql.ps1) - deterministic seed script to be updated or parameterized for `test1` and `test2`.
- **FILE-010**: [testing/teardown_dual_sql.ps1](testing/teardown_dual_sql.ps1) - existing cleanup script.
- **FILE-011**: [testing/generate_tool_matrix.py](testing/generate_tool_matrix.py) - tool inventory and argument metadata generator.
- **FILE-012**: [testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py) - full dual-instance MCP tool executor.
- **FILE-013**: [testing/tool_matrix.json](testing/tool_matrix.json) - generated coverage inventory.
- **FILE-014**: [testing/tool_execution_summary.json](testing/tool_execution_summary.json) - full-run execution evidence.
- **FILE-015**: [testing/defect_register.json](testing/defect_register.json) - remediation tracking.
- **FILE-016**: [testing/TEST_REPORT.md](testing/TEST_REPORT.md) - final validation report.
- **FILE-017**: [setup_test_database.sql](setup_test_database.sql) - dummy data and database configuration source to be reused or parameterized for `test1` and `test2`.
- **FILE-018**: [testing/tool_results](testing/tool_results) - per-tool serial execution artifacts that must be read and validated before the next suffix proceeds.

## 6. Testing

- **TEST-001**: Helper unit test: `_execute_in_database()` emits `EXEC [db].sys.sp_executesql` for named-database execution and binds parameters in order.
- **TEST-002**: Helper unit test: invalid database names still raise `ValueError` before execution.
- **TEST-003**: Query-routing unit test: `_run_query_internal()` uses scoped execution for named-database requests and preserves readonly enforcement.
- **TEST-004**: Integration test: `db_sql2019_list_tables`, `db_sql2019_get_schema`, `db_sql2019_execute_query`, `db_sql2019_run_query`, and `db_sql2019_explain_query` succeed against `test1` for `instance=1` and `test2` for `instance=2` after the refactor.
- **TEST-005**: Dual-instance integration test: the same query shape returns valid results for both `instance=1` and `instance=2` while each call explicitly resolves to its mapped database name, with no database-context bleed.
- **TEST-006**: Blackbox HTTP test: MCP `/mcp` and `/sse` endpoints remain reachable under the dual-instance configuration.
- **TEST-007**: End-to-end matrix test: [testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py) completes the suffix-pair serial loop with zero failed tools in [testing/tool_execution_summary.json](testing/tool_execution_summary.json).
- **TEST-008**: Functional SQL scope test: execute representative table-size queries through `EXEC [test1].sys.sp_executesql ...` on server 1 and `EXEC [test2].sys.sp_executesql ...` on server 2 from `master` sessions and verify returned table metadata matches the seeded database on each instance.
- **TEST-009**: Write-path safety test: write tools still require the environment flags in [testing/dual_sql_env.ps1](testing/dual_sql_env.ps1) and only mutate disposable test databases.
- **TEST-010**: Stress test: [tests/test_stress_tools.py](tests/test_stress_tools.py) passes after the helper refactor.
- **TEST-011**: Artifact review test: each per-tool artifact written to [testing/tool_results](testing/tool_results) is read immediately after generation and contains no `error`, traceback, or unexpected database attribution before the next suffix executes.
- **TEST-012**: Stop-on-failure workflow test: a deliberately failed suffix pair blocks later suffix execution until the defect is fixed and the repaired artifact passes reread validation.
- **TEST-013**: Pooling regression test: repeated tool calls on the same instance reuse pooled sessions instead of forcing new `pyodbc.connect()` calls for ordinary scoped reads.
- **TEST-014**: Per-instance isolation test: pool activity for `instance=1` never drains from or returns to the pool for `instance=2`, even when `test1` and `test2` are exercised in rapid alternation.
- **TEST-015**: Resource-usage test: pool sizes, replacement-connection cleanup, and autocommit behavior remain stable under the refactor, with no unexpected growth in open connections.

## 7. Risks & Assumptions

- **RISK-001**: Some SQL Server statements behave differently under database-scoped `sp_executesql` than under `USE`. Mitigation: keep a documented allowlist for `master_only` statements and validate each affected tool with focused tests.
- **RISK-002**: Dynamic parameter declaration generation for `sp_executesql` can introduce binding defects. Mitigation: cover parameterless, single-parameter, and multi-parameter cases in unit tests before tool migration.
- **RISK-003**: Existing integration tests currently contain payload-shape drift unrelated to this refactor. Mitigation: repair only blocking assertions and log unrelated failures separately in [testing/defect_register.json](testing/defect_register.json).
- **RISK-004**: Some DMVs or `SHOWPLAN_ALL` behavior may require the connection's current database or session settings rather than only a scoped execution wrapper. Mitigation: handle those cases explicitly as `hybrid` or `master_only` after focused validation.
- **RISK-005**: The full dual-instance run may fail due to environment prerequisites such as Docker readiness or ODBC driver mismatch. Mitigation: validate the environment first with [testing/provision_dual_sql.ps1](testing/provision_dual_sql.ps1) and a small smoke query on both instances.
- **RISK-006**: The current tool matrix and runner still default to `TEST_DB`, which would invalidate the requested `test1`/`test2` coverage if left unchanged. Mitigation: update matrix generation and runner defaults before any serial tool execution begins.
- **RISK-007**: A batch runner can mask which artifact first failed if it continues after errors. Mitigation: enforce suffix-pair stop-on-failure semantics in [testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py).
- **RISK-008**: If `get_connection(database=...)` keeps using database-specific connection strings in the pooled path, the refactor could silently reduce pool reuse and increase connection churn. Mitigation: validate and, if needed, redesign acquisition so pooling stays instance-stable while database scope moves into execution.
- **RISK-009**: Database-scoped execution may leave pooled sessions in an unexpected state if helper logic adds session settings later. Mitigation: keep scoped execution statement-local and extend pooled cleanup tests before rollout.
- **ASSUMPTION-001**: The host can run two SQL Server 2019 containers concurrently.
- **ASSUMPTION-002**: The existing seed assets can be updated or parameterized to produce usable `test1` and `test2` databases on the two instances without introducing schema drift between them.
- **ASSUMPTION-003**: The current FastMCP runtime supports the existing tool-registration and HTTP execution flow used by [testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py).

## 8. Related Specifications / Further Reading

[mcp_sqlserver/server.py](mcp_sqlserver/server.py)
[tests/test_execute_in_database.py](tests/test_execute_in_database.py)
[tests/test_run_query_internal.py](tests/test_run_query_internal.py)
[tests/test_integration_tools.py](tests/test_integration_tools.py)
[tests/test_blackbox_http.py](tests/test_blackbox_http.py)
[testing/README.md](testing/README.md)
[testing/provision_dual_sql.ps1](testing/provision_dual_sql.ps1)
[testing/seed_dual_sql.ps1](testing/seed_dual_sql.ps1)
[testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py)
[setup_test_database.sql](setup_test_database.sql)