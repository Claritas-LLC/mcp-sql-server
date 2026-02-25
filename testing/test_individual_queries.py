#!/usr/bin/env python3
"""Test individual queries for db_sql2019_db_sec_perf_metrics."""

import sys
import os

# Add the current directory to Python path to import server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import get_connection
import json

def test_individual_queries():
    """Test each query individually."""
    print("Testing individual security and performance queries...")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Test queries one by one
        queries = [
            ("Login Audit", """
                SELECT 
                    name,
                    type_desc,
                    is_disabled,
                    create_date,
                    modify_date,
                    default_database_name,
                    is_fixed_role
                FROM sys.server_principals 
                WHERE type IN ('S', 'U', 'G') 
                AND name NOT LIKE '##%'
                ORDER BY name
            """),
            ("Permissions Audit", """
                SELECT 
                    prin.name AS principal_name,
                    prin.type_desc AS principal_type,
                    perm.permission_name,
                    perm.state_desc AS permission_state,
                    obj.name AS object_name,
                    obj.type_desc AS object_type
                FROM sys.server_permissions perm
                JOIN sys.server_principals prin ON perm.grantee_principal_id = prin.principal_id
                LEFT JOIN sys.objects obj ON perm.major_id = obj.object_id
                WHERE prin.name NOT LIKE '##%'
                ORDER BY prin.name, perm.permission_name
            """),
            ("Security Config", """
                SELECT 
                    name,
                    value,
                    value_in_use,
                    description
                FROM sys.configurations 
                WHERE name IN (
                    'cross db ownership chaining',
                    'xp_cmdshell', 
                    'Ad Hoc Distributed Queries',
                    'clr enabled',
                    'Database Mail XPs',
                    'Ole Automation Procedures'
                )
                ORDER BY name
            """),
            ("Wait Stats", """
                SELECT TOP 10
                    wait_type,
                    waiting_tasks_count,
                    wait_time_ms,
                    max_wait_time_ms,
                    signal_wait_time_ms,
                    CAST(100.0 * wait_time_ms / SUM(wait_time_ms) OVER() AS DECIMAL(5,2)) AS wait_percentage
                FROM sys.dm_os_wait_stats 
                WHERE wait_type NOT IN (
                    'BROKER_EVENTHANDLER', 'BROKER_RECEIVE_WAITFOR', 'BROKER_TASK_STOP',
                    'BROKER_TO_FLUSH', 'BROKER_TRANSMITTER', 'CHECKPOINT_QUEUE',
                    'CLR_AUTO_EVENT', 'CLR_MANUAL_EVENT', 'CLR_SEMAPHORE',
                    'DBMIRROR_DBM_EVENT', 'DBMIRROR_EVENTS_QUEUE', 'DBMIRROR_WORKER_QUEUE',
                    'DBMIRRORING_CMD', 'DIRTY_PAGE_POLL', 'DISPATCHER_QUEUE_SEMAPHORE',
                    'EXECSYNC', 'FSAGENT', 'FT_IFTS_SCHEDULER_IDLE_WAIT', 'FT_IFTSHC_MUTEX',
                    'HADR_CLUSAPI_CALL', 'HADR_FILESTREAM_IOMGR_IOCOMPLETION', 'HADR_LOGCAPTURE_WAIT',
                    'HADR_NOTIFICATION_DEQUEUE', 'HADR_TIMER_TASK', 'HADR_WORK_QUEUE',
                    'KSOURCE_WAKEUP', 'LAZYWRITER_SLEEP', 'LOGMGR_QUEUE', 'MEMORY_ALLOCATION_EXT',
                    'ONDEMAND_TASK_QUEUE', 'PARALLEL_REDO_DRAIN_WORKER', 'PARALLEL_REDO_LOG_CACHE',
                    'PARALLEL_REDO_TRAN_LIST', 'PARALLEL_REDO_WORKER_SYNC', 'PARALLEL_REDO_WORKER_WAIT_WORK',
                    'PREEMPTIVE_XE_GETTARGETSTATE', 'PWAIT_ALL_COMPONENTS_INITIALIZED', 'PWAIT_DIRECTLOGCONSUMER_GETNEXT',
                    'QDS_ASYNC_QUEUE', 'QDS_CLEANUP_STALE_QUERIES_TASK_MAIN_LOOP_SLEEP', 'QDS_PERSIST_TASK_MAIN_LOOP_SLEEP',
                    'QDS_SHUTDOWN_QUEUE', 'QDS_WIP', 'REDO_THREAD_PENDING_WORK', 'REQUEST_FOR_DEADLOCK_SEARCH',
                    'RESOURCE_QUEUE', 'SERVER_IDLE_CHECK', 'SLEEP_BPOOL_FLUSH', 'SLEEP_DBSTARTUP',
                    'SLEEP_DCOMSTARTUP', 'SLEEP_MSDBSTARTUP', 'SLEEP_SYSTEMTASK', 'SLEEP_TASK',
                    'SLEEP_TEMPDBSTARTUP', 'SNI_HTTP_ACCEPT', 'SP_SERVER_DIAGNOSTICS_SLEEP', 'SQLTRACE_BUFFER_FLUSH',
                    'SQLTRACE_INCREMENTAL_FLUSH_SLEEP', 'SQLTRACE_WAIT_ENTRIES', 'STARTUP_DEPENDENCY_MANAGER',
                    'UCS_SESSION_REGISTRATION', 'WAIT_FOR_RESULTS', 'WAIT_XTP_HOST_WAIT', 'WAIT_XTP_OFFLINE_CKPT_NEW_LOG',
                    'WAIT_XTP_CKPT_CLOSE', 'WAIT_XTP_RECOVERY', 'XE_BUFFERMGR_ALLPROCESSED_EVENT', 'XE_DISPATCHER_JOIN',
                    'XE_DISPATCHER_WAIT', 'XE_LIVE_TARGET_TVF', 'XE_TIMER_EVENT'
                )
                ORDER BY wait_time_ms DESC
            """),
            ("Memory Usage", """
                SELECT 
                    physical_memory_kb / 1024 AS physical_memory_mb,
                    virtual_memory_kb / 1024 AS virtual_memory_mb,
                    committed_kb / 1024 AS committed_mb,
                    committed_target_kb / 1024 AS committed_target_mb,
                    CAST(100.0 * committed_kb / committed_target_kb AS DECIMAL(5,2)) AS memory_utilization_percent
                FROM sys.dm_os_sys_memory
            """),
            ("CPU Stats", """
                SELECT 
                    cpu_count,
                    hyperthread_ratio,
                    physical_memory_kb / 1024 AS physical_memory_mb,
                    virtual_machine_type_desc,
                    softnuma_configuration_desc
                FROM sys.dm_os_sys_info
            """),
        ]
        
        for query_name, query in queries:
            try:
                print(f"\n--- Testing: {query_name} ---")
                cursor.execute(query)
                columns = [desc[0] for desc in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                print(f"✅ Success: {len(results)} rows returned")
                if results:
                    print(f"Sample result: {results[0]}")
            except Exception as e:
                print(f"❌ Error in {query_name}: {e}")
                return False
        
        conn.close()
        print("\n✅ All queries tested successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_individual_queries()
