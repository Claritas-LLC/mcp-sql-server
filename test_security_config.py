#!/usr/bin/env python3
"""Test the security config query specifically."""

import sys
import os

# Add the current directory to Python path to import server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import get_connection

def test_security_config():
    """Test the security configurations query."""
    print("Testing security configurations query...")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Test simpler version first
        print("Testing simple configuration query...")
        cursor.execute("SELECT name, value, value_in_use, description FROM sys.configurations WHERE name = 'xp_cmdshell'")
        result = cursor.fetchone()
        if result:
            print(f"✅ Simple query works: {result}")
        
        # Now test the full query with all configurations
        print("\nTesting full security config query...")
        configurations = [
            'cross db ownership chaining',
            'xp_cmdshell', 
            'Ad Hoc Distributed Queries',
            'clr enabled',
            'Database Mail XPs',
            'Ole Automation Procedures'
        ]
        
        for config_name in configurations:
            try:
                cursor.execute("SELECT name, value, value_in_use, description FROM sys.configurations WHERE name = ?", config_name)
                result = cursor.fetchone()
                if result:
                    print(f"✅ {config_name}: value={result[1]}, in_use={result[2]}")
                else:
                    print(f"ℹ️  {config_name}: not found or no access")
            except Exception as e:
                print(f"❌ Error with {config_name}: {e}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_security_config()