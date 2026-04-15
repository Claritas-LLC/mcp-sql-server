from mcp_sqlserver import server


def test_apply_field_projection_selects_nested_fields():
    payload = {
        "database": "TEST_DB",
        "summary": {"total": 3, "high": 1},
        "long_running_queries": [
            {"query_id": 10, "avg_duration_ms": 100.5, "text": "SELECT 1"},
            {"query_id": 11, "avg_duration_ms": 200.0, "text": "SELECT 2"},
        ],
    }

    projected = server._apply_field_projection(
        payload,
        "database,summary.total,long_running_queries.query_id,long_running_queries.avg_duration_ms",
    )

    assert projected["database"] == "TEST_DB"
    assert projected["summary"]["total"] == 3
    assert projected["long_running_queries"] == [
        {"query_id": 10, "avg_duration_ms": 100.5},
        {"query_id": 11, "avg_duration_ms": 200.0},
    ]
    assert "text" not in projected["long_running_queries"][0]


def test_apply_field_projection_preserves_pagination_metadata():
    payload = {
        "items": [{"id": 1, "name": "A"}],
        "pagination": {"page": 1, "total_items": 1},
    }

    projected = server._apply_field_projection(payload, "items.id")

    assert projected["items"] == [{"id": 1}]
    assert projected["pagination"]["page"] == 1


def test_apply_token_budget_applies_truncation_metadata():
    payload = {
        "database": "TEST_DB",
        "long_running_queries": [{"query_id": i, "query_sql_text": "X" * 200} for i in range(30)],
        "summary": {"long_running_queries_count": 30},
    }

    budgeted = server._apply_token_budget(payload, token_budget=120)

    assert isinstance(budgeted, dict)
    assert "_truncation" in budgeted
    assert budgeted["_truncation"]["applied"] is True


def test_apply_token_budget_none_keeps_payload():
    payload = {"a": [1, 2, 3], "summary": {"count": 3}}

    budgeted = server._apply_token_budget(payload, token_budget=None)

    assert budgeted == payload


def test_render_data_model_html_sanitizes_relationship_label_strictly():
    model = {
        "summary": {"database": "TEST_DB", "generated_at_utc": "2026-01-01T00:00:00Z", "issues_count": {}},
        "logical_model": {
            "entities": [
                {"schema_name": "dbo", "entity_name": "Parent", "attributes": []},
                {"schema_name": "dbo", "entity_name": "Child", "attributes": []},
            ],
            "relationships": [
                {
                    "name": "FK bad-label <script>alert(1)</script>",
                    "from_entity": "dbo.Child",
                    "to_entity": "dbo.Parent",
                }
            ],
        },
    }

    html = server._render_data_model_html("model-1", model, page=1, focus_entity=None)

    assert "FKbadlabelscriptalert1script" in html
    assert "bad-label" not in html
    assert "<script>alert(1)</script>" not in html.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" not in html.lower()


def test_render_data_model_html_escapes_mermaid_payload_in_dom():
    model = {
        "summary": {"database": "TEST_DB", "generated_at_utc": "2026-01-01T00:00:00Z", "issues_count": {}},
        "logical_model": {
            "entities": [
                {"schema_name": "dbo", "entity_name": "Parent", "attributes": []},
                {"schema_name": "dbo", "entity_name": "Child", "attributes": []},
            ],
            "relationships": [
                {
                    "name": "FK_LABEL",
                    "from_entity": "dbo.Child",
                    "to_entity": "dbo.Parent",
                }
            ],
        },
    }

    html = server._render_data_model_html("model-2", model, page=1, focus_entity=None)

    assert '<div id="diagramLayer" class="mermaid">' in html
    assert "&quot;FK_LABEL&quot;" in html
    assert ': "FK_LABEL"' not in html
