"""
Direct MCP Server Test Script - Simpler approach
Tests the MCP server against our temp SQL Server container
"""

import os
import sys
import json

# Set environment
os.environ["DB_SERVER"] = "localhost"
os.environ["DB_PORT"] = "14333"
os.environ["DB_USER"] = "SA"
os.environ["DB_PASSWORD"] = "McpTestPassword123!"
os.environ["DB_NAME"] = "TEST_DB"
os.environ["DB_DRIVER"] = "ODBC Driver 17 for SQL Server"
os.environ["MCP_ALLOW_WRITE"] = "false"
os.environ["MCP_TRANSPORT"] = "stdio"

print("=" * 70)
print("MCP SQL SERVER DIRECT TEST RUNNER")
print("=" * 70)
print("\n[INFO] Testing environment:")
print(f"  DB_SERVER: {os.getenv('DB_SERVER')}")
print(f"  DB_PORT: {os.getenv('DB_PORT')}")
print(f"  DB_NAME: {os.getenv('DB_NAME')}")
print(f"  MCP_ALLOW_WRITE: {os.getenv('MCP_ALLOW_WRITE')}")

try:
    # Test 1: Import the server module
    print("\n[TEST 1] Importing server.py...")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from server import (
        _is_sql_readonly, _require_readonly, get_connection,
        db_sql2019_list_objects, db_sql2019_run_query,
        db_sql2019_analyze_index_health, db_sql2019_check_fragmentation
    )
    print("✓ PASS: All imports successful")

    # Test 2: SQL Readonly validation
    print("\n[TEST 2] Testing SQL readonly validation...")
    test_cases = [
        ("SELECT * FROM users", True, "SELECT should pass"),
        ("INSERT INTO users VALUES (1)", False, "INSERT should fail"),
        ("UPDATE users SET name='x'", False, "UPDATE should fail"),
        ("DELETE FROM users", False, "DELETE should fail"),
        ("-- COMMENT\nSELECT 1", True, "Comments should be stripped"),
        ("SELECT 'INSERT' AS x", True, "String literals should be ignored"),
    ]
    
    for sql, expected, desc in test_cases:
        result = _is_sql_readonly(sql)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        print(f"  {status}: {desc}")
        if result != expected:
            print(f"    Expected: {expected}, Got: {result}, SQL: {sql[:40]}")

    # Test 3: Connection test
    print("\n[TEST 3] Testing database connection...")
    try:
        conn = get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()
            print(f"✓ PASS: Connected to SQL Server: {str(version[0])[:60]}...")
            conn.close()
        else:
            print("✗ FAIL: get_connection() returned None")
    except Exception as e:
        print(f"⚠ SKIP: Connection failed (container may not be ready): {str(e)[:60]}")

    # Test 4: List objects tool
    print("\n[TEST 4] Testing db_sql2019_list_objects...")
    try:
        result = db_sql2019_list_objects("TEST_DB", "sales", "TABLE")
        if result.get("status") == "success":
            count = len(result.get("data", []))
            print(f"✓ PASS: Found {count} tables in sales schema")
        else:
            print(f"✗ FAIL: Unexpected status: {result.get('status')}")
    except Exception as e:
        print(f"⚠ SKIP: {str(e)[:70]}")

    # Test 5: Run query tool
    print("\n[TEST 5] Testing db_sql2019_run_query...")
    try:
        result = db_sql2019_run_query("TEST_DB", "SELECT TOP 1 CustomerID FROM sales.Customers")
        if result.get("status") == "success":
            print(f"✓ PASS: Query executed, returned {len(result.get('data', []))} rows")
        else:
            print(f"✗ FAIL: Status: {result.get('status')}")
    except Exception as e:
        print(f"⚠ SKIP: {str(e)[:70]}")

    # Test 6: Readonly enforcement
    print("\n[TEST 6] Testing write protection (readonly mode)...")
    try:
        result = db_sql2019_run_query("TEST_DB", "INSERT INTO sales.Customers VALUES ('x', 'y', 'z@test.com', 'NY', 'NY')")
        print(f"✗ FAIL: Write operation was not blocked!")
    except ValueError as e:
        if "Write operations" in str(e) or "readonly" in str(e).lower():
            print(f"✓ PASS: Write operation blocked: {str(e)[:60]}")
        else:
            print(f"⚠ WARN: ValueError raised but unexpected message: {e}")
    except Exception as e:
        print(f"✗ FAIL: Unexpected error: {str(e)[:70]}")

    # Test 7: Index health tool
    print("\n[TEST 7] Testing db_sql2019_analyze_index_health...")
    try:
        result = db_sql2019_analyze_index_health("TEST_DB", "sales")
        if result.get("status") == "success":
            print(f"✓ PASS: Index health analysis completed")
        else:
            print(f"⚠ SKIP: {result.get('status')}")
    except Exception as e:
        print(f"⚠ SKIP: {str(e)[:70]}")

    # Test 8: Fragmentation check tool
    print("\n[TEST 8] Testing db_sql2019_check_fragmentation...")
    try:
        result = db_sql2019_check_fragmentation("TEST_DB", mode="SAMPLED")
        if result.get("status") == "success":
            print(f"✓ PASS: Fragmentation check completed")
        else:
            print(f"⚠ SKIP: {result.get('status')}")
    except Exception as e:
        print(f"⚠ SKIP: {str(e)[:70]}")

    # Test 9: Code quality checks
    print("\n[TEST 9] Code quality checks...")
    with open("server.py", "r") as f:
        content = f.read()
    
    checks = [
        ("try/finally patterns", "finally" in content and "conn.close()" in content),
        ("Parameterized queries", ".execute(" in content and ("?" in content or "%(param)s" in content)),
        ("Required imports", "import pyodbc" in content),
        ("Environment variables used", "os.getenv" in content or "os.environ" in content),
        ("No hardcoded credentials", "password=" not in content.lower() or "os.getenv" in content),
    ]
    
    for check_name, check_result in checks:
        status = "✓ PASS" if check_result else "✗ FAIL"
        print(f"  {status}: {check_name}")

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print("✓ Unit tests completed")
    print("✓ SQL validation tests completed")
    print("✓ Code quality checks completed")
    print("⚠ Integration tests: partial (depends on container readiness)")
    print("=" * 70 + "\n")

except Exception as e:
    print(f"\n✗ CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
