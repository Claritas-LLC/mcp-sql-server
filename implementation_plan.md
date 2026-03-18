# Implementation Plan: Connect to Two SQL Server Instances

## Goal Description
The server needs to be modified to connect to two SQL Server instances simultaneously. We need to retain all tools prefixed with [db_01_sql2019_](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#1120-1137) to connect to the first SQL Server instance, and duplicate them as `db_02_sql2019_` tools to connect to the second SQL Server instance. The environment variables also need to be updated to support two database configurations.

## User Review Required
> [!IMPORTANT]
> - Do you want both databases to share the same rate limits and audit file settings, or should those also be duplicated per instance? The plan below assumes rate limits and global settings apply to *the whole MCP server*, but the database credentials are split.
> - The new connection variables will use prefixes `DB_01_*` and `DB_02_*` instead of just `DB_*`. For backwards compatibility, if only `DB_*` is provided, we can map it to `DB_01_*`.

## Proposed Changes

### Configuration Layer (server.py + .env)
- Update [Settings](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#78-119) class in [server.py](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py) to include credentials for two databases:
  - `db_01_server`, `db_01_port`, `db_01_user`, `db_01_password`, `db_01_name`, `db_01_driver`
  - `db_02_server`, `db_02_port`, `db_02_user`, `db_02_password`, `db_02_name`, `db_02_driver`
- Update [_load_settings()](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#156-205) to read `DB_01_*` and `DB_02_*` from the `.env` file.
- Update `.env.example` to show `DB_01_*` and `DB_02_*` usage.

### Connection Layer (server.py)
- Modify [_connection_string()](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#534-545) and [get_connection()](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#547-558) to accept a target instance parameter (e.g. `instance=1` and `instance=2`) so they connect to the appropriate server.

### Tool Registration (server.py)
- All existing `db_01_sql2019_*` functions will explicitly pass `instance=1` to [get_connection(...)](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#547-558) and other internal helpers.
- Use a Python AST script or text replacement script to duplicate all `db_01_sql2019_*` functions, renaming them to `db_02_sql2019_*`, and make them pass `instance=2` inside the tools.

### Testing and Documentation
- Update [README.md](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/README.md) to document the new `DB_01_*` and `DB_02_*` environment variables and the availability of the `db_02_sql2019_*` tools.
- Update automated tests locally if necessary.

## Verification Plan
1. Restart the server and ensure it starts up without errors.
2. Check that both [db_01_sql2019_ping](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#1120-1137) and `db_02_sql2019_ping` are returned by the FastMCP server when queried.
