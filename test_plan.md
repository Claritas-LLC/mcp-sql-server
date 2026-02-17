# MCP Server Test Plan

## 1. Introduction

This document outlines the comprehensive test plan for the MCP server, focusing on ensuring the accuracy, completeness, and reliability of its readonly tools. The plan covers various testing methodologies, including unit, integration, stress, and blackbox testing.

## 2. Readonly Tools Identified

Based on the code review of `server.py`, the following tools have been identified as readonly and will be the focus of this test plan:

- `db_sql2019_check_fragmentation`
- `db_sql2019_db_stats`
- `db_sql2019_db_analyze_query_store`
- `temp_analyze_query_store_wrapper`
- `db_sql2019_analyze_index_health`
- `db_sql2019_sec_perf_metrics`
- `db_sql2019_recommend_partitioning`
- `db_sql2019_analyze_sessions`
- `db_sql2019_server_info`
- `db_sql2019_get_db_parameters`
- `db_sql2019_list_objects`
- `db_sql2019_analyze_indexes`
- `db_sql2019_analyze_table_health`
- `db_sql2019_db_sec_perf_metrics`
- `db_sql2019_analyze_logical_data_model`
- `db_sql2019_describe_table`
- `db_sql2019_run_query`
- `db_sql2019_explain_query`
- `ping`
- `server_info_mcp`
- `monitor_sessions`

## 3. Testing Phases

### 3.1. Unit Testing

**Objective:** To test individual tools in isolation to verify their logic and data transformations.

**Methodology:**
- Use the `unittest` framework in Python.
- Mock database connections and function calls to external services.
- Create mock data to simulate various scenarios, including valid, invalid, and edge cases.
- Write assertions to validate the output of each tool against expected results.
- Focus on the `tests/unit_test_mocked.py` file for implementation.

### 3.2. Integration Testing

**Objective:** To test the interaction between the MCP server and a live SQL Server database.

**Methodology:**
- Use a dedicated test database to avoid impacting production data.
- The `.env` file will be configured to connect to the test database.
- Write tests that execute each readonly tool against the test database.
- Validate the results returned by the tools against the known state of the test database.
- These tests will be implemented in `tests/test_server.py`.

### 3.3. Stress Testing

**Objective:** To evaluate the server's performance and stability under heavy load.

**Methodology:**
- Use a tool like `locust` or a custom Python script to send a high volume of concurrent requests to the MCP server.
- Monitor server-side metrics such as CPU usage, memory consumption, and response times.
- Identify performance bottlenecks and potential breaking points.
- The `tests/comprehensive_test.py` file will be a good place to add these tests.

### 3.4. Blackbox Testing

**Objective:** To test the MCP server's functionality from a user's perspective without any knowledge of the internal implementation.

**Methodology:**
- Use the MCP client or a tool like `curl` or `Postman` to send requests to the server's API endpoints.
- Verify that the responses are well-formed (e.g., valid JSON) and contain the expected data.
- Test various input parameters for each tool to ensure they are handled correctly.
- This will be done manually and also can be scripted in `tests/test_server.py`.

## 4. Test Execution and Reporting

- Tests will be executed in a dedicated CI/CD pipeline (if available) or manually.
- Test results will be documented, and any failures will be investigated.
- Bugs will be reported and tracked using a bug tracking system (if available).
- The `README.md` and `DEPLOYMENT.md` files will be updated with the latest information after successful testing.
