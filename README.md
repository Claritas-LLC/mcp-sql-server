# mcp-sql-server

![CI](https://github.com/harryvaldez/mcp-sql-server/actions/workflows/ci.yml/badge.svg)

MCP server for Microsoft SQL Server, built with FastMCP, with support for multi-instance configuration, operational dashboards, and containerized deployment.

## Documentation

- [User Manual](docs/users-manual.md)

## Features

- SQL Server MCP tools exposed through FastMCP
- Support for two configured database instances (`DB_01_*` and `DB_02_*`)
- Web UI routes:
  - `/data-model-analysis?id=<report_id>`
  - `/sessions-monitor?instance=1` (or `instance=2`)
- Optional runtime controls for audit logging, rate limiting, and write safety

## Prerequisites

- Python 3.12+
- ODBC Driver 17 or 18 for SQL Server
- SQL Server credentials for at least one instance
- Optional: Docker Desktop for container workflows

## Local Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Create an `.env` file and define at least one SQL instance:

```env
DB_01_SERVER=your-sql-host
DB_01_PORT=1433
DB_01_USER=your-user
DB_01_PASSWORD=your-password
DB_01_NAME=master
DB_01_DRIVER=ODBC Driver 18 for SQL Server

MCP_TRANSPORT=http
MCP_HOST=0.0.0.0
MCP_PORT=8000
```

## Run Locally

```powershell
.\.venv\Scripts\Activate.ps1
python server_startup.py
```

## Run with Docker

```powershell
docker build -t mcp-sql-server:local .
docker run -d --name mcp-sqlserver -p 8085:8000 --env MCP_TRANSPORT=http --env-file .env mcp-sql-server:local
```

## Key Environment Variables

- `DB_01_*`, `DB_02_*`: SQL Server instance settings
- `DB_01_POOL_SIZE`, `DB_02_POOL_SIZE`: connection pool sizes
- `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`: server transport and binding
- `MCP_ALLOW_WRITE`, `MCP_CONFIRM_WRITE`: write protection controls
- `MCP_MAX_ROWS`, `MCP_STATEMENT_TIMEOUT_MS`: query guardrails
- `MCP_AUDIT_LOG_QUERIES`, `MCP_AUDIT_LOG_FILE`: audit logging controls
- `MCP_LOG_LEVEL`, `MCP_LOG_FILE`, `MCP_LOG_ROTATE_*`: runtime logging controls
- `MCP_TOOL_EXECUTION_LOG_ENABLED`: tool execution event logging toggle

## Troubleshooting

- ODBC driver errors: confirm SQL Server ODBC driver is installed and matches `DB_01_DRIVER`.
- Connection failures: validate host, port, and credentials in `.env`.
- No report page output: verify `id` is provided for `/data-model-analysis`.
- Session monitor errors: verify `instance` query parameter is `1` or `2` and instance is configured.

## Security Notes

- Do not commit `.env`.
- Use least-privilege SQL accounts where possible.
- Keep `MCP_ALLOW_WRITE=false` unless write operations are explicitly required.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
