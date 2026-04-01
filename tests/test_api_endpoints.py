import os
import requests
import pytest

REQUEST_TIMEOUT = 10
BASE_URL = os.getenv("MCP_SQLSERVER_BASE_URL", "http://localhost:8085")
TEST_DATABASE_NAME = os.getenv("MCP_SQLSERVER_TEST_DATABASE", "TEST_DB")

def test_ping():
    resp = requests.get(f"{BASE_URL}/ping", timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"

def test_list_databases():
    resp = requests.get(f"{BASE_URL}/list_databases", timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_list_tables():
    params = {"database_name": TEST_DATABASE_NAME}
    resp = requests.get(f"{BASE_URL}/list_tables", params=params, timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_get_schema():
    params = {"database_name": TEST_DATABASE_NAME, "table_name": "Customers"}
    resp = requests.get(f"{BASE_URL}/get_schema", params=params, timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_list_objects():
    params = {"database_name": TEST_DATABASE_NAME, "object_type": "TABLE"}
    resp = requests.get(f"{BASE_URL}/list_objects", params=params, timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_index_fragmentation():
    params = {"database_name": TEST_DATABASE_NAME}
    resp = requests.get(f"{BASE_URL}/index_fragmentation", params=params, timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_index_health():
    params = {"database_name": TEST_DATABASE_NAME}
    resp = requests.get(f"{BASE_URL}/index_health", params=params, timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_table_health():
    params = {"database_name": TEST_DATABASE_NAME, "table_name": "Customers"}
    resp = requests.get(f"{BASE_URL}/table_health", params=params, timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_show_top_queries():
    params = {"database_name": TEST_DATABASE_NAME}
    resp = requests.get(f"{BASE_URL}/show_top_queries", params=params, timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)

def test_db_sec_perf_metrics():
    params = {"database_name": TEST_DATABASE_NAME}
    resp = requests.get(f"{BASE_URL}/db_sec_perf_metrics", params=params, timeout=REQUEST_TIMEOUT)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
