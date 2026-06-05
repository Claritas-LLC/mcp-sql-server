import pyodbc, time

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=10.125.1.8,1433;"
    "DATABASE=US_RT_User_800;"
    "UID=mcp_readonly;"
    "PWD=***REMOVED***;"
    "Encrypt=no;TrustServerCertificate=yes;"
    "Connect Timeout=5;Command Timeout=15"
)
print("Connected!")
cur = conn.cursor()
print("Running COUNT(*) FROM sys.tables...")
t0 = time.time()
try:
    cur.execute("SELECT COUNT(*) FROM sys.tables")
    row = cur.fetchone()
    print(f"Tables count: {row[0]}, elapsed: {time.time()-t0:.2f}s")
except Exception as e:
    print(f"ERROR: {e}")

print("Running table_size_query...")
t0 = time.time()
try:
    cur.execute(
        "SELECT TOP 5 s.name AS schema_name, t.name AS table_name, "
        "SUM(ps.row_count) AS row_count, "
        "CAST(SUM(ps.used_page_count)*8.0/1024 AS DECIMAL(18,2)) AS total_space_mb "
        "FROM sys.tables t "
        "JOIN sys.schemas s ON t.schema_id=s.schema_id "
        "JOIN sys.dm_db_partition_stats ps ON t.object_id=ps.object_id AND ps.index_id IN (0,1) "
        "GROUP BY s.name, t.name ORDER BY total_space_mb DESC"
    )
    rows = cur.fetchall()
    for r in rows:
        print(f"  {r[0]}.{r[1]} - {r[2]} rows, {r[3]} MB")
    print(f"table_size_query done: {time.time()-t0:.2f}s")
except Exception as e:
    print(f"ERROR: {e}")

conn.close()
print("Done!")
