# MCP SQL Server User Guide

This guide explains how to integrate and use the SQL Server Model Context Protocol (MCP) server with various client applications including n8n, VS Code, and Cursor.

## Overview

The SQL Server MCP server provides a standardized interface for LLMs to interact with SQL Server databases. It supports dual-instance connectivity, allowing you to manage two different database servers (`db_01` and `db_02`) through a single MCP interface.

All tools are prefixed based on the target instance:
- `db_01_*`: Tools for the first SQL Server instance.
- `db_02_*`: Tools for the second SQL Server instance.

---

## Integration with n8n

n8n can interact with this MCP server either via the **HTTP Transport** (if running as a remote service) or by executing the server locally using the **Execute Command** node.

### Option 1: Using the MCP Node (Direct)
If you have the n8n MCP node installed:
1.  Add an **MCP** node to your workflow.
2.  Set the **Transport** to `stdio`.
3.  Set the **Command** to `python`.
4.  Set the **Arguments** to the path of the `server.py` file.
5.  All 50 tools will appear in the node's tool selection.

### Option 2: Remote MCP via HTTP
To use the MCP server as a remote service:
1.  Deploy the MCP server as a container (see [Azure Deployment Guide](AZURE_DEPLOYMENT_GUIDE.md)).
2.  In n8n, use the **HTTP Request** node to call the MCP endpoints or use a specialized MCP client node pointing to the server's URL.

---

## Integration with VS Code

VS Code supports MCP via several extensions (e.g., "MCP Client" or specialized AI assistants).

1.  **Install the Extension**: Install an MCP-compatible assistant extension.
2.  **Configure MCP Settings**:
    Add the following to your extension's MCP configuration:
    ```json
    {
      "mcpServers": {
        "sql-server": {
          "command": "python",
          "args": ["C:/absolute/path/to/mcp_sqlserver/server.py"],
          "env": {
            "SQL_SERVER_01": "your-server-01",
            "SQL_DATABASE_01": "your-db-01",
            "SQL_USER_01": "your-user-01",
            "SQL_PASSWORD_01": "your-password-01"
          }
        }
      }
    }
    ```
3.  **Usage**: Open the AI chat and ask: "List the tables in db_01" or "Check the health of the Orders table in db_02".

---

## Integration with Cursor

Cursor has built-in support for MCP servers.

1.  **Open Cursor Settings**: Go to `Settings` -> `Features` -> `MCP`.
2.  **Add New MCP Server**:
    - **Name**: `SQL Server`
    - **Type**: `command`
    - **Command**: `python c:/path/to/mcp_sqlserver/server.py`
3.  **Verification**: Click the "Refresh" icon. You should see "50 tools found".
4.  **Usage**: In Cursor Chat (Ctrl+L) or Composer (Ctrl+I), you can now use natural language to query your databases:
    - *"@SQL Server show me the schema of the Users table"*
    - *"Analyze the performance of the query in this file against db_02"*

---

## Common Use Cases

### Diagnostic & Health
- `db_01_table_health`: Get a comprehensive health report for a table (indexes, stats, fragmentation).
- `db_01_check_fragmentation`: Check which indexes need rebuilding.

### Performance Tuning
- `db_01_show_top_queries`: Identify the most expensive queries by CPU or I/O.
- `db_01_explain_query`: Paste a SQL query to see its execution plan without running it.

### Data Modeling
- `db_01_analyze_logical_data_model`: Analyze relationships and find normalization issues.
- `db_01_open_logical_model`: Generate an HTML view of your ERD.

---

## Troubleshooting

- **Connectivity**: Ensure your IP is whitelisted in SQL Server / Azure Firewall.
- **Drivers**: Ensure `ODBC Driver 17 for SQL Server` or `ODBC Driver 18 for SQL Server` is installed.
- **Permissions**: The SQL user requires `VIEW DATABASE STATE` for performance tools and standard `db_datareader` for schema tools.
