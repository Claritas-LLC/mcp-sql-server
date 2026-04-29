import os
import json
import logging
from mcp_sqlserver.server import db_sql2019_check_fragmentation, initialize_connection_pools, SETTINGS

# Setup logging to see our new per-instance traces
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    print("Initializing connection pools...")
    initialize_connection_pools()
    
    print("\nCalling db_sql2019_check_fragmentation for Instance 2...")
    print("Database: US_RT_User_800")
    
    try:
        # We call the core function. Note: instance=2 is explicitly passed.
        # This will test our fix for per-instance locks and pool initialization.
        result = db_sql2019_check_fragmentation(
            instance=2,
            database_name="US_RT_User_800",
            min_fragmentation=0.0,
            page_size=10
        )
        
        print("\n--- RESULTS ---")
        print(json.dumps(result, indent=2))
        
        items = result.get("items", [])
        if items:
            print(f"\nFound {len(items)} fragmented indexes.")
        else:
            print("\nNo fragmented indexes found (or fragmentation levels are below thresholds).")
            
    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    main()
