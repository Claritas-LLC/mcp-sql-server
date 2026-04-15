from mcp_sqlserver import server


class _FixedUuid:
    hex = "abc123fixed"


def test_open_logical_model_returns_html_by_default(monkeypatch):
    model_result = {"summary": {"entity_count": 2}, "issues": {}}
    html = "<html>report</html>"

    monkeypatch.setattr(server, "_analyze_logical_data_model_internal", lambda *args, **kwargs: model_result)
    monkeypatch.setattr(server, "_render_data_model_html", lambda result, issues: html)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: _FixedUuid())
    monkeypatch.setattr(server, "_persist_report_html", lambda report_id, report_html: None)
    monkeypatch.setattr(server, "get_instance_config", lambda instance: {"db_name": "TEST_DB"})

    output = server.db_sql2019_open_logical_model(instance=1)

    assert output == html
    assert server._REPORT_STORAGE["abc123fixed"]["html"] == html


def test_open_logical_model_returns_dict_when_requested(monkeypatch):
    model_result = {"summary": {"entity_count": 3}, "issues": {}}
    html = "<html>report</html>"

    monkeypatch.setattr(server, "_analyze_logical_data_model_internal", lambda *args, **kwargs: model_result)
    monkeypatch.setattr(server, "_render_data_model_html", lambda result, issues: html)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: _FixedUuid())
    monkeypatch.setattr(server, "_persist_report_html", lambda report_id, report_html: None)
    monkeypatch.setattr(server, "_public_base_url", lambda: "http://localhost:8000")
    monkeypatch.setattr(server, "get_instance_config", lambda instance: {"db_name": "TEST_DB"})

    output = server.db_sql2019_open_logical_model(instance=1, return_dict=True)

    assert output["database"] == "TEST_DB"
    assert output["erd_url"] == "http://localhost:8000/data-model-analysis?id=abc123fixed"
    assert output["report_id"] == "abc123fixed"
    assert output["summary"] == model_result["summary"]
