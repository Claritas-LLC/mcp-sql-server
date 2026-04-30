import pytest

from mcp_sqlserver import server


def test_is_sql_readonly_allows_select():
    assert server._is_sql_readonly("SELECT 1") is True


def test_is_sql_readonly_blocks_write():
    assert server._is_sql_readonly("UPDATE sales.Customers SET City = 'X'") is False


def test_require_readonly_raises_for_write():
    with pytest.raises(ValueError):
        server._require_readonly("DELETE FROM sales.Customers")
