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
