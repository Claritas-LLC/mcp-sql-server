import unittest
from unittest.mock import patch

from mcp_sqlserver import server


class _FakeCursor:
    def execute(self, *_args, **_kwargs):
        return None


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def cursor(self):
        return _FakeCursor()

    def close(self):
        self.closed = True


class TestRunQueryInternal(unittest.TestCase):
    def test_ddl_programming_error_returns_legacy_dict(self):
        fake_conn = _FakeConnection()

        with patch.object(server, "validate_instance"), \
            patch.object(server, "_enforce_table_scope_for_sql"), \
            patch.object(server, "_write_query_audit_record"), \
            patch.object(server, "get_instance_config", return_value={"db_name": "master"}), \
            patch.object(server, "get_connection", return_value=fake_conn), \
            patch.object(server, "_fetch_limited", side_effect=server.pyodbc.ProgrammingError("No results")):
            result = server._run_query_internal(
                instance=1,
                database_name="master",
                sql="CREATE TABLE t(id INT)",
                enforce_readonly=False,
                tool_name="db_sql2019_create_object",
            )

        self.assertEqual(result, {"status": "success", "message": "DDL executed successfully."})
        self.assertTrue(fake_conn.closed)

    def test_non_ddl_programming_error_is_raised(self):
        fake_conn = _FakeConnection()

        with patch.object(server, "validate_instance"), \
            patch.object(server, "_require_readonly"), \
            patch.object(server, "_enforce_table_scope_for_sql"), \
            patch.object(server, "_write_query_audit_record"), \
            patch.object(server, "get_instance_config", return_value={"db_name": "master"}), \
            patch.object(server, "get_connection", return_value=fake_conn), \
            patch.object(server, "_fetch_limited", side_effect=server.pyodbc.ProgrammingError("No results")):
            with self.assertRaises(server.pyodbc.ProgrammingError):
                server._run_query_internal(
                    instance=1,
                    database_name="master",
                    sql="SELECT 1",
                    enforce_readonly=True,
                    tool_name="db_sql2019_run_query",
                )

        self.assertTrue(fake_conn.closed)


if __name__ == "__main__":
    unittest.main()
