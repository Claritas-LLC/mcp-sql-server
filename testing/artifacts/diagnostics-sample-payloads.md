# Diagnostics Sample Payloads

Date: 2026-05-09

This artifact captures sanitized sample responses for the rollout verification endpoints added during the Entra auth and SQL pooling work.

## /diagnostics/security

```json
{
  "advanced_tools": [
    "db_1_sql2019_analyze_sec_config",
    "db_1_sql2019_sessions_dashboard"
  ],
  "advanced_tools_count": 2,
  "auth": {
    "auth_mode": "azure_token_verifier",
    "azure_auth_enabled": true,
    "azure_group_authorization_enabled": true,
    "read_group_count": 2,
    "required_scopes": [
      "read",
      "write"
    ],
    "write_group_count": 1
  },
  "denied_requests": 2,
  "last_secret_refresh_utc": "2026-05-09T00:00:00Z",
  "policy_checksum_sha256": "39f795826c63723423b45c99170b033c5336a08b10c8a510928bbc01adee9f0d",
  "rate_limit_backend": "local",
  "registered_tools": [
    "db_primary_sql2019_select",
    "db_1_sql2019_analyze_sec_config",
    "db_1_sql2019_sessions_dashboard"
  ],
  "registered_tools_count": 3,
  "tool_flag_env_applied": false,
  "write_mode_default": "deny"
}
```

Verification intent:

- Confirm auth mode and toggle posture.
- Confirm required scopes are surfaced without exposing tenant or secret material.
- Confirm advanced-tool registration is visible for rollout verification.

## /diagnostics/pool

```json
{
  "instances": {
    "primary": {
      "available": 2,
      "created_total": 5,
      "discarded_total": 1,
      "enabled": true,
      "in_use": 1,
      "pool_max": 10,
      "pool_size": 3,
      "reused_total": 11
    }
  }
}
```

Verification intent:

- Confirm pooling is enabled for the instance.
- Confirm reuse is occurring (`reused_total > 0`).
- Confirm capacity and occupancy can be checked during rollout without exposing connection details.

## Notes

- Payloads were generated from the current route schema using FastAPI `TestClient` with sanitized in-memory state.
- These samples are evidence artifacts, not production captures.