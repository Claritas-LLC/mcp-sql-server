---
goal: Execute all read-only MCP tools against non-production SQL Server instances, capture and review per-tool artifacts, and remediate all errors until zero defects remain
version: 1.1
date_created: 2026-05-01
last_updated: 2026-05-04
owner: QA Engineering
status: 'In progress'
tags: [process, qa, testing, read-only, non-production, dual-instance]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

This plan defines a deterministic, serial workflow to validate all read-only MCP tools across two non-production SQL Server instances and four target databases. Credentials and server addresses are loaded from the repository `.env` file. Each tool variant is executed per database, artifacts are immediately reviewed, and all discovered defects are remediated before the sequence advances. The plan succeeds when every artifact contains zero error fields and the final defect register is empty.

**v1.1 changes (2026-05-04):** Added three previously missing tool suffixes to the QA scope — `list_registered_tools`, `generate_sessions_dashboard`, and `open_logical_model_viewer` (alias for `open_logical_model`). Added TASK-005b (tool registration verification) to Phase 1, TASK-015b (`generate_sessions_dashboard`) and TASK-015c (`list_registered_tools`) to Phase 3. Updated execution counts from 70 to 78 units. Corrected `open_logical_model` task to note both the matrix canonical name and the users-manual alias and require live registration verification.

**Execution Matrix at a glance:**

| Instance | Tool Prefix | Server | Databases |
|---|---|---|---|
| 1 | `db_01_*` | `10.125.1.7:1433` | `USGISPRO_800`, `US_RT_User_800` |
| 2 | `db_02_*` | `10.125.1.8:1433` | `ListGateway`, `US_UserData` |

- **Total suffix pairs:** 22 (44 tools across both instances)
- **Total execution units:** 78 (16 database-scoped suffixes × 4 databases + 6 instance-scoped suffixes × 2 instances)
- **Instance-scoped suffixes (6):** `ping`, `list_databases`, `server_info_mcp`, `generate_sessions_dashboard`, `list_registered_tools`, `open_logical_model_viewer`
- **Write mode:** disabled (`MCP_ALLOW_WRITE=false` enforced throughout)

---

## 1. Requirements & Constraints

- **REQ-001**: Execute all 22 read-only suffix pairs in the deterministic order defined in `testing/run_all_tools_dual_http.py` `PAIR_ORDER` dictionary. The 22 suffixes comprise 16 database-scoped and 6 instance-scoped suffixes.
- **REQ-002**: For each database-scoped suffix (16 suffixes), run the tool against all four target databases: `USGISPRO_800` and `US_RT_User_800` on Instance 1, `ListGateway` and `US_UserData` on Instance 2.
- **REQ-003**: For instance-scoped suffixes that do not accept a `database_name` parameter (`ping`, `list_databases`, `server_info_mcp`, `generate_sessions_dashboard`, `list_registered_tools`, `open_logical_model_viewer`), execute once per instance (2 executions per suffix).
- **REQ-003a**: Before executing any other tool, call `db_01_list_registered_tools` and `db_02_list_registered_tools` and confirm that all 22 read-only suffixes targeted by this plan are present in the response. Any suffix absent from the live registration must be logged as a defect in `testing/nonprod_defect_register.json` before the run proceeds.
- **REQ-004**: Load all connection parameters exclusively from `.env`. Do not hard-code passwords or server addresses in any test artifact or script.
- **REQ-005**: Persist a dedicated artifact JSON file for every single execution unit immediately after the call completes, before advancing to the next unit.
- **REQ-006**: Read and validate the content of each artifact before advancing to the next suffix. If the artifact contains an error, halt the sequence, log the defect, fix the root cause, rerun the failed unit, reread the artifact, and only then continue.
- **REQ-007**: Produce a final `testing/nonprod_defect_register.json` containing all defects encountered during the run, each with status `resolved` by plan completion.
- **REQ-008**: Produce a final `testing/nonprod_test_report.md` summarizing pass/fail totals, all artifact file paths, and representative data excerpts from each database.
- **REQ-009**: All schema and table references in tool arguments must be discovered from the target database before execution; do not reuse seed-data arguments (`sales.Customers`, `sales.Products`) that are only valid in test containers.
- **REQ-010**: The MCP server must be running and reachable at `http://localhost:8085/sse` (or the Docker container) before any tool invocations begin.
- **SEC-001**: `MCP_ALLOW_WRITE=false` must be confirmed active on the running MCP server before executing any tool. If write mode is detected as enabled, abort and do not proceed.
- **SEC-002**: Artifact JSON files must not contain raw connection strings, passwords, or sensitive PII row values. Redact before persisting if needed.
- **SEC-003**: Validate that `_is_sql_readonly()` passes for every SQL argument used in `execute_query`, `run_query`, and `explain_query` calls. Only `SELECT` statements are permitted.
- **CON-001**: Instances are non-production environments. No DDL, DML write operations, or session kills are permitted at any point.
- **CON-002**: Do not restart or reconfigure the running MCP server container between suffix pairs.
- **CON-003**: Tool execution must go through the MCP HTTP JSON-RPC endpoint (`/messages`), not by calling Python functions directly, so transport-layer behavior is validated alongside logic.
- **CON-004**: Artifact files must be written to `testing/tool_results/nonprod_<instance_prefix>_<database_name>_<suffix>.json` to avoid colliding with prior test-container artifacts.
- **GUD-001**: Discover schema and table names from each database using `list_databases` and `list_tables` before attempting any tool that requires `schema_name`, `table_name`, or `schema` arguments.
- **GUD-002**: Choose the first available user schema (non-`sys`, non-`INFORMATION_SCHEMA`) and the first returned table as representative arguments for analysis tools.
- **GUD-003**: For `execute_query`, `run_query`, and `explain_query`, use a safe top-5 `SELECT *` from the discovered first table; always include `TOP 5` to respect `MCP_MAX_ROWS` and avoid large payloads.
- **PAT-001**: Serial execution order per suffix: db_01 × USGISPRO_800, db_01 × US_RT_User_800, db_02 × ListGateway, db_02 × US_UserData. Complete all four variants before advancing to the next suffix.
- **PAT-002**: On first error in any artifact, stop the suffix sequence, log the defect, apply the minimal fix, re-execute the failed unit, re-read the artifact, and confirm green before continuing.
- **PAT-003**: Use `testing/nonprod_defect_register.json` as the single source of defect truth. Never mark a defect resolved without a confirmed clean artifact reread.

---

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Verify prerequisites — confirm server reachability, read-only enforcement, and .env values before any tool is invoked.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-001 | Confirm the MCP server container is running: `docker ps --filter name=mcp-sqlserver --format "{{.Names}} {{.Status}}"`. If not running, start it with `docker run -d --name mcp-sqlserver -p 8085:8000 --env MCP_TRANSPORT=http --env-file .env harryvaldez/mcp-sql-server:latest`. | | |
| TASK-002 | Verify the SSE endpoint responds: `Invoke-RestMethod -Uri http://localhost:8085/sse -Method Get -TimeoutSec 5`. Expect an HTTP 200. | | |
| TASK-003 | Confirm read-only mode: call `db_01_ping` via MCP JSON-RPC and inspect the server response for `allow_write: false` or absence of write capabilities. If write mode is unexpectedly active, stop immediately and investigate the `.env` value `MCP_ALLOW_WRITE`. | | |
| TASK-004 | Verify `.env` is correctly loaded: confirm `DB_01_SERVER=10.125.1.7`, `DB_02_SERVER=10.125.1.8`, `DB_01_USER=mcp_readonly`, `DB_02_USER=mcp_readonly`, and `MCP_ALLOW_WRITE=false` are present using `Get-Content .env \| Select-String "DB_01_SERVER\|DB_02_SERVER\|MCP_ALLOW_WRITE"`. | | |
| TASK-005 | Confirm SQL connectivity to both instances by calling `db_01_ping` and `db_02_ping` via MCP HTTP; persist responses to `testing/tool_results/nonprod_preflight_ping_i1.json` and `testing/tool_results/nonprod_preflight_ping_i2.json`. Abort if either returns an error. | | |
| TASK-005b | **Tool registration verification** — Call `db_01_list_registered_tools` and `db_02_list_registered_tools` with `as_json=true`. Persist responses to `testing/tool_results/nonprod_db_01_list_registered_tools_preflight.json` and `testing/tool_results/nonprod_db_02_list_registered_tools_preflight.json`. Read both artifacts and confirm all 22 read-only suffixes targeted by this plan are present in each instance's tool list: `ping`, `list_databases`, `server_info_mcp`, `generate_sessions_dashboard`, `list_registered_tools`, `open_logical_model_viewer` (or `open_logical_model`), `list_tables`, `get_schema`, `execute_query`, `run_query`, `list_objects`, `index_fragmentation`, `index_health`, `table_health`, `db_stats`, `show_top_queries`, `check_fragmentation`, `db_sec_perf_metrics`, `explain_query`, `analyze_logical_data_model`, `generate_ddl`. Log any missing suffix as a defect in `testing/nonprod_defect_register.json` with `category: registration_gap` before proceeding. | | |
| TASK-006 | Create `testing/nonprod_defect_register.json` with initial content `[]` and `testing/nonprod_execution_log.jsonl` as an empty file to receive one JSON-lines entry per execution unit. | | |

### Implementation Phase 2

- GOAL-002: Discover real schemas and tables from each of the four target databases to build valid args templates for database-scoped tools.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-007 | Call `db_01_list_databases` via MCP JSON-RPC; persist the response to `testing/tool_results/nonprod_db_01_list_databases.json`. Confirm `USGISPRO_800` and `US_RT_User_800` appear in the result. | | |
| TASK-008 | Call `db_02_list_databases` via MCP JSON-RPC; persist the response to `testing/tool_results/nonprod_db_02_list_databases.json`. Confirm `ListGateway` and `US_UserData` appear in the result. | | |
| TASK-009 | For each of the four databases, call `db_01_list_tables` (for Instance 1 databases) or `db_02_list_tables` (for Instance 2 databases) with `database_name` set to the target database and no `schema_name` filter. Persist to `testing/tool_results/nonprod_db_01_USGISPRO_800_list_tables_discovery.json`, `nonprod_db_01_US_RT_User_800_list_tables_discovery.json`, `nonprod_db_02_ListGateway_list_tables_discovery.json`, and `nonprod_db_02_US_UserData_list_tables_discovery.json`. | | |
| TASK-010 | Read each discovery artifact. For each database extract: the first non-system schema name (exclude `sys`, `INFORMATION_SCHEMA`, `guest`, `db_owner`) and the first returned table name within that schema. Record the four tuples as `(schema, table)` pairs in a local reference: `USGISPRO_800`, `US_RT_User_800`, `ListGateway`, `US_UserData`. | | |
| TASK-011 | Build `testing/nonprod_args_templates.json`: a JSON object keyed by `<instance_prefix>_<database_name>` (e.g., `db_01_USGISPRO_800`) containing `schema`, `table_name`, `database_name`, and a safe `SELECT TOP 5 * FROM [schema].[table_name]` SQL string using the discovered values from TASK-010. | | |
| TASK-012 | Verify the args templates JSON is valid and each entry contains non-empty `schema`, `table_name`, `database_name`, and `sql` fields. If any discovery failed (empty tables list, no user schema), record the gap in `testing/nonprod_defect_register.json` and determine a suitable fallback query using only `INFORMATION_SCHEMA` or system views. | | |

### Implementation Phase 3

- GOAL-003: Execute instance-scoped read-only tools (no `database_name` param) for both instances and review artifacts.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-013 | Call `db_01_ping` and `db_02_ping` via MCP JSON-RPC with no arguments. Persist responses to `testing/tool_results/nonprod_db_01_ping.json` and `testing/tool_results/nonprod_db_02_ping.json`. Read both files; confirm neither contains an `error` field. | | |
| TASK-014 | Call `db_01_list_databases` and `db_02_list_databases` via MCP JSON-RPC with no arguments. Persist to `testing/tool_results/nonprod_db_01_list_databases.json` and `testing/tool_results/nonprod_db_02_list_databases.json`. Read both; confirm database count is non-zero and no `error` field is present. | | |
| TASK-015 | Call `db_01_server_info_mcp` and `db_02_server_info_mcp` via MCP JSON-RPC with no arguments. Persist to `testing/tool_results/nonprod_db_01_server_info_mcp.json` and `testing/tool_results/nonprod_db_02_server_info_mcp.json`. Read both; confirm SQL Server version string is present and no `error` field. | | |
| TASK-015b | **Suffix: `generate_sessions_dashboard`** — Call `db_01_generate_sessions_dashboard` and `db_02_generate_sessions_dashboard` via MCP JSON-RPC with no arguments. Persist to `testing/tool_results/nonprod_db_01_generate_sessions_dashboard.json` and `testing/tool_results/nonprod_db_02_generate_sessions_dashboard.json`. Read both; confirm a `sessions_monitor_url` field is present and no `error` field. The URL itself does not need to be reachable during this test; presence of the field confirms the tool is registered and responding correctly. | | |
| TASK-015c | **Suffix: `list_registered_tools`** — Call `db_01_list_registered_tools` and `db_02_list_registered_tools` with `as_json=true`. Persist to `testing/tool_results/nonprod_db_01_list_registered_tools.json` and `testing/tool_results/nonprod_db_02_list_registered_tools.json`. Read both; confirm `tool_count` is non-zero, the `tools` array is present, and no `error` field. Cross-check that the tool count matches or exceeds the count observed in TASK-005b. | | |
| TASK-016 | Append six JSON-lines entries to `testing/nonprod_execution_log.jsonl` (one per instance-scoped suffix: `ping`, `list_databases`, `server_info_mcp`, `generate_sessions_dashboard`, `list_registered_tools`, `open_logical_model_viewer`) recording `suffix`, `scope`, `instance_1_status`, `instance_2_status`, and `timestamp_utc`. | | |

### Implementation Phase 4

- GOAL-004: Execute all 16 database-scoped read-only suffix pairs across all four target databases in deterministic serial order. Artifact-review and halt-on-error discipline is mandatory at every step.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-017 | **Suffix: `list_tables` (order 3)** — For each of the four `(instance_prefix, database_name)` combinations, call the matching `db_0N_list_tables` tool with `database_name` from the args template and no schema filter. Persist to `testing/tool_results/nonprod_<prefix>_<db>_list_tables.json`. After all four calls, read each artifact and confirm `tables` list is non-empty and no `error` field is present before continuing. | | |
| TASK-018 | **Suffix: `get_schema` (order 4)** — Call `db_0N_get_schema` for each (prefix, database) pair using the discovered `schema`, `table_name`, and `database_name` from `testing/nonprod_args_templates.json`. Persist four artifacts. Read each; confirm column definitions are returned and no `error` field. | | |
| TASK-019 | **Suffix: `execute_query` (order 5)** — Call `db_0N_execute_query` for each (prefix, database) pair using the `TOP 5 SELECT *` SQL from the args template with the matching `database_name`. Persist four artifacts. Read each; confirm `rows` array is present (may be empty if table is empty) and no `error` field. | | |
| TASK-020 | **Suffix: `run_query` (order 6)** — Call `db_0N_run_query` for each (prefix, database) pair using `arg1=<database_name>` and `arg2=<TOP 5 SELECT sql>` from the args template. Persist four artifacts. Read each; confirm result rows and no `error` field. | | |
| TASK-021 | **Suffix: `list_objects` (order 7)** — Call `db_0N_list_objects` with `object_type=TABLE`, `schema=<discovered_schema>`, and `database_name=<target_db>` for each (prefix, database) pair. Persist four artifacts. Read each; confirm objects list is present and no `error` field. | | |
| TASK-022 | **Suffix: `index_fragmentation` (order 8)** — Call `db_0N_index_fragmentation` with `schema=<discovered_schema>`, `min_fragmentation=0.0`, `min_page_count=1`, `limit=20`, and `database_name=<target_db>`. Persist four artifacts. Read each; confirm no `error` field (empty result is acceptable if no fragmented indexes exist). | | |
| TASK-023 | **Suffix: `index_health` (order 9)** — Call `db_0N_index_health` with the same schema and database args as TASK-022. Persist four artifacts. Read each; confirm no `error` field. | | |
| TASK-024 | **Suffix: `table_health` (order 10)** — Call `db_0N_table_health` with `schema=<discovered_schema>`, `table_name=<discovered_table>`, `view=standard`, and `database_name=<target_db>`. Persist four artifacts. Read each; confirm health metrics block is present and no `error` field. | | |
| TASK-025 | **Suffix: `db_stats` (order 11)** — Call `db_0N_db_stats` with `database=<target_db>` for each (prefix, database) pair. Persist four artifacts. Read each; confirm database size or stats block is present and no `error` field. | | |
| TASK-026 | **Suffix: `show_top_queries` (order 13)** — Call `db_0N_show_top_queries` with `view=summary` and `database_name=<target_db>`. Persist four artifacts. Read each; confirm no `error` field (empty query store is acceptable if QS is not enabled). | | |
| TASK-027 | **Suffix: `check_fragmentation` (order 14)** — Call `db_0N_check_fragmentation` with `schema_name=<discovered_schema>`, `table_name=<discovered_table>`, and `database_name=<target_db>`. Persist four artifacts. Read each; confirm no `error` field. | | |
| TASK-028 | **Suffix: `db_sec_perf_metrics` (order 15)** — Call `db_0N_db_sec_perf_metrics` with `database_name=<target_db>`. Persist four artifacts. Read each; confirm security or permissions section is present and no `error` field. | | |
| TASK-029 | **Suffix: `explain_query` (order 16)** — Call `db_0N_explain_query` with `sql=<TOP 5 SELECT sql>` and `database_name=<target_db>`. Persist four artifacts. Read each; confirm execution plan XML or text is returned and no `error` field. | | |
| TASK-030 | **Suffix: `analyze_logical_data_model` (order 17)** — Call `db_0N_analyze_logical_data_model` with `schema=<discovered_schema>`, `view=summary`, and `database_name=<target_db>`. Persist four artifacts. Read each; confirm relationships or table list is returned and no `error` field. | | |
| TASK-031 | **Suffix: `open_logical_model` / `open_logical_model_viewer` (order 18)** — The tool matrix registers this suffix as `open_logical_model`; the users manual also documents it as `open_logical_model_viewer`. Before executing, confirm the live registered name via the TASK-005b artifact: use whichever name is present in the registration response. Call `db_0N_open_logical_model` (or `db_0N_open_logical_model_viewer` if that is the registered name) with `schema=<discovered_schema>` and `database_name=<target_db>`. Persist four artifacts to `testing/tool_results/nonprod_<prefix>_<db>_open_logical_model.json`. Read each; confirm HTML model content or a report URL is returned and no `error` field. If both names are registered, test both and persist separate artifacts. | | |
| TASK-032 | **Suffix: `generate_ddl` (order 19)** — Call `db_0N_generate_ddl` with `schema_name=<discovered_schema>`, `table_name=<discovered_table>`, and `database_name=<target_db>`. Persist four artifacts. Read each; confirm `CREATE TABLE` DDL text is returned and no `error` field. | | |
| TASK-033 | After all suffix groups complete, run a bulk artifact audit: read every `testing/tool_results/nonprod_*.json` file, count total artifacts, confirm count equals 78 (16 database-scoped suffixes × 4 executions + 6 instance-scoped suffixes × 2 executions), and confirm zero files contain an `error` key at the top level. Record the audit result in `testing/nonprod_execution_log.jsonl`. | | |

### Implementation Phase 5

- GOAL-005: Remediate every defect logged during Phase 3 and Phase 4 until the defect register contains zero open entries.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-034 | Read `testing/nonprod_defect_register.json`. For each entry with `status: open`, identify whether the root cause is in: (a) the args template (wrong schema/table name); (b) `mcp_sqlserver/server.py` tool or helper logic; (c) the MCP server configuration; or (d) a database permission gap for `mcp_readonly`. Record the root cause category for each open defect. | | |
| TASK-035 | **Args template defects**: Update `testing/nonprod_args_templates.json` for any database where the discovered schema or table name was incorrect or where the SQL statement failed. Re-run the failed execution unit using the corrected template and reread the artifact. Mark defect `resolved` only after artifact is clean. | | |
| TASK-036 | **Server logic defects**: Apply minimal targeted fixes to `mcp_sqlserver/server.py`. Run `pytest tests/test_execute_in_database.py tests/test_run_query_internal.py -q` after each change to confirm no regression. Rebuild the Docker image with `docker build --no-cache -t harryvaldez/mcp-sql-server:latest .`, restart the container, and re-run the failed execution unit. | | |
| TASK-037 | **Permission defects**: For any `mcp_readonly` login that lacks `CONNECT` or `VIEW DATABASE STATE` on the target database, document the required grant statement in `testing/nonprod_defect_register.json` under a `remediation_sql` field, obtain DBA approval, and retest after the grant is applied. | | |
| TASK-038 | After all targeted fixes are applied, re-run the full Phase 4 artifact audit from TASK-033. Confirm total artifact count is still 78 and zero files contain an `error` key. If new errors appear, add them to `testing/nonprod_defect_register.json` and repeat the remediation loop from TASK-034. | | |
| TASK-039 | Confirm `testing/nonprod_defect_register.json` contains zero entries with `status: open` before proceeding to Phase 6. | | |

### Implementation Phase 6

- GOAL-006: Generate an auditable final test report and confirm the non-production environment is in a clean state.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-040 | Generate `testing/nonprod_test_report.md` with: (a) run date and MCP server version; (b) execution matrix table (instance, prefix, database, suffix count, passed, failed); (c) total execution units attempted, passed, and failed; (d) link table to every artifact file; (e) defect summary with counts by category and resolution. | | |
| TASK-041 | Include in `testing/nonprod_test_report.md` representative data excerpts from each of the four databases: at minimum `list_tables` row count, `get_schema` first column definition, and `execute_query` first returned row (redact PII if present). | | |
| TASK-042 | Add a reproducibility block to `testing/nonprod_test_report.md` listing the exact MCP server image tag, `.env` variables used (excluding passwords), and the MCP JSON-RPC invocation pattern used for tool calls. | | |
| TASK-043 | Append a final summary entry to `testing/nonprod_execution_log.jsonl` with fields: `event=final_summary`, `total_units=78`, `passed=<N>`, `failed=0`, `open_defects=0`, `timestamp_utc=<ISO8601>`. | | |
| TASK-044 | Confirm the MCP server container is still running and responsive (`db_01_ping` returns success) after all testing, to confirm the container was not degraded during the run. | | |

---

## 3. Alternatives

- **ALT-001**: Execute tools via direct Python function calls (`mcp_sqlserver/server.py` imports) instead of HTTP JSON-RPC. Rejected because it bypasses transport-layer behavior, middleware, and auth enforcement that are part of the production surface.
- **ALT-002**: Reuse the existing `testing/run_all_tools_dual_http.py` harness unchanged with `test1`/`test2` database names overridden via env vars. Rejected because the real databases have different schemas and no seed data; direct template override produces misleading artifacts.
- **ALT-003**: Run a single database per instance instead of both. Rejected because the requirement specifies two databases per instance and coverage of `USGISPRO_800`, `US_RT_User_800`, `ListGateway`, and `US_UserData` is explicit.
- **ALT-004**: Provision new Docker containers for this validation run. Rejected because the instances at `10.125.1.7` and `10.125.1.8` are the designated non-production environments and are the correct validation target.

---

## 4. Dependencies

- **DEP-001**: MCP server container `harryvaldez/mcp-sql-server:latest` must be running and bound to `localhost:8085` before Phase 3 begins.
- **DEP-002**: `mcp_readonly` SQL login must exist on both `10.125.1.7` and `10.125.1.8` with `CONNECT` permission to `USGISPRO_800`, `US_RT_User_800`, `ListGateway`, and `US_UserData` respectively.
- **DEP-003**: `ODBC Driver 17 for SQL Server` must be installed in the Docker container image (already present in `harryvaldez/mcp-sql-server:latest`).
- **DEP-004**: `testing/tool_matrix.json` must be current and contain 38 tools classified as `read` (verified: 38 tools confirmed).
- **DEP-005**: Network path from the Docker container to `10.125.1.7:1433` and `10.125.1.8:1433` must be open. Use `--network host` on Linux or Docker Desktop host networking on Windows.
- **DEP-006**: `python 3.12+` with `requests` or `httpx` available in the local `.venv` for any helper scripts that call the MCP HTTP endpoint directly.

---

## 5. Files

- **FILE-001**: [.env](.env) — Source of all connection parameters; read-only during this plan, never modified.
- **FILE-002**: [testing/tool_matrix.json](testing/tool_matrix.json) — Authoritative tool inventory; read-only reference. Note: `generate_sessions_dashboard`, `list_registered_tools`, and `open_logical_model_viewer` are not yet in the matrix (added in v1.1 scope); verify live registration via TASK-005b.
- **FILE-003**: [testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py) — Reference for `PAIR_ORDER` and tool invocation patterns.
- **FILE-004**: `testing/nonprod_args_templates.json` — Created in TASK-011; per-database args templates with discovered schema/table names.
- **FILE-005**: `testing/nonprod_defect_register.json` — Created in TASK-006; accumulates all defects with status tracking.
- **FILE-006**: `testing/nonprod_execution_log.jsonl` — Created in TASK-006; append-only execution event log.
- **FILE-007**: `testing/tool_results/nonprod_*.json` — 78 per-execution-unit artifact files created throughout Phases 3 and 4.
- **FILE-008**: `testing/nonprod_test_report.md` — Created in TASK-040; final human-readable summary report.
- **FILE-009**: [mcp_sqlserver/server.py](mcp_sqlserver/server.py) — Modified only if Phase 5 logic defects are identified.

---

## 6. Testing

- **TEST-001**: Pre-flight ping both instances before any tool execution (TASK-005). Failure aborts the entire run.
- **TEST-002**: Schema discovery validation per database (TASK-009–TASK-012). Failure triggers a fallback to `INFORMATION_SCHEMA` queries before any database-scoped tool runs.
- **TEST-003**: Per-artifact immediate read-and-validate after every execution unit (TASK-013 through TASK-032). Failure triggers the TASK-034 remediation loop before the next suffix advances.
- **TEST-004**: Bulk artifact count audit after all Phase 4 suffixes complete (TASK-033). Expected count: 78 artifacts, 0 errors.
- **TEST-004a**: Tool registration check (TASK-005b). All 22 read-only suffixes must appear in the live `list_registered_tools` response for both instances before any tool execution begins. Missing registrations are logged as `category: registration_gap` defects.
- **TEST-005**: Full regression suite `pytest tests/test_execute_in_database.py tests/test_run_query_internal.py tests/test_get_connection_retry_cleanup.py -q` after any `server.py` change in TASK-036. Expected: 10 passed, 0 failed.
- **TEST-006**: Final ping health check after all testing (TASK-044). Confirms container integrity post-run.

---

## 7. Risks & Assumptions

- **RISK-001**: The `mcp_readonly` user may lack permissions on one or more of the four target databases. Mitigation: TASK-003 preflight checks connectivity; TASK-037 documents required grants and escalates to DBA.
- **RISK-002**: Real database schemas may use only `dbo` or system schemas with no user tables discoverable by the standard filter. Mitigation: TASK-012 defines a fallback to `INFORMATION_SCHEMA.TABLES` queries and documents the gap in the defect register.
- **RISK-003**: `show_top_queries` and `explain_query` may fail if Query Store is not enabled on the target databases. Mitigation: empty result set is treated as a pass; only an `error` field in the artifact triggers a defect entry.
- **RISK-004**: `analyze_logical_data_model`, `open_logical_model` / `open_logical_model_viewer`, and `generate_sessions_dashboard` may time out on large schemas or under load. Mitigation: `MCP_STATEMENT_TIMEOUT_MS=120000` is already set; if timeout occurs, log as a defect and reduce scope via `page_size` parameter. For `generate_sessions_dashboard`, a URL response with no data fetch is expected so timeout risk is low.
- **RISK-005**: Docker container networking may not route to `10.125.1.7` or `10.125.1.8` depending on Docker Desktop mode on Windows. Mitigation: TASK-001 verifies container is up; TASK-005 verifies actual SQL reachability before the run starts.
- **RISK-006**: `list_registered_tools`, `generate_sessions_dashboard`, and `open_logical_model_viewer` are not yet in `testing/tool_matrix.json`. If these suffixes are not registered on the live server, TASK-005b will catch the gap and log a `registration_gap` defect before any execution proceeds. Mitigation: resolve registration gaps in Phase 5 TASK-036 before re-running affected units.
- **ASSUMPTION-001**: Both non-production SQL Server instances at `10.125.1.7:1433` and `10.125.1.8:1433` are online and accessible from the Docker container network at plan execution time.
- **ASSUMPTION-002**: `mcp_readonly` is a SQL authentication login (not Windows auth), matching the `.env` values `DB_01_USER=mcp_readonly` and `DB_02_USER=mcp_readonly`.
- **ASSUMPTION-003**: The four specified databases (`USGISPRO_800`, `US_RT_User_800`, `ListGateway`, `US_UserData`) already exist on their respective instances and contain at least one user table.
- **ASSUMPTION-004**: No schema changes or bulk data loads are in progress on the non-production databases during the test run that would cause intermittent lock contention on read queries.

---

## 8. Related Specifications / Further Reading

- [plan/feature-dual-instance-database-scope-sql-1.md](plan/feature-dual-instance-database-scope-sql-1.md) — Completed implementation plan for the `sp_executesql` refactor that this QA plan validates in production-like conditions.
- [plan/process-mcp-tools-dual-sql-validation-1.md](plan/process-mcp-tools-dual-sql-validation-1.md) — Reference test-container validation plan; this plan follows the same serial artifact-review discipline adapted for real instances.
- [testing/tool_matrix.json](testing/tool_matrix.json) — Authoritative tool inventory with classification and args templates.
- [testing/run_all_tools_dual_http.py](testing/run_all_tools_dual_http.py) — Reference serial execution harness and `PAIR_ORDER` dictionary.
- [testing/TEST_REPORT.md](testing/TEST_REPORT.md) — Most recent test-container validation report (May 1, 2026, 50/50 passed).
- [USERS_GUIDE.md](USERS_GUIDE.md) — MCP tool reference including parameter schemas for all 22 read-only tool suffixes covered by this plan.
