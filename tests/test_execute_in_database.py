import unittest
from unittest.mock import patch, MagicMock

from mcp_sqlserver import server


class TestExecuteInDatabase(unittest.TestCase):
    def test_execute_in_database_wraps_with_sp_executesql(self):
        cur = MagicMock()
        db = "mydb"
        sql = "SELECT 1"

        with patch.object(server, "_execute_safe", autospec=True) as mock_safe:
            server._execute_in_database(cur, db, sql)

            mock_safe.assert_called_once_with(cur, f"EXEC [{db}].sys.sp_executesql N'SELECT 1'", None)

    def test_execute_in_database_rewrites_positional_params(self):
        cur = MagicMock()
        db = "mydb"
        sql = "SELECT * FROM dbo.Users WHERE Id = ? AND Name = ?"
        params = [7, "alice"]

        with patch.object(server, "_execute_safe", autospec=True) as mock_safe:
            server._execute_in_database(cur, db, sql, params)

            mock_safe.assert_called_once_with(
                cur,
                "EXEC [mydb].sys.sp_executesql N'SELECT * FROM dbo.Users WHERE Id = @p1 AND Name = @p2', N'@p1 BIGINT, @p2 NVARCHAR(MAX)', @p1 = ?, @p2 = ?",
                (7, "alice"),
            )

    def test_execute_in_database_ignores_question_marks_inside_strings(self):
        scoped_sql, scoped_params = server._build_scoped_exec_sql(
            "mydb",
            "SELECT '?' AS literal_value, Col FROM dbo.Users WHERE Id = ?",
            [5],
        )

        self.assertIn("SELECT ''?'' AS literal_value, Col FROM dbo.Users WHERE Id = @p1", scoped_sql)
        self.assertEqual(scoped_params, (5,))

    def test_execute_in_database_invalid_database_raises(self):
        cur = MagicMock()
        with self.assertRaises(ValueError):
            server._execute_in_database(cur, "invalid-db!", "SELECT 1")

    def test_execute_in_database_placeholder_mismatch_raises(self):
        cur = MagicMock()
        with self.assertRaises(ValueError):
            server._execute_in_database(cur, "mydb", "SELECT * FROM dbo.Users WHERE Id = ?", [])

    def test_execute_in_database_propagates_errors_from_execute_safe(self):
        cur = MagicMock()
        db = "mydb"
        sql = "SELECT 1"

        with patch.object(server, "_execute_safe", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                server._execute_in_database(cur, db, sql)

    def test_execute_in_database_bypasses_scope_when_matches_pooled_default(self):
        cur = MagicMock()
        with patch.object(server, "_execute_safe", autospec=True) as mock_safe:
            server._execute_in_database(
                cur, "mydb", "SELECT 1", None, pooled_instance_default_db="mydb"
            )
        mock_safe.assert_called_once_with(cur, "SELECT 1", None)

    def test_execute_in_database_uses_sp_executesql_when_not_pooled_default(self):
        cur = MagicMock()
        with patch.object(server, "_execute_safe", autospec=True) as mock_safe:
            server._execute_in_database(
                cur, "otherdb", "SELECT 1", None, pooled_instance_default_db="mydb"
            )
        called_sql = mock_safe.call_args[0][1]
        self.assertIn("sp_executesql", called_sql)


if __name__ == "__main__":
    unittest.main()
