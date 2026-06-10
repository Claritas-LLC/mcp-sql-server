# MCP SQL Server — Demo Narration Script

A brief script for recording a video walkthrough of the MCP SQL Server dual-instance service.

Note: this is a presentation script, not the canonical tool contract. For authoritative runtime tool names and parameters, use [mcp-tool-catalog.md](mcp-tool-catalog.md). Tool names in this script reflect the actual runtime registration: 7 named-family tools (`db_primary_sql2019_*` / `db_secondary_sql2019_*`) and 9 numbered-family tools (`db_1_sql2019_*` / `db_2_sql2019_*`).

The demo databases are:
| Instance | Databases |
|----------|-----------|
| Instance 1 (primary / `1`) | General, US_RT_User_800, USGISPRO_800, US_UserData |
| Instance 2 (secondary / `2`) | ListGateway, PrizmPremier, US_Spatial_800, GeoGrid |

---

## 1. Introduction (approx. 30 sec)

"Welcome. Today I'm demonstrating the MCP SQL Server — a remote FastMCP service that exposes SQL Server 2019 diagnostics and analysis tools through the Model Context Protocol.

This server connects to two SQL Server 2019 instances — a primary (`gisdevsql01` at 10.125.1.7) and a secondary (`gisdevsql02` at 10.125.1.8) — and surfaces tools under two naming families: a named-instance family using `primary`/`secondary`, and a numbered-instance family using `1`/`2`. It's built with Python using FastMCP and FastAPI, running over HTTP at the `/mcp` endpoint. The architecture enforces a strong read-only posture with controlled-write guardrails, rate limiting, and comprehensive audit logging.

Key features include per-database context switching on every tool, connection pooling with per-instance isolation, and structured diagnostic reports with DBA-review disclaimers. Let me show you the key capabilities."

---

## 2. Service Health & Diagnostics (approx. 45 sec)

"I'll start by checking the service health endpoints. These are plain HTTP GET requests — no MCP client needed.

First, the root endpoint — this confirms the service is running and lists all registered tools.

> *[Show `GET /` — response shows service status and tool list]*

Next, the health diagnostics endpoint — this tells us the connectivity state of each SQL instance, the pool sizes, and the overall service health.

> *[Show `GET /diagnostics/health` — response shows per-instance status]*

The security diagnostics endpoint shows the authentication mode, the required authorization scopes, and the group-to-privilege mapping.

> *[Show `GET /diagnostics/security` — response shows auth config and tool inventory]*

And the pool diagnostics endpoint gives us per-instance connection pool metrics — how many connections are available, in use, created, reused, and discarded.

> *[Show `GET /diagnostics/pool` — response shows pool state per instance]*

These endpoints are invaluable for operational monitoring and troubleshooting."

---

## 3. Top Queries & Top Statements (approx. 50 sec)

"Now let me switch to an MCP client and call the actual tools. I'll demonstrate two related tools.

First, the **top queries report** — this returns the most expensive cached queries from the plan cache, sorted by total worker time. It's great for quick performance triage.

> *[Call `db_primary_sql2019_top_queries_report(limit=10)`]*

You can optionally pass a `database_name` to scope results to queries cached from a specific database context.

Next, the **top statements** tool — this is a deeper analysis that pulls from Query Store by default, looking at execution counts, average duration, and plan-level metrics over a configurable lookback window. Note that `top_statements` is a numbered-family tool, so I use `db_1_sql2019` rather than `db_primary_sql2019`.

> *[Call `db_1_sql2019_top_statements(database_name="USGISPRO_800", top_n=10, lookback_minutes=1440)`]*

The output includes the data source — Query Store or DMV fallback — plus prescriptive recommendations for indexing, query rewrites, and partitioning. When Query Store isn't available on the target database, it gracefully falls back to DMV data with a clear `data_source` indicator.

Both tools are also available on Instance 2 — `db_2_sql2019_top_statements` for the numbered family, or `db_secondary_sql2019_top_queries_report` for the named family."

---

## 4. Active Sessions Report (approx. 35 sec)

"Next, the **active sessions report**. This shows who's connected, what they're running, and what state their requests are in.

> *[Call `db_secondary_sql2019_active_sessions_report(limit=10)`]*

The output includes session IDs, login names, host names, program names, request commands, wait types, wait times, and CPU time. You can target a specific database context with the `database_name` parameter, or omit it to query at the instance level. This is the go-to tool for real-time concurrency monitoring and blocking chain investigation."

---

## 5. Blocking Report (approx. 30 sec)

"The **block report** identifies active blocking chains in real time.

> *[Call `db_primary_sql2019_block_report(database_name="USGISPRO_800")`]*

It returns the top blocking sessions with their SQL text, wait types, and wait durations. Combine this with the active sessions report for a full picture of contention. The `database_name` parameter lets you filter to blocking chains within a specific database. On Instance 2, I'd call `db_secondary_sql2019_block_report(database_name="PrizmPremier")`."

---

## 6. Index Health Report (approx. 35 sec)

"The **index health report** summarizes index usage statistics across tables.

> *[Call `db_primary_sql2019_index_health_report(limit=20, database_name="US_RT_User_800")`]*

You get table names, index names, type descriptors, and usage counters — seeks, scans, lookups, and updates. This directly informs your index rebuild and reorganize maintenance windows. Results are database-scoped when you provide a `database_name`, or instance-wide when you omit it. On Instance 2, `db_secondary_sql2019_index_health_report(limit=20, database_name="US_Spatial_800")`."

---

## 7. Table Health Analysis (approx. 50 sec)

"This is one of the more powerful analysis tools — **analyze table health**. Note that the analysis tools live in the numbered-instance family.

It performs a deep dive on a specific database, examining table sizes, index fragmentation, missing primary keys, stale or never-updated statistics, low-sampled statistics, heap tables, and duplicate key candidates. It even supports optional histogram skew analysis for detecting data distribution issues.

> *[Call `db_1_sql2019_analyze_tab_health(database_name="US_RT_User_800", top_n=10, include_histogram_analysis=false)]*]

The report comes back as a deterministic JSON envelope with a summary, severity counts, prioritized findings, and actionable recommendations. Each recommendation includes a DBA review disclaimer — the tool advises, but a human DBA approves before any changes are applied. On Instance 2: `db_2_sql2019_analyze_tab_health(database_name="ListGateway", top_n=10)`."

---

## 8. Data Model Analysis (approx. 30 sec)

"The **analyze data model** tool — another numbered-family analysis tool — extracts the foreign-key graph from a database and detects circular dependencies — essential for understanding referential integrity and refactoring risk.

> *[Call `db_1_sql2019_analyze_db_data_model(database_name="US_UserData")`]*

It also flags soft-delete columns, data type inconsistencies, and potential normalization issues. The result includes a structured model graph that helps you visualize table relationships and identify risky schema patterns. On Instance 2: `db_2_sql2019_analyze_db_data_model(database_name="PrizmPremier")`."

---

## 9. Security Configuration Analysis (approx. 35 sec)

"The **analyze security configuration** tool performs a security posture assessment on a database.

> *[Call `db_1_sql2019_analyze_sec_config(database_name="USGISPRO_800", include_server_scope=true)]*]

It checks for orphaned database users, elevated role memberships, guest user access, and backup recency. When `include_server_scope` is enabled, it also checks whether `xp_cmdshell` is enabled at the server level. Results come back as the same structured report envelope with findings, severity counts, and prioritized recommendations. On Instance 2: `db_2_sql2019_analyze_sec_config(database_name="US_Spatial_800", include_server_scope=true)`."

---

## 10. Sessions Dashboard (approx. 40 sec)

"The **sessions dashboard** is an interactive tool that builds a live HTML dashboard of session activity, lock chains, and blocking diagnostics.

> *[Call `db_1_sql2019_sessions_dashboard(database_name="General", lookback_minutes=15, include_locks=true)]*]

The response includes an HTML fragment with a data model containing active sessions, lock chains, head blockers, and prescriptive recommendations. This can be rendered directly in MCP-compatible clients for a visual diagnostics experience. The same dashboard data is also accessible via a dedicated HTTP refresh endpoint for auto-updating views. On Instance 2: `db_2_sql2019_sessions_dashboard(database_name="GeoGrid", lookback_minutes=15, include_locks=true)`."

---

## 11. Direct SQL Execution (approx. 30 sec)

"Beyond the structured analysis tools, the server also supports direct read-only SQL execution with full security enforcement.

The **select** tool — a named-family tool — lets you run arbitrary read queries against an instance, with SQL denylist enforcement blocking dangerous statements.

> *[Call `db_primary_sql2019_select(sql="SELECT TOP 5 name, create_date FROM sys.tables ORDER BY create_date DESC", database_name="US_UserData")`]*

The **execute query** tool — a numbered-family tool — runs SQL in an explicit database context and supports COMPACT and FULL view modes.

> *[Call `db_1_sql2019_execute_query(database_name="USGISPRO_800", sql_statement="SELECT TOP 5 name, type_desc FROM sys.objects WHERE type_desc='USER_TABLE' ORDER BY name", view_mode="COMPACT")`]*

Both tools pass through write-guard validation, rate limiting, and audit logging before execution."

---

## 12. Controlled Write — Stored Procedure Execution (approx. 35 sec)

"While the server is read-only by default, it does support **controlled-write** through allowlisted stored procedure execution. Procedures must be explicitly listed in `policy/sql-allowlist.yaml` — `sp_who` and other ad-hoc system procedures are not permitted.

> *[Call `db_primary_sql2019_exec_proc(proc_name="USGISPRO_800.dbo.usp_CaptureProcOutput", params=["sp_who",""], database_name="USGISPRO_800")`]*

Write access is enforced in layers: the tool must be in the `allowed_write_tools` list, the instance must have it enabled, the procedure must be on the procedure allowlist, and the SQL login must have EXECUTE permissions. The `database_name` parameter lets you target a specific database context for database-scoped procedures. This deny-by-default approach ensures no accidental writes happen without explicit policy approval."

---

## 13. Rate Limiting & Security (approx. 30 sec)

"Every tool call passes through several enforcement layers:

- **Rate limiting** — per-actor and global limits, configurable in `config/rate-limit.yaml`, backed by Redis for distributed deployments.
- **Session management** — 100 concurrent sessions per actor, 5-minute inactivity timeout. Sessions are keyed on the MCP session ID, so all tool calls within a single MCP connection share one slot.
- **SQL denylist** — dangerous statements like `DROP`, `TRUNCATE`, `ALTER`, and `xp_cmdshell` are blocked before execution.
- **Audit logging** — every request is logged with actor identity, tool name, decision, and latency.
- **Sensitive field redaction** — login names and host names are redacted in diagnostic outputs.
- **Connection pool isolation** — per-instance pools with discard-on-error protection ensure one session's failure never corrupts the pool for other sessions.

This makes the server safe for exposing to automated agents and LLM-based tool-calling systems."

---

## 14. Database Context Switching (approx. 25 sec)

"One important design feature: every tool that touches user databases supports a `database_name` parameter for explicit context switching.

When you provide a `database_name`, the server creates a dedicated connection to that database — isolated from the shared connection pool. When you omit it, the tool uses the pooled connection to the instance's default database. This two-path design ensures that cross-database queries are always correctly scoped while keeping the pool healthy for concurrent access.

This is especially critical for Query Store-backed tools like `db_1_sql2019_top_statements`, where Query Store views are database-scoped and connecting to the wrong database would return the wrong data."

---

## 15. Closing (approx. 20 sec)

"That covers the main tool set. To recap, this MCP SQL Server provides:

- **Read and analysis tools** — top queries, active sessions, blocking, index health, table health, top statements, and security/data-model analysis
- **Direct SQL execution** with write-guard enforcement and execution plan support
- **An interactive sessions dashboard** for visual diagnostics
- **Controlled-write procedure execution** secured by a multi-layer policy system
- **Per-database context switching** on every tool
- **Full diagnostics endpoints** for operational monitoring

All tools are available on both the primary and secondary SQL Server 2019 instances. The full source code, configuration guides, and deployment runbooks are in the repository. Thanks for watching."

---

## Quick Reference — Tool Inventory

### Named-Instance Family (`primary` / `secondary`)

| Tool | Category | Key Parameters |
|------|----------|---------------|
| `db_<inst>_sql2019_select` | read_only | `sql`, `database_name`, `actor` |
| `db_<inst>_sql2019_exec_proc` | controlled_write | `proc_name`, `params`, `database_name`, `actor` |
| `db_<inst>_sql2019_latency_report` | read_only | `actor` |
| `db_<inst>_sql2019_block_report` | read_only | `database_name`, `actor` |
| `db_<inst>_sql2019_top_queries_report` | read_only | `limit`, `database_name`, `actor` |
| `db_<inst>_sql2019_active_sessions_report` | read_only | `limit`, `database_name`, `actor` |
| `db_<inst>_sql2019_index_health_report` | read_only | `limit`, `database_name`, `actor` |

Where `<inst>` is `primary` or `secondary`.

### Numbered-Instance Family (`1` / `2`)

| Tool | Category | Key Parameters |
|------|----------|---------------|
| `db_<n>_sql2019_ping` | read_only | `actor` |
| `db_<n>_sql2019_list_tools` | read_only | `actor` |
| `db_<n>_sql2019_list_object` | read_only | `database_name`, `object_type`, `actor` |
| `db_<n>_sql2019_execute_query` | read_only | `database_name`, `sql_statement`, `view_mode`, `actor` |
| `db_<n>_sql2019_analyze_tab_health` | read_only_analysis | `database_name`, `top_n`, `include_histogram_analysis`, `include_statistics`, `actor` |
| `db_<n>_sql2019_analyze_db_data_model` | read_only_analysis | `database_name`, `schema_filter`, `actor` |
| `db_<n>_sql2019_analyze_sec_config` | read_only_analysis | `database_name`, `include_server_scope`, `actor` |
| `db_<n>_sql2019_sessions_dashboard` | interactive_dashboard | `database_name`, `lookback_minutes`, `include_locks`, `actor` |
| `db_<n>_sql2019_top_statements` | read_only_analysis | `database_name`, `top_n`, `lookback_minutes`, `view_mode`, `actor` |

Where `<n>` is `1` or `2`.
