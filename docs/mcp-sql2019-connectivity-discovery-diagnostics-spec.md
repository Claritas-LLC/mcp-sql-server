# MCP SQL Server 2019 Multi-Instance Tool Specification

## 1. Scope

This specification defines four MCP tools for SQL Server 2019 operations across two managed instances:

- Instance 1
- Instance 2

All tools must:

- Execute against either instance on demand.
- Accept a target database context where applicable.
- Support cross-database access through fully qualified object names, for example:
  - [Database].[Schema].[Object]
  - [USGISPRO_800].[sys].[tables]

## 2. Instance Mapping and Naming Convention

### 2.1 Canonical Tool Names

For each tool type, expose two concrete tool names:

- db_1_sql2019_ping
- db_2_sql2019_ping
- db_1_sql2019_list_tools
- db_2_sql2019_list_tools
- db_1_sql2019_list_object
- db_2_sql2019_list_object
- db_1_sql2019_execute_query
- db_2_sql2019_execute_query
- db_1_sql2019_analyze_tab_health
- db_2_sql2019_analyze_tab_health
- db_1_sql2019_analyze_db_data_model
- db_2_sql2019_analyze_db_data_model
- db_1_sql2019_analyze_sec_config
- db_2_sql2019_analyze_sec_config
- db_1_sql2019_sessions_dashboard
- db_2_sql2019_sessions_dashboard

### 2.2 Behavioral Rule

Each tool is hard-bound to exactly one instance by name and cannot switch instance at runtime.

## 3. Common Operational Requirements

### 3.1 Security and Policy

- Enforce actor-based session control.
- Enforce rate limits before SQL execution.
- Enforce SQL write restriction policy where configured.
- Write audit events for each invocation:
  - request_id
  - actor
  - tool
  - instance
  - decision
  - sql_hash when SQL is present
  - latency_ms
  - error_code

### 3.2 Cross-Database Query Support

- For object and query tools, support queries that reference other databases using fully qualified names.
- Tool must not rewrite fully qualified object names.
- Tool may execute under current database context while reading remote database metadata by fully qualified reference.

### 3.3 Error Contract

All tools should use deterministic error codes:

- INSTANCE_UNREACHABLE
- AUTH_FAILED
- RATE_LIMIT_EXCEEDED
- SESSION_LIMIT_EXCEEDED
- SQL_BLOCKED_BY_POLICY
- INVALID_INPUT
- SQL_EXECUTION_ERROR
- TIMEOUT

## 4. Tool Specifications

## 4.1 db_<instance #>_sql2019_ping

### Purpose

Check accessibility and runtime identity of a SQL Server 2019 instance.

### Input Parameters

- actor: string
  - Optional
  - Default: `system`

Instance binding is implicit from the concrete tool name (`db_1_...` or `db_2_...`) and is not supplied by the caller.

### Execution Behavior

- Open a connection to the instance.
- Run lightweight identity query for:
  - instance name
  - server host
  - server version
  - server IP
  - system date/time
- Return accessibility true if all checks pass.

### Output Structure

```json
{
  "accessible": true,
  "instance_number": 1,
  "instance_name": "SQL2019-PRD-01",
  "hostname": "sql2019-primary.company.internal",
  "database_version": "Microsoft SQL Server 2019 (RTM-CU...)",
  "ip_address": "10.20.30.40",
  "system_date": "2026-05-06T14:23:01Z",
  "latency_ms": 38
}
```

### Example Use Case

Run db_1_sql2019_ping before executing diagnostics to ensure connectivity and identity match expected target.

## 4.2 db_<instance #>_sql2019_list_tools

### Purpose

List registered MCP tools available on the selected instance endpoint.

### Input Parameters

- actor: string
  - Optional
  - Default: `system`

### Execution Behavior

- Retrieve tool registry active for that instance.
- Include tool descriptions and required parameters.
- Include runtime metadata and retrieval timestamp.

### Output Structure

```json
{
  "instance_number": 1,
  "database_instance_name": "SQL2019-PRD-01",
  "ip_address": "10.20.30.40",
  "system_date": "2026-05-06T14:24:22Z",
  "tools": [
    {
      "name": "db_1_sql2019_ping",
      "description": "Check accessibility of SQL instance 1",
      "required_parameters": []
    },
    {
      "name": "db_1_sql2019_execute_query",
      "description": "Execute SQL query on instance 1",
      "required_parameters": ["database_name", "sql_statement"],
      "optional_parameters": ["actor", "view_mode"]
    }
  ]
}
```

### Example Use Case

Run db_2_sql2019_list_tools to dynamically discover which operations are allowed for Instance 2 in canary mode.

## 4.3 db_<instance #>_sql2019_list_object

### Purpose

List objects inside a specified database by type.

### Input Parameters

- database_name: string
  - Required
  - Example: USGISPRO_800
- object_type: string
  - Required
  - Allowed values: table, view, procedure, function, synonym
- actor: string
  - Optional
  - Default: `system`

### Execution Behavior

- Validate object_type.
- Query system catalogs for the requested database.
- Return object name, schema, type, and owning database.
- Sort alphabetically by schema then object.

### Output Structure

```json
{
  "instance_number": 1,
  "database_name": "USGISPRO_800",
  "system_date": "2026-05-06T14:26:02Z",
  "object_type": "table",
  "objects": [
    {
      "object_name": "Parcel",
      "schema_name": "dbo",
      "object_type": "table",
      "owning_database": "USGISPRO_800"
    },
    {
      "object_name": "Zoning",
      "schema_name": "dbo",
      "object_type": "table",
      "owning_database": "USGISPRO_800"
    }
  ],
  "row_count": 2
}
```

### Example Use Case

From instance 1, run:

- tool: db_1_sql2019_list_object
- inputs: database_name=USGISPRO_800, object_type=table

Expected result: list of tables in USGISPRO_800.

## 4.4 db_<instance #>_sql2019_execute_query

### Purpose

Execute a SQL statement with optional compact or full diagnostic view.

### Input Parameters

- database_name: string
  - Required
  - Connection context database.
- sql_statement: string
  - Required
  - May include fully qualified object names.
- view_mode: string
  - Optional (default: COMPACT)
  - Allowed values: FULL, COMPACT
- actor: string
  - Optional
  - Default: `system`

### Execution Behavior

- Validate view_mode.
- Enforce security and policy checks before execution.
- Execute sql_statement in database_name context.
- If view_mode is FULL:
  - include explain plan summary where available
  - include estimated cost indicators
  - include accessed objects summary
- If view_mode is COMPACT:
  - return rows and minimal metadata only

### Output Structure

```json
{
  "instance_number": 1,
  "database_name": "master",
  "execution_datetime_utc": "2026-05-06T14:28:15Z",
  "view_mode": "FULL",
  "row_count": 5,
  "columns": ["TableName", "RowCounts", "TotalSpaceMB"],
  "rows": [
    {"TableName": "Parcel", "RowCounts": 1200344, "TotalSpaceMB": 1840.44}
  ],
  "plan": {
    "available": true,
    "estimated_cost": 3.442,
    "accessed_objects": [
      "[USGISPRO_800].[sys].[tables]",
      "[USGISPRO_800].[sys].[indexes]",
      "[USGISPRO_800].[sys].[partitions]"
    ]
  }
}
```

### Example Use Case

Connected to database master on Instance 1, execute:

```sql
SELECT TOP 50
    t.name AS TableName,
    SUM(p.rows) AS RowCounts,
    CAST(SUM(a.total_pages) * 8.0 / 1024 AS DECIMAL(18,2)) AS TotalSpaceMB
FROM [USGISPRO_800].[sys].[tables] t
JOIN [USGISPRO_800].[sys].[indexes] i
    ON t.object_id = i.object_id
JOIN [USGISPRO_800].[sys].[partitions] p
    ON i.object_id = p.object_id AND i.index_id = p.index_id
JOIN [USGISPRO_800].[sys].[allocation_units] a
    ON p.partition_id = a.container_id
GROUP BY t.name
ORDER BY TotalSpaceMB DESC;
```

Expected behavior:

- Query succeeds while connected to master because objects are fully qualified to USGISPRO_800.
- Output contains ordered table size metrics.

## 5. Validation Criteria

### Functional Validation

- Ping succeeds independently for both instances.
- List tools returns only tools registered for the selected instance.
- List object returns correct object set for the specified database and type.
- Execute query supports fully qualified references to external databases.

### Operational Validation

- All tool calls generate audit entries.
- Rate limit and session controls apply uniformly.
- Error codes conform to Section 3.3.

## 4.5 db_<instance #>_sql2019_analyze_tab_health

### Purpose

Analyze table, index, and statistics health for a selected database context.

### Input Parameters

- database_name: string (required)
- schema_name: string (optional)
- table_name: string (optional)
- include_indexes: boolean (optional, default true)
- include_statistics: boolean (optional, default true)
- include_histogram_analysis: boolean (optional, default false)
- histogram_top_n: integer (optional, default 10, max 100)
- top_n: integer (optional, default 50)

### Output Highlights

- summary with table/index/statistics scan counts and auto-stats settings
- prioritized findings with severities
- actionable recommendations
- statistics findings include stale, never-updated, low-sampled, and limited-coverage heuristic categories
- optional histogram-based skew indicators are only included when `include_histogram_analysis=true`

## 4.6 db_<instance #>_sql2019_analyze_db_data_model

### Purpose

Analyze data model relationships and identify structural issues.

### Input Parameters

- database_name: string (required)
- schema_filter: string (optional)
- max_edges: integer (optional)

### Output Highlights

- FK graph summary (nodes/edges)
- circular dependency findings
- normalization/integrity recommendations

## 4.7 db_<instance #>_sql2019_analyze_sec_config

### Purpose

Assess security and configuration risks in database and optional server scope.

### Input Parameters

- database_name: string (required)
- include_server_scope: boolean (optional, default true)

### Output Highlights

- orphan users and elevated role memberships
- backup recency indicators
- hardening recommendations with severity prioritization

## 4.8 db_<instance #>_sql2019_sessions_dashboard

### Purpose

Generate interactive session and lock-chain dashboard payload.

### Input Parameters

- database_name: string (optional, default master)
- lookback_minutes: integer (optional)
- include_locks: boolean (optional, default true)

### Output Highlights

- `content_type: text/html`
- `html` fragment for interactive clients
- widget data for active sessions, lock chains, and head blocker recommendations

## 5. Cross-Database Query Examples

Example table-size query from `master` into another database using fully qualified names:

```sql
SELECT TOP 50
    t.name AS TableName,
    SUM(p.rows) AS RowCounts,
    CAST(SUM(a.total_pages) * 8.0 / 1024 AS DECIMAL(18,2)) AS TotalSpaceMB
FROM [USGISPRO_800].[sys].[tables] t
JOIN [USGISPRO_800].[sys].[indexes] i
    ON t.object_id = i.object_id
JOIN [USGISPRO_800].[sys].[partitions] p
    ON i.object_id = p.object_id AND i.index_id = p.index_id
JOIN [USGISPRO_800].[sys].[allocation_units] a
    ON p.partition_id = a.container_id
GROUP BY t.name
ORDER BY TotalSpaceMB DESC;
```

### Functional Validation

- Ping succeeds independently for both instances.
- List tools returns only tools registered for the selected instance.
- List object returns correct object set for the specified database and type.
- Execute query supports fully qualified references to external databases.
- Advanced analysis tools return deterministic JSON envelopes with severity counts and recommendations.

### Operational Validation

- All tool calls generate audit entries.
- Rate limit and session controls apply uniformly.
- Error codes conform to Section 3.3.

### Performance Validation

- COMPACT mode returns lower payload than FULL mode for same query.
- FULL mode adds plan metadata without altering result rows.
- Sessions dashboard payload remains bounded by row limits for predictable runtime.
