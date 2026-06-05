# MCP SQL Server — Demo Narration Script

A brief script for recording a video walkthrough of the MCP SQL Server dual-instance service.

Note: this is a presentation script, not the canonical tool contract. For authoritative runtime tool names and parameters, use [mcp-tool-catalog.md](mcp-tool-catalog.md).

---

## 1. Introduction (approx. 30 sec)

"Welcome. Today I'm demonstrating the MCP SQL Server — a remote FastMCP service that exposes SQL Server 2019 diagnostics and analysis tools through the Model Context Protocol.

This server connects to two SQL Server 2019 instances — a primary and a secondary — and surfaces every tool twice, once per instance. It's built with Python using FastMCP and FastAPI, running over HTTP at the `/mcp` endpoint. The architecture enforces a strong read-only posture with controlled-write guardrails, rate limiting, and comprehensive audit logging.

Let me show you the key capabilities."

---

## 2. Service Health & Diagnostics (approx. 45 sec)

"I'll start by checking the service health endpoints. These are plain HTTP GET requests — no MCP client needed.

First, the root endpoint — this confirms the service is running and lists all registered tools.

> *[Show `GET /` — response shows service status and tool list]*

Next, the health diagnostics endpoint — this tells us the connectivity state of each SQL instance, the pool sizes, and the overall service health.

> *[Show `GET /diagnostics/health` — response shows per-instance status]*

The security diagnostics endpoint shows the authentication mode, the required authorization scopes, and the group-to-privilege mapping.

> *[Show `GET /diagnostics/security` — response shows auth config and tool inventory]*

And the pool diagnostics endpoint gives us per-instance connection pool metrics — how many connections are available, in use, created, and reused.

> *[Show `GET /diagnostics/pool` — response shows pool state per instance]*

These endpoints are invaluable for operational monitoring and troubleshooting."

---

## 3. Top Queries Report (approx. 40 sec)

"Now let me switch to an MCP client and call the actual tools. I'll start with the **top queries report**.

This tool returns the top CPU-consuming and longest-running cached queries from the plan cache. It helps with performance tuning triage.

> *[Call `db_primary_sql2019_top_queries_report(datalimit=10)`]*

The response includes the instance name, the tool name, a row count, and the result rows — each containing the query text, execution stats, and duration metrics. You can optionally pass an `actor` parameter for audit traceability.

The same tool is also available on the secondary instance — just swap `primary` for `secondary` in the tool name."

---

## 4. Active Sessions Report (approx. 35 sec)

"Next, the **active sessions report**. This shows who's connected, what they're running, and what state their requests are in.

> *[Call `db_primary_sql2019_active_sessions_report(limit=20)`]*

The output includes session IDs, login names, host names, the current SQL text being executed, wait types, and blocking information. This is the go-to tool for real-time concurrency monitoring and blocking chain investigation."

---

## 5. Index Health Report (approx. 35 sec)

"The **index health report** summarizes fragmentation levels, index usage statistics, and maintenance recommendations.

> *[Call `db_primary_sql2019_index_health_report(limit=20)`]*

You get row counts, index size, fragmentation percentages, and last-accessed timestamps. This directly informs your index rebuild and reorganize maintenance windows."

---

## 6. Table Health Analysis (approx. 50 sec)

"This is one of the more powerful analysis tools — **analyze table health**.

It performs a deep dive on a specific database, examining table and index health, statistics freshness, missing primary keys, stale or never-updated statistics, and low-sampled statistics. It even supports optional histogram skew analysis.

> *[Call `db_1_sql2019_analyze_tab_health(database_name="AdventureWorks", top_n=10)`]*

The report comes back as a deterministic JSON envelope with a summary, severity counts, prioritized findings, and actionable recommendations. Each recommendation includes a DBA review disclaimer — the tool advises, but a human DBA approves before any changes are applied."

---

## 7. Top Statements Analysis (approx. 40 sec)

"The **top statements** tool analyzes the longest-running SQL queries in a database context. It pulls data from Query Store by default, and gracefully falls back to DMV data if Query Store views aren't available.

> *[Call `db_1_sql2019_top_statements(database_name="AdventureWorks", top_n=10, lookback_minutes=1440)`]*

The output tells you which data source was used — Query Store or DMV fallback — and includes execution counts, average duration, and prescriptive recommendations for index strategy, query rewrites, and partitioning."

---

## 8. Data Model & Security Analysis (approx. 45 sec)

"There are two more analysis tools worth highlighting.

**Analyze data model** extracts the foreign-key graph from a database and detects circular dependencies — essential for understanding referential integrity and refactoring risk.

> *[Call `db_1_sql2019_analyze_db_data_model(database_name="AdventureWorks")`]*

**Analyze security configuration** checks for orphaned users, elevated database roles, and backup recency — a quick security posture snapshot.

> *[Call `db_1_sql2019_analyze_sec_config(database_name="AdventureWorks")`]*

Both return the same structured report envelope with findings, severity counts, and DBA-review-disclaimered recommendations."

---

## 9. Sessions Dashboard (approx. 40 sec)

"The **sessions dashboard** is an interactive tool that builds a live HTML dashboard of session activity, lock chains, and blocking diagnostics.

> *[Call `db_1_sql2019_sessions_dashboard(database_name="master", lookback_minutes=15)`]*

The response includes an HTML fragment with a data model containing active sessions, lock chains, head blockers, and recommendations. This can be rendered directly in MCP-compatible clients for a visual diagnostics experience. The same dashboard data is also accessible via a dedicated HTTP refresh endpoint."

---

## 10. Controlled Write — Stored Procedure Execution (approx. 35 sec)

"While the server is read-only by default, it does support **controlled-write** through allowlisted stored procedure execution.

> *[Call `db_primary_sql2019_exec_proc(proc_name="sp_who", params=[])`]*

Write access is enforced in layers: the tool must be in the `allowed_write_tools` list, the instance must have it enabled, the procedure must be on the procedure allowlist, and the SQL login must have EXECUTE permissions. This deny-by-default approach ensures no accidental writes happen without explicit policy approval."

---

## 11. Rate Limiting & Security (approx. 30 sec)

"Every tool call passes through several enforcement layers:

- **Rate limiting** — per-actor and global limits, configurable in `config/rate-limit.yaml`, backed by either local memory or Redis for distributed deployments.
- **Session management** — concurrent session limits with inactivity timeouts.
- **SQL denylist** — dangerous statements like `DROP`, `TRUNCATE`, `ALTER`, and `xp_cmdshell` are blocked before execution.
- **Audit logging** — every request is logged with actor identity, tool name, decision, and timing.
- **Sensitive field redaction** — login names and other identifying fields are redacted in diagnostic outputs.

This makes the server safe for exposing to automated agents and LLM-based tool-calling systems."

---

## 12. Closing (approx. 20 sec)

"That covers the main tool set. To recap, this MCP SQL Server provides:

- **Read and analysis tools** — top queries, active sessions, index health, table health, top statements, and security/data-model analysis
- **An interactive sessions dashboard** for visual diagnostics
- **Controlled-write procedure execution** secured by a multi-layer policy system
- **Full diagnostics endpoints** for operational monitoring

All tools are available on both the primary and secondary SQL Server 2019 instances. The full source code, configuration guides, and deployment runbooks are in the repository. Thanks for watching."

---

## Quick Reference — Tool Inventory

| Tool | Category | Description |
|------|----------|-------------|
| `db_<inst>_sql2019_top_queries_report` | read_only | Top CPU-consuming cached queries |
| `db_<inst>_sql2019_active_sessions_report` | read_only | Active user sessions and request state |
| `db_<inst>_sql2019_index_health_report` | read_only | Index fragmentation and usage |
| `db_<inst>_sql2019_analyze_tab_health` | read_only_analysis | Deep table/index/statistics health analysis |
| `db_<inst>_sql2019_top_statements` | read_only_analysis | Longest-running queries via Query Store / DMV |
| `db_<inst>_sql2019_analyze_db_data_model` | read_only_analysis | FK graph and circular dependency detection |
| `db_<inst>_sql2019_analyze_sec_config` | read_only_analysis | Security posture (orphan users, roles, backups) |
| `db_<inst>_sql2019_sessions_dashboard` | interactive_dashboard | Live HTML sessions & lock-chain dashboard |
| `db_<inst>_sql2019_exec_proc` | controlled_write | Allowlisted stored procedure execution |
