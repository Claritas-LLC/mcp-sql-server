import pytest

# Import internal helper to normalize ERD view values
import importlib

server = importlib.import_module("mcp_sqlserver.server")

def test_normalize_erd_view_variants():
    assert server._normalize_erd_view(None) == "standard"
    assert server._normalize_erd_view("FULL") == "full"
    assert server._normalize_erd_view("summary") == "summary"
    # Unknown value should default to standard
    assert server._normalize_erd_view("unknown_value") == "standard"
