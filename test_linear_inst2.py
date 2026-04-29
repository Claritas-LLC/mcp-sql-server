import time
from mcp_sqlserver.server import db_sql2019_run_query, initialize_connection_pools
import logging
logging.basicConfig(level=logging.ERROR)

initialize_connection_pools()

print("Testing linear queries on Instance 2")
for i in range(5):
    t0 = time.time()
    try:
        res = db_sql2019_run_query(instance=2, database_name='US_RT_User_800', sql='SELECT TOP 1 * FROM sys.tables')
        print(f"Run {i} finished in {time.time()-t0:.2f}s items={len(res.get('items',[]))}")
    except Exception as e:
        print(f"Run {i} failed in {time.time()-t0:.2f}s: {e}")
