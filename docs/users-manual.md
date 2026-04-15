# mcp-sql-server User Manual

## 1. Overview

`mcp-sql-server` is a FastMCP-based server that exposes Microsoft SQL Server operations as MCP tools.

This manual covers:

- What the server does and does not do
- How to run the server
- How to issue tools from MCP clients
- Which tools are available
- Scope, safety controls, and limitations

## 2. Architecture and Naming

### 2.1 Instance model

The server supports up to two configured SQL Server instances:

- Instance 1: configured with `DB_01_*`
- Instance 2: configured with `DB_02_*`

If only one instance is configured, only `db_01_*` tools are available.

### 2.2 Canonical tool names

Use canonical names:

- `db_01_<tool_suffix>` for instance 1
- `db_02_<tool_suffix>` for instance 2

Examples:

- `db_01_ping`
- `db_01_list_tables`
- `db_02_show_top_queries`

## 3. Prerequisites

- Python 3.12+
- SQL Server ODBC driver (`ODBC Driver 17` or `ODBC Driver 18`)
- SQL credentials for at least one database instance
- Optional: Docker for container-based runtime

## 4. Setup and Run

### 4.1 Local Python setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

### 4.2 Minimum `.env` example

```env
DB_01_SERVER=your-sql-host
DB_01_PORT=1433
DB_01_USER=your-user
DB_01_PASSWORD=your-password
DB_01_NAME=master
DB_01_DRIVER=ODBC Driver 18 for SQL Server

MCP_TRANSPORT=http
MCP_HOST=0.0.0.0
MCP_PORT=8000
```

### 4.3 Run locally

```powershell
.\.venv\Scripts\Activate.ps1
python server_startup.py
```

### 4.4 Run with Docker

```powershell
docker build -t mcp-sql-server:local .
docker run -d --name mcp-sqlserver -p 8085:8000 --env MCP_TRANSPORT=http --env-file .env mcp-sql-server:local
```

## 5. Running Modes and Transports

The server supports these transport modes via `MCP_TRANSPORT`:

- `http`
- `sse`
- `stdio`

Notes:

- Web UI routes are separately exposed by custom routes:
  - `/sessions-monitor?instance=1`
  - `/data-model-analysis?id=<report_id>`
- `MCP_HOST` and `MCP_PORT` control bind address and listening port.

## 6. How to Issue Tools

### 6.1 Core rule

Pick the instance prefix first, then append the tool suffix.

- Instance 1: `db_01_<tool_suffix>`
- Instance 2: `db_02_<tool_suffix>`

### 6.2 Generic MCP invocation shape

```json
{
  "tool": "db_01_list_tables",
  "args": {
    "database_name": "master"
  }
}
```

### 6.3 Practical examples

Example 1: Health check instance 1

```json
{
  "tool": "db_01_ping",
  "args": {}
}
```

Example 2: List databases on instance 2

```json
{
  "tool": "db_02_list_databases",
  "args": {}
}
```

Example 3: List tables

```json
{
  "tool": "db_01_list_tables",
  "args": {
    "database_name": "USGISPRO_800",
    "schema_name": "dbo"
  }
}
```

Example 4: Read query execution

```json
{
  "tool": "db_01_execute_query",
  "args": {
    "database_name": "USGISPRO_800",
    "sql": "SELECT TOP 5 name FROM sys.tables"
  }
}
```

Example 5: Data model analysis

```json
{
  "tool": "db_01_analyze_logical_data_model",
  "args": {
    "database_name": "USGISPRO_800",
    "schema": "dbo",
    "view": "summary"
  }
}
```

Example 6: Open model report URL

```json
{
  "tool": "db_01_open_logical_model",
  "args": {
    "database_name": "USGISPRO_800"
  }
}
```

Example 7: Generative sessions dashboard

```json
{
  "tool": "db_01_generate_sessions_dashboard",
  "args": {}
}
```

## 7. Tool Catalog

### 7.1 Canonical tool suffixes from dual-instance registration

All suffixes below are available as both `db_01_<suffix>` and `db_02_<suffix>` when both instances are configured.

#### Connectivity and discovery

- `ping`
- `list_databases`
- `list_tables`
- `get_schema`
- `list_objects`
- `db_stats`
- `server_info_mcp`

#### Query and diagnostics

- `execute_query`
- `run_query`
- `explain_query`

#### Performance and health

- `index_fragmentation`
- `index_health`
- `table_health`
- `show_top_queries`
- `check_fragmentation`
- `db_sec_perf_metrics`

#### Data model and DDL

- `analyze_logical_data_model`
- `open_logical_model`
- `generate_ddl`

#### Admin and write operations

- `create_db_user`
- `drop_db_user`
- `kill_session`
- `create_object`
- `alter_object`
- `drop_object`

### 7.2 Generative dashboard tool suffixes

These are registered separately and available as both `db_01_<suffix>` and `db_02_<suffix>`:

- `generate_sessions_dashboard`
- `generate_model_diagram`
- `generate_performance_dashboard`

## 8. Tool Family Intent Map

| Family | Canonical Suffix Examples | Primary Intent |
| --- | --- | --- |
| Connectivity | `ping`, `server_info_mcp` | Validate server/db availability and runtime info |
| Discovery | `list_databases`, `list_tables`, `get_schema`, `list_objects` | Inspect database structure |
| Query | `execute_query`, `run_query`, `explain_query` | Execute SQL and inspect plans |
| Performance | `show_top_queries`, `index_fragmentation`, `index_health`, `check_fragmentation`, `table_health` | Diagnose and tune workload health |
| Security and posture | `db_sec_perf_metrics` | Review security/performance configuration signals |
| Data model | `analyze_logical_data_model`, `open_logical_model`, `generate_ddl` | Understand relational model and DDL |
| Admin/write | `create_db_user`, `drop_db_user`, `kill_session`, `create_object`, `alter_object`, `drop_object` | Controlled administrative actions |
| Generative dashboards | `generate_sessions_dashboard`, `generate_model_diagram`, `generate_performance_dashboard` | Return context for LLM-built Prefab UI dashboards |

## 9. Configuration Reference

### 9.1 Core runtime settings

- `MCP_TRANSPORT` (default `http`)
- `MCP_HOST` (default `0.0.0.0`)
- `MCP_PORT` (default `8000`)
- `MCP_MAX_ROWS` (default `500`)
- `MCP_STATEMENT_TIMEOUT_MS` (default `120000`)

### 9.2 Safety and write controls

- `MCP_ALLOW_WRITE` (default `false`)
- `MCP_CONFIRM_WRITE` (default `false`)
- `FASTMCP_AUTH_TYPE`

Write safeguards enforced at startup:

- If `MCP_ALLOW_WRITE=true`, then `MCP_CONFIRM_WRITE=true` is required.
- If write mode is enabled over `http` or `sse`, `FASTMCP_AUTH_TYPE` must be set.

### 9.3 Scope enforcement and rate limiting

- `MCP_TABLE_SCOPE_ENFORCED`
- `MCP_ALLOWED_TABLES`
- `MCP_RATE_LIMIT_ENABLED`
- `MCP_RATE_LIMIT_WINDOW_SECONDS` (default `60`)
- `MCP_RATE_LIMIT_MAX_REQUESTS` (default `240`)
- `MCP_RATE_LIMIT_BREAKER_SECONDS` (default `60`)
- `MCP_RATE_LIMIT_BREAKER_VIOLATIONS` (default `3`)

### 9.4 Audit and execution logging

- `MCP_AUDIT_LOG_QUERIES`
- `MCP_AUDIT_LOG_FILE`
- `MCP_AUDIT_LOG_INCLUDE_PARAMS`
- `MCP_ALLOW_RAW_PROMPTS`
- `MCP_LOG_LEVEL`
- `MCP_LOG_FILE`
- `MCP_TOOL_EXECUTION_LOG_ENABLED`

## 10. Scope and Limitations

### 10.1 Scope

This MCP server is scoped to:

- Microsoft SQL Server operations
- Up to two configured SQL instances
- MCP tool-based execution for inspection, querying, and controlled administration
- Optional web routes for session and model report viewing

### 10.2 Limitations

- Two-instance limit in current registration loops (`instance in [1, 2]`).
- Generative dashboard tools require optional dependency support (`fastmcp[apps]`).
- Write/admin tools are disabled by default and require explicit guard configuration.
- Table scope enforcement requires valid `MCP_ALLOWED_TABLES` patterns when enabled.
- Operational behavior varies by environment configuration (auth mode, ODBC driver, SQL permissions).

### 10.3 Non-goals

This server does not aim to:

- Manage GitHub repository settings or project boards
- Act as a generic orchestration platform for non-database workflows
- Guarantee behavior for non-SQL-Server dialects

## 11. Security Expectations

- Never commit `.env` or credential-bearing files.
- Use least-privilege SQL accounts for production.
- Keep `MCP_ALLOW_WRITE=false` unless a write workflow is explicitly needed.
- Configure authentication when exposing HTTP/SSE transports in shared environments.

## 12. Troubleshooting

- ODBC error: verify SQL Server ODBC driver installation and `DB_01_DRIVER`/`DB_02_DRIVER`.
- Connection error: validate host, port, user, password, and network/firewall rules.
- Write tool rejected: verify `MCP_ALLOW_WRITE=true`, `MCP_CONFIRM_WRITE=true`, and `FASTMCP_AUTH_TYPE` for HTTP/SSE.
- Table scope errors: validate `MCP_ALLOWED_TABLES` format (`schema.table`, optional `*` wildcard).
- Generative tool unavailable: install optional dependencies and restart server.

## 13. FAQ

### Q1: Which tool names should I use?

Use canonical names: `db_01_*` and `db_02_*`.

### Q2: Are aliases supported?

Yes, for compatibility. Use canonical names for new clients and automation.

### Q3: Can I use only one instance?

Yes. Configure only `DB_01_*`; then use `db_01_*` tools.

### Q4: Why does write mode fail at startup?

Because runtime guards enforce confirmation and auth requirements in write mode.

## 14. Compatibility Alias Appendix

Compatibility aliases may exist, including patterns such as:

- `db_sql2019_*`
- `db_db2019_*`
- `db_01_sql2019_*`
- `db_02_sql2019_*`

Use these only for legacy client compatibility. Canonical names remain `db_01_*` and `db_02_*`.
