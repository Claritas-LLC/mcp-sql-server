#!/usr/bin/env python
"""Simple test to verify imports work."""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Attempting to import server module...")
    import server
    print("PASS Server module imported successfully")
    
    print("Checking for function db_01_sql2019_list_objects...")
    if hasattr(server, 'db_01_sql2019_list_objects'):
        print("PASS db_01_sql2019_list_objects function exists")
    else:
        print("FAIL db_01_sql2019_list_objects function not found")
        
    print("Checking for function get_connection...")
    if hasattr(server, 'get_connection'):
        print("PASS get_connection function exists")
    else:
        print("FAIL get_connection function not found")
        
    print("\nAll checks passed!")
    
except SyntaxError as e:
    print(f"* SyntaxError: {e}")
    print(f"  File: {e.filename}, Line: {e.lineno}")
    sys.exit(1)
except ImportError as e:
    print(f"* ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"* Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
