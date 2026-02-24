#!/usr/bin/env python3
"""
Comprehensive MCP Tools Testing Script
Tests all SQL Server MCP tools with the TEST_DB database
"""

import os
import sys
import json
import traceback
from datetime import datetime, date, timedelta
from typing import Any, Dict, List

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import server module (with FastMCP decorators commented out)
import server

# Set up environment variables for testing
os.environ['DB_SERVER'] = 'localhost'
os.environ['DB_PORT'] = '1433'
os.environ['DB_USER'] = 'SA'
os.environ['DB_PASSWORD'] = 'YourStrong!Password1'
os.environ['DB_NAME'] = 'TEST_DB'
os.environ['DB_DRIVER'] = 'ODBC Driver 17 for SQL Server'

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_test_header(test_name: str):
    print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}TESTING: {test_name}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")

def print_test_result(test_name: str, success: bool, error: str = None):
    if success:
        print(f"{Colors.OKGREEN}✓ {test_name} PASSED{Colors.ENDC}")
    else:
        print(f"{Colors.FAIL}✗ {test_name} FAILED{Colors.ENDC}")
        if error:
            print(f"{Colors.FAIL}Error: {error}{Colors.ENDC}")

def safe_json_serialize(obj: Any) -> str:
    """Safely serialize objects to JSON"""
    def json_default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, timedelta):
            return str(obj)
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return str(obj)
    
    try:
        return json.dumps(obj, indent=2, default=json_default)
    except Exception as e:
        return f"JSON serialization error: {str(e)}"

def test_server_info():
    """Test db_sql2019_server_info_mcp tool"""
    print_test_header("db_sql2019_server_info_mcp")
    try:
        result = server.db_sql2019_server_info_mcp()
        print("Server Info Result:")
        print(safe_json_serialize(result))
        print_test_result("Server Info", True)
        return True
    except Exception as e:
        print_test_result("Server Info", False, str(e))
        traceback.print_exc()
        return False

def test_list_objects():
    """Test db_sql2019_list_objects tool with various parameters"""
    print_test_header("db_sql2019_list_objects")
    success_count = 0
    total_tests = 0
    
    # Test different object types
    test_cases = [
        ("TABLE", None, None),
        ("VIEW", None, None),
        ("PROCEDURE", None, None),
        ("TABLE", "sales", None),
        ("TABLE", "hr", None),
        ("TABLE", "inventory", None),
    ]
    
    for object_type, schema, filter_pattern in test_cases:
        total_tests += 1
        try:
            result = server.db_sql2019_list_objects(object_type=object_type, schema=schema, filter_pattern=filter_pattern)
            print(f"\nObjects ({object_type}, schema={schema}, filter={filter_pattern}):")
            print(safe_json_serialize(result))
            success_count += 1
        except Exception as e:
            print(f"Error testing {object_type} with schema {schema}: {str(e)}")
    
    print_test_result(f"List Objects ({success_count}/{total_tests})", success_count == total_tests)
    return success_count == total_tests

def test_analyze_table_health():
    """Test db_sql2019_analyze_table_health tool"""
    print_test_header("db_sql2019_analyze_table_health")
    success_count = 0
    total_tests = 0
    
    test_tables = [
        ("TEST_DB", "sales", "Customers"),
        ("TEST_DB", "sales", "Products"),
        ("TEST_DB", "hr", "Employees"),
        ("TEST_DB", "inventory", "StockMovements"),
    ]
    
    for database_name, schema, table_name in test_tables:
        total_tests += 1
        try:
            result = server.db_sql2019_analyze_table_health(database_name=database_name, schema=schema, table_name=table_name)
            print(f"\nTable Health ({database_name}.{schema}.{table_name}):")
            print(safe_json_serialize(result))
            success_count += 1
        except Exception as e:
            print(f"Error analyzing {database_name}.{schema}.{table_name}: {str(e)}")
    
    print_test_result(f"Table Health Analysis ({success_count}/{total_tests})", success_count == total_tests)
    return success_count == total_tests

def test_check_fragmentation():
    """Test db_sql2019_check_fragmentation tool"""
    print_test_header("db_sql2019_check_fragmentation")
    try:
        result = server.db_sql2019_check_fragmentation(database_name="TEST_DB")
        print("Fragmentation Analysis Result:")
        print(safe_json_serialize(result))
        print_test_result("Fragmentation Check", True)
        return True
    except Exception as e:
        print_test_result("Fragmentation Check", False, str(e))
        traceback.print_exc()
        return False

def test_show_top_queries():
    """Test db_sql2019_show_top_queries tool"""
    print_test_header("db_sql2019_show_top_queries")
    try:
        result = server.db_sql2019_show_top_queries(database="TEST_DB")
        print("Top Queries Result:")
        print(safe_json_serialize(result))
        print_test_result("Top Queries", True)
        return True
    except Exception as e:
        print_test_result("Top Queries", False, str(e))
        traceback.print_exc()
        return False

def test_db_sec_perf_metrics():
    """Test db_sql2019_db_sec_perf_metrics tool with different profiles"""
    print_test_header("db_sql2019_db_sec_perf_metrics")
    success_count = 0
    total_tests = 0
    
    profiles = ["oltp", "analytics", "mixed"]
    
    for profile in profiles:
        total_tests += 1
        try:
            result = server.db_sql2019_db_sec_perf_metrics(database_name="TEST_DB", profile=profile)
            print(f"\nSecurity & Performance Metrics ({profile} profile):")
            print(safe_json_serialize(result))
            success_count += 1
        except Exception as e:
            print(f"Error testing profile {profile}: {str(e)}")
    
    print_test_result(f"DB Security & Performance Metrics ({success_count}/{total_tests})", success_count == total_tests)
    return success_count == total_tests

def test_analyze_logical_data_model():
    """Test db_sql2019_analyze_logical_data_model tool"""
    print_test_header("db_sql2019_analyze_logical_data_model")
    try:
        result = server.db_sql2019_analyze_logical_data_model(database_name="TEST_DB")
        print("Logical Data Model Analysis Result:")
        print(safe_json_serialize(result))
        print_test_result("Logical Data Model Analysis", True)
        return True
    except Exception as e:
        print_test_result("Logical Data Model Analysis", False, str(e))
        traceback.print_exc()
        return False

def test_generate_ddl():
    """Test db_sql2019_generate_ddl tool"""
    print_test_header("db_sql2019_generate_ddl")
    success_count = 0
    total_tests = 0
    
    test_objects = [
        ("TEST_DB", "sales.Customers", "TABLE"),
        ("TEST_DB", "sales.Products", "TABLE"),
    ]
    
    for database_name, object_name, object_type in test_objects:
        total_tests += 1
        try:
            result = server.db_sql2019_generate_ddl(database_name=database_name, object_name=object_name, object_type=object_type)
            print(f"\nDDL Generation ({database_name}.{object_name}):")
            print(safe_json_serialize(result))
            success_count += 1
        except Exception as e:
            print(f"Error generating DDL for {database_name}.{object_name}: {str(e)}")
    
    print_test_result(f"DDL Generation ({success_count}/{total_tests})", success_count == total_tests)
    return success_count == total_tests

def test_explain_query():
    """Test db_sql2019_explain_query tool"""
    print_test_header("db_sql2019_explain_query")
    success_count = 0
    total_tests = 0
    
    test_queries = [
        "SELECT * FROM sales.Customers WHERE CustomerID = 1",
        "SELECT c.FirstName, c.LastName, COUNT(o.OrderID) as OrderCount FROM sales.Customers c LEFT JOIN sales.Orders o ON c.CustomerID = o.CustomerID GROUP BY c.CustomerID, c.FirstName, c.LastName",
        "SELECT * FROM sales.Products WHERE Price > 100 ORDER BY Price DESC",
    ]
    
    for query in test_queries:
        total_tests += 1
        try:
            result = server.db_sql2019_explain_query(database_name="TEST_DB", query=query)
            print(f"\nQuery Explanation ({query[:50]}...):")
            print(safe_json_serialize(result))
            success_count += 1
        except Exception as e:
            print(f"Error explaining query {query[:50]}...: {str(e)}")
    
    print_test_result(f"Query Explanation ({success_count}/{total_tests})", success_count == total_tests)
    return success_count == total_tests

def test_run_query():
    """Test db_sql2019_run_query tool in read mode"""
    print_test_header("db_sql2019_run_query (READ mode)")
    success_count = 0
    total_tests = 0
    
    test_queries = [
        "SELECT COUNT(*) as CustomerCount FROM sales.Customers",
        "SELECT TOP 5 * FROM sales.Products ORDER BY Price DESC",
        "SELECT Department, COUNT(*) as EmployeeCount FROM hr.Employees GROUP BY Department",
    ]
    
    for query in test_queries:
        total_tests += 1
        try:
            result = server.db_sql2019_run_query(database_name="TEST_DB", query=query, mode="read")
            print(f"\nQuery Result ({query[:50]}...):")
            print(safe_json_serialize(result))
            success_count += 1
        except Exception as e:
            print(f"Error running query {query[:50]}...: {str(e)}")
    
    print_test_result(f"Run Query Read Mode ({success_count}/{total_tests})", success_count == total_tests)
    return success_count == total_tests

def test_user_management():
    """Test user management tools"""
    print_test_header("User Management Tools")
    success_count = 0
    total_tests = 0
    
    # Test create user
    total_tests += 1
    try:
        result = server.create_db_user(database_name="TEST_DB", username="test_user_2024", password="TestPass123!")
        print("Create User Result:")
        print(safe_json_serialize(result))
        success_count += 1
    except Exception as e:
        print(f"Error creating user: {str(e)}")
    
    # Test drop user
    total_tests += 1
    try:
        result = server.drop_db_user(database_name="TEST_DB", username="test_user_2024")
        print("Drop User Result:")
        print(safe_json_serialize(result))
        success_count += 1
    except Exception as e:
        print(f"Error dropping user: {str(e)}")
    
    print_test_result(f"User Management ({success_count}/{total_tests})", success_count == total_tests)
    return success_count == total_tests

def main():
    """Main testing function"""
    print(f"{Colors.BOLD}{Colors.OKBLUE}Starting Comprehensive MCP Tools Testing{Colors.ENDC}")
    print(f"Test Database: TEST_DB")
    print(f"Test Started: {datetime.now()}")
    
    test_functions = [
        test_server_info,
        test_list_objects,
        test_analyze_table_health,
        test_check_fragmentation,
        test_show_top_queries,
        test_db_sec_perf_metrics,
        test_analyze_logical_data_model,
        test_generate_ddl,
        test_explain_query,
        test_run_query,
        test_user_management,
    ]
    
    passed_tests = 0
    total_tests = len(test_functions)
    
    for test_func in test_functions:
        try:
            if test_func():
                passed_tests += 1
        except Exception as e:
            print(f"{Colors.FAIL}Test function {test_func.__name__} failed with error: {str(e)}{Colors.ENDC}")
            traceback.print_exc()
    
    print(f"\n{Colors.BOLD}{Colors.OKBLUE}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKBLUE}TESTING COMPLETED{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKBLUE}{'='*80}{Colors.ENDC}")
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    print(f"Test Completed: {datetime.now()}")
    
    if passed_tests == total_tests:
        print(f"{Colors.OKGREEN}All tests passed successfully!{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}Some tests failed. Please review the output above.{Colors.ENDC}")

if __name__ == "__main__":
    main()