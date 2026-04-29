import time
from mcp_sqlserver.server import get_connection, initialize_connection_pools, _execute_safe, _fetch_limited, _rows_to_dicts

initialize_connection_pools()

print("Testing exact steps of _run_query_internal")
conn = get_connection('US_RT_User_800', instance=2)
print("Got connection")
try:
    cur = conn.cursor()
    print("Got cursor")
    sql = 'SELECT TOP 1 * FROM sys.tables'
    print(f"Executing: {sql}")
    
    t0=time.time()
    _execute_safe(cur, sql, None)
    print(f"Execute finished in {time.time()-t0:.2f}s")
    
    rows = _fetch_limited(cur, 100)
    print("Fetch finished")
    res = _rows_to_dicts(cur, rows)
    print(f"Dicts created: {len(res)}")
finally:
    conn.close()
    print("Connection closed")
