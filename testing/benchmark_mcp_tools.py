import urllib.request, json, time

def mcp(method, params=None, session_id=None):
    payload = json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params or {}}).encode()
    headers = {'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
    if session_id:
        headers['mcp-session-id'] = session_id
    req = urllib.request.Request('http://localhost:8080/mcp/', data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as resp:
        sid = resp.headers.get('mcp-session-id','') or session_id or ''
        body = resp.read().decode()
        for line in body.split(chr(10)):
            line = line.strip()
            if line.startswith('data: '):
                try:
                    obj = json.loads(line[6:])
                    if 'result' in obj:
                        return sid, obj
                except:
                    pass
        return sid, None

sid, _ = mcp('initialize', {'protocolVersion':'0.1.0','capabilities':{},'clientInfo':{'name':'bench','version':'1.0.0'}})
print('Session: ' + sid)
print()

benchmarks = [
    ('analyze_tab_health (top_n=5)', 'db_2_sql2019_analyze_tab_health', {'database_name':'US_RT_User_800','top_n':5}),
    ('analyze_tab_health (top_n=50)', 'db_2_sql2019_analyze_tab_health', {'database_name':'US_RT_User_800','top_n':50}),
    ('analyze_db_data_model', 'db_2_sql2019_analyze_db_data_model', {'database_name':'US_RT_User_800'}),
    ('analyze_sec_config', 'db_2_sql2019_analyze_sec_config', {'database_name':'US_RT_User_800'}),
    ('top_statements (top_n=5)', 'db_2_sql2019_top_statements', {'database_name':'US_RT_User_800','top_n':5}),
    ('top_statements (top_n=25)', 'db_2_sql2019_top_statements', {'database_name':'US_RT_User_800','top_n':25}),
    ('list_object (tables,10)', 'db_2_sql2019_list_object', {'database_name':'US_RT_User_800','object_type':'table','top_n':10}),
    ('ping', 'db_2_sql2019_ping', {'database_name':'US_RT_User_800'}),
]

print('Tool Call'.ljust(55) + 'Time(s)'.rjust(8) + 'Status'.rjust(10))
print('-' * 75)

for label, tool, args in benchmarks:
    t0 = time.perf_counter()
    try:
        _, result = mcp('tools/call', {'name':tool, 'arguments':args}, session_id=sid)
        elapsed = time.perf_counter() - t0
        if result and 'result' in result:
            is_err = result['result'].get('isError', False)
            status = 'ERROR' if is_err else 'OK'
        else:
            status = 'NO_RESULT'
        print(label.ljust(55) + str(round(elapsed, 3)).rjust(8) + 's ' + status.rjust(9))
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(label.ljust(55) + str(round(elapsed, 3)).rjust(8) + 's ' + 'EXCEPTION'.rjust(9))
