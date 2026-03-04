import pytest

import server


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: marks tests that require reachable SQL Server")


@pytest.fixture(scope="session")
def db_available():
    try:
        result = server.db_sql2019_ping()
        if isinstance(result, dict) and result.get("status") == "ok":
            return True
        pytest.skip(f"Integration DB ping returned unexpected payload: {result}")
    except Exception as exc:
        pytest.skip(f"Integration DB is unavailable: {exc}")
