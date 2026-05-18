# MCP Tool Catalog

This catalog defines the first expansion batch of remote MCP tools for dual SQL Server 2019 instances.

## Naming Standard

All tools follow:
- `db_<instance>_sql2019_<toolname>`

Supported instances:
- `primary`
- `secondary`

## Batch 1 Tool Set

### 1. `db_<instance>_sql2019_top_queries_report`
- Category: `read_only`
- Purpose: Return top CPU/time-consuming cached queries for tuning triage.
- Input:
  - `limit` (int, optional, default 20, max 100)
  - `actor` (str, optional)
- Output:
  - `instance` (str)
  - `tool` (str)
  - `row_count` (int)
  - `rows` (array)
- SQL Privilege Profile:
  - Requires DMV read access to `sys.dm_exec_query_stats` and `sys.dm_exec_sql_text`.
- Failure Codes:
  - `RATE_LIMIT_EXCEEDED`
  - `SESSION_LIMIT_EXCEEDED`
  - `SQL_BLOCKED_BY_POLICY`
  - `SQL_EXECUTION_ERROR`

### 2. `db_<instance>_sql2019_active_sessions_report`
- Category: `read_only`
- Purpose: Return active user sessions and request state.
- Input:
  - `limit` (int, optional, default 50, max 200)
  - `actor` (str, optional)
- Output:
  - `instance` (str)
  - `tool` (str)
  - `row_count` (int)
  - `rows` (array)
- SQL Privilege Profile:
  - Requires DMV read access to `sys.dm_exec_sessions` and `sys.dm_exec_requests`.
- Failure Codes:
  - `RATE_LIMIT_EXCEEDED`
  - `SESSION_LIMIT_EXCEEDED`
  - `SQL_BLOCKED_BY_POLICY`
  - `SQL_EXECUTION_ERROR`

### 3. `db_<instance>_sql2019_index_health_report`
- Category: `read_only`
- Purpose: Summarize index health and usage indicators for maintenance planning.
- Input:
  - `limit` (int, optional, default 50, max 200)
  - `actor` (str, optional)
- Output:
  - `instance` (str)
  - `tool` (str)
  - `row_count` (int)
  - `rows` (array)
- SQL Privilege Profile:
  - Requires catalog and DMV read access.
- Failure Codes:
  - `RATE_LIMIT_EXCEEDED`
  - `SESSION_LIMIT_EXCEEDED`
  - `SQL_BLOCKED_BY_POLICY`
  - `SQL_EXECUTION_ERROR`

## Actor Identity Expectations

- Human DBA actor: named principal (for example `dba.jane`).
- Automation actor: named service identity (for example `svc-nightly-reporting`).
- System actor: reserved `system` value for internal jobs only.

## Controlled Write Tools

No new controlled-write tools are included in Batch 1.
Existing write-capable tools remain:
- `db_primary_sql2019_exec_proc`
- `db_secondary_sql2019_exec_proc`

Any future write-capable additions require:
- Security owner approval
- Explicit `allowed_write_tools` entry in `config/runtime-policy.yaml`
- Corresponding `allowed_tools.<tool>.allowed_procedures` entry in `config/runtime-policy.yaml`

Notes:
- `config/runtime-policy.yaml` is the runtime-enforced policy source.
- `policy/sql-allowlist.yaml` is a review/reference mirror and not loaded at runtime.
- Procedure allowlisting does not grant database permissions. The MCP SQL principal still needs EXECUTE rights on approved procedures.

## Batch 2 Advanced Analysis Tool Set

### 4. `db_<instance #>_sql2019_analyze_tab_health`
- Category: `read_only_analysis`
- Purpose: Analyze table/index health (size, fragmentation, missing primary keys) and produce prioritized findings.
- Input:
  - `database_name` (str, required)
  - `schema_name` (str, optional)
  - `table_name` (str, optional)
  - `include_indexes` (bool, optional, default true)
  - `top_n` (int, optional, default 50, max 500)
  - `actor` (str, optional)
- Output:
  - deterministic JSON report envelope
  - `summary`, `severity_counts`, `findings`, `recommendations`

### 5. `db_<instance #>_sql2019_analyze_db_data_model`
- Category: `read_only_analysis`
- Purpose: Analyze logical data model quality using foreign-key graph extraction and circular dependency detection.
- Input:
  - `database_name` (str, required)
  - `schema_filter` (str, optional)
  - `max_edges` (int, optional, default 500, max 5000)
  - `actor` (str, optional)
- Output:
  - deterministic JSON report envelope
  - graph summary (`node_count`, `edge_count`, `circular_dependency_count`)
  - prioritized findings and recommendations

### 6. `db_<instance #>_sql2019_analyze_sec_config`
- Category: `read_only_analysis`
- Purpose: Assess database security/configuration posture (orphan users, elevated roles, backup recency, optional server-scope checks).
- Input:
  - `database_name` (str, required)
  - `include_server_scope` (bool, optional, default true)
  - `actor` (str, optional)
- Output:
  - deterministic JSON report envelope
  - security findings with redacted evidence rows

### 7. `db_<instance #>_sql2019_sessions_dashboard`
- Category: `interactive_dashboard`
- Purpose: Build session activity and lock-chain dashboard payload for FastMCP interactive app clients.
- Input:
  - `database_name` (str, optional, default `master`)
  - `lookback_minutes` (int, optional, default 15, max 1440)
  - `include_locks` (bool, optional, default true)
  - `actor` (str, optional)
- Output:
  - `content_type: text/html`
  - `html` dashboard fragment
  - `data` model with active sessions, lock chains, head blockers, and recommendations
