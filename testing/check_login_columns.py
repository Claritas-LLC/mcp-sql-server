#!/usr/bin/env python3
"""Test script to check SQL Server login columns."""

import sys
import os

# Add the current directory to Python path to import server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import get_connection

def check_login_columns():
    """Check the correct column names for sys.server_principals."""
    print("Checking sys.server_principals column names...")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get column information
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'server_principals' AND TABLE_SCHEMA = 'sys'
            ORDER BY ORDINAL_POSITION
        """)
        
        columns = cursor.fetchall()
        print("Available columns in sys.server_principals:")
        for col in columns:
            print(f"  - {col[0]} ({col[1]}) - Nullable: {col[2]}")
        
        # Also try a simple select to see what we get
        cursor.execute("SELECT TOP 1 * FROM sys.server_principals WHERE type = 'S'")
        cursor_description = cursor.description
        print("\nColumn names from cursor description:")
        for i, desc in enumerate(cursor_description):
            print(f"  {i}: {desc[0]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    check_login_columns()
