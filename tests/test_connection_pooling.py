from __future__ import annotations

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
