from __future__ import annotations

import pytest

from src.db.connection_manager import ConnectionManager
from src.models import SqlInstanceConfig


class _FakeProcCursorWithRows:
    def __init__(self) -> None:
        self.description = [("id",), ("name",)]
        self.rowcount = 2
        self.executed_sql: str | None = None

    def execute(self, sql: str, params: list[object] | None = None) -> None:
        self.executed_sql = sql
        _ = params

    def fetchall(self):
        return [(1, "alpha"), (2, "beta")]


class _FakeProcCursorNoRows:
    def __init__(self) -> None:
        self.description = None
        self.rowcount = 0
        self.executed_sql: str | None = None

    def execute(self, sql: str, params: list[object] | None = None) -> None:
        self.executed_sql = sql
        _ = params


class _FakeConnection:
    def __init__(self, cursor_obj: object) -> None:
        self._cursor_obj = cursor_obj
        self.autocommit = False
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor_obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _instance() -> SqlInstanceConfig:
    return SqlInstanceConfig(
        id="primary",
        host="localhost",
        database="master",
        auth_secret_ref="secret/sql/primary",
        pool_enabled=False,
    )


def _resolver(_secret_ref: str) -> dict[str, str]:
    return {"username": "u", "password": "p"}


def test_execute_proc_returns_result_set_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeProcCursorWithRows()

    def _fake_connect(*_args, **_kwargs):
        return _FakeConnection(cursor)

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)
    manager = ConnectionManager([_instance()], secret_resolver=_resolver)

    result = manager.execute_proc("primary", "dbo.usp_Test", [1])

    assert result["status"] == "ok"
    assert result["procedure"] == "dbo.usp_Test"
    assert result["has_result_set"] is True
    assert result["rowcount"] == 2
    assert result["columns"] == ["id", "name"]
    assert result["rows"] == [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]


def test_execute_proc_returns_metadata_when_no_result_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeProcCursorNoRows()

    def _fake_connect(*_args, **_kwargs):
        return _FakeConnection(cursor)

    monkeypatch.setattr("src.db.connection_manager.pyodbc.connect", _fake_connect)
    manager = ConnectionManager([_instance()], secret_resolver=_resolver)

    result = manager.execute_proc("primary", "dbo.usp_NoRows", [42])

    assert result["status"] == "ok"
    assert result["procedure"] == "dbo.usp_NoRows"
    assert result["has_result_set"] is False
    assert result["rowcount"] == 0
    assert result["columns"] == []
    assert result["rows"] == []