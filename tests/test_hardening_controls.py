import json
import hashlib

import server


def _reset_rate_limit_state() -> None:
    server._RATE_LIMIT_REQUESTS.clear()
    server._RATE_LIMIT_VIOLATIONS.clear()
    server._RATE_LIMIT_BLOCKED_UNTIL.clear()
    server._RATE_LIMIT_CHECK_COUNTER = 0


def test_table_scope_denies_out_of_allowlist(monkeypatch):
    monkeypatch.setattr(server.SETTINGS, "table_scope_enforced", True)
    monkeypatch.setattr(server, "_TABLE_SCOPE_PATTERNS", {"dbo.*"})

    try:
        server._enforce_table_scope_for_sql("SELECT TOP 1 name FROM sys.tables")
    except ValueError as exc:
        assert "Access denied by table scope policy" in str(exc)
    else:
        raise AssertionError("Expected table scope denial for sys.tables")


def test_extract_referenced_tables_includes_dml_targets():
    sql = "INSERT INTO sales.Orders (OrderID) VALUES (1); UPDATE dbo.Customers SET Name = 'A'; DELETE FROM [archive].[Orders] WHERE OrderID = 1; MERGE INTO dbo.Inventory AS t USING dbo.SourceInventory AS s ON t.Id = s.Id WHEN MATCHED THEN UPDATE SET t.Qty = s.Qty;"

    refs = server._extract_referenced_tables(sql)

    assert ("sales", "orders") in refs
    assert ("dbo", "customers") in refs
    assert ("archive", "orders") in refs
    assert ("dbo", "inventory") in refs


def test_extract_referenced_tables_includes_cte_names_and_defaults_schema():
    sql = "WITH SalesCte AS (SELECT * FROM sales.Orders), RegionCte AS (SELECT * FROM dbo.Regions) SELECT * FROM SalesCte JOIN RegionCte ON 1 = 1"

    refs = server._extract_referenced_tables(sql)

    assert ("dbo", "salescte") in refs
    assert ("dbo", "regioncte") in refs
    assert ("sales", "orders") in refs
    assert ("dbo", "regions") in refs


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


def test_rate_limiter_non_breaker_uses_window_retry_after(monkeypatch):
    monkeypatch.setattr(server.SETTINGS, "rate_limit_enabled", True)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_window_seconds", 10)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_max_requests", 2)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_breaker_violations", 3)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_breaker_seconds", 60)
    _reset_rate_limit_state()

    server._RATE_LIMIT_REQUESTS["ci-client"] = [100.0, 104.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: 105.0)

    allowed, retry_after = server._rate_limit_check("ci-client")

    assert allowed is False
    assert retry_after == 5
    assert server._RATE_LIMIT_VIOLATIONS["ci-client"] == 1
    assert "ci-client" not in server._RATE_LIMIT_BLOCKED_UNTIL


def test_rate_limit_cleanup_prunes_stale_keys(monkeypatch):
    monkeypatch.setattr(server.SETTINGS, "rate_limit_window_seconds", 60)
    monkeypatch.setattr(server.SETTINGS, "rate_limit_breaker_seconds", 10)
    _reset_rate_limit_state()

    now = 10_000.0
    stale_time = now - (server.SETTINGS.rate_limit_window_seconds + server.SETTINGS.rate_limit_breaker_seconds) - 1.0

    server._RATE_LIMIT_REQUESTS["stale"] = [stale_time]
    server._RATE_LIMIT_VIOLATIONS["stale"] = 2
    server._RATE_LIMIT_BLOCKED_UNTIL["stale"] = stale_time + 5

    server._RATE_LIMIT_REQUESTS["empty"] = []
    server._RATE_LIMIT_VIOLATIONS["empty"] = 1
    server._RATE_LIMIT_BLOCKED_UNTIL["empty"] = now + 30

    server._RATE_LIMIT_REQUESTS["fresh"] = [now - 1]
    server._RATE_LIMIT_VIOLATIONS["fresh"] = 1
    server._RATE_LIMIT_BLOCKED_UNTIL["fresh"] = now + 5

    removed = server._rate_limit_cleanup(now)

    assert removed == 2
    assert "stale" not in server._RATE_LIMIT_REQUESTS
    assert "stale" not in server._RATE_LIMIT_VIOLATIONS
    assert "stale" not in server._RATE_LIMIT_BLOCKED_UNTIL
    assert "empty" not in server._RATE_LIMIT_REQUESTS
    assert "empty" not in server._RATE_LIMIT_VIOLATIONS
    assert "empty" not in server._RATE_LIMIT_BLOCKED_UNTIL
    assert "fresh" in server._RATE_LIMIT_REQUESTS
    assert "fresh" in server._RATE_LIMIT_VIOLATIONS
    assert "fresh" in server._RATE_LIMIT_BLOCKED_UNTIL



def test_audit_log_redacts_prompt_by_default(tmp_path, monkeypatch):
    audit_file = tmp_path / "query_audit.jsonl"

    monkeypatch.setattr(server.SETTINGS, "audit_log_queries", True)
    monkeypatch.setattr(server.SETTINGS, "audit_log_file", str(audit_file))
    monkeypatch.setattr(server.SETTINGS, "audit_log_include_params", False)
    monkeypatch.setattr(server.SETTINGS, "allow_raw_prompts", False)

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
    assert payload["sql"] == "SELECT TOP 1 * FROM dbo.Customers"
    assert "prompt" not in payload
    assert payload.get("prompt_sha256") == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert payload.get("prompt_redaction_token", "").startswith("[REDACTED_PROMPT:")
    assert payload.get("prompt_storage_mode") == "hashed_redacted"


def test_audit_log_allows_raw_prompt_when_explicitly_enabled(tmp_path, monkeypatch):
    audit_file = tmp_path / "query_audit_raw.jsonl"

    monkeypatch.setattr(server.SETTINGS, "audit_log_queries", True)
    monkeypatch.setattr(server.SETTINGS, "audit_log_file", str(audit_file))
    monkeypatch.setattr(server.SETTINGS, "audit_log_include_params", False)
    monkeypatch.setattr(server.SETTINGS, "allow_raw_prompts", True)

    prompt = "User asked for latest customer row"
    server._write_query_audit_record(
        tool_name="db_sql2019_run_query",
        database_name="TEST_DB",
        sql="SELECT TOP 1 * FROM dbo.Customers",
        params_json=None,
        prompt_context=prompt,
    )

    payload = json.loads(audit_file.read_text(encoding="utf-8").splitlines()[0])

    assert payload.get("prompt") == prompt
    assert payload.get("prompt_sha256") == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert payload.get("prompt_storage_mode") == "raw_opt_in"
    assert payload.get("raw_prompt_storage_enabled") is True


def test_audit_log_includes_api_caller_identity(tmp_path, monkeypatch):
    audit_file = tmp_path / "query_audit_caller.jsonl"

    monkeypatch.setattr(server.SETTINGS, "audit_log_queries", True)
    monkeypatch.setattr(server.SETTINGS, "audit_log_file", str(audit_file))
    monkeypatch.setattr(server.SETTINGS, "audit_log_include_params", False)
    monkeypatch.setattr(server, "_current_api_caller", lambda: "token:abc123def456")

    server._write_query_audit_record(
        tool_name="db_sql2019_run_query",
        database_name="TEST_DB",
        sql="SELECT 1",
        params_json=None,
        prompt_context=None,
    )

    payload = json.loads(audit_file.read_text(encoding="utf-8").splitlines()[0])
    assert payload.get("api_caller") == "token:abc123def456"
    assert payload.get("db_user") == server.SETTINGS.db_user


def test_parse_schema_qualified_name_supports_explicit_and_default_schema():
    schema_name, table_name = server._parse_schema_qualified_name("sales.Customers")
    assert schema_name == "sales"
    assert table_name == "Customers"

    schema_name, table_name = server._parse_schema_qualified_name("[reporting].[DailySummary]")
    assert schema_name == "reporting"
    assert table_name == "DailySummary"

    schema_name, table_name = server._parse_schema_qualified_name("Customers")
    assert schema_name == "dbo"
    assert table_name == "Customers"


def test_generate_ddl_enforces_table_scope_with_parsed_schema(monkeypatch):
    captured: dict[str, str] = {}

    def _capture_enforce(schema_name: str, table_name: str) -> None:
        captured["schema"] = schema_name
        captured["table"] = table_name
        raise RuntimeError("scope-checked")

    monkeypatch.setattr(server, "_enforce_table_scope_for_ident", _capture_enforce)

    try:
        server.db_sql2019_generate_ddl(
            database_name="TEST_DB",
            object_name="sales.Customers",
            object_type="table",
        )
    except RuntimeError as exc:
        assert str(exc) == "scope-checked"
    else:
        raise AssertionError("Expected sentinel exception after scope enforcement")

    assert captured == {"schema": "sales", "table": "Customers"}
