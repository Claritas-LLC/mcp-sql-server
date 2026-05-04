import sys
sys.path.insert(0,'.')
from mcp_sqlserver import server

targets=[(1,'USGISPRO_800'),(1,'US_RT_User_800'),(2,'ListGateway'),(2,'US_UserData')]

print('=== CONTROL: execute_query DB_NAME() ===')
for inst,db in targets:
    r=server.db_sql2019_execute_query(instance=inst,database_name=db,sql='SELECT DB_NAME() AS dbname')
    items=r.get('items',[])
    print(inst, db, '->', items[0].get('dbname') if items else None)

print('\n=== db_stats ===')
for inst,db in targets:
    r=server.db_sql2019_db_stats(instance=inst,database=db)
    print(inst, db, '->', r.get('DatabaseName'), 'tables=', r.get('TableCount'))

print('\n=== analyze_logical_data_model(summary) ===')
for inst,db in targets:
    r=server.db_sql2019_analyze_logical_data_model(instance=inst,database_name=db,view='summary')
    s=r.get('summary',{})
    print(inst, db, 'entity_count=', s.get('entity_count'), 'relationship_count=', s.get('relationship_count'))

print('\n=== show_top_queries(summary) + query_store truth ===')
for inst,db in targets:
    tq=server.db_sql2019_show_top_queries(instance=inst,database_name=db,view='summary')
    truth=server.db_sql2019_execute_query(instance=inst,database_name=db,sql='SELECT DB_NAME() AS dbname, actual_state_desc FROM sys.database_query_store_options')
    tr=(truth.get('items') or [{}])[0]
    print(inst, db, 'top_queries_enabled=', tq.get('query_store_enabled'), 'truth=', tr.get('actual_state_desc'), 'truth_db=', tr.get('dbname'))
