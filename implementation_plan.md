# Implementation Plan: Connect to Two SQL Server Instances

## Goal Description
The server needs to be modified to connect to two SQL Server instances simultaneously. We need to retain all tools prefixed with [db_01_sql2019_](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#1120-1137) to connect to the first SQL Server instance, and duplicate them as `db_02_sql2019_` tools to connect to the second SQL Server instance. The environment variables also need to be updated to support two database configurations.

## User Review Required
> [!IMPORTANT]
> - Do you want both databases to share the same rate limits and audit file settings, or should those also be duplicated per instance? The plan below assumes rate limits and global settings apply to *the whole MCP server*, but the database credentials are split. - Answer is Yes
> - The new connection variables will use prefixes `DB_01_*` and `DB_02_*` instead of just `DB_*`. For backwards compatibility, if only `DB_*` is provided, we can map it to `DB_01_*`. Answer is yes

## Decisions

- **Rate Limits & Audit/Global Settings Scope:**
  - Rate limits and audit/global settings (such as logging, audit file, and global rate limiting) are **shared across the entire MCP server**. They are not duplicated per database instance. This ensures consistent enforcement and centralized auditing regardless of which SQL Server instance (db_01 or db_02) is being accessed.

- **Environment Variable Mapping & Backward Compatibility:**
  - The new environment variable prefixes are `DB_01_*` and `DB_02_*`, supporting configuration for two separate SQL Server instances.
  - For backward compatibility, if only the legacy `DB_*` variables are provided, the MCP server will map them to `DB_01_*` automatically. This allows existing deployments to continue functioning without changes, while new deployments should use the explicit `DB_01_*` and `DB_02_*` prefixes.
  - All references to `DB_01_*`, `DB_02_*`, and `DB_*` in configuration and documentation should make this mapping and intent clear.

These decisions clarify the architecture intent for rate limiting, audit/global settings, and environment variable naming before implementation.

## Operational and Architectural Considerations


### Error Handling
1. On server startup, the system attempts to initialize each instance via `get_connection(instance=1|2)` and `_connection_string`. Only instances that successfully initialize will have their tools registered. Any failing instances are recorded in a startup-warnings log.
2. Any runtime call into functions that use `get_connection` or `_connection_string` must propagate a clear, instance-tagged error (including the instance id and underlying error) so failures always carry context.
3. The system must provide a non-blocking health-surface (e.g., a health endpoint and startup warnings list) that reports unavailable instances and supports automatic recovery without requiring a server restart (by retrying initialization or re-checking connections periodically or on settings change).


### Connection Pooling
- Each database instance must have its own connection pool.
- Pool sizes are configurable per instance via Settings and `_load_settings`.
- The `_load_settings` function must parse all environment variables matching `DB_<IDENTIFIER>_POOL_SIZE`, where `<IDENTIFIER>` can be a numeric suffix (e.g., `01`, `2`) or a string alias (e.g., `ANALYTICS`).
  - Numeric suffixes like `01` or `1` are converted to integer instance keys (e.g., `DB_01_POOL_SIZE` → instance 1, `DB_2_POOL_SIZE` → instance 2).
  - For non-numeric identifiers, a registry (mapping) is supported, allowing aliases like `DB_ANALYTICS_POOL_SIZE` to be mapped to a numeric instance id or named key. This registry can be provided to `_load_settings` or `Settings` for future extensibility.
  - If a pool size value is invalid or missing, default to 10.
- The `Settings` class includes a `db_pool_sizes: dict[int, int]` field mapping instance numbers to pool sizes.
- Example: set `DB_01_POOL_SIZE=15` and `DB_02_POOL_SIZE=20` in the environment to control pool sizes for each instance. For a named instance, provide a registry mapping (e.g., `{"ANALYTICS": 3}`) so `DB_ANALYTICS_POOL_SIZE` → instance 3.
- Sizing guidance: default pool size 10-20 per instance for typical workloads; allow tuning for high concurrency or resource-constrained environments.
- Document this mapping and registry behavior so future DB_ANALYTICS_POOL_SIZE can be resolved consistently.

### Transaction Handling
- Cross-instance transactions are **not supported**. Each tool (e.g., `db_01_sql2019_*` vs `db_02_sql2019_*`) must enforce that all operations within a transaction are scoped to a single instance.
- **Enforcement by design:** All connection objects (e.g., Connection or DbClient) must be explicitly scoped to an instance (carry an `instanceId` or `instance_name`).
- **Runtime safeguard:** The transaction orchestration code (e.g., `TransactionManager.beginTransaction` or `executeTransaction`) must validate that all operations/connections in a transaction share the same `instanceId`. If a mismatch is detected, raise a clear error indicating that cross-instance transactions are not allowed.
- If cross-instance transactions are ever required, a distributed transaction coordinator or explicit two-phase commit strategy would be needed (not planned for initial implementation).

### Monitoring/Observability
- Add instance-specific health checks and metrics to surface per-instance connectivity and query errors.
- Expose health endpoints and metrics that distinguish between DB_01 and DB_02 status, query error rates, and connection pool usage.

### Security
- Credentials for `db_01_user` and `db_02_user` should follow least privilege principles and be rotated regularly.
- Store credentials in `.env` or a secrets manager; never hardcode in source.
- Update `README.md` to document these operational requirements and best practices for secure credential management, monitoring, and error handling.

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

- Refactor all `db_01_sql2019_*` functions to accept an `instance` parameter and wire them to `get_connection(instance=...)` and all internal helpers.
- Create a registrar (e.g., `register_tool(name, func)` and a dict of tools) and register partialized functions using `functools.partial`:
    - Register `functools.partial(db_01_sql2019_x, instance=1)` as "db_01_sql2019_x"
    - Register `functools.partial(db_01_sql2019_x, instance=2)` as "db_02_sql2019_x"
- This ensures there is only one implementation per tool and explicit mapping for each instance/tool name.
- Only use a decorator if you must infer instance solely from the function name; otherwise, prefer the explicit factory/registrar for clearer tests, easier debugging, and simpler registration logic.

### Testing and Documentation
- Update [README.md](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/README.md) to document the new `DB_01_*` and `DB_02_*` environment variables and the availability of the `db_02_sql2019_*` tools.
- Update automated tests locally if necessary.

## Verification Plan
1. Restart the server and ensure it starts up without errors.
2. Check that both [db_01_sql2019_ping](file:///c:/Users/HarryValdez/OneDrive/Documents/trae/mcp-sql-server/server.py#1120-1137) and `db_02_sql2019_ping` are returned by the FastMCP server when queried.
