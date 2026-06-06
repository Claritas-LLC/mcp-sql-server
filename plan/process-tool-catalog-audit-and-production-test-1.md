---
goal: Audit and update mcp-tool-catalog.md and create production test verification document
version: 1.0
date_created: 2026-06-06
last_updated: 2026-06-06
owner: MCP SQL Server Team
status: In Progress
tags: [audit, documentation, testing, production-readiness, tool-catalog]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-planned-blue)

This plan covers two related activities: (1) auditing and correcting docs/mcp-tool-catalog.md against the actual source code in src/tools/sql_tools.py and src/tools/tool_registry.py, and (2) creating a production test verification document (docs/production-tool-verification.md) as a child of docs/demo-narration-script.md that tests every registered MCP tool against Instance 1 (10.125.1.7) and Instance 2 (10.125.1.8) using specified databases and records actual output for production rollout sign-off.

## 1. Requirements & Constraints

- **REQ-001**: mcp-tool-catalog.md must reflect the actual tool registry — only tools decorated with @mcp.tool and callable at runtime
- **REQ-002**: Production test doc must test every callable tool against both instances with at least one database from each instance's specified list
- **REQ-003**: Named-instance family tools use primary/secondary suffix; numbered-instance family uses 1/2 suffix
- **REQ-004**: Instance 1 databases: General, US_RT_User_800, USGISPRO_800, US_UserData
- **REQ-005**: Instance 2 databases: ListGateway, PrizmPremier, US_Spatial_800, GeoGrid
- **REQ-006**: Test results must include actual output summaries (row counts, key fields) to verify correctness
- **REQ-007**: The test doc must serve as an alternative to demo-narration-script.md suitable for production rollout
- **CON-001**: Server must be running and accessible (Docker container mcp-sqlserver on port 8085, or local python src/server.py on port 8080)
- **CON-002**: Both SQL instances must be reachable from the server's network
- **GUD-001**: Follow the production test narrative style — factual, traceable, reproducible

## 2. Implementation Steps

### Implementation Phase 1: Audit mcp-tool-catalog.md

- GOAL-001: Identify and fix all discrepancies between docs/mcp-tool-catalog.md and the actual source code

| Task     | Description           | Completed | Date       |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Read src/tools/tool_registry.py — confirm generate_tool_specs() produces 12 ToolSpec entries per instance: select, exec_proc, latency_report, block_report, top_queries_report, active_sessions_report, index_health_report, analyze_tab_health, analyze_db_data_model, analyze_sec_config, sessions_dashboard, top_statements | | |
| TASK-002 | Read src/tools/sql_tools.py register_sql_tools() — confirm which tools actually receive @mcp.tool decorators in the named-instance family loop (lines 1126-1640): only select, exec_proc, latency_report, block_report, top_queries_report, active_sessions_report, index_health_report are decorated | | |
| TASK-003 | Read src/tools/sql_tools.py numbered-instance loop (lines 1770-3800+) — confirm all 9 tools decorated: ping, list_tools, list_object, execute_query, analyze_tab_health, analyze_db_data_model, analyze_sec_config, sessions_dashboard, top_statements | | |
| TASK-004 | Identify catalog error #1: named-instance family section lists analyze_tab_health, analyze_db_data_model, analyze_sec_config, sessions_dashboard, top_statements — but these are NOT callable as db_primary_sql2019_analyze_*. They are only callable as db_1_sql2019_analyze_* and db_2_sql2019_analyze_* | | |
| TASK-005 | Identify catalog error #2: catalog omits database_name parameter from named-family tools (block_report, top_queries_report, active_sessions_report, index_health_report). Source code shows database_name: str = "" with non-pooled path when set | | |
| TASK-006 | Identify catalog error #3: catalog omits database_name parameter from numbered-family sessions_dashboard. Source code has it as optional parameter | | |
| TASK-007 | Identify catalog error #4: catalog lists select under named family without database_name parameter. Source code has database_name: str = "" | | |
| TASK-008 | Identify catalog error #5: catalog numbered family lists nalyze_tab_health without include_statistics parameter. Source code has include_statistics: bool = True | | |
| TASK-009 | Rewrite docs/mcp-tool-catalog.md to reflect actual tool inventory with correct parameter lists, removing incorrectly-listed named-family analysis tools and adding them only to numbered-family section | | |
| TASK-010 | Add cross-reference table mapping named-family tools to their numbered-family equivalents where applicable (e.g., db_primary_sql2019_select ↔ db_1_sql2019_select does NOT exist — select is named-only; db_primary_sql2019_analyze_tab_health does NOT exist — analyze is numbered-only) | | |

### Implementation Phase 2: Create Production Test Document

- GOAL-002: Create docs/production-tool-verification.md with test results for all tools against both instances

| Task     | Description           | Completed | Date       |
| -------- | --------------------- | --------- | ---------- |
| TASK-011 | Create docs/production-tool-verification.md with front matter, introduction explaining purpose (production rollout verification), and environment details (server endpoint, instances, databases) | | |
| TASK-012 | Section: Named-Instance Family — Instance 1 (primary). Test all 7 tools: select (with US_UserData), exec_proc (sp_who), latency_report, block_report (with USGISPRO_800), top_queries_report (limit=10), active_sessions_report (limit=10), index_health_report (with US_RT_User_800, limit=20). Record HTTP response summaries including row_count and key output fields | | |
| TASK-013 | Section: Named-Instance Family — Instance 2 (secondary). Test all 7 tools: select (with GeoGrid), exec_proc (sp_who), latency_report, block_report (with PrizmPremier), top_queries_report (limit=10), active_sessions_report (limit=10), index_health_report (with ListGateway, limit=20). Record HTTP response summaries | | |
| TASK-014 | Section: Numbered-Instance Family — Instance 1. Test all 9 tools: ping, list_tools, list_object (General, table), execute_query (USGISPRO_800, SELECT TOP 5), analyze_tab_health (US_RT_User_800, top_n=10), analyze_db_data_model (US_UserData), analyze_sec_config (USGISPRO_800), sessions_dashboard (General, lookback_minutes=15), top_statements (USGISPRO_800, top_n=10). Record structured output summaries | | |
| TASK-015 | Section: Numbered-Instance Family — Instance 2. Test all 9 tools: ping, list_tools, list_object (ListGateway, table), execute_query (PrizmPremier, SELECT TOP 5), analyze_tab_health (ListGateway, top_n=10), analyze_db_data_model (PrizmPremier), analyze_sec_config (US_Spatial_800), sessions_dashboard (GeoGrid, lookback_minutes=15), top_statements (PrizmPremier, top_n=10). Record structured output summaries | | |
| TASK-016 | Section: Cross-Instance Consistency Checks. Verify ping returns ccessible: true for both instances. Verify list_tools returns identical tool count for both instances. Verify system dates are within reasonable skew | | |
| TASK-017 | Section: Error Handling Verification. Test invalid database_name on select (should return SQL error, not crash). Test missing required parameter on analyze_tab_health (should return validation error). Test write-denied SQL via select (should return write guard denial) | | |
| TASK-018 | Section: Summary & Sign-Off Checklist. Create table of all 32 tool-instance combinations with pass/fail status, row counts, and notes. Add production readiness checklist (all tools respond, errors are deterministic, sensitive fields redacted, audit logs written) | | |

### Implementation Phase 3: Final Validation

- GOAL-003: Commit changes and validate documentation consistency

| Task     | Description           | Completed | Date       |
| -------- | --------------------- | --------- | ---------- |
| TASK-019 | Run 
uff check . to ensure no lint errors introduced | | |
| TASK-020 | Cross-reference docs/production-tool-verification.md tool inventory against docs/mcp-tool-catalog.md to ensure consistency | | |
| TASK-021 | Commit both files with descriptive message: "docs: audit mcp-tool-catalog.md and add production tool verification doc" | | |

## 3. Alternatives

- **ALT-001**: Register named-family analysis tools (db_primary_sql2019_analyze_*) — would require adding @mcp.tool decorators for analyze_* tools in the named-instance loop. Rejected for this plan: catalog should reflect current state, not desired state
- **ALT-002**: Test via curl only (no structured doc) — rejected because a formal signed-off document is needed for production rollout

## 4. Dependencies

- **DEP-001**: Docker container mcp-sqlserver running on port 8085 with Redis connectivity (mcp-net shared network)
- **DEP-002**: Both SQL Server 2019 instances (10.125.1.7 and 10.125.1.8) accessible
- **DEP-003**: Specified databases must exist on the target instances

## 5. Files

- **FILE-001**: docs/mcp-tool-catalog.md — will be rewritten with corrected tool inventory and parameter lists
- **FILE-002**: docs/production-tool-verification.md — new file, child of demo-narration-script.md
- **FILE-003**: src/tools/sql_tools.py — read-only reference for audit
- **FILE-004**: src/tools/tool_registry.py — read-only reference for tool spec generation

## 6. Testing

- **TEST-001**: Verify every tool listed in updated mcp-tool-catalog.md matches an @mcp.tool-decorated function
- **TEST-002**: Verify no tool in production-tool-verification.md references a non-existent tool name
- **TEST-003**: Verify all 32 tool-instance-database combinations produce non-error responses
- **TEST-004**: Verify error handling tests produce deterministic error codes (not raw stack traces)

## 7. Risks & Assumptions

- **RISK-001**: Some specified databases may not exist on target instances — tools will return SQL errors which should be recorded as "database not found" rather than "tool failure"
- **RISK-002**: nalyze_tab_health with histogram analysis on large databases may timeout (600s timeout set) — use include_histogram_analysis=false for initial tests
- **ASSUMPTION-001**: Server authentication is disabled (auth_mode=disabled), so no bearer tokens needed for testing
- **ASSUMPTION-002**: Rate limiting backend (Redis) is healthy and won't reject test calls
- **ASSUMPTION-003**: Both SQL instances are online and the mcp-sqlserver container has network access

## 8. Related Specifications / Further Reading

- [docs/demo-narration-script.md](../docs/demo-narration-script.md) — parent document for production test doc
- [docs/mcp-tool-catalog.md](../docs/mcp-tool-catalog.md) — current tool catalog (to be updated)
- [src/tools/sql_tools.py](../src/tools/sql_tools.py) — source of truth for tool definitions
- [src/tools/tool_registry.py](../src/tools/tool_registry.py) — tool spec generation
