from mcp_sqlserver import server


class _FakeCursor:
    def __init__(self):
        self.sql_calls = []
        self._fetches = [(5,), (3,)]

    def fetchone(self):
        if self._fetches:
            return self._fetches.pop(0)
        return None


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        return None


def test_generate_model_diagram_quotes_database_identifier(monkeypatch):
    fake_cursor = _FakeCursor()

    monkeypatch.setattr(server, "GENERATIVE_UI_AVAILABLE", True)
    monkeypatch.setattr(server, "get_instance_config", lambda instance: {"db_server": "localhost"})
    monkeypatch.setattr(server, "get_connection", lambda instance=1: _FakeConnection(fake_cursor))

    def _capture_execute(cur, sql, params=None):
        cur.sql_calls.append(sql)

    monkeypatch.setattr(server, "_execute_safe", _capture_execute)

    malicious_name = "safe_db]]; DROP TABLE users;--"
    result = server.db_sql2019_generate_model_diagram(database_name=malicious_name, instance=1)

    assert result["status"] == "ready"
    assert len(fake_cursor.sql_calls) == 2
    assert "DROP TABLE users" in fake_cursor.sql_calls[0]
    assert "[safe_db]]]]; DROP TABLE users;--].INFORMATION_SCHEMA.TABLES" in fake_cursor.sql_calls[0]
    assert "[safe_db]]]]; DROP TABLE users;--].INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in fake_cursor.sql_calls[1]
