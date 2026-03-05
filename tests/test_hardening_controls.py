import json

import server


def _reset_rate_limit_state() -> None:
    server._RATE_LIMIT_REQUESTS.clear()
    server._RATE_LIMIT_VIOLATIONS.clear()
    server._RATE_LIMIT_BLOCKED_UNTIL.clear()


def test_table_scope_denies_out_of_allowlist(monkeypatch):
    monkeypatch.setattr(server.SETTINGS, "table_scope_enforced", True)
    monkeypatch.setattr(server, "_TABLE_SCOPE_PATTERNS", {"dbo.*"})

    try:
        server._enforce_table_scope_for_sql("SELECT TOP 1 name FROM sys.tables")
    except ValueError as exc:
        assert "Access denied by table scope policy" in str(exc)
    else:
        raise AssertionError("Expected table scope denial for sys.tables")


def test_rate_limiter_trips_breaker(monkeypatch):
    monkeypatch.setattr(server.SETTINGS, "rate_limit_enabled", True)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_window_seconds", 60)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_max_requests", 2)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_breaker_violations", 1)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_breaker_seconds", 5)
    _reset_rate_limit_state()

    assert server._rate_limit_check("ci-client") == (True, None)
    assert server._rate_limit_check("ci-client") == (True, None)

    allowed, retry_after = server._rate_limit_check("ci-client")
    assert allowed is False
    assert retry_after == 5



def test_audit_log_writes_exact_prompt(tmp_path, monkeypatch):
    audit_file = tmp_path / "query_audit.jsonl"

    monkeypatch.setattr(server.SETTINGS, "audit_log_queries", True)
    monkeypatch.setattr(server.SETTINGS, "audit_log_file", str(audit_file))
    monkeypatch.setattr(server.SETTINGS, "audit_log_include_params", False)

    prompt = "User asked for latest customer row"
    server._write_query_audit_record(
        tool_name="db_sql2019_run_query",
        database_name="TEST_DB",
        sql="SELECT TOP 1 * FROM dbo.Customers",
        params_json=None,
        prompt_context=prompt,
    )

    assert audit_file.exists()
    payload = json.loads(audit_file.read_text(encoding="utf-8").splitlines()[0])

    assert payload["tool"] == "db_sql2019_run_query"
    assert payload["database"] == "TEST_DB"
    assert payload["prompt"] == prompt
    assert payload["sql"] == "SELECT TOP 1 * FROM dbo.Customers"
    assert payload.get("prompt_sha256")
