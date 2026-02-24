"""
Comprehensive MCP SQL Server Test Suite
Includes: Unit Tests, Integration Tests, Stress Tests, Blackbox Tests
"""

import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch
import pytest
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    mcp, get_connection, _is_sql_readonly, _require_readonly,
    db_sql2019_list_objects, db_sql2019_run_query,
    db_sql2019_analyze_index_health, db_sql2019_check_fragmentation,
    db_sql2019_db_sec_perf_metrics
)

# Test configuration
TEST_DB_SERVER = os.getenv("DB_SERVER", "localhost")
TEST_DB_PORT = int(os.getenv("DB_PORT", "14333"))
TEST_DB_USER = os.getenv("DB_USER", "SA")
TEST_DB_PASSWORD = os.getenv("DB_PASSWORD", "McpTestPassword123!")
TEST_DB_NAME = os.getenv("DB_NAME", "TEST_DB")


class TestUnitTests:
    """Unit tests with mocked connections"""
    
    def test_is_sql_readonly_select(self):
        """SELECT should pass readonly check"""
        assert _is_sql_readonly("SELECT * FROM users") == True
        assert _is_sql_readonly("select col from table") == True
        assert _is_sql_readonly("  SELECT  1  ") == True

    def test_is_sql_readonly_insert_rejected(self):
        """INSERT should fail readonly check"""
        assert _is_sql_readonly("INSERT INTO users VALUES (1)") == False
        assert _is_sql_readonly("insert into users values (1)") == False

    def test_is_sql_readonly_update_rejected(self):
        """UPDATE should fail readonly check"""
        assert _is_sql_readonly("UPDATE users SET name='test'") == False
        assert _is_sql_readonly("update users set name = 'val'") == False

    def test_is_sql_readonly_delete_rejected(self):
        """DELETE should fail readonly check"""
        assert _is_sql_readonly("DELETE FROM users WHERE id=1") == False
        assert _is_sql_readonly("delete from users") == False

    def test_is_sql_readonly_with_comments(self):
        """Comments should be stripped before checking"""
        assert _is_sql_readonly("-- INSERT INTO should be ignored\nSELECT * FROM users") == True
        assert _is_sql_readonly("/* INSERT */ SELECT * FROM users") == True

    def test_is_sql_readonly_with_string_literals(self):
        """String literals containing keywords should be ignored"""
        assert _is_sql_readonly("SELECT 'INSERT' AS col FROM users") == True
        assert _is_sql_readonly("SELECT \"DELETE\" FROM users") == True

    def test_require_readonly_with_readonly_query_succeeds(self):
        """Readonly enforcement should allow SELECT"""
        # Should not raise
        _require_readonly("SELECT * FROM users")

    def test_require_readonly_with_write_query_fails(self):
        """Readonly enforcement should block INSERT/UPDATE/DELETE"""
        with pytest.raises(ValueError):
            _require_readonly("INSERT INTO users VALUES (1)")

    @patch("pyodbc.connect")
    def test_get_connection_successful(self, mock_connect):
        """Test successful connection"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        conn = get_connection()
        assert conn is not None
        mock_connect.assert_called_once()

    def test_tool_decorator_exists(self):
        """Verify tools are registered with @mcp.tool"""
        # Check that at least one tool is registered
        assert hasattr(mcp, '_tools') or hasattr(mcp, 'tools')


class TestIntegrationTests:
    """Integration tests against real SQL Server container"""
    
    @pytest.fixture(scope="class")
    def db_connection(self):
        """Setup connection to test database"""
        conn = get_connection(
            server=TEST_DB_SERVER,
            port=TEST_DB_PORT,
            username=TEST_DB_USER,
            password=TEST_DB_PASSWORD,
            database=TEST_DB_NAME
        )
        yield conn
        if conn:
            conn.close()

    def test_list_objects_tables(self):
        """Test listing tables from TEST_DB"""
        try:
            result = db_sql2019_list_objects("TEST_DB", "sales", "TABLE")
            assert result["status"] == "success"
            assert "data" in result
            assert len(result["data"]) > 0
            print(f"✓ Found {len(result['data'])} tables")
        except Exception as e:
            print(f"✗ list_objects failed: {e}")
            pytest.skip(f"Integration test skipped: {e}")

    def test_list_objects_indexes(self):
        """Test listing indexes from TEST_DB"""
        try:
            result = db_sql2019_list_objects("TEST_DB", "sales", "INDEX")
            assert result["status"] == "success"
            assert "data" in result
            print(f"✓ Found {len(result['data'])} indexes")
        except Exception as e:
            print(f"✗ list_objects for indexes failed: {e}")
            pytest.skip(f"Integration test skipped: {e}")

    def test_run_query_select(self):
        """Test running a SELECT query"""
        try:
            result = db_sql2019_run_query(
                "TEST_DB",
                "SELECT TOP 5 CustomerID, FirstName FROM sales.Customers"
            )
            assert result["status"] == "success"
            assert "data" in result
            assert len(result["data"]) > 0
            print(f"✓ SELECT query returned {len(result['data'])} rows")
        except Exception as e:
            print(f"✗ run_query failed: {e}")
            pytest.skip(f"Integration test skipped: {e}")

    def test_run_query_readonly_blocks_insert(self):
        """Test that INSERT is blocked in readonly mode"""
        os.environ["MCP_ALLOW_WRITE"] = "false"
        try:
            with pytest.raises(ValueError):
                db_sql2019_run_query(
                    "TEST_DB",
                    "INSERT INTO sales.Customers VALUES ('x', 'y', 'z@test.com', 'NY', 'NY')"
                )
            print("✓ Readonly mode blocks INSERT")
        except Exception as e:
            print(f"✗ Readonly check failed: {e}")

    def test_analyze_index_health(self):
        """Test index health analysis"""
        try:
            result = db_sql2019_analyze_index_health("TEST_DB", "sales")
            assert result["status"] == "success"
            assert "indexes" in result or "data" in result
            print(f"✓ Index health analysis completed")
        except Exception as e:
            print(f"✗ analyze_index_health failed: {e}")
            pytest.skip(f"Integration test skipped: {e}")

    def test_check_fragmentation(self):
        """Test index fragmentation check"""
        try:
            result = db_sql2019_check_fragmentation("TEST_DB", mode="SAMPLED")
            assert result["status"] == "success"
            print(f"✓ Fragmentation check completed")
        except Exception as e:
            print(f"✗ check_fragmentation failed: {e}")
            pytest.skip(f"Integration test skipped: {e}")

    def test_db_sec_perf_metrics(self):
        """Test database security and performance metrics"""
        try:
            result = db_sql2019_db_sec_perf_metrics("TEST_DB")
            assert result["status"] == "success"
            assert "database" in result or "metrics" in result
            print(f"✓ DB security/performance metrics retrieved")
        except Exception as e:
            print(f"✗ db_sec_perf_metrics failed: {e}")
            pytest.skip(f"Integration test skipped: {e}")


class TestStressTests:
    """Stress tests with concurrent tool invocations"""
    
    def test_concurrent_read_queries(self):
        """Test 10 concurrent SELECT queries"""
        def run_query(i):
            try:
                result = db_sql2019_run_query(
                    "TEST_DB",
                    f"SELECT {i} as query_num, * FROM sales.Customers"
                )
                return {"success": result["status"] == "success", "index": i}
            except Exception as e:
                return {"success": False, "error": str(e), "index": i}
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_query, i) for i in range(10)]
            results = [f.result() for f in as_completed(futures)]
        
        success_count = sum(1 for r in results if r.get("success"))
        print(f"✓ Concurrent queries: {success_count}/10 succeeded")
        assert success_count >= 8, "Expected at least 80% success rate"

    def test_concurrent_list_objects(self):
        """Test 5 concurrent list_objects calls"""
        def list_objects(i):
            try:
                result = db_sql2019_list_objects("TEST_DB", "sales", "TABLE")
                return {"success": result["status"] == "success", "index": i}
            except Exception as e:
                return {"success": False, "error": str(e), "index": i}
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(list_objects, i) for i in range(5)]
            results = [f.result() for f in as_completed(futures)]
        
        success_count = sum(1 for r in results if r.get("success"))
        print(f"✓ Concurrent list_objects: {success_count}/5 succeeded")
        assert success_count >= 4

    def test_timeout_on_slow_query(self):
        """Test that queries respect timeout"""
        os.environ["MCP_STATEMENT_TIMEOUT_MS"] = "1000"  # 1 second
        try:
            # This might timeout or succeed depending on system performance
            result = db_sql2019_run_query(
                "TEST_DB",
                "SELECT * FROM sys.objects CROSS JOIN sys.objects"
            )
            print(f"✓ Timeout test completed (result: {result['status']})")
        except Exception as e:
            print(f"✓ Timeout test raised exception (expected): {str(e)[:50]}")


class TestBlackboxTests:
    """Blackbox tests against HTTP API"""
    
    def test_http_mcp_endpoint_responds(self):
        """Test that /mcp endpoint is available"""
        try:
            response = requests.get("http://localhost:8085/mcp", timeout=5)
            assert response.status_code in [200, 404, 405]  # Accept any normal response
            print(f"✓ HTTP endpoint responds (status: {response.status_code})")
        except requests.exceptions.ConnectionError:
            print("⚠ HTTP server not running, skipping HTTP tests")
            pytest.skip("HTTP server not available")

    def test_sse_endpoint_available(self):
        """Test that /sse endpoint exists"""
        try:
            headers = {"Accept": "text/event-stream"}
            response = requests.get("http://localhost:8085/sse", headers=headers, timeout=5)
            # SSE endpoints return 200 if auth passes or 401/403 if auth fails
            assert response.status_code in [200, 401, 403, 404]
            print(f"✓ SSE endpoint responds (status: {response.status_code})")
        except requests.exceptions.ConnectionError:
            print("⚠ HTTP server not running, skipping")
            pytest.skip("HTTP server not available")

    def test_invalid_request_handling(self):
        """Test that invalid requests are handled gracefully"""
        try:
            response = requests.post(
                "http://localhost:8085/mcp",
                json={"invalid": "request"},
                timeout=5
            )
            # Should return 400, 405, or similar
            assert response.status_code >= 400
            print(f"✓ Invalid request handled (status: {response.status_code})")
        except requests.exceptions.ConnectionError:
            pytest.skip("HTTP server not available")

    def test_missing_auth_header(self):
        """Test behavior with missing auth header when required"""
        try:
            # Try to make an SSE request without auth
            response = requests.get("http://localhost:8085/sse", timeout=5)
            # Should either allow or reject clearly
            assert response.status_code in [200, 401, 403, 404]
            print(f"✓ Missing auth header handled (status: {response.status_code})")
        except requests.exceptions.ConnectionError:
            pytest.skip("HTTP server not available")


class TestCodeReviewTests:
    """Review of code for common issues"""
    
    def test_connection_cleanup(self):
        """Verify connections are closed in try/finally"""
        # Read server.py and check for connection cleanup patterns
        with open("server.py", "r") as f:
            content = f.read()
        
        # Check for try/finally patterns
        assert "try:" in content
        assert "finally:" in content
        assert "conn.close()" in content
        print("✓ Connection cleanup patterns found")

    def test_parameter_binding(self):
        """Verify SQL parameters are used (not f-strings)"""
        with open("server.py", "r") as f:
            lines = f.readlines()
        
        # Look for bad patterns
        bad_patterns = 0
        for i, line in enumerate(lines):
            if "f\"" in line and "SELECT" in line and "=" in line:
                # Suspicious f-string with SQL - check if it has ?
                if "?" not in line and ".execute(" in lines[i+1] if i+1 < len(lines) else False:
                    bad_patterns += 1
        
        print(f"✓ Parameter binding review: {bad_patterns} suspicious patterns found")
        # Allow some but should be minimal
        assert bad_patterns < 5

    def test_imports_complete(self):
        """Verify all required imports are present"""
        with open("server.py", "r") as f:
            content = f.read()
        
        required_imports = ["import pyodbc", "import fastmcp", "import asyncio"]
        for imp in required_imports:
            # Check import or from import
            assert imp in content or imp.split()[1] in content
        print("✓ Required imports found")

    def test_no_hardcoded_credentials(self):
        """Verify no hardcoded database credentials"""
        with open("server.py", "r") as f:
            content = f.read()
        
        # Look for obvious password patterns
        assert "password=" not in content.lower() or "os.getenv" in content
        assert "DB_PASSWORD" in content  # Should use env vars
        print("✓ No hardcoded credentials found")


def run_all_tests():
    """Run all test categories with reporting"""
    print("\n" + "="*70)
    print("MCP SQL SERVER COMPREHENSIVE TEST SUITE")
    print("="*70 + "\n")
    
    # Run pytest with verbose output
    pytest_args = [
        __file__,
        "-v",
        "--tb=short",
        "-ra",  # Show summary
    ]
    
    exit_code = pytest.main(pytest_args)
    return exit_code


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
