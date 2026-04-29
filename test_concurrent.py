import threading, time
from mcp_sqlserver.server import db_sql2019_check_fragmentation, initialize_connection_pools
import logging
logging.basicConfig(level=logging.ERROR)

initialize_connection_pools()

def run_frag(i):
    t0 = time.time()
    try:
        res = db_sql2019_check_fragmentation(instance=2, database_name='US_RT_User_800', table_name='rt_71f76269bc204ec1bd9cc7bf59fe1e48_US')
        print(f"Thread {i} finished in {time.time()-t0:.2f}s items={len(res.get('items',[]))}")
    except Exception as e:
        print(f"Thread {i} failed in {time.time()-t0:.2f}s: {e}")

threads = [threading.Thread(target=run_frag, args=(i,)) for i in range(5)]
for t in threads: t.start()
for t in threads: t.join()
