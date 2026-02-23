#!/usr/bin/env python3
"""Simple connection test."""

import sys
import os

# Add the current directory to Python path to import server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import get_connection

def test_connection():
    """Test basic connection."""
    print("Testing basic connection...")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Simple test query
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        print(f"✅ Connection successful!")
        print(f"SQL Server Version: {version[:100]}...")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    test_connection()