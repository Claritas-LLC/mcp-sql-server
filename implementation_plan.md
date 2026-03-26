# Restoration of Missing MCP Tools

The goal is to restore missing MCP tools in [server.py](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/profile_server.py) based on the [README.md](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/README.md) and the functionalities present in a previous version (commit `dc1267a4b5a6b74a5921ac4c71c7f8bec880f69c`). The current [server.py](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/profile_server.py) has been partially migrated to a dual-instance pattern but many tools were left out of the registration or are missing their implementations.

## User Review Required

> [!IMPORTANT]
> The missing tools will be restored using the implementation from the target commit, but adapted for the dual-instance pattern (adding [instance](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/mcp_sqlserver/server.py#119-143) parameter and using the correct connection).

## Proposed Changes

### [Component Name] mcp_sqlserver

#### [MODIFY] [server.py](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/mcp_sqlserver/server.py)

1.  **Restore Missing Implementations**: Copy the following functions from the old [server.py](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/profile_server.py) and adapt them:
    *   [_fetch_relationships](file:///tmp/server_root_old.py#2340-2379)
    *   [_analyze_erd_issues](file:///tmp/server_root_old.py#2408-2650)
    *   [_analyze_logical_data_model_internal](file:///tmp/server_root_old.py#2652-2708)
    *   `_OPEN_MODEL_CACHE` (initialization)
    *   [_apply_top_queries_view](file:///tmp/server_root_old.py#747-773)
    *   [_apply_table_health_view](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/mcp_sqlserver/server.py#801-830)
    *   [_apply_logical_model_view](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/mcp_sqlserver/server.py#832-876)
    *   [db_sql2019_open_logical_model](file:///tmp/server_root_old.py#2713-2726) (missing from current implementations)
    *   [db_sql2019_generate_ddl](file:///tmp/server_root_old.py#2728-2830) (missing from current implementations)
    *   [db_sql2019_create_db_user](file:///tmp/server_root_old.py#2832-2863) (missing from current implementations)
    *   [db_sql2019_drop_db_user](file:///tmp/server_root_old.py#2865-2899) (missing from current implementations)
    *   [db_sql2019_kill_session](file:///tmp/server_root_old.py#2901-2923) (missing from current implementations)
    *   [db_sql2019_create_object](file:///tmp/server_root_old.py#2969-2996) (already present but verify)
    *   [db_sql2019_alter_object](file:///tmp/server_root_old.py#2998-3044) (already present but verify)
2.  **Ensure Adaptations**: Each restored function must:
    *   Accept an `instance: int = 1` parameter.
    *   Use [get_connection(..., instance=instance)](file:///tmp/server_root_old.py#514-525) where applicable.
    *   Use [get_instance_config(instance)](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/mcp_sqlserver/server.py#75-79) for instance-specific settings.
3.  **Update Tool Registration**:
    *   Modify `_register_dual_instance_tools` to use the full `_TOOL_REGISTRATION_LIST` (25+ tools) instead of the hardcoded 10 tools.
    *   Ensure all tools in `_TOOL_REGISTRATION_LIST` have corresponding implementations.
4.  **Reanalyze and Fix**: 
    *   Check for any syntax errors or lint issues in the "Problems" pane after the large-scale restoration.
    *   Fix any identified bugs or inconsistencies.

### Documentation

#### [NEW] [USERS_GUIDE.md](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/USERS_GUIDE.md)
*   Create a dedicated guide for end-users on how to integrate and use the MCP server tools with:
    *   **n8n**: Setting up the MCP node, authentication, and practical workflow examples.
    *   **VS Code**: Configuring MCP extensions (e.g., Roo Code, Cline) to connect to the server.
    *   **Cursor**: Using the MCP server within Cursor's AI features.

#### [MODIFY] [README.md](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/README.md)
*   Update the "Usage" or "Getting Started" sections to point users to the new `USERS_GUIDE.md` for detailed integration instructions.

#### [NEW] [AZURE_DEPLOYMENT_GUIDE.md](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/AZURE_DEPLOYMENT_GUIDE.md)
*   Perform a comprehensive analysis of Azure deployment options for the MCP server:
    *   **Options**: Provisioning a VM with Docker (Public IP), Azure Container Instances (ACI), Azure Kubernetes Service (AKS), Azure Container Apps (ACA).
    *   **Ranking Criteria**: Cost (Highest priority), Management Overhead, and Security.
    *   **Scope**: Focus on a remote MCP server deployable as a Docker container.
    *   **Security**: Must include Azure Entra (OAuth) for authentication and authorization.
    *   **Deliverable**: Provide assumptions, comparison table, and a definitive recommendation.

## Verification Plan

### Automated Tests
*   Run the server and verify that all 25+ tools are listed as registered.
*   Run `pytest tests/test_integration_tools.py` to verify functionality against a live SQL Server (if available/configured).
*   Run a custom script to check that both `db_01_sql2019_*` and `db_02_sql2019_*` versions of each tool are registered.

### Manual Verification
*   Check the server logs during startup to see the "Registered MCP tools" list.
