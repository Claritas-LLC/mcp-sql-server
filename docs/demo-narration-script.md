# MCP SQL Server — Demo Narration Script

A brief script for recording a video walkthrough of the MCP SQL Server dual-instance service.

Note: this is a presentation script, not the canonical tool contract. For authoritative runtime tool names and parameters, use [mcp-tool-catalog.md](mcp-tool-catalog.md).

---

## 1. Introduction (approx. 30 sec)

"Welcome. Today I'm demonstrating the MCP SQL Server — a remote FastMCP service that exposes SQL Server 2019 diagnostics and analysis tools through the Model Context Protocol.

This server connects to two SQL Server 2019 instances — a primary and a secondary — and surfaces every tool twice, once per instance. It's built with Python using FastMCP and FastAPI, running over HTTP at the `/mcp` endpoint. The architecture enforces a strong read-only posture with controlled-write guardrails, rate limiting, and comprehensive audit logging.

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

Next, the **top statements** tool — this is a deeper analysis that pulls from Query Store by default, looking at execution counts, average duration, and plan-level metrics over a configurable lookback window.

> *[Call `db_primary_sql2019_top_statements(database_name="AdventureWorks", top_n=10, lookback_minutes=1440)`]*

The output includes the data source — Query Store or DMV fallback — plus prescriptive recommendations for indexing, query rewrites, and partitioning. When Query Store isn't available on the target database, it gracefully falls back to DMV data with a clear `data_source` indicator.

Both tools are also available on the secondary instance — just swap `primary` for `secondary` in the tool name."

---

## 4. Active Sessions Report (approx. 35 sec)

"Next, the **active sessions report**. This shows who's connected, what they're running, and what state their requests are in.

> *[Call `db_primary_sql2019_active_sessions_report(limit=50, database_name="AdventureWorks")`]*

The output includes session IDs, login names, host names, program names, request commands, wait types, wait times, and CPU time. You can target a specific database context with the `database_name` parameter, or omit it to query at the instance level. This is the go-to tool for real-time concurrency monitoring and blocking chain investigation."

---

## 5. Blocking Report (approx. 30 sec)

"The **block report** identifies active blocking chains in real time.

> *[Call `db_primary_sql2019_block_report(database_name="AdventureWorks")`]*

It returns the top blocking sessions with their SQL text, wait types, and wait durations. Combine this with the active sessions report for a full picture of contention. The `database_name` parameter lets you filter to blocking chains within a specific database."

---

## 6. Index Health Report (approx. 35 sec)

"The **index health report** summarizes index usage statistics across tables.

> *[Call `db_primary_sql2019_index_health_report(limit=50, database_name="AdventureWorks")`]*

You get table names, index names, type descriptors, and usage counters — seeks, scans, lookups, and updates. This directly informs your index rebuild and reorganize maintenance windows. Results are database-scoped when you provide a `database_name`, or instance-wide when you omit it."

---

## 7. Table Health Analysis (approx. 50 sec)

"This is one of the more powerful analysis tools — **analyze table health**.

It performs a deep dive on a specific database, examining table sizes, index fragmentation, missing primary keys, stale or never-updated statistics, low-sampled statistics, heap tables, and duplicate key candidates. It even supports optional histogram skew analysis for detecting data distribution issues.

> *[Call `db_primary_sql2019_analyze_tab_health(database_name="AdventureWorks", top_n=10, include_histogram_analysis=true)]*]

The report comes back as a deterministic JSON envelope with a summary, severity counts, prioritized findings, and actionable recommendations. Each recommendation includes a DBA review disclaimer — the tool advises, but a human DBA approves before any changes are applied."

---

## 8. Data Model Analysis (approx. 30 sec)

"The **analyze data model** tool extracts the foreign-key graph from a database and detects circular dependencies — essential for understanding referential integrity and refactoring risk.

> *[Call `db_primary_sql2019_analyze_db_data_model(database_name="AdventureWorks")`]*

It also flags soft-delete columns, data type inconsistencies, and potential normalization issues. The result includes a structured model graph that helps you visualize table relationships and identify risky schema patterns."

---

## 9. Security Configuration Analysis (approx. 35 sec)

"The **analyze security configuration** tool performs a security posture assessment on a database.

> *[Call `db_primary_sql2019_analyze_sec_config(database_name="AdventureWorks", include_server_scope=true)]*]

It checks for orphaned database users, elevated role memberships, guest user access, and backup recency. When `include_server_scope` is enabled, it also checks whether `xp_cmdshell` is enabled at the server level. Results come back as the same structured report envelope with findings, severity counts, and prioritized recommendations."

---

## 10. Sessions Dashboard (approx. 40 sec)

"The **sessions dashboard** is an interactive tool that builds a live HTML dashboard of session activity, lock chains, and blocking diagnostics.

> *[Call `db_primary_sql2019_sessions_dashboard(database_name="master", lookback_minutes=15, include_locks=true)]*]

The response includes an HTML fragment with a data model containing active sessions, lock chains, head blockers, and prescriptive recommendations. This can be rendered directly in MCP-compatible clients for a visual diagnostics experience. The same dashboard data is also accessible via a dedicated HTTP refresh endpoint for auto-updating views."

---

## 11. Direct SQL Execution (approx. 30 sec)

"Beyond the structured analysis tools, the server also supports direct read-only SQL execution with full security enforcement.

The **select** tool lets you run arbitrary read queries against an instance, with SQL denylist enforcement blocking dangerous statements.

> *[Call `db_primary_sql2019_select(sql="SELECT TOP 10 * FROM sys.tables", database_name="AdventureWorks")`]*

The **execute query** tool goes further — it runs SQL in an explicit database context and supports a FULL view mode that appends an estimated execution plan.

> *[Call `db_primary_sql2019_execute_query(database_name="AdventureWorks", sql_statement="SELECT COUNT(*) FROM sys.objects", view_mode="FULL")`]*

Both tools pass through write-guard validation, rate limiting, and audit logging before execution."

---

## 12. Controlled Write — Stored Procedure Execution (approx. 35 sec)

"While the server is read-only by default, it does support **controlled-write** through allowlisted stored procedure execution.

> *[Call `db_primary_sql2019_exec_proc(proc_name="sp_who", params=[], database_name="master")`]*

Write access is enforced in layers: the tool must be in the `allowed_write_tools` list, the instance must have it enabled, the procedure must be on the procedure allowlist, and the SQL login must have EXECUTE permissions. The `database_name` parameter lets you target a specific database context for database-scoped procedures. This deny-by-default approach ensures no accidental writes happen without explicit policy approval."

---

## 13. Rate Limiting & Security (approx. 30 sec)

"Every tool call passes through several enforcement layers:

- **Rate limiting** — per-actor and global limits, configurable in `config/rate-limit.yaml`, backed by either local memory or Redis for distributed deployments.
- **Session management** — concurrent session limits with inactivity timeouts.
- **SQL denylist** — dangerous statements like `DROP`, `TRUNCATE`, `ALTER`, and `xp_cmdshell` are blocked before execution.
- **Audit logging** — every request is logged with actor identity, tool name, decision, and latency.
- **Sensitive field redaction** — login names and other identifying fields are redacted in diagnostic outputs.
- **Connection pool isolation** — per-instance pools with discard-on-error protection ensure one session's failure never corrupts the pool for other sessions.

This makes the server safe for exposing to automated agents and LLM-based tool-calling systems."

---

## 14. Database Context Switching (approx. 25 sec)

"One important design feature: every tool that touches user databases supports a `database_name` parameter for explicit context switching.

When you provide a `database_name`, the server creates a dedicated connection to that database — isolated from the shared connection pool. When you omit it, the tool uses the pooled connection to the instance's default database. This two-path design ensures that cross-database queries are always correctly scoped while keeping the pool healthy for concurrent access.

This is especially critical for Query Store-backed tools like `top_statements`, where Query Store views are database-scoped and connecting to the wrong database would return the wrong data."

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

| Tool | Category | Key Parameters |
|------|----------|---------------|
| `db_<inst>_sql2019_select` | read_only | `sql`, `database_name`, `actor` |
| `db_<inst>_sql2019_execute_query` | read_only | `database_name`, `sql_statement`, `view_mode`, `actor` |
| `db_<inst>_sql2019_top_queries_report` | read_only | `limit`, `database_name`, `actor` |
| `db_<inst>_sql2019_active_sessions_report` | read_only | `limit`, `database_name`, `actor` |
| `db_<inst>_sql2019_block_report` | read_only | `database_name`, `actor` |
| `db_<inst>_sql2019_index_health_report` | read_only | `limit`, `database_name`, `actor` |
| `db_<inst>_sql2019_analyze_tab_health` | read_only_analysis | `database_name`, `top_n`, `include_histogram_analysis`, `actor` |
| `db_<inst>_sql2019_top_statements` | read_only_analysis | `database_name`, `top_n`, `lookback_minutes`, `view_mode`, `actor` |
| `db_<inst>_sql2019_analyze_db_data_model` | read_only_analysis | `database_name`, `schema_filter`, `actor` |
| `db_<inst>_sql2019_analyze_sec_config` | read_only_analysis | `database_name`, `include_server_scope`, `actor` |
| `db_<inst>_sql2019_sessions_dashboard` | interactive_dashboard | `database_name`, `lookback_minutes`, `include_locks`, `actor` |
| `db_<inst>_sql2019_list_object` | read_only | `database_name`, `object_type`, `actor` |
| `db_<inst>_sql2019_ping` | read_only | `actor` |
| `db_<inst>_sql2019_list_tools` | read_only | `actor` |
| `db_<inst>_sql2019_exec_proc` | controlled_write | `proc_name`, `params`, `database_name`, `actor` |

Where `<inst>` is `primary` or `secondary` for the named-instance family, or `1` or `2` for the numbered-instance family.
