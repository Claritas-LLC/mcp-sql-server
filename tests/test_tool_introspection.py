import pytest
from mcp_sqlserver import server

def test_list_registered_tools_json():
    result = server.list_registered_tools(instance=1, as_json=True)
    assert 'tools' in result
    assert isinstance(result['tools'], list)
    assert any('name' in t and 'description' in t for t in result['tools'])
    # Should include the introspection tool itself
    assert any(t['name'] == 'list_registered_tools' for t in result['tools'])


def test_list_registered_tools_text():
    result = server.list_registered_tools(instance=1, as_json=False)
    assert 'text' in result
    assert 'Tool:' in result['text']
    assert 'list_registered_tools' in result['text']
