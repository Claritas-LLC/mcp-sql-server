import requests
import pytest

BASE_URL = "http://localhost:8085"

def test_ping():
    resp = requests.get(f"{BASE_URL}/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"

def test_list_databases():
    resp = requests.get(f"{BASE_URL}/list_databases")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_list_tables():
    # Replace 'TEST_DB' with your test database name if different
    params = {"database_name": "TEST_DB"}
    resp = requests.get(f"{BASE_URL}/list_tables", params=params)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_get_schema():
    params = {"database_name": "TEST_DB", "table_name": "Customers"}
    resp = requests.get(f"{BASE_URL}/get_schema", params=params)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_list_objects():
    params = {"database_name": "TEST_DB", "object_type": "TABLE"}
    resp = requests.get(f"{BASE_URL}/list_objects", params=params)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_index_fragmentation():
    params = {"database_name": "TEST_DB"}
    resp = requests.get(f"{BASE_URL}/index_fragmentation", params=params)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_index_health():
    params = {"database_name": "TEST_DB"}
    resp = requests.get(f"{BASE_URL}/index_health", params=params)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_table_health():
    params = {"database_name": "TEST_DB", "table_name": "Customers"}
    resp = requests.get(f"{BASE_URL}/table_health", params=params)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_show_top_queries():
    params = {"database_name": "TEST_DB"}
    resp = requests.get(f"{BASE_URL}/show_top_queries", params=params)
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)

def test_db_sec_perf_metrics():
    params = {"database_name": "TEST_DB"}
    resp = requests.get(f"{BASE_URL}/db_sec_perf_metrics", params=params)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
