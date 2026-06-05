---
goal: Audit and enforce consistent database context switching via database_name parameter across all MCP tools
version: 1.2
date_created: 2026-06-05
last_updated: 2026-06-05
owner: MCP SQL Server Team
status: Implementing
parent_plan: plan/feature-advanced-sql-monitoring-tools-1.md
tags: [feature, audit, database-context, consistency, sql-server, fastmcp, query-store]
---

# Introduction

![Status: Implementing](https://img.shields.io/badge/status-Implementing-yellow)

This plan audits every MCP tool registered by `register_sql_tools()` to verify that when `database_name` is part of the input parameters, the database context is actually switched before query execution. It addresses inconsistencies where tools either (a) lack a `database_name` parameter entirely, (b) accept `database_name` but route through execution paths that ignore it, or (c) use `_run_read_tool()` which has no database override support. **Phases 1-3 implemented 2026-06-05.** The plan enforces **REQ-005** (cross-database retrieval via fully qualified names) and **REQ-007** (each tool must support `database_name` input where context is required) from the parent plan.

## Critical Query Store Consideration

In SQL Server 2019, **Query Store is a database-scoped feature**. Each database has its own set of Query Store views (`sys.query_store_query`, `sys.query_store_plan`, `sys.query_store_runtime_stats`, etc.) that are only accessible when connected to that specific database. This means:

- **Correct `database_name` context switching is essential** for `top_statements` — connecting to the wrong database returns the wrong Query Store data.
- **When Query Store is enabled** on the target database: `execute_catalog_query(instance_id, database_name, sql)` correctly creates a connection targeting `database_name`, which gives access to that database's Query Store views. ✅
- **When Query Store is disabled** on the target database: the 42S02 fallback to `sys.dm_exec_query_stats` (DMV) returns **server-wide cached plan data for ALL databases**, ignoring the `database_name` parameter entirely. ❌ This is a critical data integrity issue — the caller expects database-scoped results but gets instance-wide results without clear indication.
- **`top_statements_object_pressure_query()`** uses `DB_ID()` in its `WHERE ius.database_id = DB_ID()` clause, which IS correctly database-scoped when the connection targets the right database. ✅
- **`sys.dm_db_index_usage_stats`** returns data for ALL databases but is correctly filtered to the current database via `DB_ID()`. ✅

### DMV Fallback: The Gap

The DMV fallback query (`top_statements_dmv_fallback_query`) lacks a database filter:
```sql
SELECT ...
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
WHERE qs.execution_count > 0
ORDER BY weighted_avg_duration_us DESC
```

On SQL Server 2019, `sys.dm_exec_query_stats` does not expose `database_id` directly. To scope DMV fallback to a specific database, you would need to use `sys.dm_exec_plan_attributes` with the plan handle:
```sql
CROSS APPLY sys.dm_exec_plan_attributes(qs.plan_handle) pa
WHERE pa.attribute = 'dbid' AND pa.value = DB_ID(@database_name)
```

## 1. Requirements & Constraints

- **REQ-001**: Every tool that executes SQL against a user database must expose a `database_name: str` parameter.
- **REQ-002**: Tools whose queries are server-scoped (server config, instance-level DMVs) may omit `database_name` but must document why in their docstring.
- **REQ-003**: `_run_read_tool()` helper must be extended to accept an optional `database_name` parameter and route through `execute_catalog_query()` or `execute_read_in_database()` instead of `execute_read()`.
- **REQ-004**: Every tool that accepts `database_name` must be tested with at least two different database names to prove context switching works.
- **REQ-005**: Cross-database queries using fully qualified names (`[DB].[schema].[object]`) must continue to work regardless of the connection's `database_name` context.
- **REQ-006**: Pool bypass must be verified: when `database_override` is set, a new connection (not pooled) must be created to the target database.
- **REQ-007**: All analysis tools (`_analyze_tab_health`, `_analyze_db_data_model`, `_analyze_sec_config`, `_sessions_dashboard`, `_top_statements`) that already accept `database_name` must be verified to pass it correctly through to `execute_catalog_query()`.
- **SEC-001**: Database name must be validated via `validate_database_name()` before being passed to any connection method.
- **CON-001**: Do not alter write-guard, rate-limiting, session, audit, or redaction behavior.
- **CON-002**: Existing tool contracts (parameter names, return shapes) must remain backward compatible.
- **CON-003**: **Dual-instance symmetry must be preserved** — every change applied to instance 1 (`db_1_sql2019_*`) must be identically applied to instance 2 (`db_2_sql2019_*`). The tool registration loop in `register_sql_tools()` iterates over all enabled instance IDs; any new `database_name` parameter or `_run_read_tool()` fix must work correctly regardless of which instance the tool is bound to. Do not introduce instance-specific branching in shared executor functions.
- **CON-004**: **Connection pool isolation must be preserved** — the connection pool is per-instance and per-identity (keyed by instance ID). When `database_name` is NOT provided, the existing pooled path (`execute_read()`) must be used, returning connections to the pool after each call. When `database_name` IS provided, the non-pooled path (`execute_catalog_query()` / `execute_read_in_database()`) must create a new connection targeting the specified database and close it after the call completes. One session's timeout or error must NOT corrupt the pool for other sessions — the pool's existing discard-on-error behavior (`_release_connection` with `had_error=True` discards the faulty connection) already guarantees this, and must remain intact.
- **CON-005**: **Connection retry logic must be preserved** — `_run_read_operation()` retries transient errors up to 3 times. The `database_override` path already participates in this retry loop. Any new code path that calls `execute_catalog_query()` inherits this retry behavior automatically.
- **CON-006**: **Non-pooled connections must be reliably closed** — when `database_override` is set, `_release_connection()` with `pooled=False` calls `conn.close()` in a `contextlib.suppress(Exception)` block. This must not be weakened. Connections created for context-switched queries must never be returned to the pool (they target a different database and would corrupt the pool's database affinity).
- **GUD-001**: Document the default database for each tool in its docstring when `database_name` is omitted.
- **PAT-001**: Follow the established pattern used by `_analyze_tab_health` for tools that need context switching.
- **QST-001**: The `top_statements` `data_source` output field must clearly indicate when results are server-wide (DMV fallback) vs database-scoped (Query Store).
- **QST-002**: DMV fallback query (`top_statements_dmv_fallback_query`) must be scoped to the target database using `sys.dm_exec_plan_attributes` filter with `DB_ID(@database_name)` to avoid returning server-wide cached plan data.
- **QST-003**: The `data_source` output must include the target `database_name` so callers can verify context.
- **QST-004**: Query Store configuration status (`is_query_store_on`, `actual_state_desc`) should be included in the `top_statements` output payload when in FULL view_mode, to aid diagnostics.
- **QST-005**: The `_collect_top_statement_metrics` function must verify that the returned Query Store data matches the requested `database_name` (defensive check).

## 2. Implementation Steps

### Implementation Phase 1 — Audit: Inventory All Tools

- GOAL-001: Classify every registered MCP tool by whether it needs `database_name`, already has it, or is server-scoped. All tools are registered per-instance via `register_sql_tools()` — each tool exists as `db_1_sql2019_*` and `db_2_sql2019_*`. Fixes must apply symmetrically to both instances.

| Tool Name | Has `database_name`? | Execution Path | Needs Fix? |
|-----------|---------------------|----------------|------------|
| `_select` | ❌ No | `execute_read()` — instance default DB | **YES** — add `database_name` param |
| `_exec_proc` | ❌ No | `exec_proc_in_database()` — hard-coded DB | **YES** — add `database_name` param |
| `_latency_report` | ❌ No | Returns guidance text, no SQL | No — server-scoped guidance |
| `_block_report` | ❌ No | `_run_read_tool()` → `execute_read()` | **YES** — add `database_name` + fix executor |
| `_top_queries_report` | ❌ No | `_run_read_tool()` → `execute_read()` | **YES** — add `database_name` + fix executor |
| `_active_sessions_report` | ❌ No | `_run_read_tool()` → `execute_read()` | **YES** — add `database_name` + fix executor |
| `_index_health_report` | ❌ No | `_run_read_tool()` → `execute_read()` | **YES** — add `database_name` + fix executor |
| `_ping` | ❌ No | `execute_read()` — server info | No — server-scoped identity |
| `_list_tools` | ❌ No | `execute_read()` — metadata | No — server-scoped metadata |
| `_list_object` | ✅ Yes | `list_objects()` — routes `database_name` | Verify correct |
| `_execute_query` | ✅ Yes | `execute_catalog_query()` — routes correctly | Verify correct |
| `_analyze_tab_health` | ✅ Yes | `execute_catalog_query()` — routes correctly | Verify correct |
| `_analyze_db_data_model` | ✅ Yes | `execute_catalog_query()` — routes correctly | Verify correct |
| `_analyze_sec_config` | ✅ Yes | `execute_catalog_query()` — routes correctly | Verify correct |
| `_sessions_dashboard` | ✅ Yes | `execute_catalog_query()` — routes correctly | Verify correct |
| `_top_statements` | ✅ Yes | `execute_catalog_query()` — routes correctly | Verify correct |

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Run audit: grep every `@mcp.tool` registration and classify against table above. Document any tool not listed. | | |
| TASK-002 | Verify each tool flagged as "Verify correct" actually passes `database_name` through the full call chain to `_connection_string()`. | | |

### Implementation Phase 2 — Fix `_run_read_tool()` to Support Database Override (Pool-Aware)

- GOAL-002: Add optional `database_name` parameter to `_run_read_tool()` and route through `execute_catalog_query()` (non-pooled) when provided. When omitted, the existing pooled `execute_read()` path must remain unchanged. This ensures pool isolation per CON-004: only the pooled path reuses connections; the database-override path creates a fresh connection that is closed after each call.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-003 | Add `database_name: str \| None = None` parameter to `_run_read_tool()` signature. | ✅ | 2026-06-05 |
| TASK-004 | **Pooled vs non-pooled routing**: When `database_name` is provided (non-pooled path), call `state.connection_manager.execute_catalog_query(instance, database_name, sql, max_rows)` — this creates a new connection via `connect(database_override=database_name)` and closes it after use. When `database_name is None` or empty string (pooled path), keep existing `state.connection_manager.execute_read(instance, sql, max_rows)` which uses the pool. | ✅ | 2026-06-05 |
| TASK-005 | When `database_name` is provided, wrap the returned dict to match `execute_read()` return shape (`rows` list). | ✅ | 2026-06-05 |
| TASK-006 | Keep existing `execute_read()` path (pooled) when `database_name is None` for backward compatibility. | ✅ | 2026-06-05 |
| TASK-007 | Update `_run_read_tool()` return dict to include `database_name` key when overridden. | ✅ | 2026-06-05 |
| TASK-007b | **Pool integrity assertion**: In the `database_name` branch, ensure the connection returned by `execute_catalog_query()` is never returned to the pool — verify that `_release_connection` is called with `pooled=False`. This prevents a connection targeting a different database from corrupting the pool. | ✅ | 2026-06-05 |

### Implementation Phase 3 — Add `database_name` to Tools Missing It

- GOAL-003: Add `database_name` parameter to `_select`, `_exec_proc`, `_block_report`, `_top_queries_report`, `_active_sessions_report`, and `_index_health_report`. All changes apply identically to both instances because these tools are registered inside the `for spec in generate_tool_specs(instance_ids)` loop in `register_sql_tools()`. A single code change to each tool function body fixes both `db_1_sql2019_*` and `db_2_sql2019_*` variants.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | **`_select`**: Add `database_name: str = ""` parameter. When non-empty, validate and pass to `execute_read_in_database()` (non-pooled, creates new connection to target DB). When empty, keep existing pooled path (`execute_read()`). Update docstring. Applies to both instance variants via tool registration loop. | ✅ | 2026-06-05 |
| TASK-009 | **`_exec_proc`**: Add `database_name: str = ""` parameter. When non-empty, validate and pass to `execute_proc(database_override=...)`. Update docstring. | ✅ | 2026-06-05 |
| TASK-010 | **`_block_report`**: Add `database_name: str = ""` parameter, pass to `_run_read_tool()`. Update docstring. | ✅ | 2026-06-05 |
| TASK-011 | **`_top_queries_report`**: Add `database_name: str = ""` parameter, pass to `_run_read_tool()`. Update docstring. | ✅ | 2026-06-05 |
| TASK-012 | **`_active_sessions_report`**: Add `database_name: str = ""` parameter, pass to `_run_read_tool()`. Update docstring. | ✅ | 2026-06-05 |
| TASK-013 | **`_index_health_report`**: Add `database_name: str = ""` parameter, pass to `_run_read_tool()`. Update docstring. | ✅ | 2026-06-05 |
| TASK-014 | Update `tool_registry.py` `generate_tool_specs()` if tool metadata needs to reflect new optional parameters. | N/A | 2026-06-05 |

### Implementation Phase 4 — Validate Existing Tools with `database_name`

- GOAL-004: Verify tools that already accept `database_name` correctly switch context.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-015 | **`_execute_query`**: Trace call chain: `database_name` → `validate_database_name()` → `execute_catalog_query()` → `execute_read_in_database()` → `_run_read_operation()` → `connect(database_override=database_name)` → `_connection_string(DATABASE=database_name)`. Verify all links. | | |
| TASK-016 | **`_list_object`**: Trace `database_name` → `list_objects()` → `_run_read_operation(database_override=database_name)`. Verify. | | |
| TASK-017 | **`_analyze_tab_health`**: Verify all `execute_catalog_query()` calls pass the user-provided `database_name` (not the instance default). | | |
| TASK-018 | **`_analyze_db_data_model`**: Same verification as TASK-017. | | |
| TASK-019 | **`_analyze_sec_config`**: Same verification. | | |
| TASK-020 | **`_sessions_dashboard`**: Same verification. | | |
| TASK-021 | **`_top_statements`**: Same verification. | | |
| TASK-022 | Verify that `guest_access_query()` uses `DB_NAME()` (already confirmed) and returns the correct database under context switch. | | |
| TASK-023 | **Query Store — Verify `top_statements` query_store path**: When connected to `database_name` with Query Store enabled, confirm `sys.query_store_*` views return data for that specific database only. | | |
| TASK-024 | **Query Store — Verify DMV fallback scope**: `top_statements_dmv_fallback_query` returns server-wide data. Add `sys.dm_exec_plan_attributes` filter by `DB_ID(@database_name)` to scope results. | | |
| TASK-025 | **Query Store — Verify `data_source` field**: Confirm the output includes accurate `data_source` (`query_store`, `dmv_fallback`, `unavailable`) and that DMV fallback results are clearly labeled as server-wide. | | |
| TASK-026 | **Query Store — Add diagnostics query**: Add `query_store_config_query()` to `query_catalog.py` returning `is_query_store_on`, `actual_state_desc`, `desired_state_desc`, `current_storage_size_mb`, and `max_storage_size_mb` for the target database. | | |
| TASK-027 | **Query Store — Integrate config into FULL view_mode**: When `view_mode=FULL`, include Query Store configuration in `_top_statements` output. | | |
| TASK-028 | **Query Store — Defensive context check**: In `_collect_top_statement_metrics`, after Query Store query succeeds, verify `DB_NAME()` matches the requested `database_name` as a runtime guard. | | |

### Implementation Phase 5 — Tests

- GOAL-005: Add/update tests to prove database context switching works end-to-end.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-023 | Add `test_run_read_tool_with_database_override()` to verify `_run_read_tool()` uses `execute_catalog_query` when `database_name` is provided. | | |
| TASK-024 | Add `test_select_with_database_name_switches_context()`: invoke `_select` with two different `database_name` values and assert different row results. | | |
| TASK-025 | Add `test_exec_proc_with_database_name()`: verify stored procedure executes in the specified database context. | | |
| TASK-026 | Add `test_index_health_report_returns_db_scoped_data()`: verify `_index_health_report` returns different results per database. | | |
| TASK-027 | Add `test_block_report_with_database_name()`: verify `_block_report` accepts and passes `database_name`. | | |
| TASK-028 | Add `test_database_name_param_in_tool_docstrings()`: assert every tool with `database_name` in its signature mentions it in the docstring. | | |
| TASK-029 | Add `test_cross_database_fully_qualified_query()`: run a query using `[DB2].[sys].[tables]` while connected to `DB1` to verify REQ-005. | | |
| TASK-030 | **Pool resilience**: Add `test_database_override_bypasses_pool()`: verify that `database_override` creates a new connection with `pooled=False` and the connection is closed (not returned to pool) after use. | | |
| TASK-031 | **Pool resilience**: Add `test_pool_default_path_still_pooled()`: verify that when `database_name` is empty/omitted, tools use the pooled path — connection is taken from and returned to the pool. | | |
| TASK-032 | **Pool resilience**: Add `test_pool_not_corrupted_by_tool_error()`: simulate a timeout/error in one tool call via `_run_read_tool()` (e.g., force `had_error=True`), then verify subsequent tool calls on the same instance succeed using fresh connections from the pool. | | |
| TASK-033 | **Pool resilience**: Add `test_concurrent_sessions_independent_pools()`: simulate two concurrent sessions calling tools on the same instance — verify one session's error (forced) does not block the other session's ability to acquire and use connections. | | |
| TASK-034 | **Pool resilience**: Add `test_non_pooled_connection_closed_on_error()`: verify that when `database_override` is set and an error occurs, `_release_connection` with `pooled=False` closes the connection (not returned to pool). | | |
| TASK-035 | **Query Store test**: Add `test_top_statements_switches_query_store_context()`: invoke `_top_statements` with two different `database_name` values and verify `data_source` reflects per-database Query Store data. | | |
| TASK-036 | **Query Store test**: Add `test_dmv_fallback_scoped_to_database()`: verify that DMV fallback query includes `sys.dm_exec_plan_attributes` filter and does not return server-wide data. | | |
| TASK-037 | **Query Store test**: Add `test_query_store_config_query_structure()`: verify `query_store_config_query()` returns expected columns. | | |
| TASK-038 | **Query Store test**: Add `test_top_statements_data_source_accuracy()`: verify `data_source` field matches actual Query Store availability on the target database. | | |

### Implementation Phase 6 — Documentation & Verification

- GOAL-006: Update tool docstrings and docs to reflect database context behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-031 | Update docstrings for all tools modified in Phase 3 to document default database behavior. | | |
| TASK-032 | Update `docs/mcp-tool-catalog.md` with `database_name` parameter for each tool. | | |
| TASK-033 | Update `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` with context-switching guidance. | | |
| TASK-034 | Run `ruff check .` and `pytest -q` to validate all changes. | | |

## 3. Alternatives

- **ALT-001**: Make `database_name` required for all tools. Rejected because server-scoped tools (`_ping`, `_list_tools`) don't need a database context and adding one would confuse callers.
- **ALT-002**: Use `USE [database]` SQL statement within a single connection instead of creating a new connection per database. Rejected because it would introduce connection state mutation issues with the pool and potential race conditions.
- **ALT-003**: Keep `_run_read_tool()` unchanged and add separate wrapper tools. Rejected because it would double the tool count and violate DRY.

## 4. Dependencies

- **DEP-001**: `src/tools/sql_tools.py` — all tool registrations and `_run_read_tool()` helper.
- **DEP-002**: `src/db/connection_manager.py` — `execute_read()`, `execute_read_in_database()`, `execute_catalog_query()`, `_connect_new()`, `_connection_string()`.
- **DEP-003**: `src/tools/input_validation.py` — `validate_database_name()`.
- **DEP-004**: `tests/test_advanced_analysis_tools.py` — existing test structure to extend.
- **DEP-005**: `docs/mcp-tool-catalog.md` — documentation updates.
- **DEP-006**: `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` — spec updates.

## 5. Files

- **FILE-001**: `src/tools/sql_tools.py` — add `database_name` to `_run_read_tool()` and tools missing it.
- **FILE-002**: `src/tools/tool_registry.py` — optional metadata updates.
- **FILE-003**: `src/db/connection_manager.py` — verify existing `_connection_string` override path works.
- **FILE-004**: `src/tools/query_catalog.py` — add `query_store_config_query()` and fix DMV fallback scope in `top_statements_dmv_fallback_query()`.
- **FILE-005**: `tests/test_advanced_analysis_tools.py` — add context-switching and Query Store tests.
- **FILE-006**: `tests/test_database_context_switching.py` — new test module for context-switching.
- **FILE-007**: `docs/mcp-tool-catalog.md` — parameter documentation updates.
- **FILE-008**: `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` — context-switching and Query Store guidance.

## 6. Testing

- **TEST-001**: Unit test `_run_read_tool()` routes to `execute_catalog_query()` when `database_name` is provided.
- **TEST-002**: Unit test each tool that gained `database_name` accepts it without breaking existing calls (default empty string).
- **TEST-003**: Unit test `validate_database_name()` is called before connection methods.
- **TEST-004**: Integration test cross-database query using fully qualified names (REQ-005).
- **TEST-005**: Integration test context switch by comparing `DB_NAME()` results from two different tool calls with different `database_name` values.
- **TEST-006**: Verify pool bypass: `_acquire_connection()` returns `pooled=False` when `database_override` is set.
- **TEST-007**: Regression: all existing tests continue to pass unchanged.
- **TEST-008**: Query Store: verify `top_statements` returns database-scoped data when Query Store is enabled.
- **TEST-009**: Query Store: verify DMV fallback is scoped via `sys.dm_exec_plan_attributes` and does not return server-wide data.
- **TEST-010**: Query Store: verify `query_store_config_query()` structure and column types.
- **TEST-011**: Query Store: verify `data_source` output field accuracy matches Query Store availability.

## 7. Risks & Assumptions

- **RISK-001**: Adding `database_name` to tools that query server-scoped DMVs (`sys.dm_exec_query_stats`, `sys.dm_exec_sessions`) may create a misleading expectation that results are database-scoped when they are not. Mitigation: document in docstring that these tools query instance-level DMVs.
- **RISK-002**: Pool bypass (new connection per unique `database_name`) increases connection creation overhead. Mitigation: `database_override` by design creates short-lived connections; cache pressure is acceptable for diagnostic tools.
- **RISK-003**: Adding optional `database_name` with default `""` is backward compatible but may not be discovered by existing callers. Mitigation: update tool catalog and list-tools output.
- **RISK-004**: **Query Store DMV fallback returns server-wide data** — when Query Store is disabled on the target database, `top_statements_dmv_fallback_query()` returns cached plan data for ALL databases on the instance, not just the target. Mitigation: add `sys.dm_exec_plan_attributes` filter by `DB_ID(database_name)` to scope the fallback, and clearly label fallback results as server-wide.
- **RISK-005**: **Query Store may be in READ_ONLY state** — SQL Server 2019 Query Store can transition to READ_ONLY when full (`max_storage_size_mb` exceeded). The `top_statements` tool can still read from it, but new queries aren't tracked. Mitigation: include `actual_state_desc` in FULL view_mode output so users can diagnose.
- **RISK-006**: **Cross-database Query Store queries via fully qualified names** — Query Store views (`sys.query_store_query`, etc.) cannot be referenced cross-database with a 3-part name (`[DB].[sys].[query_store_query]`). They must be queried while connected to the target database. This makes `database_name` context switching the ONLY way to access Query Store for different databases.
- **ASSUMPTION-001**: All analysis tools that accept `database_name` already pass it correctly (Phase 4 verification exists to prove this).
- **ASSUMPTION-002**: The `_connection_string()` method's `database_override` parameter correctly targets the desired database in the ODBC connection string.
- **ASSUMPTION-003**: `_select` and `_exec_proc` are the two tools most likely used with ad-hoc `database_name` and highest priority for fixing.
- **ASSUMPTION-004**: Query Store is available on SQL Server 2019 databases where `top_statements` is used. Databases without Query Store will fall back to DMV data, but the scope will be limited by the `sys.dm_exec_plan_attributes` filter to match the requested database.

## 8. Related Specifications / Further Reading

- `plan/feature-advanced-sql-monitoring-tools-1.md` (parent plan — REQ-005, REQ-007)
- `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md`
- `docs/mcp-tool-catalog.md`
- `docs/access-levels-and-controlled-write.md`
- `src/db/connection_manager.py` — connection override logic
