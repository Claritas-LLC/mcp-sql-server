import threading, time, sys, traceback
from mcp_sqlserver.server import db_sql2019_run_query, initialize_connection_pools
import logging
logging.basicConfig(level=logging.ERROR)

initialize_connection_pools()

def run_query(i):
    t0 = time.time()
    try:
        res = db_sql2019_run_query(instance=2, database_name='US_RT_User_800', sql='SELECT TOP 1 * FROM sys.tables')
        print(f"Thread {i} finished in {time.time()-t0:.2f}s items={len(res.get('items',[]))}")
    except Exception as e:
        print(f"Thread {i} failed in {time.time()-t0:.2f}s: {e}")

threads = [threading.Thread(target=run_query, args=(i,)) for i in range(5)]
for t in threads: t.start()

def dump_stacks():
    time.sleep(5) # wait for them to block
    print("DUMPING THREAD STACKS")
    for thread_id, frame in sys._current_frames().items():
        print(f"\n--- Thread {thread_id} ---")
        traceback.print_stack(frame)

threading.Thread(target=dump_stacks, daemon=True).start()

for t in threads: t.join()
