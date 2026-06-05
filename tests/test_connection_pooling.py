from __future__ import annotations

import pyodbc
import pytest

from src.db.connection_manager import ConnectionManager
from src.models import SqlInstanceConfig


class _FakeCursor:
    def __init__(self) -> None:
        self.description = [("value",)]
        self.rowcount = 1

    def execute(self, sql: str, *args) -> None:
        _ = sql
        _ = args

    def fetchone(self):
        return (1,)

    def fetchmany(self, _max_rows: int):
        return [(1,)]


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False
        self.autocommit = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _instance(
    pool_max: int = 10, pool_enabled: bool = True, acquire_timeout: int = 1
) -> SqlInstanceConfig:
    return SqlInstanceConfig(
        id="primary",
        host="localhost",
        database="master",
        auth_secret_ref="secret/sql/primary",
        pool_max=pool_max,
        pool_enabled=pool_enabled,
        pool_acquire_timeout_sec=acquire_timeout,
    )


def _resolver(_secret_ref: str) -> dict[str, str]:
    return {"username": "u", "password": "p"}


def test_pool_reuses_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeConnection] = []

    def _fake_connect(*_args, **_kwargs):
        conn = _FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)

    manager = ConnectionManager([_instance(pool_max=2)], secret_resolver=_resolver)

    with manager.connect("primary") as c1:
        assert c1 is not None
    with manager.connect("primary") as c2:
        assert c2 is not None

    assert len(created) == 1
    assert c1 is c2

    metrics = manager.get_pool_diagnostics()["primary"]
    assert metrics["created_total"] == 1
    assert metrics["reused_total"] >= 1
    assert metrics["available"] == 1
    assert metrics["in_use"] == 0


def test_pool_acquire_timeout_when_full(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_connect(*_args, **_kwargs):
        return _FakeConnection()

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)
    manager = ConnectionManager(
        [_instance(pool_max=1, acquire_timeout=0)], secret_resolver=_resolver
    )

    first = manager.connect("primary")
    conn = first.__enter__()
    assert conn is not None
    try:
        with pytest.raises(TimeoutError, match="Connection pool acquire timeout"):
            with manager.connect("primary"):
                pass
    finally:
        first.__exit__(None, None, None)


def test_close_all_pools_closes_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeConnection] = []

    def _fake_connect(*_args, **_kwargs):
        conn = _FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)
    manager = ConnectionManager([_instance(pool_max=2)], secret_resolver=_resolver)

    with manager.connect("primary"):
        pass

    manager.close_all_pools()

    assert created and all(c.closed for c in created)
    metrics = manager.get_pool_diagnostics()["primary"]
    assert metrics["available"] == 0
    assert metrics["in_use"] == 0


def test_execute_read_retries_once_on_transient_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailOnceCursor(_FakeCursor):
        def __init__(self, should_fail: bool) -> None:
            super().__init__()
            self._should_fail = should_fail

        def execute(self, sql: str, *args) -> None:
            _ = args
            if self._should_fail and "SELECT 1" not in sql:
                self._should_fail = False
                raise pyodbc.Error(
                    "08S01",
                    "[08S01] [Microsoft][ODBC Driver 17 for SQL Server]TCP Provider: Error code 0x2714 (10004) (SQLExecDirectW)",
                )
            _ = sql

    class _ConnWithCursor(_FakeConnection):
        def __init__(self, should_fail: bool) -> None:
            super().__init__()
            self._cursor = _FailOnceCursor(should_fail)

        def cursor(self) -> _FakeCursor:
            return self._cursor

    created: list[_ConnWithCursor] = []

    def _fake_connect(*_args, **_kwargs):
        should_fail = len(created) == 0
        conn = _ConnWithCursor(should_fail=should_fail)
        created.append(conn)
        return conn

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)

    manager = ConnectionManager(
        [_instance(pool_enabled=False)],
        secret_resolver=_resolver,
    )

    rows = manager.execute_read("primary", "SELECT 42 AS value", max_rows=1)

    assert rows == [{"value": 1}]
    assert len(created) == 2


# ---------------------------------------------------------------------------
# Pool resilience tests — verify CON-004, CON-005, CON-006 non-pooled paths
# ---------------------------------------------------------------------------


def test_database_override_bypasses_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """TASK-030: database_override creates a new connection (pooled=False),
    connection is NOT returned to pool."""
    created: list[_FakeConnection] = []

    def _fake_connect(*_args, **_kwargs):
        conn = _FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)

    manager = ConnectionManager(
        [_instance(pool_max=2, pool_enabled=True)], secret_resolver=_resolver
    )

    # With database_override: should create a new connection each time
    result1 = manager.execute_read_in_database(
        "primary", "OtherDB", "SELECT 1 AS n", max_rows=1
    )
    result2 = manager.execute_read_in_database(
        "primary", "OtherDB2", "SELECT 2 AS n", max_rows=1
    )

    assert result1["rows"] == [{"value": 1}]
    assert result2["rows"] == [{"value": 1}]
    # Both should create new connections (non-pooled)
    assert len(created) == 2

    # Pool should be untouched — no connections in available or in_use
    metrics = manager.get_pool_diagnostics()["primary"]
    assert metrics["available"] == 0
    assert metrics["in_use"] == 0
    assert metrics["created_total"] == 0


def test_pool_default_path_still_pooled(monkeypatch: pytest.MonkeyPatch) -> None:
    """TASK-031: When database_name is empty/omitted (database_override=None),
    the pooled path is used — connection is taken from and returned to pool."""
    created: list[_FakeConnection] = []

    def _fake_connect(*_args, **_kwargs):
        conn = _FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)

    manager = ConnectionManager(
        [_instance(pool_max=2, pool_enabled=True)], secret_resolver=_resolver
    )

    # First call: creates connection, returns to pool
    rows1 = manager.execute_read("primary", "SELECT 1 AS n", max_rows=1)
    assert rows1 == [{"value": 1}]
    assert len(created) == 1

    # Second call: reuses pooled connection
    rows2 = manager.execute_read("primary", "SELECT 2 AS n", max_rows=1)
    assert rows2 == [{"value": 1}]
    # Still only 1 connection created — reused from pool
    assert len(created) == 1

    metrics = manager.get_pool_diagnostics()["primary"]
    assert metrics["created_total"] == 1
    assert metrics["reused_total"] >= 1
    assert metrics["available"] == 1
    assert metrics["in_use"] == 0


def test_non_pooled_connection_closed_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-034: When database_override is set and an error occurs,
    _release_connection with pooled=False closes the connection."""
    created: list[_FakeConnection] = []

    def _fake_connect(*_args, **_kwargs):
        conn = _FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)

    class _FailingCursor(_FakeCursor):
        def execute(self, sql: str, *args) -> None:
            raise pyodbc.Error("42000", "Simulated SQL error")

    class _FailingConnection(_FakeConnection):
        def cursor(self) -> _FailingCursor:
            return _FailingCursor()

    # Override: first connect returns a failing connection
    call_count = [0]

    def _alternating_connect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _FailingConnection()
        conn = _FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr(
        "src.db.connection_manager.pyodbc.connect", _alternating_connect
    )

    manager = ConnectionManager(
        [_instance(pool_enabled=False)], secret_resolver=_resolver
    )

    # First call with non-pooled connection should fail
    with pytest.raises(pyodbc.Error, match="Simulated SQL error"):
        manager.execute_read_in_database(
            "primary", "BadDB", "SELECT fail", max_rows=1
        )

    # But subsequent calls with healthy connections should still work
    rows = manager.execute_read("primary", "SELECT 1 AS n", max_rows=1)
    assert rows == [{"value": 1}]
    # A new connection was created for the successful call
    assert len(created) == 1


def test_pool_not_corrupted_by_database_override_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-032: Simulate an error in a non-pooled tool call, then verify
    pooled path still works — fresh connections from pool are unaffected."""
    created: list[_FakeConnection] = []

    def _fake_connect(*_args, **_kwargs):
        conn = _FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)

    class _FailingCursor(_FakeCursor):
        def execute(self, sql: str, *args) -> None:
            raise pyodbc.Error("42000", "Simulated SQL error in override path")

    class _FailingConnection(_FakeConnection):
        def cursor(self) -> _FailingCursor:
            return _FailingCursor()

    call_count = [0]

    def _alternating_connect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _FailingConnection()
        conn = _FakeConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr(
        "src.db.connection_manager.pyodbc.connect", _alternating_connect
    )

    manager = ConnectionManager(
        [_instance(pool_max=2, pool_enabled=True)], secret_resolver=_resolver
    )

    # First: non-pooled call fails (database_override path)
    with pytest.raises(pyodbc.Error, match="Simulated SQL error"):
        manager.execute_read_in_database(
            "primary", "BadDB", "SELECT fail", max_rows=1
        )

    # Pool should be unaffected
    metrics = manager.get_pool_diagnostics()["primary"]
    assert metrics["available"] == 0
    assert metrics["in_use"] == 0

    # Subsequent pooled call should work fine
    rows = manager.execute_read("primary", "SELECT 1 AS n", max_rows=1)
    assert rows == [{"value": 1}]
    assert len(created) == 1

    # Pool should now have the connection
    metrics = manager.get_pool_diagnostics()["primary"]
    assert metrics["created_total"] == 1
    assert metrics["available"] == 1
