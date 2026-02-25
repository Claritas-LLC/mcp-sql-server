import pytest
import asyncio
import os
import sys
import json
from unittest.mock import MagicMock, patch
import importlib

# Add parent directory to path to import server
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Late import of server to allow for env var patching
import server

@pytest.fixture(scope="module", autouse=True)
def setup_env():
    """Set up environment variables for testing"""
    with patch.dict(os.environ, {
        "DB_SERVER": os.environ.get("DB_SERVER", "127.0.0.1"),
        "DB_PORT": os.environ.get("DB_PORT", "1433"),
        "DB_USER": os.environ.get("DB_USER", "sa"),
        "DB_PASSWORD": os.environ.get("DB_PASSWORD", "McpTestPassword123!"),
        "DB_NAME": os.environ.get("DB_NAME", "testdb"),
        "DB_DRIVER": os.environ.get("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
        "DB_ENCRYPT": "no",
        "DB_TRUST_CERT": "yes",
        "MCP_ALLOW_WRITE": "true",
        "MCP_CONFIRM_WRITE": "true",
        "FASTMCP_AUTH_TYPE": "none",
        "MCP_TRANSPORT": "stdio",
        "MCP_SKIP_CONFIRMATION": "true"
    }):
        importlib.reload(server)
        yield

from server import (
    db_sql2019_list_objects,
    db_sql2019_run_query,
    db_sql2019_check_fragmentation,
    db_sql2019_analyze_index_health,
    mcp,
    get_connection # Import to check connectivity
)



def is_db_available():
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception:
        return False

db_required = pytest.mark.skipif(not is_db_available(), reason="Database not available")

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@db_required
class TestUnit:
    """Unit tests for tool functions"""

    def test_list_tables(self):
        # This is effectively an integration test as it hits the DB, 
        # but verifies the tool logic
        result = db_sql2019_list_objects(database_name="testdb", object_type="table")
        table_names = [t['name'] for t in result]
        assert "products" in table_names

    def test_describe_table(self):
        # Using sp_columns to simulate describe
        result = db_sql2019_run_query(database_name="testdb", sql_query="EXEC sp_columns @table_name = 'products'")
        columns = [row['COLUMN_NAME'] for row in result['rows']]
        assert "id" in columns
        assert "price" in columns

    def test_run_query_select(self):
        result = db_sql2019_run_query(database_name="testdb", sql_query="SELECT COUNT(*) as count FROM products")
        # Result is a dict with 'rows' key
        assert result["rows"][0]["count"] == 5

    def test_run_query_parameterized(self):
        # The tool expects parameters as a list
        params = [1]
        result = db_sql2019_run_query(database_name="testdb", sql_query="SELECT name FROM products WHERE id = ?", parameters=params)
        assert result["rows"][0]["name"] == "Laptop"


@db_required
class TestIntegration:
    """Integration scenarios"""

    # Skipped: db_sql2019_create_object and db_sql2019_drop_object do not exist in server.py
    # def test_create_and_drop_view(self):
    #     pass

@db_required
class TestStress:
    """Stress testing performance"""
    
    def test_multiple_queries(self):
        import time
        start = time.time()
        for i in range(50):
            db_sql2019_run_query(database_name="testdb", sql_query="SELECT * FROM products")
        end = time.time()
        duration = end - start
        print(f"50 queries took {duration:.2f}s")
        assert duration < 20 # Should be very fast locally

@db_required
class TestBlackbox:
    """Blackbox testing via MCP protocol simulation"""
    # This would typically involve running the MCP server process and communicating via stdio
    # For now, we simulate the tool calls which is the core logic
    
    def test_fragmentation_check(self):
        result = db_sql2019_check_fragmentation(database_name="testdb")
        # Should return a dict with fragmentation analysis
        assert isinstance(result, dict)
        # If we had fragmentation, we'd check for specific keys
        if "fragmented_indexes" in result:
            assert isinstance(result["fragmented_indexes"], list)

    # Skipped: db_sql2019_analyze_indexes does not exist in server.py
    # def test_analyze_indexes(self):
    #     pass

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
