# Non-Production Read-Only QA Test Report

**Run Date (UTC):** 2026-05-01
**MCP Framework:** FastMCP 3.2.4
**Container Image:** `harryvaldez/mcp-sql-server:latest`
**Transport:** HTTP (MCP_TRANSPORT=http, port 8085)
**Harness:** testing/nonprod_harness.py (5th execution run)

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| Total execution units | 70 |
| **Passed** | **66** |
| **Failed (pending DBA)** | **4** |
| Open code defects | 0 |
| Artifact files generated | 78 |
| Test databases | 4 |
| Test instances | 2 |

All 66 passing units returned successful responses. The 4 failures are exclusively explain_query on all four test databases, caused by a missing SHOWPLAN permission for the mcp_readonly user. No code defects remain.

---

## 2. Execution Matrix

Instance-scoped tools (ping, list_databases, server_info_mcp) each ran once per prefix (2 x 3 = 6 units).
Database-scoped tools (16 suffixes x 4 databases = 64 units). Total = 70 units.

| Instance | Prefix | Database | DB-Scoped Passed | DB-Scoped Failed | Failed Suffix |
|----------|--------|----------|-----------------|-----------------|---------------|
| 1 | db_01 | USGISPRO_800 | 15 | 1 | explain_query |
| 1 | db_01 | US_RT_User_800 | 15 | 1 | explain_query |
| 2 | db_02 | ListGateway | 15 | 1 | explain_query |
| 2 | db_02 | US_UserData | 15 | 1 | explain_query |
| 1 | db_01 | (instance) | 3/3 | 0 | - |
| 2 | db_02 | (instance) | 3/3 | 0 | - |

---

## 3. Tool Coverage

All 19 read-only tool suffixes exercised:

| # | Suffix | Scope | All 4 DBs Pass? |
|---|--------|-------|----------------|
| 1 | ping | instance | YES |
| 2 | list_databases | instance | YES |
| 3 | server_info_mcp | instance | YES |
| 4 | list_tables | database | YES |
| 5 | get_schema | database | YES |
| 6 | execute_query | database | YES |
| 7 | run_query | database | YES |
| 8 | list_objects | database | YES |
| 9 | index_fragmentation | database | YES |
| 10 | index_health | database | YES |
| 11 | table_health | database | YES |
| 12 | db_stats | database | YES |
| 13 | show_top_queries | database | YES |
| 14 | check_fragmentation | database | YES |
| 15 | db_sec_perf_metrics | database | YES |
| 16 | explain_query | database | PENDING DBA |
| 17 | analyze_logical_data_model | database | YES |
| 18 | open_logical_model | database | YES |
| 19 | generate_ddl | database | YES |

---

## 4. Defect Register Summary

Full register: testing/nonprod_defect_register.json

| ID | Tool | Database | Status | Root Cause |
|----|------|----------|--------|------------|
| DEF-001 | db_01_explain_query | USGISPRO_800 | pending | SHOWPLAN permission denied (SQL error 262) |
| DEF-002 | db_01_explain_query | US_RT_User_800 | pending | SHOWPLAN permission denied (SQL error 262) |
| DEF-003 | db_02_explain_query | ListGateway | pending | SHOWPLAN permission denied (SQL error 262) |
| DEF-004 | db_02_explain_query | US_UserData | pending | SHOWPLAN permission denied (SQL error 262) |

### DBA Remediation SQL

`sql
USE [USGISPRO_800];  GRANT SHOWPLAN TO [mcp_readonly];
USE [US_RT_User_800]; GRANT SHOWPLAN TO [mcp_readonly];
USE [ListGateway];   GRANT SHOWPLAN TO [mcp_readonly];
USE [US_UserData];   GRANT SHOWPLAN TO [mcp_readonly];
`

---

## 5. Representative Data Excerpts

Columns containing personal data have been redacted.

### Instance 1 - USGISPRO_800

**Discovery table:** dbo.Account
**get_schema first column:** AccountID (int, NOT NULL)
**execute_query sample row (PII redacted):**

`json
{"AccountID": 1, "CompanyID": 2, "AccountName": "***", "Title": "***", "FirstName": "***", "LastName": "***"}
`

### Instance 1 - US_RT_User_800

**Discovery table:** dbo.000D6C78-5784-4A7F-8C31-3DEEF4457529 (UUID-named table)
**Note:** First two tables in this database ([US_Retailers_2023], [US_Retailers_2025]) have literal square brackets embedded in their object names. The harness skips bracket-named tables.
**execute_query:** 0 rows (table is empty).

### Instance 2 - ListGateway

**Discovery table:** dbo.bb_202101_bg
**get_schema first column:** GeoFIPS (varchar, NOT NULL)
**execute_query sample row:**

`json
{"GeoFIPS": "010010201001", "GeoNAME": "010010201001", "State": "AL", "BB202101T_TOTAL": 18}
`

### Instance 2 - US_UserData

**Discovery table:** dbo._ln_155_056fef58-efd6-48d2-94e5-9009d3111549
**execute_query sample rows:**

`json
[{"GeoFIPS": "AL", "col1": 4374}, {"GeoFIPS": "AK", "col1": 1161}, {"GeoFIPS": "AZ", "col1": 52412}]
`

---

## 6. Issues Found and Fixed During This QA Run

| Issue | Root Cause | Fix Applied | Outcome |
|-------|-----------|-------------|---------|
| list_tables discovery key mismatch | Harness used tables key; API returns items (paginated) | Updated _extract_user_schema_table to read items key | Fixed |
| explain_query wrong database context | get_connection() ignores database param post-refactor | Added USE [db] before SET SHOWPLAN_ALL ON in server.py | Fixed |
| generate_ddl wrong database context | INFORMATION_SCHEMA.COLUMNS query ran against master | Routed query through _execute_in_database | Fixed |
| execute_query double-bracket table name | list_tables returns [US_Retailers_2023] with literal brackets; harness double-wrapped them | Added _strip_brackets() + plain-name preference in discovery | Fixed |

---

## 7. Reproducibility

### Container Start

`ash
docker run -d --name mcp-sqlserver -p 8085:8000 --env MCP_TRANSPORT=http --env-file .env harryvaldez/mcp-sql-server:latest
`

### Example JSON-RPC Invocation

`ash
curl -s -X POST http://localhost:8085/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"db_01_list_tables","arguments":{"instance":1,"database_name":"USGISPRO_800"}}}'
`

### Re-run Harness

`
python testing/nonprod_harness.py 2>&1 | Tee-Object testing/nonprod_run_output.txt
`

---

## 8. Artifact Index

All artifacts saved to testing/tool_results/nonprod_*.json

| Pattern | Count | Notes |
|---------|-------|-------|
| nonprod_db_01_USGISPRO_800_*.json | 16 | 15 SUCCESS, 1 FAILED (explain_query) |
| nonprod_db_01_US_RT_User_800_*.json | 16 | 15 SUCCESS, 1 FAILED (explain_query) |
| nonprod_db_02_ListGateway_*.json | 16 | 15 SUCCESS, 1 FAILED (explain_query) |
| nonprod_db_02_US_UserData_*.json | 16 | 15 SUCCESS, 1 FAILED (explain_query) |
| Discovery + instance-scoped | ~14 | All SUCCESS |

---

## 9. Sign-Off Criteria

| Criterion | Met? |
|-----------|------|
| All instance-scoped tools pass on both instances | YES |
| All database-scoped tools excluding explain_query pass on all 4 DBs | YES |
| Zero open code defects | YES |
| explain_query failures documented with DBA remediation SQL | YES |
| All artifacts saved to testing/tool_results/ | YES |
| Defect register finalised | YES |

**QA Status: PASSED (pending DBA SHOWPLAN grants for explain_query on 4 databases)**

---

*Generated 2026-05-01 — testing/nonprod_harness.py*
