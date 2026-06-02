# Production Configuration Matrix

This matrix documents critical runtime configuration used for production deployment.

| Setting | Required | Default | Source | Notes |
| --- | --- | --- | --- | --- |
| `FASTMCP_CONFIG_PATH` | Yes | `config/instances.yaml` | Container env | SQL instance definitions |
| `FASTMCP_POLICY_PATH` | Yes | `config/runtime-policy.yaml` | Container env | Runtime-enforced policy |
| `FASTMCP_RATE_LIMIT_PATH` | Yes | `config/rate-limit.yaml` | Container env | Rate/session controls |
| `FASTMCP_HOST` | Yes | `0.0.0.0` | Container env | Service bind host |
| `FASTMCP_PORT` | Yes | `8080` | Container env | Service port |
| `FASTMCP_RATE_LIMIT_BACKEND` | Yes | `local` | `.env` / env var | `local` or `redis` |
| `FASTMCP_REDIS_URL` | Conditionally | empty | `.env` / env var | Required when backend is `redis` |
| `FASTMCP_REDIS_NAMESPACE` | No | `mcp:ratelimit` | `.env` / env var | Redis key namespace |
| `FASTMCP_SQL_POOL_ENABLED` | No | instance config | `.env` / env var | Overrides per-instance pool setting |
| `FASTMCP_SQL_POOL_MAX` | No | instance config | `.env` / env var | Positive integer |
| `FASTMCP_SQL_POOL_IDLE_TIMEOUT_SEC` | No | instance config | `.env` / env var | Positive integer |
| `FASTMCP_SQL_POOL_ACQUIRE_TIMEOUT_SEC` | No | instance config | `.env` / env var | Positive integer |
| `FASTMCP_AZURE_AUTH_ENABLED` | No | policy default | `.env` / env var | Enables Entra token verification |
| `FASTMCP_AZURE_TENANT_ID` | If Entra enabled | empty | `.env` / env var | Entra tenant |
| `FASTMCP_AZURE_CLIENT_ID` | If Entra enabled | empty | `.env` / env var | App registration client id |
| `FASTMCP_AZURE_CLIENT_SECRET_REF` | If Entra enabled | empty | `.env` / env var | Secret reference key |
| `FASTMCP_AZURE_REQUIRED_SCOPES` | If Entra enabled | policy default | `.env` / env var | CSV parsed to list |
| `FASTMCP_AZURE_GROUP_AUTHORIZATION_ENABLED` | No | policy default | `.env` / env var | Enables group privilege mapping |
| `FASTMCP_TOOL_ENABLE_FLAGS_JSON` | No | empty | `.env` / env var | Global tool toggles |
| `FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON` | No | empty | `.env` / env var | Per-instance tool toggles |

## Secret-Mapped Credentials

`auth_secret_ref` in `config/instances.yaml` maps to env vars in this pattern:

- `<SECRET_REF>_USERNAME`
- `<SECRET_REF>_PASSWORD`

Example:

- `auth_secret_ref: secret/sql/primary`
- Required env vars:
  - `SECRET_SQL_PRIMARY_USERNAME`
  - `SECRET_SQL_PRIMARY_PASSWORD`
