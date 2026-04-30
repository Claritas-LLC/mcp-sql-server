import pytest
from mcp_sqlserver.server import unwrap_rx, _qualified_db_object, _qualified_information_schema, _qualified_sys_object

class DummyRx:
    def __init__(self, value):
        self.value = value

def test_unwrap_rx_simple():
    assert unwrap_rx(5) == 5
    assert unwrap_rx(DummyRx(5)) == 5
    assert unwrap_rx(DummyRx(DummyRx(5))) == 5

def test_qualified_db_object():
    assert _qualified_db_object('mydb', 'dbo', 'mytable') == '[mydb].dbo.mytable'
    assert _qualified_db_object(None, 'dbo', 'mytable') == 'dbo.mytable'

def test_qualified_information_schema():
    assert _qualified_information_schema('mydb', 'COLUMNS') == '[mydb].INFORMATION_SCHEMA.COLUMNS'
    assert _qualified_information_schema(None, 'COLUMNS') == 'INFORMATION_SCHEMA.COLUMNS'

def test_qualified_sys_object():
    assert _qualified_sys_object('mydb', 'tables') == '[mydb].sys.tables'
    assert _qualified_sys_object(None, 'tables') == 'sys.tables'
