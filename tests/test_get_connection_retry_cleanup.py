import unittest
from threading import Lock
from unittest.mock import patch

from mcp_sqlserver import server


class _FakeConn:
    def __init__(self):
        self.autocommit = False
        self.closed = False

    def cursor(self):
        return self

    def execute(self, *_args, **_kwargs):
        return None

    def close(self):
        self.closed = True


class _AlwaysFailPool:
    def get(self, timeout=5):
        raise server.queue.Empty()


class TestGetConnectionRetryCleanup(unittest.TestCase):
    def test_pool_exhaustion_uses_instance_default_database(self):
        replacement_conn = _FakeConn()

        with patch.object(server, "validate_instance"), \
            patch.object(server, "_instance_connection_database", return_value="test1"), \
            patch.object(server, "_CONN_POOLS", {1: _AlwaysFailPool()}), \
            patch.object(server, "_CONN_POOL_LOCKS", {1: Lock()}), \
            patch.object(server, "_connection_string", return_value="DRIVER=x;DATABASE=test1;") as mock_connection_string, \
            patch.object(server.pyodbc, "connect", return_value=replacement_conn):
            pooled = server.get_connection(database="master", instance=1)

        self.assertIsInstance(pooled, server.PooledConnection)
        self.assertTrue(replacement_conn.autocommit)
        mock_connection_string.assert_called_once_with("test1", 1)


if __name__ == "__main__":
    unittest.main()
