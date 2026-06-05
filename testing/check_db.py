import pyodbc
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=10.125.1.8,1433;"
    "DATABASE=master;"
    "UID=mcp_readonly;"
    "PWD=***REMOVED***;"
    "Encrypt=no;TrustServerCertificate=yes;"
    "Connect Timeout=5;Command Timeout=5"
)
cur = conn.cursor()
cur.execute("SELECT name, state_desc, recovery_model_desc FROM sys.databases WHERE name='US_RT_User_800'")
row = cur.fetchone()
print(f"Database state: {row}")
conn.close()
print("Done!")
