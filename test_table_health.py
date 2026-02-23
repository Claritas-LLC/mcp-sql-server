#!/usr/bin/env python3

import asyncio
import json
import sys
import os

# Add the current directory to the path so we can import from server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import db_sql2019_analyze_table_health

async def test_table_health():
    """Test the table health analysis function"""
    try:
        print("Testing db_sql2019_analyze_table_health function...")
        
        # Call the function
        result = db_sql2019_analyze_table_health(
            database_name='USGISPRO_800',
            schema='dbo',
            table_name='Account'
        )
        
        print("Function executed successfully!")
        print(f"Result type: {type(result)}")
        print(f"Result keys: {list(result.keys())}")
        
        # Print the result in a formatted way
        print("\nFull Result:")
        print(json.dumps(result, indent=2, default=str))
        
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(test_table_health())