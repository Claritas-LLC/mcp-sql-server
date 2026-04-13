# MCP SQL Server

SQL Server Model Context Protocol (MCP) server for AI integration.

## Quick Start

> **Security Warning**: Never pass sensitive credentials (like `DB_PASSWORD`) directly via command-line flags (`-e`), as they can appear in process listings and shell history. Use `--env-file` or Docker Secrets instead.

```bash
# Option 1: Using .env file (Recommended)
# Create a .env file with your variables
docker run -d \
  --name mcp-sqlserver \
  -p 8085:8000 \
  --env-file .env \
  harryvaldez/mcp_sqlserver:latest

# Option 2: Docker Secrets (Swarm/Compose)
# Pass the password via Docker secrets (e.g., /run/secrets/DB_PASSWORD)
```

## Environment Variables

- `SQL_SERVER`: SQL Server hostname (also `DB_SERVER`)
- `SQL_DATABASE`: Database name (also `DB_DATABASE` or `DB_NAME`)
- `SQL_USER`: Database user (also `DB_USER`)
- `SQL_PASSWORD`: Database password (also `DB_PASSWORD`)
- `SQL_DRIVER`: ODBC driver (default: `ODBC Driver 18 for SQL Server`) (also `DB_DRIVER`)
- `SQL_PORT`: SQL Server port (default: 1433) (also `DB_PORT`)

## Security Note

**⚠️ Critical Security Warning**: `SQL_PASSWORD` is a highly sensitive credential that should **never** be passed directly via command-line `-e` flags, as it can be exposed in:
- Process listings (`ps aux`)
- Shell history
- Docker logs
- Container inspection

### Secure Configuration Methods (in order of preference):

1. **Docker Secrets** (Swarm/Compose): Use Docker's built-in secrets management
   ```yaml
   secrets:
     db_password:
       external: true
   ```

2. **Environment Files** with restricted permissions:
   ```bash
   # Create .env file with chmod 600
   echo "DB_PASSWORD=your_secure_password" > .env
   chmod 600 .env
   docker run --env-file .env ...
   ```

3. **External Secret Managers**: Integrate with HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, or similar services

### See Also:
- [Quick Start section](#quick-start) for secure configuration examples
- [Environment Variables section](#environment-variables) for complete variable reference
- Docker documentation on [Managing Secrets](https://docs.docker.com/engine/swarm/secrets/)

## Usage

The server exposes MCP tools for SQL Server management:
- Database schema analysis
- Query execution
- Performance monitoring
- User management
- Index optimization

See [README.md](README.md) for detailed API documentation.