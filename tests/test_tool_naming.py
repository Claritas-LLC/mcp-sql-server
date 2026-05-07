from src.tools.tool_registry import generate_tool_specs


def test_tool_names_follow_convention() -> None:
    specs = generate_tool_specs(["primary", "secondary"])
    names = [s.full_name for s in specs]
    assert "db_primary_sql2019_select" in names
    assert "db_primary_sql2019_exec_proc" in names
    assert "db_secondary_sql2019_select" in names
    assert "db_secondary_sql2019_exec_proc" in names
    assert "db_primary_sql2019_top_queries_report" in names
    assert "db_primary_sql2019_active_sessions_report" in names
    assert "db_primary_sql2019_index_health_report" in names
    assert "db_primary_sql2019_analyze_tab_health" in names
    assert "db_primary_sql2019_analyze_db_data_model" in names
    assert "db_primary_sql2019_analyze_sec_config" in names
    assert "db_primary_sql2019_sessions_dashboard" in names
    assert "db_secondary_sql2019_top_queries_report" in names
    assert "db_secondary_sql2019_active_sessions_report" in names
    assert "db_secondary_sql2019_index_health_report" in names
    assert "db_secondary_sql2019_analyze_tab_health" in names
    assert "db_secondary_sql2019_analyze_db_data_model" in names
    assert "db_secondary_sql2019_analyze_sec_config" in names
    assert "db_secondary_sql2019_sessions_dashboard" in names
    assert all(name.startswith("db_") and "_sql2019_" in name for name in names)
