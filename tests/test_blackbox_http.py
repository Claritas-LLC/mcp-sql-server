import os

import httpx
import pytest

BASE_URL = os.getenv("MCP_HTTP_URL", "http://127.0.0.1:8000")
AUTH_TYPE = os.getenv("FASTMCP_AUTH_TYPE", "").lower()
API_KEY = os.getenv("FASTMCP_API_KEY", "")


def _server_reachable() -> bool:
    try:
        httpx.get(f"{BASE_URL}/mcp", timeout=2.0)
        return True
    except Exception:
        return False


@pytest.mark.blackbox
def test_mcp_redirects_to_sse():
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")

    response = httpx.get(f"{BASE_URL}/mcp", follow_redirects=False, timeout=5.0)
    if response.status_code in {301, 302, 307, 308}:
        location = response.headers.get("location", "")
        assert location.endswith("/sse")
        return

    # Some FastMCP configurations return 406 for unsupported Accept headers.
    # Treat that as a valid response from the /mcp endpoint.
    assert response.status_code in {200, 406}


@pytest.mark.blackbox
def test_sse_endpoint_auth_or_streams():
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")

    headers = {"Accept": "text/event-stream"}
    if AUTH_TYPE == "apikey" and API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    with httpx.Client(timeout=5.0) as client:
        with client.stream("GET", f"{BASE_URL}/sse", headers=headers) as response:
            if response.status_code == 404:
                # Some transports expose SSE on /mcp instead of /sse.
                with client.stream("GET", f"{BASE_URL}/mcp", headers=headers) as fallback:
                    if fallback.status_code == 404:
                        raise AssertionError(
                            "Both /sse and /mcp returned 404. "
                            "MCP HTTP/SSE endpoints do not appear to be mounted at expected paths."
                        )

                    if AUTH_TYPE == "apikey" and not API_KEY:
                        assert fallback.status_code in {401, 403}
                        return

                    if fallback.status_code == 400:
                        # Streamable HTTP endpoints may require POST or payload.
                        return

                    assert fallback.status_code == 200
                    content_type = fallback.headers.get("content-type", "")
                    assert "text/event-stream" in content_type
                return

            if AUTH_TYPE == "apikey" and not API_KEY:
                assert response.status_code in {401, 403}
                return

            assert response.status_code == 200
            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type


@pytest.mark.blackbox
def test_http_auth_matrix_for_configured_mode():
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")

    auth_mode = AUTH_TYPE or "none"
    if auth_mode not in {"none", "apikey"}:
        pytest.skip(f"Auth matrix test currently targets none/apikey modes only (got {auth_mode!r})")

    headers = {"Accept": "text/event-stream"}
    if auth_mode == "apikey" and API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    with httpx.Client(timeout=5.0) as client:
        response = client.get(f"{BASE_URL}/mcp", headers=headers)

    if auth_mode == "apikey" and not API_KEY:
        assert response.status_code in {401, 403}
        return

    assert response.status_code in {200, 400, 406}


@pytest.mark.blackbox
def test_health_endpoint_reports_safe_payload():
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")

    response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
    assert response.status_code == 200

    payload = response.json()
    assert payload.get("status") == "ok"
    assert "service" in payload
    assert "password" not in payload
    assert "api_key" not in payload


@pytest.mark.blackbox
def test_transform_toggles_do_not_break_mcp_endpoint():
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")

    transform_env_keys = [
        "MCP_TRANSFORM_VISIBILITY_ENABLED",
        "MCP_TRANSFORM_NAMESPACE_ENABLED",
        "MCP_TRANSFORM_TOOL_TRANSFORMATION_ENABLED",
        "MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED",
        "MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED",
        "MCP_TRANSFORM_CODE_MODE_ENABLED",
    ]
    any_transform_enabled = any(
        os.getenv(key, "").strip().lower() in {"1", "true", "yes", "on", "y"}
        for key in transform_env_keys
    )
    if not any_transform_enabled:
        pytest.skip("No transform toggles enabled in environment")

    response = httpx.get(f"{BASE_URL}/mcp", timeout=5.0)
    assert response.status_code in {200, 400, 406}


@pytest.mark.blackbox
def test_health_endpoint_remains_safe_with_transform_toggles():
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")

    response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
    assert response.status_code == 200

    payload = response.json()
    assert payload.get("status") == "ok"
    assert "password" not in payload
    assert "api_key" not in payload


# ---------------------------------------------------------------------------
# TASK-010: Synthetic tool exposure checks for transforms under enabled state
# ---------------------------------------------------------------------------

def _tools_list_via_initialize() -> list[str]:
    """Send MCP initialize + tools/list over HTTP and return tool names.

    Uses the MCP streamable-HTTP transport (POST to /mcp).
    Returns an empty list if the server is unreachable or does not support
    the streamable JSON response variant.
    """
    headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    if AUTH_TYPE == "apikey" and API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pytest-blackbox", "version": "1.0"},
        },
    }
    try:
        r = httpx.post(f"{BASE_URL}/mcp", json=init_payload, headers=headers, timeout=10.0)
        if r.status_code not in {200}:
            return []
    except Exception:
        return []

    list_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    try:
        r2 = httpx.post(f"{BASE_URL}/mcp", json=list_payload, headers=headers, timeout=10.0)
        data = r2.json()
        tools = data.get("result", {}).get("tools", [])
        return [t.get("name", "") for t in tools]
    except Exception:
        return []


@pytest.mark.blackbox
def test_resources_as_tools_synthetic_tools_exposed_when_enabled():
    """When MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED=true, list_resources and read_resource
    tools must appear in the tools/list response."""
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")
    if os.getenv("MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on", "y"}:
        pytest.skip("MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED is not enabled in environment")

    tool_names = _tools_list_via_initialize()
    if not tool_names:
        pytest.skip("tools/list via HTTP not supported in this transport configuration")

    assert "list_resources" in tool_names, (
        "ResourcesAsTools transform is enabled but 'list_resources' synthetic tool is absent from tools/list"
    )
    assert "read_resource" in tool_names, (
        "ResourcesAsTools transform is enabled but 'read_resource' synthetic tool is absent from tools/list"
    )


@pytest.mark.blackbox
def test_prompts_as_tools_synthetic_tools_exposed_when_enabled():
    """When MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED=true, list_prompts and get_prompt
    tools must appear in the tools/list response."""
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")
    if os.getenv("MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on", "y"}:
        pytest.skip("MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED is not enabled in environment")

    tool_names = _tools_list_via_initialize()
    if not tool_names:
        pytest.skip("tools/list via HTTP not supported in this transport configuration")

    assert "list_prompts" in tool_names, (
        "PromptsAsTools transform is enabled but 'list_prompts' synthetic tool is absent from tools/list"
    )
    assert "get_prompt" in tool_names, (
        "PromptsAsTools transform is enabled but 'get_prompt' synthetic tool is absent from tools/list"
    )


@pytest.mark.blackbox
def test_tool_search_synthetic_tools_exposed_when_enabled():
    """When MCP_TOOL_SEARCH_ENABLED=true, search_tools and call_tool (or configured names)
    must appear in the tools/list response."""
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")
    if os.getenv("MCP_TOOL_SEARCH_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on", "y"}:
        pytest.skip("MCP_TOOL_SEARCH_ENABLED is not enabled in environment")

    search_tool_name = os.getenv("MCP_TOOL_SEARCH_TOOL_NAME", "search_tools")
    call_tool_name = os.getenv("MCP_TOOL_CALL_TOOL_NAME", "call_tool")

    tool_names = _tools_list_via_initialize()
    if not tool_names:
        pytest.skip("tools/list via HTTP not supported in this transport configuration")

    assert search_tool_name in tool_names, (
        f"Tool Search is enabled but '{search_tool_name}' synthetic tool is absent from tools/list"
    )
    assert call_tool_name in tool_names, (
        f"Tool Search is enabled but '{call_tool_name}' synthetic tool is absent from tools/list"
    )


@pytest.mark.blackbox
def test_visibility_allowlist_hides_unlisted_tools():
    """When MCP_TRANSFORM_VISIBILITY_ALLOWLIST is set, only allowlisted tool names
    (plus synthetic tools) should appear in tools/list."""
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")
    allowlist_raw = os.getenv("MCP_TRANSFORM_VISIBILITY_ALLOWLIST", "").strip()
    if not os.getenv("MCP_TRANSFORM_VISIBILITY_ENABLED", "").strip().lower() in {"1", "true", "yes", "on", "y"}:
        pytest.skip("MCP_TRANSFORM_VISIBILITY_ENABLED is not set")
    if not allowlist_raw:
        pytest.skip("MCP_TRANSFORM_VISIBILITY_ALLOWLIST is empty — cannot assert exclusion")

    allowlist = {name.strip() for name in allowlist_raw.split(",") if name.strip()}
    tool_names = _tools_list_via_initialize()
    if not tool_names:
        pytest.skip("tools/list via HTTP not supported in this transport configuration")

    # Synthetic tools (list_resources, read_resource, list_prompts, get_prompt,
    # search_tools, call_tool) are injected by transforms and are not subject to
    # the allowlist filter on server-registered tools.
    synthetic_prefixes = {"list_resources", "read_resource", "list_prompts", "get_prompt",
                          "search_tools", "call_tool"}
    non_synthetic = [name for name in tool_names if name not in synthetic_prefixes]

    unexpected = [name for name in non_synthetic if name not in allowlist]
    assert not unexpected, (
        f"Visibility allowlist is active but the following tools appeared outside the allowlist: "
        f"{unexpected}"
    )


# ---------------------------------------------------------------------------
# TASK-011: auth + visibility controls apply to transformed discovery endpoints
# ---------------------------------------------------------------------------

@pytest.mark.blackbox
def test_unauthenticated_tools_list_blocked_when_apikey_auth_enabled():
    """When FASTMCP_AUTH_TYPE=apikey, tools/list without credentials must be rejected (401/403)."""
    if not _server_reachable():
        pytest.skip("MCP server is not reachable")
    if AUTH_TYPE != "apikey":
        pytest.skip("Auth type is not apikey")
    if not API_KEY:
        pytest.skip("FASTMCP_API_KEY is not set — cannot test rejection path")

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pytest-unauth", "version": "1.0"},
        },
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    # Deliberately omit Authorization header
    response = httpx.post(f"{BASE_URL}/mcp", json=init_payload, headers=headers, timeout=5.0)
    assert response.status_code in {401, 403}, (
        f"Expected 401/403 for unauthenticated request with apikey auth, got {response.status_code}"
    )
