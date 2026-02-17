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
    db_sql2019_analyze_logical_data_model,
    db_sql2019_check_fragmentation,
    db_sql2019_analyze_indexes,
    db_sql2019_create_object,
    db_sql2019_drop_object,
    mcp,
    get_connection # Import to check connectivity
)

@pytest.fixture(scope="class")
def setup_products_table(request):
    """Create and populate a products table for testing"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Create table
        cursor.execute("""
            CREATE TABLE products (
                id INT PRIMARY KEY,
                name NVARCHAR(100),
                price DECIMAL(10, 2)
            );
        """)
        # Insert data
        cursor.execute("INSERT INTO products (id, name, price) VALUES (1, 'Laptop', 1200.00);")
        cursor.execute("INSERT INTO products (id, name, price) VALUES (2, 'Mouse', 25.00);")
        conn.commit()
        yield
    finally:
        cursor.execute("DROP TABLE products;")
        conn.commit()
        cursor.close()
        conn.close()

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

@pytest.mark.usefixtures("setup_products_table")
@db_required
class TestUnit:
    """Unit tests for tool functions"""

    def test_list_tables(self):
        # This is effectively an integration test as it hits the DB, 
        # but verifies the tool logic
        result = db_sql2019_list_objects.fn(object_type="table")
        table_names = [t['name'] for t in result]
        assert "products" in table_names

    def test_describe_table(self):
        # Using sp_columns to simulate describe
        result = db_sql2019_run_query.fn("EXEC sp_columns @table_name = 'products'")
        columns = [row['COLUMN_NAME'] for row in result['rows']]
        assert "id" in columns
        assert "price" in columns

    def test_run_query_select(self):
        result = db_sql2019_run_query.fn("SELECT COUNT(*) as count FROM products")
        # Result is a dict with 'rows' key
        assert result["rows"][0]["count"] == 2

    def test_run_query_parameterized(self):
        # The tool expects parameters as a JSON string of a list
        params_json = json.dumps([1])
        result = db_sql2019_run_query.fn("SELECT name FROM products WHERE id = ?", params_json=params_json)
        assert result["rows"][0]["name"] == "Laptop"

    def test_analyze_data_model(self):
        result = db_sql2019_analyze_logical_data_model.fn()
        # The result contains a summary and a URL
        assert "summary" in result
        assert result["summary"]["entities"] >= 3 # products, customers, orders
        assert "report_url" in result

@pytest.mark.usefixtures("setup_products_table")
@db_required
class TestIntegration:
    """Integration scenarios"""

    def test_create_and_drop_view(self):
        view_name = "test_view_products"
        
        # Create
        # server.py: db_sql2019_create_object(object_type, object_name, schema, parameters={'query': ...})
        result = db_sql2019_create_object.fn(
            object_type="view",
            object_name=view_name,
            schema="dbo",
            parameters={"query": "SELECT name, price FROM products"}
        )
        assert f"View '{view_name}' created" in result or "created successfully" in result

        # Verify
        tables = db_sql2019_list_objects.fn(object_type="view", schema="dbo")
        view_names = [t['name'] for t in tables]
        assert view_name in view_names

        # Drop
        result = db_sql2019_drop_object.fn(
            object_type="view",
            object_name=view_name,
            schema="dbo"
        )
        assert f"View '{view_name}' dropped" in result or "dropped successfully" in result

@pytest.mark.usefixtures("setup_products_table")
@db_required
class TestStress:
    """Stress testing performance"""
    
    def test_multiple_queries(self):
        import time
        start = time.time()
        for i in range(50):
            db_sql2019_run_query.fn("SELECT * FROM products")
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
        result = db_sql2019_check_fragmentation.fn()
        # Fresh DB shouldn't have fragmentation, but tool should return a list (possibly empty)
        assert isinstance(result, list)
        # If we had fragmentation, we'd check for specific keys
        if result:
             assert "object_name" in result[0]

    def test_analyze_indexes(self):
        result = db_sql2019_analyze_indexes.fn()
        # Should return analysis dict
        assert "unused_indexes" in result
        assert "missing_indexes" in result

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
