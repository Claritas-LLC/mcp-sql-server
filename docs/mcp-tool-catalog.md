# MCP Tool Catalog

This catalog documents the MCP tools currently registered by the service.

Source of truth:

- Tool registration logic: `src/tools/sql_tools.py`
- Named tool spec generator: `src/tools/tool_registry.py`
- Runtime registration list: root endpoint `GET /` (`tools` field)

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

### `select`

- Tool name format: `db_<instance_name>_sql2019_select`
- Purpose: Execute read SQL with write guard enforcement.
- Required parameters: `sql`
- Optional parameters: `actor`

### `exec_proc`

- Tool name format: `db_<instance_name>_sql2019_exec_proc`
- Purpose: Execute allowlisted stored procedures only.
- Required parameters: `proc_name`
- Optional parameters: `params`, `actor`
- Security gates:
  - write privilege authorization
  - tool write allowlist (`allowed_write_tools`)
  - procedure allowlist (`allowed_tools.<tool>.allowed_procedures`)
  - SQL EXECUTE permission on target procedure

### `latency_report`

- Tool name format: `db_<instance_name>_sql2019_latency_report`
- Purpose: Return guidance to use diagnostics metrics endpoints.
- Required parameters: none
- Optional parameters: `actor`

### `block_report`

- Tool name format: `db_<instance_name>_sql2019_block_report`
- Purpose: Show active blockers/waits from DMVs.
- Required parameters: none
- Optional parameters: `actor`

### `top_queries_report`

- Tool name format: `db_<instance_name>_sql2019_top_queries_report`
- Purpose: Top expensive cached queries.
- Required parameters: none
- Optional parameters: `limit`, `actor`

### `active_sessions_report`

- Tool name format: `db_<instance_name>_sql2019_active_sessions_report`
- Purpose: Active sessions and requests.
- Required parameters: none
- Optional parameters: `limit`, `actor`

### `index_health_report`

- Tool name format: `db_<instance_name>_sql2019_index_health_report`
- Purpose: Index usage indicators.
- Required parameters: none
- Optional parameters: `limit`, `actor`

### `analyze_tab_health`

- Tool name format: `db_<instance_name>_sql2019_analyze_tab_health`
- Purpose: Analyze table/index/statistics health.
- Required parameters: `database_name`
- Optional parameters: `schema_name`, `table_name`, `include_indexes`, `include_statistics`, `include_histogram_analysis`, `histogram_top_n`, `top_n`, `actor`

### `analyze_db_data_model`

- Tool name format: `db_<instance_name>_sql2019_analyze_db_data_model`
- Purpose: Analyze FK graph quality and circular dependencies.
- Required parameters: `database_name`
- Optional parameters: `schema_filter`, `max_edges`, `actor`

### `analyze_sec_config`

- Tool name format: `db_<instance_name>_sql2019_analyze_sec_config`
- Purpose: Security/configuration assessment.
- Required parameters: `database_name`
- Optional parameters: `include_server_scope`, `actor`

### `sessions_dashboard`

- Tool name format: `db_<instance_name>_sql2019_sessions_dashboard`
- Purpose: Build sessions/locking dashboard payload.
- Required parameters: none
- Optional parameters: `database_name`, `lookback_minutes`, `include_locks`, `actor`

### `top_statements`

- Tool name format: `db_<instance_name>_sql2019_top_statements`
- Purpose: Long-running statement analysis with recommendations.
- Required parameters: `database_name`
- Optional parameters: `top_n`, `lookback_minutes`, `view_mode`, `actor`
- Data source behavior:
  - Primary: Query Store
  - Fallback: DMV (`data_source = "dmv_fallback"`) when Query Store views are unavailable

## Tool Set: Numbered-instance Family

Registered for each configured instance number (`1`, `2`).

### `ping`

- Tool name format: `db_<instance_number>_sql2019_ping`
- Purpose: Connectivity/identity check for bound instance.
- Required parameters: none
- Optional parameters: `actor`

### `list_tools`

- Tool name format: `db_<instance_number>_sql2019_list_tools`
- Purpose: Enumerate available numbered tools and metadata.
- Required parameters: none
- Optional parameters: `actor`

### `list_object`

- Tool name format: `db_<instance_number>_sql2019_list_object`
- Purpose: Catalog listing by object type.
- Required parameters: `database_name`, `object_type`
- Optional parameters: `actor`

### `execute_query`

- Tool name format: `db_<instance_number>_sql2019_execute_query`
- Purpose: Execute SQL in explicit DB context.
- Required parameters: `database_name`, `sql_statement`
- Optional parameters: `view_mode`, `actor`
- Supported `view_mode`: `COMPACT`, `FULL`

### `analyze_tab_health`

- Tool name format: `db_<instance_number>_sql2019_analyze_tab_health`
- Purpose: Same analysis class as named version, bound by instance number.
- Required parameters: `database_name`
- Optional parameters: `schema_name`, `table_name`, `include_indexes`, `include_statistics`, `include_histogram_analysis`, `histogram_top_n`, `top_n`, `actor`

### `analyze_db_data_model`

- Tool name format: `db_<instance_number>_sql2019_analyze_db_data_model`
- Purpose: FK dependency/data model analysis.
- Required parameters: `database_name`
- Optional parameters: `schema_filter`, `max_edges`, `actor`

### `analyze_sec_config`

- Tool name format: `db_<instance_number>_sql2019_analyze_sec_config`
- Purpose: Security/configuration analysis.
- Required parameters: `database_name`
- Optional parameters: `include_server_scope`, `actor`

### `sessions_dashboard`

- Tool name format: `db_<instance_number>_sql2019_sessions_dashboard`
- Purpose: Interactive dashboard payload and `dashboard_url`.
- Required parameters: none
- Optional parameters: `database_name`, `lookback_minutes`, `include_locks`, `actor`

### `top_statements`

- Tool name format: `db_<instance_number>_sql2019_top_statements`
- Purpose: Top long-running statements.
- Required parameters: `database_name`
- Optional parameters: `top_n`, `lookback_minutes`, `view_mode`, `actor`

## Common Runtime Controls

All SQL tools are wrapped by:

- actor/session tracking
- rate limiting (`local` or `redis` backend)
- write guard / denylist enforcement
- structured audit logging

Deterministic failure patterns include (non-exhaustive):

- `RATE_LIMIT_EXCEEDED`
- `SESSION_LIMIT_EXCEEDED`
- `SQL_BLOCKED_BY_POLICY`
- `INVALID_INPUT`
- `SQL_EXECUTION_ERROR`

## Streamable HTTP MCP Invocation Requirements

When calling tools over HTTP transport (`/mcp`), clients must follow session flow:

1. Send `initialize` request with header:
   - `Accept: application/json, text/event-stream`
2. Capture response header:
   - `Mcp-Session-Id`
3. Include that session ID in subsequent requests:
   - `Mcp-Session-Id: <value>`

Without this, tool calls can fail with session/accept errors.
