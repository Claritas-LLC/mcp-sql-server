# MCP Tool Catalog

> **Audit date**: 2026-06-06  
> **Source of truth**: `src/tools/sql_tools.py` (register_sql_tools), `src/tools/tool_registry.py` (generate_tool_specs)  
> **Runtime verification**: root endpoint `GET /` (`tools` field)

This catalog documents every MCP tool registered with `@mcp.tool` and callable at runtime.

Source of truth:

- Tool registration logic: `src/tools/sql_tools.py`
- Tool spec generator: `src/tools/tool_registry.py`
- Runtime registration list: root endpoint `GET /` (`tools` field)

> **Important**: `tool_registry.py` generates specs for all 12 tool types per instance, but only 7 are decorated with `@mcp.tool` in the named-instance loop. The 5 analysis tools (`analyze_*`, `sessions_dashboard`, `top_statements`) are exclusively registered in the numbered-instance loop.

## Naming Families

The server exposes two naming families.

### 1) Named-instance family

Pattern:

- `db_<instance_name>_sql2019_<tool_name>`

Current instance names:

- `primary`
- `secondary`

### 2) Numbered-instance family

Pattern:

- `db_<instance_number>_sql2019_<tool_name>`

Current instance numbers:

- `1`
- `2`

## Tool Set: Named-instance Family

Registered per instance (`primary`, `secondary`) when enabled by policy flags.
These 7 tools are decorated via the `generate_tool_specs` loop in `register_sql_tools()`.

### `select`

- Tool name format: `db_<instance_name>_sql2019_select`
- Purpose: Execute read SQL with write guard enforcement.
- Required parameters: `sql`
- Optional parameters: `database_name`, `actor`
- Database context: When `database_name` is provided, connects non-pooled to the target database. When omitted, uses the instance default database via the shared connection pool.

### `exec_proc`

- Tool name format: `db_<instance_name>_sql2019_exec_proc`
- Purpose: Execute allowlisted stored procedures only.
- Required parameters: `proc_name`
- Optional parameters: `params`, `database_name`, `actor`
- Security gates:
  - write privilege authorization
  - tool write allowlist (`allowed_write_tools`)
  - procedure allowlist (`allowed_tools.<tool>.allowed_procedures`)
  - SQL EXECUTE permission on target procedure

### `latency_report`

- Tool name format: `db_<instance_name>_sql2019_latency_report`
- Purpose: Return guidance to use diagnostics metrics endpoints for latency analysis.
- Required parameters: none
- Optional parameters: `actor`
- Note: No database context switching — returns a static guidance message.

### `block_report`

- Tool name format: `db_<instance_name>_sql2019_block_report`
- Purpose: Show active blockers/waits from DMVs (TOP 25 by wait_time DESC).
- Required parameters: none
- Optional parameters: `database_name`, `actor`
- Tags: `blocking`

### `top_queries_report`

- Tool name format: `db_<instance_name>_sql2019_top_queries_report`
- Purpose: Top expensive cached queries by total worker time.
- Required parameters: none
- Optional parameters: `limit` (1–100, default 20), `database_name`, `actor`

### `active_sessions_report`

- Tool name format: `db_<instance_name>_sql2019_active_sessions_report`
- Purpose: Active user sessions with request/wait state.
- Required parameters: none
- Optional parameters: `limit` (1–200, default 50), `database_name`, `actor`

### `index_health_report`

- Tool name format: `db_<instance_name>_sql2019_index_health_report`
- Purpose: Index usage counters (seeks, scans, lookups, updates) for maintenance triage.
- Required parameters: none
- Optional parameters: `limit` (1–200, default 50), `database_name`, `actor`
- Note: Uses `DB_ID()` in query — when `database_name` is provided, results are scoped to the target database''s index DMV data.

## Tool Set: Numbered-instance Family

Registered for each configured instance number (`1`, `2`).
These 9 tools are decorated in the per-instance loop of `register_sql_tools()`.

### `ping`

- Tool name format: `db_<instance_number>_sql2019_ping`
- Purpose: Connectivity/identity check for bound instance.
- Required parameters: none
- Optional parameters: `actor`
- Output: `accessible` (bool), `instance_number`, `instance_name`, `hostname`, `database_version`, `ip_address`, `current_system_date`

### `list_tools`

- Tool name format: `db_<instance_number>_sql2019_list_tools`
- Purpose: Enumerate available numbered tools with descriptions, required/optional parameters, output fields, and operational behavior notes.
- Required parameters: none
- Optional parameters: `actor`
- Output: `instance_number`, `database_instance_name`, `ip_address`, `system_date`, `tools[]` array

### `list_object`

- Tool name format: `db_<instance_number>_sql2019_list_object`
- Purpose: Catalog listing by object type (table, view, procedure, function, synonym).
- Required parameters: `database_name`, `object_type`
- Optional parameters: `actor`
- Output: `instance_number`, `database_name`, `system_date`, `object_type`, `objects[]`, `row_count`

### `execute_query`

- Tool name format: `db_<instance_number>_sql2019_execute_query`
- Purpose: Execute SQL in explicit database context with write guard enforcement.
- Required parameters: `database_name`, `sql_statement`
- Optional parameters: `view_mode` (`COMPACT` or `FULL`), `actor`
- FULL mode: Appends estimated execution plan summary when available.
- Timeout: 600s

### `analyze_tab_health`

- Tool name format: `db_<instance_number>_sql2019_analyze_tab_health`
- Purpose: Analyze table size, index fragmentation, missing primary keys, stale/low-sample/never-updated statistics, heap tables, and duplicate key candidates. Returns structured findings and recommendations with DBA review disclaimer.
- Required parameters: `database_name`
- Optional parameters: `schema_name`, `table_name`, `include_indexes` (default true), `include_statistics` (default true), `include_histogram_analysis` (default false), `histogram_top_n` (default 10), `top_n` (default 50), `actor`
- Timeout: 600s
- Output: `instance_number`, `database_name`, `tool`, `generated_at_utc`, `summary`, `severity_counts`, `findings[]`, `recommendations[]`

### `analyze_db_data_model`

- Tool name format: `db_<instance_number>_sql2019_analyze_db_data_model`
- Purpose: Extract FK graph, detect circular dependencies, flag soft-delete columns, data type inconsistencies, and normalization issues. Runs subtool analysis for missing/redundant/unused indexes.
- Required parameters: `database_name`
- Optional parameters: `schema_filter`, `max_edges`, `actor`
- Timeout: 600s
- Output: `instance_number`, `database_name`, `tool`, `generated_at_utc`, `summary`, `severity_counts`, `findings[]`, `recommendations[]`, `model_graph`

### `analyze_sec_config`

- Tool name format: `db_<instance_number>_sql2019_analyze_sec_config`
- Purpose: Security posture assessment — orphaned users, elevated role memberships, guest user access, backup recency. Optionally checks server-scope settings (xp_cmdshell).
- Required parameters: `database_name`
- Optional parameters: `include_server_scope`, `actor`
- Timeout: 300s
- Note: Sensitive fields (login names) are redacted in output.
- Output: `instance_number`, `database_name`, `tool`, `generated_at_utc`, `summary`, `severity_counts`, `findings[]`, `recommendations[]`

### `sessions_dashboard`

- Tool name format: `db_<instance_number>_sql2019_sessions_dashboard`
- Purpose: Build interactive HTML dashboard payload with session activity, lock chains, head blockers, and prescriptive recommendations. Includes `dashboard_url` for HTTP refresh endpoint.
- Required parameters: none
- Optional parameters: `database_name`, `lookback_minutes`, `include_locks`, `actor`
- Output: `content_type`, `html`, `data` (machine-readable widget payload), `dashboard_url`

### `top_statements`

- Tool name format: `db_<instance_number>_sql2019_top_statements`
- Purpose: Analyze top longest-running SQL statements with execution counts and prescriptive recommendations (index strategy, query rewrites, hints, partitioning).
- Required parameters: `database_name`
- Optional parameters: `top_n`, `lookback_minutes`, `view_mode`, `actor`
- Timeout: 300s
- Data source behavior:
  - Primary: Query Store (`data_source = "query_store"`)
  - Fallback: DMV (`data_source = "dmv_fallback"`) when Query Store views are unavailable
- Output: `instance_number`, `database_name`, `tool`, `generated_at_utc`, `summary`, `severity_counts`, `findings[]`, `recommendations[]`, `top_statements[]`, `data_source`

## Common Runtime Controls

All SQL tools are wrapped by:

- actor/session tracking (with TTL and inactivity timeout)
- rate limiting (`local` or `redis` backend)
- write guard / SQL denylist enforcement
- structured audit logging (actor, tool, instance, decision, latency, rows)
- sensitive field redaction (login names, connection details)
- database context switching: pooled path when `database_name` is empty, non-pooled dedicated connection when set

Deterministic failure patterns include (non-exhaustive):

- `RATE_LIMIT_EXCEEDED` — per-actor or global limit hit
- `SESSION_LIMIT_EXCEEDED` — concurrent session cap reached
- `AUTH_FAILED` — missing/invalid bearer token or insufficient privilege
- `SQL_ERROR` — extracted SQL error code with message
- `INVALID_INPUT` — parameter validation failure
- `PERMISSION_DENIED` — write guard or denylist block

---

## Cross-Reference: Which Tools Exist Where

| Tool | Named Family (`primary`/`secondary`) | Numbered Family (`1`/`2`) |
|------|:---:|:---:|
| `select` | ✓ | — |
| `exec_proc` | ✓ | — |
| `latency_report` | ✓ | — |
| `block_report` | ✓ | — |
| `top_queries_report` | ✓ | — |
| `active_sessions_report` | ✓ | — |
| `index_health_report` | ✓ | — |
| `ping` | — | ✓ |
| `list_tools` | — | ✓ |
| `list_object` | — | ✓ |
| `execute_query` | — | ✓ |
| `analyze_tab_health` | — | ✓ |
| `analyze_db_data_model` | — | ✓ |
| `analyze_sec_config` | — | ✓ |
| `sessions_dashboard` | — | ✓ |
| `top_statements` | — | ✓ |

**Total**: 7 named-family + 9 numbered-family = 16 unique tools × 2 instances = 32 callable endpoints.

## Streamable HTTP MCP Invocation Requirements

When calling tools over HTTP transport (`/mcp`), clients must follow session flow:

1. Send `initialize` request with header:
   - `Accept: application/json, text/event-stream`
2. Capture response header:
   - `Mcp-Session-Id`
3. Include that session ID in subsequent requests:
   - `Mcp-Session-Id: <value>`

Without this, tool calls can fail with session/accept errors.
