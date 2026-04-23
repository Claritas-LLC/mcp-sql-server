import pytest
from mcp_sqlserver import server

def test_list_registered_tools_json():
    result = server.list_registered_tools(instance=1, as_json=True)
    assert 'tools' in result
    assert 'status' in result
    assert 'instance' in result
    assert 'tool_count' in result
    assert isinstance(result['tools'], list)
    assert any('name' in t and 'description' in t for t in result['tools'])
    # Should include the introspection tool itself (with instance prefix)
    assert any(t['name'] == 'db_01_list_registered_tools' for t in result['tools'])
    # All tools should be for instance 1
    assert all(t['name'].startswith('db_01_') or not t['name'].startswith('db_0') for t in result['tools'])


def test_list_registered_tools_text():
    result = server.list_registered_tools(instance=1, as_json=False)
    assert 'text' in result
    assert 'Tool:' in result['text']
    assert 'db_01_list_registered_tools' in result['text']
    assert 'Registered Tools for Instance 1' in result['text']


def test_list_registered_tools_instance_filtering():
    """Test that tools are correctly filtered by instance."""
    result_1 = server.list_registered_tools(instance=1, as_json=True)
    result_2 = server.list_registered_tools(instance=2, as_json=True)
    
    # Both should have tools
    assert len(result_1['tools']) > 0
    assert len(result_2['tools']) > 0
    
    # Instance 1 should have db_01_ tools, not db_02_
    assert any(t['name'].startswith('db_01_') for t in result_1['tools'])
    assert not any(t['name'].startswith('db_02_') for t in result_1['tools'])
    
    # Instance 2 should have db_02_ tools, not db_01_
    assert any(t['name'].startswith('db_02_') for t in result_2['tools'])
    assert not any(t['name'].startswith('db_01_') for t in result_2['tools'])
