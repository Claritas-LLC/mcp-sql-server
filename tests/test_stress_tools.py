import concurrent.futures

import server


def _call_tool(tool, *args, **kwargs):
    fn = getattr(tool, "fn", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return tool(*args, **kwargs)


def _run_query():
    return _call_tool(
        server.db_sql2019_execute_query,
        "TEST_DB",
        "SELECT TOP 1 * FROM sales.Customers"
    )


def test_concurrent_queries():
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_run_query) for _ in range(25)]
        results = [future.result() for future in futures]

    assert all(isinstance(result, list) for result in results)
