"""Diagnostic: test each catalog query against US_RT_User_800 on db_2."""
import os, sys, time
import pyodbc
from dotenv import load_dotenv
load_dotenv(override=True)

USER = os.getenv("SECRET_SQL_SECONDARY_USERNAME", "readonly_user")
PWD = os.getenv("SECRET_SQL_SECONDARY_PASSWORD", "change-me")
HOST = "10.125.1.8"
PORT = 1433
DB = "US_RT_User_800"
TOP_N = 5

conn_str = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={HOST},{PORT};"
    f"DATABASE={DB};UID={USER};PWD={PWD};"
    f"Encrypt=no;TrustServerCertificate=yes;"
    f"Connection Timeout=5;Command Timeout=10;"
)

queries = [
    ("table_size", f"""
        SELECT TOP {TOP_N} s.name AS schema_name, t.name AS table_name,
        SUM(p.rows) AS row_count,
        CAST(SUM(a.total_pages) * 8.0 / 1024 AS DECIMAL(18,2)) AS total_space_mb
        FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        JOIN sys.indexes i ON t.object_id = i.object_id
        JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
        JOIN sys.allocation_units a ON p.partition_id = a.container_id
        GROUP BY s.name, t.name ORDER BY total_space_mb DESC
    """),
    ("fragmented_indexes", f"""
        SELECT TOP {TOP_N} OBJECT_SCHEMA_NAME(ps.object_id) AS schema_name,
        OBJECT_NAME(ps.object_id) AS table_name, i.name AS index_name,
        ps.avg_fragmentation_in_percent, ps.page_count
        FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ps
        JOIN sys.indexes i ON ps.object_id = i.object_id AND ps.index_id = i.index_id
        WHERE ps.index_id > 0 AND ps.page_count >= 100
        ORDER BY ps.avg_fragmentation_in_percent DESC
    """),
    ("missing_pk", """
        SELECT s.name AS schema_name, t.name AS table_name
        FROM sys.tables t
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        LEFT JOIN sys.key_constraints k ON k.parent_object_id = t.object_id AND k.type = 'PK'
        WHERE k.object_id IS NULL ORDER BY s.name, t.name
    """),
    ("stale_statistics", f"""
        SELECT TOP {TOP_N} s.name AS schema_name, o.name AS table_name,
        st.name AS stat_name, sp.rows AS row_count,
        sp.modification_counter, sp.rows_sampled,
        STATS_DATE(o.object_id, st.stats_id) AS last_updated
        FROM sys.stats st
        JOIN sys.objects o ON st.object_id = o.object_id AND o.type = 'U'
        JOIN sys.schemas s ON o.schema_id = s.schema_id
        CROSS APPLY sys.dm_db_stats_properties(st.object_id, st.stats_id) sp
        WHERE sp.modification_counter > 0
        ORDER BY sp.modification_counter DESC
    """),
    ("stats_never_updated", f"""
        SELECT TOP {TOP_N} s.name AS schema_name, o.name AS table_name,
        st.name AS stat_name, sp.rows AS row_count, sp.rows_sampled
        FROM sys.stats st
        JOIN sys.objects o ON st.object_id = o.object_id AND o.type = 'U'
        JOIN sys.schemas s ON o.schema_id = s.schema_id
        CROSS APPLY sys.dm_db_stats_properties(st.object_id, st.stats_id) sp
        WHERE STATS_DATE(o.object_id, st.stats_id) IS NULL
        ORDER BY sp.rows DESC
    """),
    ("low_sampled_stats", f"""
        SELECT TOP {TOP_N} s.name AS schema_name, o.name AS table_name,
        st.name AS stat_name, sp.rows AS row_count, sp.rows_sampled,
        CASE WHEN sp.rows > 0 THEN CAST(sp.rows_sampled * 100.0 / sp.rows AS DECIMAL(5,2)) ELSE 0 END AS sample_pct
        FROM sys.stats st
        JOIN sys.objects o ON st.object_id = o.object_id AND o.type = 'U'
        JOIN sys.schemas s ON o.schema_id = s.schema_id
        CROSS APPLY sys.dm_db_stats_properties(st.object_id, st.stats_id) sp
        WHERE sp.rows > 0 AND sp.rows_sampled > 0
        AND CAST(sp.rows_sampled AS FLOAT) / NULLIF(sp.rows, 0) < 0.1
        ORDER BY sample_pct ASC
    """),
    ("db_stats_settings", """
        SELECT DB_NAME() AS database_name,
        is_auto_create_stats_on, is_auto_update_stats_on, is_auto_update_stats_async_on
        FROM sys.databases WHERE name = DB_NAME()
    """),
    ("missing_stats_coverage", f"""
        SELECT TOP {TOP_N} s.name AS schema_name, t.name AS table_name,
        p.rows AS row_count
        FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        LEFT JOIN sys.dm_db_partition_stats p ON t.object_id = p.object_id AND p.index_id IN (0,1)
        WHERE NOT EXISTS (
            SELECT 1 FROM sys.stats st
            WHERE st.object_id = t.object_id
            AND STATS_DATE(t.object_id, st.stats_id) IS NOT NULL
        )
        ORDER BY p.rows DESC
    """),
]

print(f"\nTesting {len(queries)} queries against {HOST}:{PORT}/{DB}")
print(f"User={USER}  Command_Timeout=10s")
print("=" * 70)

for name, sql in queries:
    print(f"\n--- {name} ---")
    sql_short = ' '.join(sql.split())[:130]
    print(f"SQL: {sql_short}...")
    sys.stdout.flush()
    started = time.time()
    try:
        conn = pyodbc.connect(conn_str, autocommit=False)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchmany(TOP_N + 1)
        elapsed = time.time() - started
        print(f"  OK  | {elapsed:.2f}s | {len(rows)} rows")
        cursor.close(); conn.close()
    except Exception as exc:
        elapsed = time.time() - started
        print(f"  FAIL | {elapsed:.2f}s | {str(exc)[:300]}")

print("\n" + "=" * 70 + "\nDone.")
