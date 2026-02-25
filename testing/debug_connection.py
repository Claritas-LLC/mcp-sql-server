import pyodbc
import os
import sys
import time

# Flush stdout automatically
sys.stdout.reconfigure(line_buffering=True)

print("--- SQL Server Connection Debugger ---", flush=True)

# List available drivers
drivers = pyodbc.drivers()
print(f"Available ODBC Drivers: {drivers}", flush=True)

# Helper to try connection
def try_connect(description, server, user, password, database, driver_candidates):
    print(f"\nAttempting to connect to {description}...", flush=True)
    
    # Find a usable driver
    driver = None
    for d in driver_candidates:
        if d in drivers:
            driver = d
            break
        # Also handle case where driver string in config includes braces
        clean_d = d.strip('{}')
        if clean_d in drivers:
            driver = clean_d
            break
            
    if not driver:
        print(f"SKIPPING: No suitable driver found. Needed one of: {driver_candidates}", flush=True)
        return

    print(f"Using Driver: {driver}", flush=True)
    
    conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={user};PWD={password};TrustServerCertificate=yes;Encrypt=no"
    
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        print("SUCCESS: Connected!", flush=True)
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        print(f"Server Version: {row[0][:50]}...", flush=True)
        conn.close()
        return True
    except Exception as e:
        print(f"FAILURE: {e}", flush=True)
        return False

# Load .env
from dotenv import load_dotenv
load_dotenv(override=True)
env_server = os.getenv("DB_SERVER", "127.0.0.1")
env_user = os.getenv("DB_USER", "sa")
env_pass = os.getenv("DB_PASSWORD", "Harryv1983")
env_driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

print(f"Config: Server={env_server}, User={env_user}, Pass={env_pass}", flush=True)

# Loop to wait for DB readiness
max_retries = 10
for i in range(max_retries):
    success = try_connect(
        f"Local DB (Attempt {i+1}/{max_retries})", 
        env_server, 
        env_user, 
        env_pass, 
        "master", 
        [env_driver, "ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]
    )
    if success:
        break
    if i < max_retries - 1:
        print("Waiting 5s for DB to come up...", flush=True)
        time.sleep(5)
