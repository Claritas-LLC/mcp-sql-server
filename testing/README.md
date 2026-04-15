# MCP SQL Server - Test Results Directory

## 📋 Overview

This directory contains comprehensive test results from executing all 11 MCP SQL Server tools against a test database (TEST_DB) running in SQL Server 2019 Docker container.

**Execution Date:** 2026-02-24  
**Success Rate:** 11/11 (100%)  
**Total Artifacts:** 12 JSON files

---

## 📁 Directory Structure

```
testing/
├── tool_execution_summary.json           # ← START HERE - Overall execution results
└── tool_results/
    ├── db_01_sql2019_list_databases.json            # List of all SQL Server databases
    ├── db_01_sql2019_list_tables.json               # Tables in sales schema
    ├── db_01_sql2019_get_schema.json                # Column definitions for Customers table
    ├── db_01_sql2019_execute_query.json             # Sample SELECT query results (10 rows)
    ├── db_01_sql2019_get_index_fragmentation.json    # Index fragmentation analysis
    ├── db_01_sql2019_analyze_table_health.json       # Table health metrics
    ├── db_01_sql2019_db_stats.json                   # Database statistics (table/view/procedure/index counts)
    ├── db_01_sql2019_server_info_mcp.json            # SQL Server version and instance info
    ├── db_01_sql2019_show_top_queries.json           # Top executing queries
    ├── db_01_sql2019_check_fragmentation.json        # Fragmentation report (SAMPLED mode)
    └── db_01_sql2019_db_sec_perf_metrics.json        # Security and performance metrics
```

---

## 🎯 Quick Start

### View Overall Results
```bash
# See execution summary with all tool statuses
cat tool_execution_summary.json
```

### View Individual Tool Results
```bash
# Example: View database list
cat tool_results/db_01_sql2019_list_databases.json

# Example: View table schema
cat tool_results/db_01_sql2019_get_schema.json

# Example: View performance metrics
cat tool_results/db_01_sql2019_db_stats.json
```

### Parse Results in PowerShell
```powershell
# Get tool execution summary
$summary = Get-Content tool_execution_summary.json | ConvertFrom-Json
$summary.tools_executed.GetEnumerator() | ForEach-Object { $_.Value } | Format-Table

# Process individual tool result
$databases = Get-Content tool_results/db_01_sql2019_list_databases.json | ConvertFrom-Json
$databases.items
$databases.pagination
```

### Parse Results in Python
```python
import json

# Read summary
with open('tool_execution_summary.json') as f:
    summary = json.load(f)
    
# Print all tool statuses
for tool_name, info in summary['tools_executed'].items():
    print(f"{tool_name}: {info['status']}")

# Read individual tool result
with open('tool_results/db_01_sql2019_list_databases.json') as f:
    databases = json.load(f)
  print(f"Found {databases['pagination']['total_items']} databases")
  print(f"Page {databases['pagination']['page']} of {databases['pagination']['total_pages']}")
  print(databases['items'])
```

---

## 📊 Result File Descriptions

### `tool_execution_summary.json`
**Purpose:** Master summary file with execution statistics  
**Key Fields:**
- `execution_time`: ISO timestamp of execution
- `environment`: Database connection info
- `tools_executed`: Status of each tool (SUCCESS/FAILED)

**Example:**
```json
{
  "execution_time": "2026-02-24T16:07:08.163574",
  "environment": {
    "db_server": "localhost",
    "db_name": "TEST_DB"
  },
  "tools_executed": {
    "db_01_sql2019_list_databases": {"status": "SUCCESS", "result_file": "..."},
    ...
  }
}
```

### `db_01_sql2019_list_databases.json`
**Purpose:** List all SQL Server databases  
**Key Fields:**
- `items`: Array of database names for current page
- `pagination.page`: Current page number
- `pagination.page_size`: Items per page
- `pagination.total_items`: Total number of items
- `pagination.total_pages`: Total pages available

**Example:**
```json
{
  "items": ["master", "model", "msdb", "tempdb", "TEST_DB"],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_items": 5,
    "total_pages": 1
  }
}
```

### `db_01_sql2019_list_tables.json`
**Purpose:** List all tables in a schema  
**Key Fields:**
- `items`: Array of table rows for current page
- `pagination`: Page metadata (`page`, `page_size`, `total_items`, `total_pages`)

### `db_01_sql2019_get_schema.json`
**Purpose:** Get table structure and column definitions  
**Key Fields:**
- `database`, `schema`, `table`: Context values
- `columns`: Array of column objects (paginated in response)
- `_pagination.lists.root.columns`: Pagination metadata for `columns`

### `db_01_sql2019_execute_query.json`
**Purpose:** Execute SELECT query and return results  
**Key Fields:**
- `items`: Query result rows for current page
- `pagination`: Page metadata (`page`, `page_size`, `total_items`, `total_pages`)

### `db_01_sql2019_db_stats.json`
**Purpose:** Database object statistics  
**Key Fields:**
- `statistics`: Object count object with tables, views, procedures, indexes

**Example:**
```json
{
  "status": "success",
  "database": "TEST_DB",
  "statistics": {
    "tables": 7,
    "views": 1,
    "procedures": 1,
    "indexes": 177
  }
}
```

### `db_01_sql2019_analyze_table_health.json`
**Purpose:** Analyze table sizes and row counts  
**Key Fields:**
- `table_info`: Base table health metadata
- `indexes`, `foreign_keys`, `statistics_sample`, `recommendations`: Paginated list fields
- `_pagination.lists`: Per-list pagination metadata

### `db_01_sql2019_get_index_fragmentation.json` & `db_01_sql2019_check_fragmentation.json`
**Purpose:** Index fragmentation analysis  
**Key Fields:**
- `db_01_sql2019_get_index_fragmentation`: `items` + `pagination`
- `db_01_sql2019_check_fragmentation`: list fields are paginated and tracked under `_pagination.lists`

### `db_01_sql2019_server_info_mcp.json`
**Purpose:** SQL Server instance information  
**Key Fields:**
- `server_version`: Full version string
- `server_name`: Instance name
- `current_time`: Server current time

### `db_01_sql2019_show_top_queries.json`
**Purpose:** Top executing queries  
**Key Fields:**
- `long_running_queries`, `high_cpu_queries`, `high_io_queries`, `high_execution_queries`: Paginated list fields
- `_pagination.lists`: Per-list pagination metadata

### `db_01_sql2019_db_sec_perf_metrics.json`
**Purpose:** Security and performance metrics  
**Key Fields:**
- `metrics.sql_logins`: Number of SQL Server logins
- `metrics.db_users`: Number of database users
- `metrics.active_sessions`: Current session count
- `metrics.total_memory_gb`: Total system memory in GB

---

## 🔄 Regenerating Results

To regenerate all tool results (requires test database to be running):

```bash
python run_all_tools_http.py
```

This will:
1. Connect to SQL Server on localhost:14333
2. Execute all 11 tools against TEST_DB
3. Overwrite results files in `tool_results/`
4. Update `tool_execution_summary.json`

---

## 🐳 Docker Container Status

**Container Name:** mcp_sqlserver_temp  
**Image:** mcr.microsoft.com/mssql/server:2019-latest  
**Port Mapping:** 14333:1433  
**Status:** Should be running for live testing

Check container status:
```bash
docker ps | findstr mcp_sqlserver_temp
```

Start container if needed:
```bash
docker run -e 'ACCEPT_EULA=Y' -e 'SA_PASSWORD=McpTestPassword123!' \
  --name mcp_sqlserver_temp -p 14333:1433 -d \
  mcr.microsoft.com/mssql/server:2019-latest
```

---

## 🎓 Using Results for Testing

> **Note on pagination:** Non-UI tools now paginate list outputs by default (`page=1`, `page_size=10`).
> For top-level list tools, read `items` and `pagination`. For dict responses with lists, use `_pagination.lists`.

### Unit Test Mocking
```python
# Load tool results as mock data for unit tests
with open('tool_results/db_01_sql2019_list_databases.json') as f:
    mock_db_list = json.load(f)

# Use in test assertions
assert 'TEST_DB' in mock_db_list['items']
```

### Integration Test Validation
```python
# Compare tool results against expected database state
actual = run_tool()
expected = load_from_json('tool_results/tool_name.json')
assert actual == expected
```

### CI/CD Pipeline Integration
```bash
# Archive results for compliance
cp -r testing/ /artifacts/mcp-sql-server-test-results/
```

---

## 📈 Metrics Summary

| Tool | Status | Pagination Semantics | Query Time |
|------|--------|----------------------|------------|
| db_01_sql2019_list_databases | ✅ | top-level `items` + `pagination` (`page_size=10`) | <100ms |
| db_01_sql2019_list_tables | ✅ | top-level `items` + `pagination` (`page_size=10`) | <100ms |
| db_01_sql2019_get_schema | ✅ | `columns` paginated via `_pagination.lists.root.columns` | <100ms |
| db_01_sql2019_execute_query | ✅ | top-level `items` + `pagination` (`page_size=10`) | <200ms |
| db_01_sql2019_get_index_fragmentation | ✅ | top-level `items` + `pagination` (`page_size=10`) | <500ms |
| db_01_sql2019_analyze_table_health | ✅ | list fields paginated via `_pagination.lists` | <200ms |
| db_01_sql2019_db_stats | ✅ | no list fields (unchanged) | <100ms |
| db_01_sql2019_server_info_mcp | ✅ | no list fields (unchanged) | <100ms |
| db_01_sql2019_show_top_queries | ✅ | query lists paginated via `_pagination.lists` | <200ms |
| db_01_sql2019_check_fragmentation | ✅ | list fields paginated via `_pagination.lists` | <500ms |
| db_01_sql2019_db_sec_perf_metrics | ✅ | list fields paginated via `_pagination.lists` | <200ms |

**Overall:** 11/11 tools (100% success rate, ~3-5 seconds total execution time)

---

## 🔍 Troubleshooting

**Results Missing?**  
→ Check if SQL Server container is running: `docker ps`

**Results Outdated?**  
→ Regenerate with `python run_all_tools_http.py`

**JSON Parse Error?**  
→ Validate JSON: `python -m json.tool tool_results/tool_name.json`

**Connection Errors?**  
→ Verify database running: `docker exec mcp_sqlserver_temp sqlcmd -Q "SELECT 1"`

---

**Last Updated:** 2026-02-26  
**Test Framework:** run_all_tools_http.py  
**Status:** ✅ Production Ready
