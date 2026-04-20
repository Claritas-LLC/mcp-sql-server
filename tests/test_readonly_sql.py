import pytest

from mcp_sqlserver import server


def test_is_sql_readonly_allows_select():
    assert server._is_sql_readonly("SELECT 1") is True


def test_is_sql_readonly_blocks_write():
    assert server._is_sql_readonly("UPDATE sales.Customers SET City = 'X'") is False


def test_require_readonly_raises_for_write():
    with pytest.raises(ValueError):
        server._require_readonly("DELETE FROM sales.Customers")


def test_validate_single_statement_blocks_chained():
    sql = "SELECT 1; DROP TABLE users;"
    assert server._validate_single_statement(sql) is True

def test_validate_single_statement_allows_single():
    sql = "SELECT 1"
    assert server._validate_single_statement(sql) is False

def test_validate_single_statement_allows_trailing_semicolon():
    sql = "SELECT 1;   "
    assert server._validate_single_statement(sql) is False

def test_validate_single_statement_blocks_multiple_semicolons():
    sql = "SELECT 1;;"
    assert server._validate_single_statement(sql) is True

def test_validate_single_statement_ignores_semicolon_in_string():
    sql = "SELECT ';' as semi"
    assert server._validate_single_statement(sql) is False

def test_validate_single_statement_comment_token_in_string():
    sql = "SELECT '-- not a comment'; DROP TABLE users;"
    assert server._validate_single_statement(sql) is True
    sql2 = "SELECT '/* not a comment */'; DROP TABLE users;"
    assert server._validate_single_statement(sql2) is True
    sql3 = "SELECT '-- not a comment' as col"
    assert server._validate_single_statement(sql3) is False
