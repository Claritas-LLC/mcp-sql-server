import os
import sys
import json
from datetime import datetime, date, timedelta

# Add the parent directory of server.py to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Set environment variables for database connection
os.environ['DB_SERVER'] = 'localhost'
os.environ['DB_PORT'] = '1433'
os.environ['DB_USER'] = 'SA'
os.environ['DB_PASSWORD'] = 'YourStrong!Password1'
os.environ['DB_NAME'] = 'TEST_DB' # Use TEST_DB for most tests
os.environ['DB_DRIVER'] = 'ODBC Driver 17 for SQL Server'

def run_test(test_name: str, func, *args, **kwargs):
    print(f"\n--- Running Test: {test_name} ---")
    try:
        result = func(*args, **kwargs)
        print(f"Result for {test_name}:")
        # Custom JSON serialization for Decimal and datetime objects
        def default_serializer(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, server.decimal.Decimal):
                return float(obj)
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        print(json.dumps(result, indent=2, default=default_serializer))
        print(f"--- Test '{test_name}' PASSED ---")
        return True
    except Exception as e:
        print(f"--- Test '{test_name}' FAILED with error: {e} ---")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Debugging: Starting test_tools.py script")
    
    print("Importing the tools from server.py...")
    try:
        import server
        print("Debugging: server.py imported successfully.")
    except Exception as e:
        print(f"Debugging: Failed to import server.py: {e}")
        sys.exit(1)

    all_tests_passed = True

    # Test 1: db_sql2019_server_info_mcp()
    if not run_test("db_sql2019_server_info_mcp", server.db_sql2019_server_info_mcp):
        all_tests_passed = False

    print("\n--- Skipping remaining tests for focused debugging ---")

    if all_tests_passed:
        print("\n===== All direct function tests PASSED =====")
    else:
        print("\n===== Some direct function tests FAILED =====")
