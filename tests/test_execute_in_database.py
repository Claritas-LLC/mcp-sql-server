import unittest
from unittest.mock import patch, MagicMock

from mcp_sqlserver import server


class TestExecuteInDatabase(unittest.TestCase):
    def test_execute_in_database_calls_execute_safe_for_use_and_sql(self):
        cur = MagicMock()
        db = "mydb"
        sql = "SELECT 1"
        params = [1]

        with patch.object(server, "_execute_safe", autospec=True) as mock_safe:
            server._execute_in_database(cur, db, sql, params)

            # First call should be USE [mydb]
            mock_safe.assert_any_call(cur, f"USE [{db}]")
            # Then the actual SQL with params
            mock_safe.assert_any_call(cur, sql, params)

    def test_execute_in_database_invalid_database_raises(self):
        cur = MagicMock()
        with self.assertRaises(ValueError):
            server._execute_in_database(cur, "invalid-db!", "SELECT 1")

    def test_execute_in_database_propagates_errors_from_execute_safe(self):
        cur = MagicMock()
        db = "mydb"
        sql = "SELECT 1"

        with patch.object(server, "_execute_safe", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                server._execute_in_database(cur, db, sql)


if __name__ == "__main__":
    unittest.main()
