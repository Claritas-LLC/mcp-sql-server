import server


def _call_tool(tool, *args, **kwargs):
    fn = getattr(tool, "fn", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return tool(*args, **kwargs)


def test_list_databases_includes_test_db():
    databases = _call_tool(server.db_sql2019_list_databases)
    assert any(db.upper() == "TEST_DB" for db in databases)


def test_list_tables_returns_sales_customers():
    tables = _call_tool(server.db_sql2019_list_tables, "TEST_DB", schema_name="sales")
    assert any(row.get("TABLE_NAME") == "Customers" for row in tables)


def test_get_schema_returns_columns():
    schema = _call_tool(server.db_sql2019_get_schema, "TEST_DB", "Customers", "sales")
    assert "columns" in schema
    assert any(col.get("COLUMN_NAME") == "CustomerID" for col in schema["columns"])


def test_execute_query_returns_rows():
    rows = _call_tool(server.db_sql2019_execute_query, "TEST_DB", "SELECT TOP 2 * FROM sales.Customers")
    assert isinstance(rows, list)
    assert rows


def test_list_objects_tables():
    result = _call_tool(server.db_sql2019_list_objects, "TEST_DB", schema="sales", object_type="TABLE")
    assert any(row.get("TABLE_NAME") == "Customers" for row in result)


def test_run_query_alias():
    rows = _call_tool(server.db_sql2019_run_query, "TEST_DB", "SELECT TOP 1 * FROM sales.Customers")
    assert isinstance(rows, list)


def test_ping():
    result = _call_tool(server.db_sql2019_ping)
    assert result.get("status") == "ok"


def test_get_index_fragmentation():
    result = _call_tool(
        server.db_sql2019_get_index_fragmentation,
        "TEST_DB",
        schema="sales",
        min_fragmentation=0.0,
        min_page_count=1,
        limit=5
    )
    assert isinstance(result, list)


def test_analyze_table_health():
    result = _call_tool(server.db_sql2019_analyze_table_health, "TEST_DB", "sales", "Customers")
    assert "table_info" in result
    assert "indexes" in result


def test_db_stats():
    result = _call_tool(server.db_sql2019_db_stats, "TEST_DB")
    assert isinstance(result, dict)
    assert result.get("DatabaseName") == "TEST_DB"


def test_server_info_mcp():
    result = _call_tool(server.db_sql2019_server_info_mcp)
    assert "server_name" in result
    assert "server_version" in result


def test_show_top_queries():
    result = _call_tool(server.db_sql2019_show_top_queries, "TEST_DB")
    assert "database" in result
    assert "query_store_enabled" in result


def test_check_fragmentation():
    result = _call_tool(
        server.db_sql2019_check_fragmentation,
        "TEST_DB",
        min_fragmentation=0.0,
        min_page_count=1,
        include_recommendations=False
    )
    assert "database" in result
    assert "fragmentation_summary" in result


def test_db_sec_perf_metrics():
    result = _call_tool(server.db_sql2019_db_sec_perf_metrics, profile="oltp")
    assert result.get("profile") == "oltp"
    assert "security_assessment" in result
    assert "performance_metrics" in result
