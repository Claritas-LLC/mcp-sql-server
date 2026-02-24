"""
Run all MCP SQL Server tools and save results to testing folder
"""

import os
import sys
import json
import traceback
from datetime import datetime
from pathlib import Path

# Set up environment
os.environ["DB_SERVER"] = "localhost"
os.environ["DB_PORT"] = "14333"
os.environ["DB_USER"] = "SA"
os.environ["DB_PASSWORD"] = "McpTestPassword123!"
os.environ["DB_NAME"] = "TEST_DB"
os.environ["MCP_ALLOW_WRITE"] = "false"
os.environ["MCP_TRANSPORT"] = "stdio"

# Add repo to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create testing folder
TESTING_DIR = Path("testing")
TESTING_DIR.mkdir(exist_ok=True)
RESULTS_DIR = TESTING_DIR / "tool_results"
RESULTS_DIR.mkdir(exist_ok=True)

# Summary file
SUMMARY_FILE = TESTING_DIR / "tool_execution_summary.json"

print("=" * 80)
print("MCP SQL SERVER - RUNNING ALL TOOLS")
print("=" * 80)
print(f"\nResults will be saved to: {RESULTS_DIR.absolute()}\n")

# Track results
results = {
    "execution_time": datetime.now().isoformat(),
    "environment": {
        "db_server": os.getenv("DB_SERVER"),
        "db_name": os.getenv("DB_NAME"),
    },
    "tools_executed": {}
}

def save_result(tool_name, status, data=None, error=None):
    """Save individual tool result"""
    result_file = RESULTS_DIR / f"{tool_name}.json"
    
    result_data = {
        "tool_name": tool_name,
        "status": status,
        "timestamp": datetime.now().isoformat(),
    }
    
    if data is not None:
        result_data["result"] = data
    if error is not None:
        result_data["error"] = error
    
    with open(result_file, 'w') as f:
        json.dump(result_data, f, indent=2, default=str)
    
    results["tools_executed"][tool_name] = {
        "status": status,
        "result_file": str(result_file),
        "error": error
    }
    
    return result_file

try:
    # Import tools
    print("[1/11] Importing tools from server.py...")
    from server import (
        db_list_databases,
        db_list_tables,
        db_get_schema,
        db_execute_query,
        db_sql2019_get_index_fragmentation,
        db_sql2019_analyze_table_health,
        db_sql2019_db_stats,
        db_sql2019_server_info_mcp,
        db_sql2019_show_top_queries,
        db_sql2019_check_fragmentation,
        db_sql2019_db_sec_perf_metrics
    )
    print("✓ All tools imported successfully\n")
    
    # Tool 1: List databases
    print("[2/11] Running db_list_databases()...")
    try:
        result = db_list_databases()
        save_result("db_list_databases", "SUCCESS", data=result)
        print(f"✓ Found {len(result)} databases")
    except Exception as e:
        save_result("db_list_databases", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 2: List tables
    print("\n[3/11] Running db_list_tables(database_name='TEST_DB', schema_name='sales')...")
    try:
        result = db_list_tables("TEST_DB", "sales")
        save_result("db_list_tables", "SUCCESS", data=result)
        print(f"✓ Found {len(result)} tables in sales schema")
    except Exception as e:
        save_result("db_list_tables", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 3: Get schema
    print("\n[4/11] Running db_get_schema(database_name='TEST_DB', table_name='Customers', schema_name='sales')...")
    try:
        result = db_get_schema("TEST_DB", "Customers", "sales")
        save_result("db_get_schema", "SUCCESS", data=result)
        print(f"✓ Schema retrieved for sales.Customers")
        print(f"  - Columns: {len(result.get('columns', []))}")
        print(f"  - Primary Keys: {len(result.get('primary_key', []))}")
        print(f"  - Foreign Keys: {len(result.get('foreign_keys', []))}")
    except Exception as e:
        save_result("db_get_schema", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 4: Execute query
    print("\n[5/11] Running db_execute_query(database_name='TEST_DB', sql_query='SELECT TOP 10 * FROM sales.Customers')...")
    try:
        result = db_execute_query("TEST_DB", "SELECT TOP 10 * FROM sales.Customers")
        save_result("db_execute_query", "SUCCESS", data=result)
        print(f"✓ Query executed, returned {len(result)} rows")
    except Exception as e:
        save_result("db_execute_query", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 5: Get index fragmentation
    print("\n[6/11] Running db_sql2019_get_index_fragmentation(database_name='TEST_DB', schema='sales')...")
    try:
        result = db_sql2019_get_index_fragmentation("TEST_DB", "sales")
        save_result("db_sql2019_get_index_fragmentation", "SUCCESS", data=result)
        print(f"✓ Index fragmentation analysis completed")
        print(f"  - Indexes analyzed: {len(result)}")
    except Exception as e:
        save_result("db_sql2019_get_index_fragmentation", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 6: Analyze table health
    print("\n[7/11] Running db_sql2019_analyze_table_health(database_name='TEST_DB', schema_name='sales')...")
    try:
        result = db_sql2019_analyze_table_health("TEST_DB", "sales")
        save_result("db_sql2019_analyze_table_health", "SUCCESS", data=result)
        print(f"✓ Table health analysis completed")
        if isinstance(result, dict) and "tables" in result:
            print(f"  - Tables analyzed: {len(result['tables'])}")
    except Exception as e:
        save_result("db_sql2019_analyze_table_health", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 7: DB stats
    print("\n[8/11] Running db_sql2019_db_stats(database='TEST_DB')...")
    try:
        result = db_sql2019_db_stats("TEST_DB")
        save_result("db_sql2019_db_stats", "SUCCESS", data=result)
        print(f"✓ Database statistics retrieved")
        if isinstance(result, dict):
            print(f"  - Keys: {', '.join(list(result.keys())[:5])}")
    except Exception as e:
        save_result("db_sql2019_db_stats", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 8: Server info
    print("\n[9/11] Running db_sql2019_server_info_mcp()...")
    try:
        result = db_sql2019_server_info_mcp()
        save_result("db_sql2019_server_info_mcp", "SUCCESS", data=result)
        print(f"✓ Server information retrieved")
        if isinstance(result, dict) and "server_name" in result:
            print(f"  - Server: {result.get('server_name')}")  
            print(f"  - Version: {result.get('sql_server_version')}")
    except Exception as e:
        save_result("db_sql2019_server_info_mcp", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 9: Show top queries
    print("\n[10/11] Running db_sql2019_show_top_queries(database_name='TEST_DB')...")
    try:
        result = db_sql2019_show_top_queries("TEST_DB")
        save_result("db_sql2019_show_top_queries", "SUCCESS", data=result)
        print(f"✓ Top queries analysis completed")
        if isinstance(result, dict):
            print(f"  - Keys: {', '.join(list(result.keys())[:5])}")
    except Exception as e:
        save_result("db_sql2019_show_top_queries", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 10: Check fragmentation
    print("\n[11/11] Running db_sql2019_check_fragmentation(database_name='TEST_DB', mode='SAMPLED')...")
    try:
        result = db_sql2019_check_fragmentation("TEST_DB", mode="SAMPLED")
        save_result("db_sql2019_check_fragmentation", "SUCCESS", data=result)
        print(f"✓ Fragmentation check completed")
        if isinstance(result, dict):
            print(f"  - Status: {result.get('status')}")
    except Exception as e:
        save_result("db_sql2019_check_fragmentation", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Tool 11: DB security/performance metrics
    print("\n[12/12] Running db_sql2019_db_sec_perf_metrics(profile='oltp')...")
    try:
        result = db_sql2019_db_sec_perf_metrics("oltp")
        save_result("db_sql2019_db_sec_perf_metrics", "SUCCESS", data=result)
        print(f"✓ Security and performance metrics retrieved")
        if isinstance(result, dict):
            print(f"  - Keys: {', '.join(list(result.keys())[:5])}")
    except Exception as e:
        save_result("db_sql2019_db_sec_perf_metrics", "FAILED", error=str(e))
        print(f"✗ Error: {str(e)[:80]}")
    
    # Save summary
    print("\n" + "=" * 80)
    with open(SUMMARY_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    # Print summary statistics
    total_tools = len(results["tools_executed"])
    successful = sum(1 for t in results["tools_executed"].values() if t["status"] == "SUCCESS")
    failed = sum(1 for t in results["tools_executed"].values() if t["status"] == "FAILED")
    
    print(f"\nEXECUTION SUMMARY")
    print("-" * 80)
    print(f"Total Tools: {total_tools}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(successful/total_tools*100):.1f}%")
    print(f"\nResults saved to: {RESULTS_DIR.absolute()}")
    print(f"Summary file: {SUMMARY_FILE.absolute()}")
    print("=" * 80)

except Exception as e:
    print(f"\n✗ Critical Error: {e}")
    traceback.print_exc()
    sys.exit(1)
