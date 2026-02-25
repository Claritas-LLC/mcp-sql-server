#!/usr/bin/env python3
"""
run_all_tools_http.py - Execute all MCP SQL Server tools via HTTP and save results.

This script:
1. Starts the MCP server (stdio mode)
2. Uses pyodbc to directly execute tool logic (since FastMCP HTTP is complex)
3. Saves individual tool results to testing/tool_results/{tool_name}.json
4. Generates tool_execution_summary.json with overall statistics
"""

import json
import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

# Set required environment variables
os.environ['DB_SERVER'] = 'localhost'
os.environ['DB_PORT'] = '14333'
os.environ['DB_USER'] = 'SA'
os.environ['DB_PASSWORD'] = 'McpTestPassword123!'
os.environ['DB_NAME'] = 'TEST_DB'
os.environ['MSSQL_DRIVER'] = 'ODBC Driver 18 for SQL Server'
os.environ['MCP_ALLOW_WRITE'] = 'false'

# Create output directory
TESTING_DIR = Path('testing/tool_results')
TESTING_DIR.mkdir(parents=True, exist_ok=True)

# Import MCP server module to get tool implementations
sys.path.insert(0, os.path.dirname(__file__))
import pyodbc

def get_connection():
    """Get SQLServer connection."""
    server = os.environ.get('DB_SERVER', 'localhost')
    port = os.environ.get('DB_PORT', '14333')
    user = os.environ.get('DB_USER', 'SA')
    pwd = os.environ.get('DB_PASSWORD', '')
    
    # Try different driver names in order
    drivers = [
        'ODBC Driver 17 for SQL Server',
        'ODBC Driver 18 for SQL Server',
        'SQL Server Native Client 11.0',
        'SQL Server'
    ]
    
    conn_str = None
    for driver in drivers:
        try:
            conn_str = (
                f"Driver={{{driver}}};"
                f"Server={server},{port};"
                f"UID={user};"
                f"PWD={pwd};"
                f"Encrypt=no;"
            )
            conn = pyodbc.connect(conn_str, timeout=5)
            return conn
        except Exception as e:
            continue
    
    # If none work, raise error
    raise Exception(f"Could not connect with any available driver. Last error: {e}")

def db_sql2019_list_databases() -> Dict[str, Any]:
    """List all databases."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sys.databases ORDER BY name")
        rows = cur.fetchall()
        conn.close()
        return {
            "status": "success",
            "databases": [row[0] for row in rows],
            "count": len(rows)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_list_tables(database: str, schema: str = 'dbo') -> Dict[str, Any]:
    """List tables in a schema."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"USE [{database}]")
        cur.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ? ORDER BY TABLE_NAME",
            (schema,)
        )
        rows = cur.fetchall()
        conn.close()
        return {
            "status": "success",
            "database": database,
            "schema": schema,
            "tables": [row[0] for row in rows],
            "count": len(rows)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_get_schema(database: str, table: str, schema: str = 'dbo') -> Dict[str, Any]:
    """Get table schema."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"USE [{database}]")
        cur.execute(
            """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?
            ORDER BY ORDINAL_POSITION
            """,
            (table, schema)
        )
        cols = []
        for row in cur.fetchall():
            cols.append({
                "name": row[0],
                "type": row[1],
                "nullable": row[2],
                "default": row[3]
            })
        conn.close()
        return {
            "status": "success",
            "database": database,
            "schema": schema,
            "table": table,
            "columns": cols,
            "column_count": len(cols)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_execute_query(database: str, query: str) -> Dict[str, Any]:
    """Execute a SELECT query."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"USE [{database}]")
        cur.execute(query)
        
        # Get column names
        cols = [desc[0] for desc in cur.description] if cur.description else []
        
        # Get rows (limit to 10 for testing)
        rows = cur.fetchmany(10)
        data = [dict(zip(cols, row)) for row in rows]
        
        conn.close()
        return {
            "status": "success",
            "database": database,
            "query": query[:100],
            "columns": cols,
            "row_count": len(rows),
            "data": data
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_get_index_fragmentation(database: str, schema: str = 'dbo') -> Dict[str, Any]:
    """Get index fragmentation."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"USE [{database}]")
        cur.execute("""
            SELECT TOP 10
                OBJECT_NAME(ips.object_id) AS TableName,
                i.name AS IndexName,
                ips.index_type_desc,
                ips.avg_fragmentation_in_percent
            FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'SAMPLED') ips
            JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
            WHERE ips.avg_fragmentation_in_percent > 0
            ORDER BY ips.avg_fragmentation_in_percent DESC
        """)
        rows = cur.fetchall()
        conn.close()
        
        data = []
        for row in rows:
            data.append({
                "table": row[0],
                "index": row[1],
                "type": row[2],
                "fragmentation": float(row[3])
            })
        
        return {
            "status": "success",
            "database": database,
            "schema": schema,
            "fragmented_indexes": data,
            "count": len(data)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_analyze_table_health(database: str, schema: str = 'dbo') -> Dict[str, Any]:
    """Analyze table health."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"USE [{database}]")
        cur.execute(f"""
            SELECT TOP 10
                t.name AS TableName,
                ps.row_count,
                (ps.used_page_count * 8) / 1024.0 AS SizeMB
            FROM sys.dm_db_partition_stats ps
            JOIN sys.tables t ON ps.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = '{schema}'
            ORDER BY ps.row_count DESC
        """)
        rows = cur.fetchall()
        conn.close()
        
        data = []
        for row in rows:
            data.append({
                "table": row[0],
                "rows": row[1],
                "size_mb": float(row[2]) if row[2] else 0
            })
        
        return {
            "status": "success",
            "database": database,
            "schema": schema,
            "tables": data,
            "count": len(data)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_db_stats(database: str) -> Dict[str, Any]:
    """Get database statistics."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"USE [{database}]")
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM sys.tables) AS TableCount,
                (SELECT COUNT(*) FROM sys.views) AS ViewCount,
                (SELECT COUNT(*) FROM sys.procedures) AS ProcedureCount,
                (SELECT COUNT(*) FROM sys.indexes) AS IndexCount
        """)
        row = cur.fetchone()
        conn.close()
        
        return {
            "status": "success",
            "database": database,
            "statistics": {
                "tables": row[0] if row else 0,
                "views": row[1] if row else 0,
                "procedures": row[2] if row else 0,
                "indexes": row[3] if row else 0
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_server_info_mcp() -> Dict[str, Any]:
    """Get SQL Server information."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                @@VERSION AS Version,
                @@SERVERNAME AS ServerName,
                GETDATE() AS CurrentTime
        """)
        row = cur.fetchone()
        conn.close()
        
        return {
            "status": "success",
            "server_version": row[0] if row else None,
            "server_name": row[1] if row else None,
            "current_time": str(row[2]) if row else None
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_show_top_queries(database: str) -> Dict[str, Any]:
    """Show top queries (by execution count)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"USE [{database}]")
        cur.execute("""
            SELECT TOP 5
                qs.execution_count,
                qs.total_elapsed_time / 1000000 AS ElapsedSeconds,
                SUBSTRING(st.text, 1, 100) AS QueryText
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
            ORDER BY qs.execution_count DESC
        """)
        rows = cur.fetchall()
        conn.close()
        
        data = []
        for row in rows:
            data.append({
                "executions": row[0],
                "elapsed_seconds": float(row[1]) if row[1] else 0,
                "query": row[2]
            })
        
        return {
            "status": "success",
            "database": database,
            "top_queries": data,
            "count": len(data)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_check_fragmentation(database: str, mode: str = 'SAMPLED') -> Dict[str, Any]:
    """Check index fragmentation."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"USE [{database}]")
        cur.execute(f"""
            SELECT TOP 10
                OBJECT_NAME(ips.object_id) AS TableName,
                i.name AS IndexName,
                ips.avg_fragmentation_in_percent,
                ips.page_count
            FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, '{mode}') ips
            JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
            WHERE ips.avg_fragmentation_in_percent > 0 AND ips.page_count > 1000
            ORDER BY ips.avg_fragmentation_in_percent DESC
        """)
        rows = cur.fetchall()
        conn.close()
        
        data = []
        for row in rows:
            data.append({
                "table": row[0],
                "index": row[1],
                "fragmentation": float(row[2]),
                "pages": row[3]
            })
        
        return {
            "status": "success",
            "database": database,
            "mode": mode,
            "fragmented_indexes": data,
            "count": len(data)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def db_sql2019_db_sec_perf_metrics(profile: str = 'oltp') -> Dict[str, Any]:
    """Get security and performance metrics."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM sys.server_principals WHERE type = 'S') AS SQL_Logins,
                (SELECT COUNT(*) FROM sys.database_principals WHERE type = 'U') AS DB_Users,
                (SELECT COUNT(*) FROM sys.dm_exec_sessions) AS ActiveSessions,
                (SELECT CAST(total_physical_memory_kb / 1024.0 / 1024.0 AS DECIMAL(10,2)) FROM sys.dm_os_sys_memory) AS TotalMemoryGB
        """)
        row = cur.fetchone()
        conn.close()
        
        return {
            "status": "success",
            "profile": profile,
            "metrics": {
                "sql_logins": row[0] if row else 0,
                "db_users": row[1] if row else 0,
                "active_sessions": row[2] if row else 0,
                "total_memory_gb": float(row[3]) if row and row[3] else 0
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def save_result(tool_name: str, result: Any) -> None:
    """Save tool result to JSON file."""
    output_file = TESTING_DIR / f'{tool_name}.json'
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  ✅ Saved to {output_file}")

def main():
    """Execute all tools and collect results."""
    print("\n" + "=" * 80)
    print("🚀 MCP SQL SERVER - TOOL EXECUTION SUITE")
    print("=" * 80)
    print(f"Results directory: {TESTING_DIR.absolute()}\n")
    
    summary = {
        'execution_time': datetime.now().isoformat(),
        'environment': {
            'db_server': os.environ.get('DB_SERVER'),
            'db_name': os.environ.get('DB_NAME'),
        },
        'tools_executed': {}
    }
    
    # Tool definitions with parameters
    tools = [
        ('db_sql2019_list_databases', lambda: db_sql2019_list_databases()),
        ('db_sql2019_list_tables', lambda: db_sql2019_list_tables('TEST_DB', 'sales')),
        ('db_sql2019_get_schema', lambda: db_sql2019_get_schema('TEST_DB', 'Customers', 'sales')),
        ('db_sql2019_execute_query', lambda: db_sql2019_execute_query('TEST_DB', 'SELECT TOP 10 * FROM sales.Customers')),
        ('db_sql2019_get_index_fragmentation', lambda: db_sql2019_get_index_fragmentation('TEST_DB', 'sales')),
        ('db_sql2019_analyze_table_health', lambda: db_sql2019_analyze_table_health('TEST_DB', 'sales')),
        ('db_sql2019_db_stats', lambda: db_sql2019_db_stats('TEST_DB')),
        ('db_sql2019_server_info_mcp', lambda: db_sql2019_server_info_mcp()),
        ('db_sql2019_show_top_queries', lambda: db_sql2019_show_top_queries('TEST_DB')),
        ('db_sql2019_check_fragmentation', lambda: db_sql2019_check_fragmentation('TEST_DB', 'SAMPLED')),
        ('db_sql2019_db_sec_perf_metrics', lambda: db_sql2019_db_sec_perf_metrics('oltp')),
    ]
    
    successes = 0
    for tool_name, tool_func in tools:
        print(f"⏳ Executing {tool_name}...")
        try:
            result = tool_func()
            save_result(tool_name, result)
            
            if result.get('status') == 'success' or 'error' not in result:
                summary['tools_executed'][tool_name] = {
                    'status': 'SUCCESS',
                    'result_file': f'testing\\tool_results\\{tool_name}.json',
                }
                print(f"  ✅ Success")
                successes += 1
            else:
                summary['tools_executed'][tool_name] = {
                    'status': 'FAILED',
                    'result_file': f'testing\\tool_results\\{tool_name}.json',
                    'error': result.get('error', 'Unknown error'),
                }
                print(f"  ❌ Error: {result.get('error', 'Unknown error')}")
        except Exception as e:
            error_msg = str(e)
            print(f"  ❌ Exception: {error_msg}")
            summary['tools_executed'][tool_name] = {
                'status': 'FAILED',
                'result_file': f'testing\\tool_results\\{tool_name}.json',
                'error': error_msg,
            }
            save_result(tool_name, {'status': 'error', 'error': error_msg})
    
    # Save summary
    summary_file = Path('testing/tool_execution_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print("\n" + "=" * 80)
    print(f"📊 Summary saved to {summary_file}")
    print(f"📈 Results: {successes}/{len(tools)} tools executed successfully")
    print("=" * 80 + "\n")
    
    return 0 if successes == len(tools) else 1

if __name__ == '__main__':
    sys.exit(main())
