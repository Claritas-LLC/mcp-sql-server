# Non-Production Read-Only QA Test Report

**Run Date (UTC):** 2026-05-02  
**MCP Framework:** FastMCP 3.2.4  
**Container Image:** `harryvaldez/mcp-sql-server:latest`  
**Transport:** HTTP (local in-process MCP; aligns with `.env`-backed dual instances)  
**Harness:** `testing/nonprod_harness.py` — full verification run after SHOWPLAN grants  

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| Total execution units | 70 |
| **Passed** | **70** |
| **Failed** | **0** |
| Open code defects | 0 |
| Artifact files (`nonprod_*.json`) | 78 |
| Test databases | 4 |
| Test instances | 2 |

All 70 units returned successful tool responses with clean artifact validation. Earlier runs failed only on `explain_query` until `SHOWPLAN` was granted to `mcp_readonly` per database; the final run exercised all suffixes successfully.

---

## 2. Execution Matrix

Instance-scoped tools (`ping`, `list_databases`, `server_info_mcp`): **2 × 3 = 6** units.  
Database-scoped tools: **16 suffixes × 4 databases = 64** units. **Total = 70.**

| Instance | Prefix | Database | DB-scoped suffixes passed | Failed |
|----------|--------|----------|---------------------------|--------|
| 1 | db_01 | USGISPRO_800 | 16 / 16 | 0 |
| 1 | db_01 | US_RT_User_800 | 16 / 16 | 0 |
| 2 | db_02 | ListGateway | 16 / 16 | 0 |
| 2 | db_02 | US_UserData | 16 / 16 | 0 |
| 1 | db_01 | (instance-scoped) | 3 / 3 | 0 |
| 2 | db_02 | (instance-scoped) | 3 / 3 | 0 |

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
| 16 | explain_query | database | YES |
| 17 | analyze_logical_data_model | database | YES |
| 18 | open_logical_model | database | YES |
| 19 | generate_ddl | database | YES |

---

## 4. Defect Register Summary

**File:** `testing/nonprod_defect_register.json` — **empty** (`[]`). No open defects.

**Historical note:** A prior cycle logged four open defects (`DEF-001`–`DEF-004`) for `SHOWPLAN permission denied` (SQL 262). After **`GRANT SHOWPLAN TO [mcp_readonly]`** on each target database and a full harness rerun, all `explain_query` artifacts passed and the register was cleared by the harness on the green run.

---

## 5. Representative Data Excerpts

Columns containing personal data have been redacted where applicable.

### Instance 1 — USGISPRO_800

**Discovery table:** `dbo.Account`  
**get_schema first column:** `AccountID` (int, NOT NULL)  
**execute_query sample row (PII redacted):**

```json
{"AccountID": 1, "CompanyID": 2, "AccountName": "***", "Title": "***", "FirstName": "***", "LastName": "***"}
```

### Instance 1 — US_RT_User_800

**Discovery table:** `dbo.000D6C78-5784-4A7F-8C31-3DEEF4457529` (UUID-named table)  
**Note:** First tables in listings may include literal `[ ]` in names; harness prefers plain identifiers.  
**execute_query:** may return 0 rows if the discovery table is empty.

### Instance 2 — ListGateway

**Discovery table:** `dbo.bb_202101_bg`  
**get_schema first column:** `GeoFIPS` (varchar, NOT NULL)  
**execute_query sample row:**

```json
{"GeoFIPS": "010010201001", "GeoNAME": "010010201001", "State": "AL", "BB202101T_TOTAL": 18}
```

### Instance 2 — US_UserData

**Discovery table:** `dbo._ln_155_056fef58-efd6-48d2-94e5-9009d3111549`  
**execute_query sample rows:**

```json
[{"GeoFIPS": "AL", "col1": 4374}, {"GeoFIPS": "AK", "col1": 1161}, {"GeoFIPS": "AZ", "col1": 52412}]
```

---

## 6. Issues Found and Fixed During QA

| Issue | Root Cause | Fix Applied | Outcome |
|-------|------------|-------------|---------|
| list_tables discovery | API paginated `items` vs flat `tables` | `_extract_user_schema_table` reads `items` first | Fixed |
| explain_query wrong DB context | Connection target vs `USE` | `USE [db]` before `SET SHOWPLAN_ALL ON` in server | Fixed |
| generate_ddl wrong context | Columns query against default DB | Routed through `_execute_in_database` | Fixed |
| double-bracket identifiers | Literal `[ ]` in some table names | `_strip_brackets()` + plain-name preference | Fixed |
| SHOWPLAN denied (262) | `mcp_readonly` lacked SHOWPLAN | DBA `GRANT SHOWPLAN` per DB | Resolved |

---

## 7. Reproducibility

### Load `.env` and run harness (PowerShell)

```powershell
$envLines = Get-Content ".env"
foreach ($line in $envLines) {
  if ($line -match '^\s*([^#][^=]*)=(.*)$') {
    $name = $matches[1].Trim()
    $value = $matches[2].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
  }
}
python testing/nonprod_harness.py 2>&1 | Tee-Object testing/nonprod_run_output.txt
```

### Container start (optional HTTP transport parity)

```bash
docker run -d --name mcp-sqlserver -p 8085:8000 --env MCP_TRANSPORT=http --env-file .env harryvaldez/mcp-sql-server:latest
```

### Example MCP JSON-RPC (HTTP)

```bash
curl -s -X POST http://localhost:8085/mcp -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"db_01_list_tables\",\"arguments\":{\"instance\":1,\"database_name\":\"USGISPRO_800\"}}}"
```

**.env:** use non-secret keys only in documentation (`DB_01_SERVER`, `DB_02_SERVER`, `MCP_ALLOW_WRITE=false`, users without passwords).

---

## 8. Artifact Index

All artifacts: `testing/tool_results/nonprod_*.json`

| Pattern | Count | Notes |
|---------|-------|-------|
| `nonprod_db_01_USGISPRO_800_*.json` | 16 | All SUCCESS |
| `nonprod_db_01_US_RT_User_800_*.json` | 16 | All SUCCESS |
| `nonprod_db_02_ListGateway_*.json` | 16 | All SUCCESS |
| `nonprod_db_02_US_UserData_*.json` | 16 | All SUCCESS |
| Preflight + discovery + instance-scoped | ~14 | All SUCCESS |

**Bulk audit expectation:** zero artifacts with `status != SUCCESS` or `result.error` present.

---

## 9. Sign-Off Criteria

| Criterion | Met? |
|-----------|------|
| All instance-scoped tools pass on both instances | YES |
| All database-scoped tools pass on all 4 DBs (including explain_query) | YES |
| Zero open code defects | YES |
| Defect register empty | YES |
| All artifacts saved under `testing/tool_results/` | YES |

**QA status: PASSED** (non-production read-only matrix complete, 70/70)

---

*Generated 2026-05-02 — aligned with harness run and artifact audit.*
