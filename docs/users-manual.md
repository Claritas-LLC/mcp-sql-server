## 7. Tool Introspection Utility

### 7.1 Overview

The `list_registered_tools` tool provides a dynamic, up-to-date list of all available tools, their descriptions, parameters (required and optional), and usage instructions for a specific instance. This is useful for discovering available capabilities and for programmatic documentation.

**Key features:**
- Automatically discovers all registered tools at runtime
- Filters tools by instance (shows only tools for instance 1 or 2)
- Supports both JSON and human-readable text output
- Includes parameter types, defaults, and usage examples
- No server restart required to reflect new or removed tools
- Does not expose sensitive information or internal implementation details

### 7.2 Usage

**Invoke via MCP (JSON output):**
```json
{
  "tool": "db_01_list_registered_tools",
  "args": { "as_json": true }
}
```

**Invoke via MCP (Text output):**
```json
{


### 7.3 Example Output

**JSON:**
```json
{
  "status": "success",
  "instance": 1,
  "tool_count": 25,
  "tools": [
    {
      "name": "db_01_ping",
      "description": "Basic connectivity probe to a SQL Server instance.",
      "parameters": [
        {"name": "instance", "type": "<class 'int'>", "required": false, "default": 1}
      ],
      "usage": "db_01_ping [instance=1]"
    },
    {
      "name": "db_01_list_tables",
      "description": "List user tables in a database.",
      "parameters": [
        {"name": "database_name", "type": "<class 'str'>", "required": true, "default": null},
        {"name": "schema_name", "type": "<class 'str'>", "required": false, "default": "dbo"}
      ],
      "usage": "db_01_list_tables database_name=<value> [schema_name='dbo']"
    }
  ]
}
```

**Text:**
```
Registered Tools for Instance 1
==================================================
Total tools: 25

Tool: db_01_list_tables
Description: List user tables in a database.
Parameters:
  - database_name (<class 'str'>): required
  - schema_name (<class 'str'>): optional, default='dbo'
Usage: db_01_list_tables database_name=<value> [schema_name='dbo']

... (other tools)
```

### 7.4 Notes

- The list is always current and reflects all tools registered in the server.
- Use this tool to programmatically discover tool names, required arguments, and usage patterns for automation or documentation.
- The tool filters results to show only tools for the specified instance (db_01_* or db_02_*).
- Generic tools without an instance prefix are also included in the output.

# Security Note

**Never commit real secrets or passwords to .env, code, or documentation.**
Always use environment variables or a secrets manager for production credentials. Replace example secrets with placeholders like `CHANGEME`.
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


### 2.2 Canonical tool names

Use canonical names:

- `db_sql2019_<tool_suffix>` for the single instance

Examples:

- `db_sql2019_ping`
- `db_sql2019_list_tables`

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

Example 5b: Data model analysis with email delivery

```json
{
  "tool": "db_01_analyze_logical_data_model",
  "args": {
    "database_name": "USGISPRO_800",
    "schema": "dbo",
    "view": "summary",
    "email_recipient": "recipient@example.com"
  }
}
```

When `email_recipient` is provided, the analysis report is sent as an HTML email via Office 365. If email sending fails, the analysis is returned in JSON format. Without `email_recipient`, the tool returns the analysis in JSON format directly.

**Background Task Support**: The `analyze_logical_data_model` tool supports background task execution for long-running analyses on large databases. When run as a background task, the tool returns a task ID immediately and provides progress updates. To use background mode, the MCP client must request task execution. The tool will run asynchronously and report progress through stages: database connection, analysis, report generation, and email sending (if applicable).

Example 5c: Data model analysis with background task (if supported by MCP client)

```json
{
  "tool": "db_01_analyze_logical_data_model",
  "args": {
    "database_name": "USGISPRO_800",
    "schema": "dbo",
    "view": "full"
  },
  "options": {
    "task": true
  }
}
```

When run as a background task, the client receives a task ID and can poll for results. Progress is reported at key stages of the analysis process.

Example 6: Sessions monitor dashboard (returns URL)

```json
{
  "tool": "db_01_generate_sessions_dashboard",
  "args": {}
}
```

Returns a URL to the sessions monitor webpage. The data is fetched on-demand when the URL is visited, avoiding MCP timeouts. Example response:

```json
{
  "status": "success",
  "message": "Sessions monitor dashboard ready.",
  "instance": 1,
  "sessions_monitor_url": "http://localhost:8000/sessions-monitor?instance=1",
  "url_hint": "The dashboard fetches data on-demand when visited. Use dedicated tools (list_sessions, kill_session) for detailed session management."
}
```


## 7. Tool Catalog

### 7.1 Canonical tool suffixes

All suffixes below are available as `db_sql2019_<suffix>` for the single instance.

#### Introspection and discovery

- `list_registered_tools`

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
- `open_logical_model_viewer`
- `generate_ddl`

#### Admin and write operations

- `create_db_user`
- `drop_db_user`
- `kill_session`
- `create_object`
- `alter_object`
- `drop_object`

### 7.2 Dashboard tool suffixes

- `generate_sessions_dashboard` - Returns a URL to the sessions monitor webpage (data fetched on-demand)
- `generate_model_diagram` - Generates a Prefab UI diagram for the logical data model (requires GenerativeUI)
- `generate_performance_dashboard` - Returns a URL to the performance dashboard webpage (data fetched on-demand)

## 8. Tool Family Intent Map

| Family | Canonical Suffix Examples | Primary Intent |
| --- | --- | --- |
| Introspection | `list_registered_tools` | Discover available tools, parameters, and usage |
| Connectivity | `ping`, `server_info_mcp` | Validate server/db availability and runtime info |
| Discovery | `list_databases`, `list_tables`, `get_schema`, `list_objects` | Inspect database structure |
| Query | `execute_query`, `run_query`, `explain_query` | Execute SQL and inspect plans |
| Performance | `show_top_queries`, `index_fragmentation`, `index_health`, `check_fragmentation`, `table_health` | Diagnose and tune workload health |
| Security and posture | `db_sec_perf_metrics` | Review security/performance configuration signals |
| Data model | `analyze_logical_data_model`, `open_logical_model_viewer`, `generate_ddl` | Understand relational model and DDL |
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

### 9.5 Office 365 email configuration

The `analyze_logical_data_model` tool can optionally send analysis reports as HTML emails via Office 365.

- `MCP_O365_EMAIL_ENABLED` (default `false`) - Enable/disable email sending
- `MCP_O365_CLIENT_ID` - Azure AD app client ID for OAuth2 authentication
- `MCP_O365_CLIENT_SECRET` - Azure AD app client secret for OAuth2 authentication
- `MCP_O365_TENANT_ID` - Azure AD tenant ID
- `MCP_O365_SENDER_EMAIL` (default `notification@example.com`) - Sender email address

**Setup instructions:**

1. Register an Azure AD application with `Mail.Send` permission
2. Set `MCP_O365_EMAIL_ENABLED=true` in your `.env` file
3. Configure `MCP_O365_CLIENT_ID` with your Azure AD app client ID
4. Configure `MCP_O365_CLIENT_SECRET` with your Azure AD app client secret
5. Configure `MCP_O365_TENANT_ID` with your Azure AD tenant ID
6. Optionally customize `MCP_O365_SENDER_EMAIL` if different from the app's default sender
7. Use the `email_recipient` parameter when calling `analyze_logical_data_model` to send the report via email

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

## 11.1 SQL Injection and Multi-Statement Enforcement

All SQL entry points (including `execute_query`, `run_query`, `create_object`, `alter_object`, and `drop_object`) enforce a strict single-statement policy:

- **Multi-statement SQL is blocked.** Any attempt to submit more than one SQL statement (e.g., using multiple semicolons or statement chaining) will be rejected with an error.
- **Trailing semicolon is allowed.** A single trailing semicolon is permitted if it is the only one present.
- **Why:** This prevents SQL injection attacks that rely on statement chaining and ensures only one operation is performed per tool call.

If you receive an error about multi-statement SQL, review your input and ensure only a single statement is present. Example of rejected input:

```sql
SELECT * FROM users; DROP TABLE users;
```

Example of accepted input:

```sql
SELECT * FROM users;
```

This applies to all tool APIs that accept SQL input.

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
