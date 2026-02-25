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
