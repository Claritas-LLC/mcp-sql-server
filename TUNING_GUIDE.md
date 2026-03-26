# MCP SQL Server Tuning Guide

This guide provides best practices and recommended values for tuning your MCP SQL Server backend for production and development environments.

---

## 1. Statement Timeout
- **Variable:** `MCP_STATEMENT_TIMEOUT_MS`
- **Production:** 60000 (60s)
- **Development:** 120000 (2 min)
- **Notes:** Lower for interactive/AI workloads. Raise for heavy analytics, but avoid unbounded queries.

## 2. Max Rows
- **Variable:** `MCP_MAX_ROWS`
- **Production:** 200
- **Development:** 500
- **Notes:** Lower for chat/AI agent use. Raise for admin/reporting, but beware of memory use.

## 3. Rate Limiting & Circuit Breaker
- **Variables:**
  - `MCP_RATE_LIMIT_ENABLED` (true)
  - `MCP_RATE_LIMIT_WINDOW_SECONDS` (60)
  - `MCP_RATE_LIMIT_MAX_REQUESTS` (120 production, 240 dev)
  - `MCP_RATE_LIMIT_BREAKER_VIOLATIONS` (3)
  - `MCP_RATE_LIMIT_BREAKER_SECONDS` (60)
- **Notes:** Lower max requests for public endpoints. Raise for trusted/internal. Adjust breaker to block abusive clients quickly.

## 4. Connection Pool Size
- **Variables:** `DB_01_POOL_SIZE`, `DB_02_POOL_SIZE`
- **Production:** 10 (typical)
- **Development:** 2
- **Notes:** Match to expected concurrency and DB server capacity. Too large may exhaust DB resources; too small may cause waits.

## 5. Log Level
- **Variable:** `MCP_LOG_LEVEL`
- **Production:** INFO
- **Development:** DEBUG
- **Notes:** Use DEBUG for troubleshooting, WARNING/ERROR for production to reduce log volume.

## 6. Log Rotation
- **Variables:**
  - `MCP_LOG_ROTATE_ENABLED`, `MCP_LOG_ROTATE_MAX_BYTES`, `MCP_LOG_ROTATE_BACKUP_COUNT`
  - `MCP_AUDIT_LOG_ROTATE_ENABLED`, `MCP_AUDIT_LOG_ROTATE_MAX_BYTES`, `MCP_AUDIT_LOG_ROTATE_BACKUP_COUNT`
- **Production:** Enabled, 10MB, 5 backups
- **Development:** Optional
- **Notes:** Enable in all production environments. Set max bytes and backup count to fit your disk and retention policy.

## 7. Security
- **Write Mode:**
  - Only enable `MCP_ALLOW_WRITE=true` and `MCP_CONFIRM_WRITE=true` when absolutely necessary.
  - Always require authentication (`FASTMCP_AUTH_TYPE`) for HTTP write mode.
- **Table Scope:**
  - Use `MCP_TABLE_SCOPE_ENFORCED=true` and `MCP_ALLOWED_TABLES` to restrict access in multi-tenant or sensitive environments.

## 8. Monitoring
- **Tool:** Use the monitoring endpoint (e.g., `db_sql2019_server_metrics`) to track resource usage and pool health.
- **Notes:** Set up external monitoring/alerting for log file size, pool exhaustion, and error rates.

---

For more details, see the README.md and .env.example files.