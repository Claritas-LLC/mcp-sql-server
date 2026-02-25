#!/usr/bin/env python3
"""
Test script to call db_sql2019_server_info_mcp() and display results.
Uses mocked readonly connection to demonstrate the function.
"""

import os
import sys
import json
from unittest import mock

# Configure readonly environment
os.environ['MCP_SKIP_CONFIRMATION'] = 'true'
os.environ['DB_SERVER'] = 'localhost'
os.environ['DB_NAME'] = 'master'
os.environ['DB_USER'] = 'sa'
os.environ['MCP_ALLOW_WRITE'] = 'false'
os.environ['MCP_TRANSPORT'] = 'stdio'


# Ensure parent directory is in sys.path for mcp_sqlserver import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


if __name__ == '__main__':
    print("=" * 80)
    print("SQL Server MCP - db_sql2019_server_info_mcp() Test")
    print("=" * 80)
    print()

    try:
        # Step 1: Import
        print("[1/5] Importing server module...")
        import importlib.util
        import sys as _sys
        server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'server.py'))
        spec = importlib.util.spec_from_file_location('server', server_path)
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        print("      [+] Server module imported")
        print()
        
        # Step 2: Verify configuration
        print("[2/5] Verifying configuration...")
        print(f"      - MCP_SKIP_CONFIRMATION = {os.environ.get('MCP_SKIP_CONFIRMATION')}")
        print(f"      - MCP_ALLOW_WRITE = {os.environ.get('MCP_ALLOW_WRITE')}")
        print(f"      - MCP_TRANSPORT = {os.environ.get('MCP_TRANSPORT')}")
        print("      [+] Configuration verified")
        print()
        
        # Step 3: Mock connection
        print("[3/5] Creating mocked SQL Server connection...")
        mock_conn = mock.MagicMock()
        mock_cursor = mock.MagicMock()

        # Provide 8 fetchone() results, one for each SQL property fetched
        mock_cursor.fetchone.side_effect = [
            ('Microsoft SQL Server 2022 (RTM) - 16.0.4001.0 (X64) Build 16.0.4001.0',),  # @@VERSION
            ('MYSERVER',),        # @@SERVERNAME
            ('master',),         # DB_NAME()
            ('sa',),             # SYSTEM_USER
            ('16.0.4001.0',),    # SERVERPROPERTY('ProductVersion')
            ('Enterprise',),     # SERVERPROPERTY('Edition')
            ('127.0.0.1',),      # CONNECTIONPROPERTY('local_net_address')
            (1433,),             # CONNECTIONPROPERTY('local_tcp_port')
        ]
        mock_conn.cursor.return_value = mock_cursor

        # Patch get_connection in the loaded server module's namespace
        server.get_connection = mock.MagicMock(return_value=mock_conn)

        print("      [+] Mock connection ready")
        print()
        
        # Step 4: Call function
        print("[4/5] Executing db_sql2019_server_info_mcp()...")
        with mock.patch('server.get_connection', return_value=mock_conn):
            result = server.db_sql2019_server_info_mcp()
        
        print("      [+] Function executed successfully")
        print()
        
        # Step 5: Assert results
        print("[5/5] Asserting results...")
        assert isinstance(result, dict), "Result should be a dictionary"
        assert result.get('server_name') == 'MYSERVER', "Server name should match mocked data"
        assert result.get('database') == 'master', "Database should match mocked data"
        assert result.get('user') == 'sa', "User should match mocked data"
        assert result.get('server_version') == 'Microsoft SQL Server 2022 (RTM) - 16.0.4001.0 (X64) Build 16.0.4001.0', "Server version should match mocked data"
        assert result.get('server_edition') == 'Enterprise', "Server edition should match mocked data"
        assert result.get('server_addr') == '127.0.0.1', "Server address should match mocked data"
        assert result.get('server_port') == 1433, "Server port should match mocked data"
        print("      [+] Assertions passed")
        print()
        
        # Display results
        print("=" * 80)
        print("RESULTS")
        print("=" * 80)
        print()
        
        if isinstance(result, dict):
            # Pretty print results
            for key, value in result.items():
                if isinstance(value, bool):
                    print(f"  {key:.<30} {str(value).upper()}")
                elif isinstance(value, int):
                    print(f"  {key:.<30} {value}")
                else:
                    print(f"  {key:.<30} {value}")
        else:
            print(json.dumps(result, indent=2, default=str))
        
        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        if isinstance(result, dict):
            print(f"  Server Name:    {result.get('server_name', 'N/A')}")
            print(f"  Database:       {result.get('database', 'N/A')}")
            print(f"  User:           {result.get('user', 'N/A')}")
            print(f"  Server Address: {result.get('server_addr', 'N/A')}:{result.get('server_port', 'N/A')}")
            print(f"  Status:         {result.get('status', 'N/A')}")
            print(f"  Transport:      {result.get('transport', 'N/A')}")
            print(f"  Allow Write:    {result.get('allow_write', 'N/A')}")
            print()
            print(f"  MCP Server:     {result.get('name', 'N/A')}")
            print(f"  MCP Version:    {result.get('version', 'N/A')}")
        
        print()
        print("=" * 80)
        print("[+] TEST PASSED - Function works correctly")
        print("=" * 80)

    except AssertionError as e:
        print(f"[!] Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[!] Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("=" * 80)
        sys.exit(1)
