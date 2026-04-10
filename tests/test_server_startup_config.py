import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock


def _reload_server_module(monkeypatch, env: dict[str, str | None]):
    # Keep reload deterministic regardless of host environment.
    monkeypatch.setenv("MCP_ALLOW_WRITE", "false")
    monkeypatch.setenv("MCP_CONFIRM_WRITE", "false")
    monkeypatch.setenv("MCP_TOOL_SEARCH_ENABLED", "false")

    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    import mcp_sqlserver.server as server_module

    return importlib.reload(server_module)


def test_package_import_does_not_eagerly_import_server(monkeypatch):
    sys.modules.pop("mcp_sqlserver", None)
    sys.modules.pop("mcp_sqlserver.server", None)

    package = importlib.import_module("mcp_sqlserver")

    assert "mcp_sqlserver.server" not in sys.modules
    server_module = package.server
    assert server_module is sys.modules["mcp_sqlserver.server"]


def test_build_mcp_constructor_config_defaults(monkeypatch):
    server = _reload_server_module(
        monkeypatch,
        {
            "MCP_SERVER_NAME": "SQL Server MCP Server",
            "MCP_SERVER_INSTRUCTIONS": None,
            "MCP_SERVER_VERSION": None,
            "MCP_LIST_PAGE_SIZE": None,
        },
    )

    config = server.build_mcp_constructor_config()

    assert config == {"name": "SQL Server MCP Server"}


def test_build_mcp_constructor_config_configured(monkeypatch):
    server = _reload_server_module(
        monkeypatch,
        {
            "MCP_SERVER_NAME": "Custom MCP",
            "MCP_SERVER_INSTRUCTIONS": "Read-only SQL helper",
            "MCP_SERVER_VERSION": "2026.04.09",
            "MCP_LIST_PAGE_SIZE": "75",
        },
    )

    config = server.build_mcp_constructor_config()

    assert config == {
        "name": "Custom MCP",
        "instructions": "Read-only SQL helper",
        "version": "2026.04.09",
        "list_page_size": 75,
    }


def test_build_mcp_run_config_stdio(monkeypatch):
    import mcp_sqlserver.server as server

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(transport="stdio", host="0.0.0.0", port=8000),
    )

    config = server.build_mcp_run_config()

    assert config == {"transport": "stdio"}


def test_build_mcp_run_config_http(monkeypatch):
    import mcp_sqlserver.server as server

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(transport="http", host="127.0.0.1", port=9090),
    )

    config = server.build_mcp_run_config()

    assert config == {"transport": "http", "host": "127.0.0.1", "port": 9090}


def test_run_server_entrypoint_uses_build_mcp_run_config(monkeypatch):
    import mcp_sqlserver.server as server

    expected_config = {"transport": "http", "host": "127.0.0.1", "port": 8085}
    fake_mcp = SimpleNamespace(run=Mock())

    monkeypatch.setattr(server, "build_mcp_run_config", lambda: expected_config)
    monkeypatch.setattr(server, "mcp", fake_mcp)

    server.run_server_entrypoint()

    fake_mcp.run.assert_called_once_with(**expected_config)


def test_run_server_entrypoint_bypasses_auth_for_stdio(monkeypatch):
    import mcp_sqlserver.server as server

    fake_mcp = SimpleNamespace(run=Mock())
    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transport="stdio",
            host="0.0.0.0",
            port=8000,
            auth_type="apikey",
            api_key="",
            allow_query_token_auth=False,
        ),
    )
    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(server, "configure_http_auth", lambda _settings=None: (_ for _ in ()).throw(RuntimeError("should not be called")))

    server.run_server_entrypoint()

    fake_mcp.run.assert_called_once_with(transport="stdio")


def test_run_server_entrypoint_calls_auth_for_http(monkeypatch):
    import mcp_sqlserver.server as server

    fake_mcp = SimpleNamespace(run=Mock())
    auth_mock = Mock(return_value={
        "auth_enabled": True,
        "auth_type": "apikey",
        "provider": "api_key",
        "validation_mode": "static_token_secure_compare",
        "allow_query_token_auth": False,
    })

    fake_settings = SimpleNamespace(
        transport="http",
        host="127.0.0.1",
        port=8085,
        auth_type="apikey",
        api_key="secret",
        allow_query_token_auth=False,
    )

    monkeypatch.setattr(server, "SETTINGS", fake_settings)
    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(server, "configure_http_auth", auth_mock)

    server.run_server_entrypoint()

    auth_mock.assert_called_once_with(fake_settings)
    fake_mcp.run.assert_called_once_with(transport="http", host="127.0.0.1", port=8085)


def test_configure_tool_search_transform_regex(monkeypatch):
    import mcp_sqlserver.server as server

    fake_mcp = SimpleNamespace(add_transform=Mock())
    fake_transform = object()

    class _RegexTransform:
        def __new__(cls, **_kwargs):
            return fake_transform

    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            tool_search_enabled=True,
            tool_search_strategy="regex",
            tool_search_max_results=5,
            tool_search_always_visible="db_01_ping",
            tool_search_tool_name="search_tools",
            tool_call_tool_name="call_tool",
        ),
    )
    monkeypatch.setattr(server, "_TOOL_SEARCH_TRANSFORM_APPLIED", False)

    fake_search_module = types.SimpleNamespace(
        RegexSearchTransform=_RegexTransform,
        BM25SearchTransform=_RegexTransform,
    )
    monkeypatch.setitem(sys.modules, "fastmcp.server.transforms.search", fake_search_module)

    server._configure_tool_search_transform()

    fake_mcp.add_transform.assert_called_once_with(fake_transform)


def test_configure_tool_search_transform_bm25(monkeypatch):
    import mcp_sqlserver.server as server

    fake_mcp = SimpleNamespace(add_transform=Mock())
    fake_transform = object()

    class _BM25Transform:
        def __new__(cls, **_kwargs):
            return fake_transform

    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            tool_search_enabled=True,
            tool_search_strategy="bm25",
            tool_search_max_results=None,
            tool_search_always_visible="",
            tool_search_tool_name="search_tools",
            tool_call_tool_name="call_tool",
        ),
    )
    monkeypatch.setattr(server, "_TOOL_SEARCH_TRANSFORM_APPLIED", False)

    fake_search_module = types.SimpleNamespace(
        RegexSearchTransform=_BM25Transform,
        BM25SearchTransform=_BM25Transform,
    )
    monkeypatch.setitem(sys.modules, "fastmcp.server.transforms.search", fake_search_module)

    server._configure_tool_search_transform()

    fake_mcp.add_transform.assert_called_once_with(fake_transform)


def test_resolve_http_app_returns_none_for_stdio(monkeypatch):
    import mcp_sqlserver.server as server

    monkeypatch.setattr(server, "SETTINGS", SimpleNamespace(transport="stdio"))

    assert server._resolve_http_app() is None


def test_resolve_http_app_returns_http_app_for_http_transport(monkeypatch):
    import mcp_sqlserver.server as server

    app = object()
    fake_mcp = SimpleNamespace(http_app=Mock(return_value=app), custom_route=Mock(side_effect=lambda **_kwargs: (lambda fn: fn)))

    monkeypatch.setattr(server, "SETTINGS", SimpleNamespace(transport="http"))
    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(server, "_HEALTH_ROUTE_REGISTERED", False)

    resolved = server._resolve_http_app()

    assert resolved is app
    fake_mcp.http_app.assert_called_once()


def test_build_provider_transform_layers_respects_order_and_flags():
    import mcp_sqlserver.server as server

    settings = SimpleNamespace(
        transform_layers_enabled=True,
        transform_layer_order="namespace,visibility",
        transform_visibility_enabled=True,
        transform_namespace_enabled=True,
        transform_tool_transformation_enabled=False,
        transform_resources_as_tools_enabled=False,
        transform_prompts_as_tools_enabled=False,
        transform_code_mode_enabled=False,
    )

    layers = server._build_provider_transform_layers(settings)

    layer_names = [layer["name"] for layer in layers]
    assert layer_names == [
        "namespace",
        "visibility",
        "tool_transformation",
        "resources_as_tools",
        "prompts_as_tools",
        "code_mode",
    ]
    enabled_layers = {layer["name"] for layer in layers if layer["enabled"]}
    assert enabled_layers == {"namespace", "visibility"}


def test_apply_provider_transform_layers_applies_enabled_layers(monkeypatch):
    import mcp_sqlserver.server as server

    first_transform = object()
    second_transform = object()
    add_transform = Mock()

    monkeypatch.setattr(server, "mcp", SimpleNamespace(add_transform=add_transform))
    monkeypatch.setattr(server, "_PROVIDER_TRANSFORM_LAYERS_APPLIED", False)

    layers = [
        {"name": "visibility", "enabled": True, "factory": lambda: first_transform},
        {"name": "namespace", "enabled": False, "factory": lambda: second_transform},
        {"name": "tool_transformation", "enabled": True, "factory": lambda: second_transform},
    ]

    result = server._apply_provider_transform_layers(layers)

    assert result["already_applied"] is False
    assert result["applied"] == ["visibility", "tool_transformation"]
    assert "namespace" in result["skipped"]
    add_transform.assert_any_call(first_transform)
    add_transform.assert_any_call(second_transform)
    assert add_transform.call_count == 2


def test_apply_provider_transform_layers_handles_missing_add_transform(monkeypatch):
    import mcp_sqlserver.server as server

    monkeypatch.setattr(server, "mcp", SimpleNamespace())
    monkeypatch.setattr(server, "_PROVIDER_TRANSFORM_LAYERS_APPLIED", False)

    result = server._apply_provider_transform_layers(
        [{"name": "visibility", "enabled": True, "factory": lambda: object()}]
    )

    assert result["applied"] == []
    assert result["skipped"] == ["visibility"]


def test_build_provider_transform_layers_returns_empty_when_disabled():
    import mcp_sqlserver.server as server

    settings = SimpleNamespace(transform_layers_enabled=False)

    assert server._build_provider_transform_layers(settings) == []


def test_apply_provider_transform_layers_noop_for_disabled_layers(monkeypatch):
    import mcp_sqlserver.server as server

    add_transform = Mock()
    monkeypatch.setattr(server, "mcp", SimpleNamespace(add_transform=add_transform))
    monkeypatch.setattr(server, "_PROVIDER_TRANSFORM_LAYERS_APPLIED", False)

    result = server._apply_provider_transform_layers(
        [
            {"name": "visibility", "enabled": False, "factory": lambda: object()},
            {"name": "namespace", "enabled": False, "factory": lambda: object()},
        ]
    )

    assert result["applied"] == []
    assert result["skipped"] == ["visibility", "namespace"]
    add_transform.assert_not_called()


def test_configure_transforms_return_none_when_disabled(monkeypatch):
    import mcp_sqlserver.server as server

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transform_visibility_enabled=False,
            transform_namespace_enabled=False,
            transform_tool_transformation_enabled=False,
            transform_resources_as_tools_enabled=False,
            transform_prompts_as_tools_enabled=False,
            transform_code_mode_enabled=False,
            transform_code_mode_policy="safe",
            transform_visibility_allowlist="",
            transform_visibility_denylist="",
            transform_namespace_prefix="",
            transform_tool_name_map="{}",
            transform_tool_description_map="{}",
        ),
    )

    assert server._configure_visibility_transform() is None
    assert server._configure_namespace_transform() is None
    assert server._configure_tool_transformation_transform() is None
    assert server._configure_resources_as_tools_transform() is None
    assert server._configure_prompts_as_tools_transform() is None
    assert server._configure_code_mode_transform() is None


def test_configure_tool_transformation_transform_uses_json_mappings(monkeypatch):
    """ToolTransformation configurator builds ToolTransformConfig entries via correct module."""
    import mcp_sqlserver.server as server
    from fastmcp.server.transforms.tool_transform import ToolTransform, ToolTransformConfig

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transform_tool_transformation_enabled=True,
            transform_tool_name_map='{"db_01_ping":"sql_ping"}',
            transform_tool_description_map='{"db_01_ping":"SQL connectivity probe"}',
        ),
    )

    result = server._configure_tool_transformation_transform()

    assert isinstance(result, ToolTransform), "Must return a ToolTransform instance"
    # Verify the transform config was correctly built
    assert "db_01_ping" in result._transforms
    config = result._transforms["db_01_ping"]
    assert isinstance(config, ToolTransformConfig)
    assert config.name == "sql_ping"
    assert config.description == "SQL connectivity probe"


def test_configure_tool_transformation_transform_name_only(monkeypatch):
    """ToolTransformation configurator works with name-only mapping (no description)."""
    import mcp_sqlserver.server as server
    from fastmcp.server.transforms.tool_transform import ToolTransform, ToolTransformConfig

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transform_tool_transformation_enabled=True,
            transform_tool_name_map='{"db_01_ping":"sql_ping"}',
            transform_tool_description_map="{}",
        ),
    )

    result = server._configure_tool_transformation_transform()

    assert isinstance(result, ToolTransform)
    assert "db_01_ping" in result._transforms
    assert result._transforms["db_01_ping"].name == "sql_ping"
    assert result._transforms["db_01_ping"].description is None


def test_configure_tool_transformation_transform_returns_none_when_maps_empty(monkeypatch):
    """ToolTransformation configurator returns None when both maps are empty."""
    import mcp_sqlserver.server as server

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transform_tool_transformation_enabled=True,
            transform_tool_name_map="{}",
            transform_tool_description_map="{}",
        ),
    )

    assert server._configure_tool_transformation_transform() is None


def test_configure_visibility_transform_uses_correct_class(monkeypatch):
    """Visibility configurator instantiates Visibility (not VisibilityTransform)."""
    import mcp_sqlserver.server as server
    from fastmcp.server.transforms.visibility import Visibility

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transform_visibility_enabled=True,
            transform_visibility_allowlist="db_01_ping,db_sql2019_list_objects",
            transform_visibility_denylist="",
        ),
    )

    result = server._configure_visibility_transform()

    assert isinstance(result, Visibility), "Must return a Visibility instance (not VisibilityTransform)"
    assert result._enabled is True
    assert "db_01_ping" in result.names
    assert "db_sql2019_list_objects" in result.names


def test_configure_visibility_transform_denylist(monkeypatch):
    """Visibility configurator with denylist sets enabled=False."""
    import mcp_sqlserver.server as server
    from fastmcp.server.transforms.visibility import Visibility

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transform_visibility_enabled=True,
            transform_visibility_allowlist="",
            transform_visibility_denylist="db_internal_tool",
        ),
    )

    result = server._configure_visibility_transform()

    assert isinstance(result, Visibility)
    assert result._enabled is False
    assert "db_internal_tool" in result.names


def test_configure_visibility_transform_match_all_when_no_filters(monkeypatch):
    """Visibility configurator with no lists uses match_all=True, enabled=True."""
    import mcp_sqlserver.server as server
    from fastmcp.server.transforms.visibility import Visibility

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transform_visibility_enabled=True,
            transform_visibility_allowlist="",
            transform_visibility_denylist="",
        ),
    )

    result = server._configure_visibility_transform()

    assert isinstance(result, Visibility)
    assert result._enabled is True
    assert result.match_all is True


def test_configure_namespace_transform_uses_correct_class(monkeypatch):
    """Namespace configurator instantiates Namespace (not NamespaceTransform)."""
    import mcp_sqlserver.server as server
    from fastmcp.server.transforms.namespace import Namespace

    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(
            transform_namespace_enabled=True,
            transform_namespace_prefix="sql",
        ),
    )

    result = server._configure_namespace_transform()

    assert isinstance(result, Namespace), "Must return a Namespace instance (not NamespaceTransform)"


def test_configure_resources_as_tools_transform_uses_mcp_instance(monkeypatch):
    """ResourcesAsTools configurator passes mcp server instance, not empty kwargs."""
    import mcp_sqlserver.server as server
    from fastmcp import FastMCP

    fake_mcp = FastMCP("test-rat")
    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(transform_resources_as_tools_enabled=True),
    )

    from fastmcp.server.transforms.resources_as_tools import ResourcesAsTools
    result = server._configure_resources_as_tools_transform()

    assert isinstance(result, ResourcesAsTools), "Must return a ResourcesAsTools instance"
    assert result._provider is fake_mcp


def test_configure_prompts_as_tools_transform_uses_mcp_instance(monkeypatch):
    """PromptsAsTools configurator passes mcp server instance, not empty kwargs."""
    import mcp_sqlserver.server as server
    from fastmcp import FastMCP

    fake_mcp = FastMCP("test-pat")
    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(transform_prompts_as_tools_enabled=True),
    )

    from fastmcp.server.transforms.prompts_as_tools import PromptsAsTools
    result = server._configure_prompts_as_tools_transform()

    assert isinstance(result, PromptsAsTools), "Must return a PromptsAsTools instance"
    assert result._provider is fake_mcp


def test_configure_resources_as_tools_transform_logs_warning_on_wrong_provider(monkeypatch, caplog):
    """ResourcesAsTools configurator logs a warning when the mcp instance is invalid."""
    import logging
    import mcp_sqlserver.server as server

    monkeypatch.setattr(server, "mcp", object())  # Not a FastMCP — triggers TypeError inside
    monkeypatch.setattr(
        server,
        "SETTINGS",
        SimpleNamespace(transform_resources_as_tools_enabled=True),
    )

    import logging
    with caplog.at_level(logging.WARNING, logger="mcp_sqlserver.server"):
        result = server._configure_resources_as_tools_transform()

    assert result is None
    assert any("ResourcesAsTools" in r.message for r in caplog.records)


def test_build_provider_transform_layers_warns_on_unknown_layer(monkeypatch, caplog):
    """Unknown layer names in MCP_TRANSFORM_LAYER_ORDER emit a warning and are dropped."""
    import logging
    import mcp_sqlserver.server as server

    settings = SimpleNamespace(
        transform_layers_enabled=True,
        transform_layer_order="visibility,typo_layer",
        transform_visibility_enabled=True,
        transform_namespace_enabled=False,
        transform_tool_transformation_enabled=False,
        transform_resources_as_tools_enabled=False,
        transform_prompts_as_tools_enabled=False,
        transform_code_mode_enabled=False,
    )

    with caplog.at_level(logging.WARNING, logger="mcp_sqlserver.server"):
        layers = server._build_provider_transform_layers(settings)

    layer_names = [layer["name"] for layer in layers]
    assert "typo_layer" not in layer_names
    assert "visibility" in layer_names
    assert any("typo_layer" in r.message for r in caplog.records)


def test_apply_provider_transform_layers_emits_plain_text_log(monkeypatch, caplog):
    """_apply_provider_transform_layers emits a plain-text INFO log with Applied/Skipped."""
    import logging
    import mcp_sqlserver.server as server

    sentinel = object()
    add_transform = Mock()
    monkeypatch.setattr(server, "mcp", SimpleNamespace(add_transform=add_transform))
    monkeypatch.setattr(server, "_PROVIDER_TRANSFORM_LAYERS_APPLIED", False)

    layers = [
        {"name": "visibility", "enabled": True, "factory": lambda: sentinel},
        {"name": "namespace", "enabled": False, "factory": lambda: sentinel},
    ]

    with caplog.at_level(logging.INFO, logger="mcp_sqlserver.server"):
        server._apply_provider_transform_layers(layers)

    matching = [r for r in caplog.records if "Applied" in r.message and "Skipped" in r.message]
    assert matching, "Expected an INFO log with 'Applied' and 'Skipped' in plain-text message"
    assert "visibility" in matching[0].message
    assert "namespace" in matching[0].message
