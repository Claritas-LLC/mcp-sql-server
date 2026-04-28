#!/usr/bin/env python3
"""Test script to call check_fragmentation tool for instance 2."""

import os
import sys
import logging

# Set up logging BEFORE importing server
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stdout,
    force=True  # Override any existing configuration
)

# Also set the mcp_sqlserver logger to DEBUG explicitly
mcp_logger = logging.getLogger("mcp_sqlserver")
mcp_logger.setLevel(logging.DEBUG)
mcp_logger.addHandler(logging.StreamHandler(sys.stdout))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import after setting up logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mcp_sqlserver'))

try:
    from server import db_sql2019_check_fragmentation, initialize_connection_pools, SETTINGS
    
    print("=" * 80)
    print("TESTING: db_02_check_fragmentation for US_RT_User_800 on instance 2")
    print("=" * 80)
    
    # Initialize connection pools
    print("\n[INIT] Initializing connection pools...")
    initialize_connection_pools()
    print(f"[INIT] Available instances: {list(SETTINGS.db_instances.keys())}")
    
    # Call the function directly (bypasses wrapper, but function has debug logging)
    print("\n[CALL] Calling db_sql2019_check_fragmentation directly...")
    result = db_sql2019_check_fragmentation(
        instance=2,
        database_name="US_RT_User_800",
        page=1,
        page_size=50
    )
    
    print("\n[RESULT] Function returned successfully")
    print(f"[RESULT] Total items: {len(result.get('items', []))}")
    if 'pagination' in result:
        print(f"[RESULT] Pagination: {result['pagination']}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETED")
    print("=" * 80)
    
except Exception as e:
    print(f"\n[ERROR] Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
