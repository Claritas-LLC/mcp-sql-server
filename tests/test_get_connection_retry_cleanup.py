import unittest
from unittest.mock import patch

from mcp_sqlserver import server


class _FakeConn:
    def __init__(self):
        self.autocommit = False
        self.closed = False

    def close(self):
        self.closed = True


class _AlwaysFailPool:
    def get(self, timeout=5):
        raise server.queue.Empty()


class TestGetConnectionRetryCleanup(unittest.TestCase):
    def test_replacement_connection_closed_when_scope_reset_fails(self):
        replacement_conn = _FakeConn()

        with patch.object(server, "validate_instance"), \
            patch.object(server, "_CONN_POOLS", {1: _AlwaysFailPool()}), \
            patch.object(server, "_CONN_POOL_LOCKS", {1: object()}), \
            patch.object(server, "_connection_string", return_value="DRIVER=x;"), \
            patch.object(server.pyodbc, "connect", return_value=replacement_conn), \
            patch.object(server, "_ensure_connection_database_scope", side_effect=[Exception("first scope fail"), Exception("second scope fail")]), \
            patch.object(server.logger, "warning") as mock_warning:
            with self.assertRaises(Exception):
                server.get_connection(database="master", instance=1)

        self.assertTrue(replacement_conn.closed)
        self.assertTrue(replacement_conn.autocommit)
        self.assertTrue(any("Failed scope reset on replacement pooled connection" in str(call.args[0]) for call in mock_warning.call_args_list))


if __name__ == "__main__":
    unittest.main()
