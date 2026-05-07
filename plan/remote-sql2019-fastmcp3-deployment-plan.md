---
goal: Secure Dual-Instance Remote SQL Server 2019 MCP Deployment with FastMCP 3.0 and Docker
version: 1.1
date_created: 2026-05-05
last_updated: 2026-05-05
owner: Cloud Solutions Architecture
status: Planned
tags: [feature, architecture, security, docker, sqlserver, mcp, fastmcp]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This implementation plan defines a deterministic, security-first deployment for a FastMCP 3.0 server that connects to two independently configured remote SQL Server 2019 instances. The design uses Docker for portability, enforces runtime safety controls, and integrates evidence collection, diagnostics, and operational workflows compatible with existing DBA practices.

## 1. Requirements & Constraints

- **REQ-001**: Deploy one FastMCP 3.0 service as a Docker container with support for two SQL Server 2019 instance connections.
- **REQ-002**: Support independently configured SQL endpoints (host, port, database, credentials, TLS mode, timeout, pool settings) for `primary` and `secondary` instances.
- **REQ-003**: Enforce tool naming convention `db_<instance>_sql2019_<toolname>` for all exposed MCP tools.
- **REQ-004**: Expose diagnostic endpoints for health, readiness, liveness, metrics, and security posture summary.
- **REQ-005**: Include report utilities for query latency, connection utilization, blocked sessions, failed auth attempts, and audit summary.
- **REQ-006**: Include sample scripts/commands for automated evidence collection and routine compliance reports.
- **REQ-007**: Include step-by-step deployment scripts for local build, secure runtime configuration, and production rollout.
- **REQ-008**: Support dual-instance operation where each instance can be independently enabled/disabled at runtime.
- **SEC-001**: Enforce least privilege by using SQL logins with role-scoped access and separate read-only/write-allowed identities per instance.
- **SEC-002**: Enforce runtime write restriction policy with default `deny` and explicit allowlist per tool.
- **SEC-003**: Enforce request rate limiting by caller identity and global quotas with burst control.
- **SEC-004**: Implement immutable audit logging for tool invocation, SQL text hash, instance target, actor identity, and decision outcome.
- **SEC-005**: Use encrypted SQL transport with certificate validation (`Encrypt=True;TrustServerCertificate=False`) unless explicit exception is documented.
- **SEC-006**: Store secrets outside image layers using environment variables, Docker secrets, or external secret manager.
- **SEC-007**: Run container as non-root, with read-only filesystem, dropped Linux capabilities, and explicit writable volume allowlist.
- **OPS-001**: Integrate with existing DBA workflows through scriptable CLI tasks and scheduled report generation.
- **OPS-002**: Enable automated rotation of logs and auditable archival retention.
- **OPS-003**: Provide rollback and emergency safe mode (`read_only_all=true`) without image rebuild.
- **CON-001**: Do not embed production credentials in source code, Dockerfile, or committed configuration files.
- **CON-002**: Do not allow unrestricted ad-hoc DDL execution through MCP tools.
- **CON-003**: Plan must remain executable for Windows-hosted operations with Docker Desktop or Linux Docker host.
- **GUD-001**: Keep configuration declarative (YAML/ENV) and avoid hardcoded instance-specific logic.
- **GUD-002**: Prefer standardized observability formats (JSON logs, Prometheus metrics, UTC timestamps).
- **PAT-001**: Use sidecar-style evidence collector scripts for repeatable compliance outputs.
- **PAT-002**: Use policy-as-configuration for tool allowlists and SQL safety guards.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Establish secure project structure, naming standards, and deterministic configuration model for dual SQL instance operation.
- EXIT-001: All required configuration files exist with schema-validated fields; tool names generated for both instances follow required naming convention.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Create folder structure: `docker/`, `config/`, `scripts/`, `reports/`, `evidence/`, `policy/`, `docs/runbooks/`, `src/tools/`, `src/middleware/`, `src/diagnostics/`. |  |  |
| TASK-002 | Define `config/instances.yaml` with two entries: `primary` and `secondary`; include keys `host`, `port`, `database`, `auth_secret_ref`, `encrypt`, `trust_server_certificate`, `connect_timeout_sec`, `command_timeout_sec`, `pool_min`, `pool_max`, `enabled`. |  |  |
| TASK-003 | Define `config/runtime-policy.yaml` including `write_mode_default=deny`, `allowed_write_tools`, `blocked_sql_patterns`, `max_result_rows`, `max_query_duration_ms`, `instance_enable_flags`. |  |  |
| TASK-004 | Define naming map generator logic in `src/tools/tool_registry.py` to emit exact tool names: `db_primary_sql2019_select`, `db_primary_sql2019_exec_proc`, `db_secondary_sql2019_select`, `db_secondary_sql2019_exec_proc`, etc. |  |  |
| TASK-005 | Define `config/rate-limit.yaml` with per-actor and global quotas (`requests_per_minute`, `burst`, `concurrent_sessions_limit`). |  |  |
| TASK-006 | Define `policy/sql-allowlist.yaml` and `policy/sql-denylist.yaml` for command class enforcement (SELECT allowed default, UPDATE/INSERT/DELETE/DDL blocked unless allowlisted tool). |  |  |

### Implementation Phase 2

- GOAL-002: Implement FastMCP 3.0 server core with dual-instance connection management, safe query execution, and middleware controls.
- EXIT-002: MCP server starts, registers tools for both instances, enforces read/write policy and rate limiting, and records audit events for every invocation.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-007 | Implement `src/server.py` to bootstrap FastMCP 3.0 app, load YAML config, and initialize both SQL pools independently. |  |  |
| TASK-008 | Implement `src/db/connection_manager.py` with separate connection pools keyed by instance id; include fail-fast health test per pool during startup. |  |  |
| TASK-009 | Implement `src/middleware/rate_limiter.py` with token-bucket policy using actor id from MCP context; reject with deterministic error code `RATE_LIMIT_EXCEEDED`. |  |  |
| TASK-010 | Implement `src/middleware/write_guard.py` to parse normalized SQL verb and enforce runtime write restrictions from `runtime-policy.yaml`. |  |  |
| TASK-011 | Implement `src/middleware/audit_logger.py` writing structured JSON lines to `/var/log/mcp/audit.log` fields: `ts_utc`, `request_id`, `actor`, `tool`, `instance`, `sql_hash`, `decision`, `latency_ms`, `rows`, `error_code`. |  |  |
| TASK-012 | Implement tool handlers in `src/tools/sql_tools.py` with strict instance routing: each tool hard-binds to one instance and one command class. |  |  |
| TASK-013 | Implement `src/security/session_manager.py` with `session_ttl_minutes`, inactivity timeout, and per-actor concurrent session cap. |  |  |

### Implementation Phase 3

- GOAL-003: Containerize and harden deployment using Docker with secure defaults and portable runtime assets.
- EXIT-003: Image passes container security baseline checks and runs with non-root, read-only root filesystem, secrets mounted externally, and healthchecks enabled.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-014 | Create `docker/Dockerfile` multi-stage build: builder stage installs dependencies; runtime stage copies app only, sets non-root user `mcpuser`, disables shell history, and sets immutable app directory. |  |  |
| TASK-015 | Create `docker/docker-compose.yml` with service `fastmcp-sql2019`, mounted configs (`/app/config`, `/app/policy`), logs volume, and secret references. |  |  |
| TASK-016 | Add container hardening flags in compose: `read_only: true`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, tmpfs for `/tmp`, explicit writable mount `/var/log/mcp`. |  |  |
| TASK-017 | Add healthcheck command calling `/diagnostics/health`; readiness depends on both instance pool checks unless disabled by policy flags. |  |  |
| TASK-018 | Add startup script `scripts/start-fastmcp.ps1` and `scripts/start-fastmcp.sh` to validate config schema then start container. |  |  |
| TASK-019 | Add deployment script `scripts/deploy-prod.ps1` to pull signed image digest, inject secrets, run compose up, and persist evidence artifact manifest. |  |  |

### Implementation Phase 4

- GOAL-004: Implement diagnostics endpoints, reporting utilities, and automated evidence collection for compliance and operational support.
- EXIT-004: All diagnostics endpoints return deterministic payloads; scheduled reports and evidence bundles generate successfully.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-020 | Implement endpoint `GET /diagnostics/health` in `src/diagnostics/routes.py` returning app version, uptime, and per-instance connectivity state. |  |  |
| TASK-021 | Implement endpoint `GET /diagnostics/readiness` verifying config loaded, policy active, rate limiter active, and required instance pools healthy. |  |  |
| TASK-022 | Implement endpoint `GET /diagnostics/metrics` with Prometheus output for request count, latency histogram, rejection counters, and per-instance query timings. |  |  |
| TASK-023 | Implement endpoint `GET /diagnostics/security` returning policy checksum, last secret rotation timestamp, and write restriction mode status. |  |  |
| TASK-024 | Create report utility `scripts/report-latency.ps1` and `scripts/report-latency.sh` producing daily CSV under `reports/latency/`. |  |  |
| TASK-025 | Create report utility `scripts/report-blocking-sessions.ps1` and `.sh` using read-only diagnostic queries per instance; output JSON under `reports/blocking/`. |  |  |
| TASK-026 | Create evidence utility `scripts/collect-evidence.ps1` and `.sh` to package config checksums, container inspect output, audit log digest, and endpoint snapshots into timestamped archive in `evidence/`. |  |  |

### Implementation Phase 5

- GOAL-005: Validate security, performance, and dual-instance behavior; operationalize maintenance and scaling guidance.
- EXIT-005: Test suite passes, performance baseline documented, maintenance runbook approved, and scale-out decision thresholds defined.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-027 | Implement tests in `tests/test_tool_naming.py` to assert all tool names follow `db_<instance>_sql2019_<toolname>` and include only enabled instances. |  |  |
| TASK-028 | Implement tests in `tests/test_write_restrictions.py` for default deny write mode, allowlisted write tool behavior, and blocked DDL patterns. |  |  |
| TASK-029 | Implement tests in `tests/test_rate_limiting.py` for actor quota, burst, and global ceiling rejection behavior. |  |  |
| TASK-030 | Implement load script `scripts/perf-smoke.ps1` and `.sh` to run deterministic query mix against both instances and record P50/P95/P99 latencies. |  |  |
| TASK-031 | Create `docs/runbooks/security-maintenance.md` defining weekly secret rotation check, monthly policy review, quarterly access recertification, and annual disaster recovery exercise. |  |  |
| TASK-032 | Create `docs/runbooks/scaling-strategy.md` with vertical scale thresholds (CPU, memory, pool saturation) and horizontal scale pattern with sticky actor routing and shared rate-limit backend. |  |  |

## 3. Alternatives

- **ALT-001**: Deploy two separate MCP containers (one per SQL instance). Not selected because unified service with strict per-instance tool routing provides easier DBA integration and lower operational overhead while preserving logical separation.
- **ALT-002**: Use host-installed service without Docker. Not selected because portability, immutable runtime, and security hardening controls are weaker and less repeatable.
- **ALT-003**: Allow generic SQL execution tool with runtime regex filtering only. Not selected because command-class-specific tools plus explicit policy files provide stronger deterministic control.
- **ALT-004**: Trust SQL server certificate in all environments. Not selected due to compliance requirements; only exception-based override is permitted with documented risk acceptance.

## 4. Dependencies

- **DEP-001**: FastMCP 3.0 runtime and compatible Python runtime.
- **DEP-002**: SQL Server 2019 network reachability for two independently administered instances.
- **DEP-003**: ODBC Driver 18 for SQL Server and Python SQL client library (pyodbc or equivalent).
- **DEP-004**: Docker Engine / Docker Desktop and Docker Compose plugin.
- **DEP-005**: Prometheus-compatible scraper (or equivalent) for metrics endpoint ingestion.
- **DEP-006**: Centralized log sink (SIEM or log platform) for audit log forwarding.
- **DEP-007**: Secret store integration (Docker secrets, Vault, Azure Key Vault, or equivalent).

## 5. Files

- **FILE-001**: `plan/remote-sql2019-fastmcp3-deployment-plan.md` - Master implementation plan.
- **FILE-002**: `docker/Dockerfile` - Secure multi-stage container build.
- **FILE-003**: `docker/docker-compose.yml` - Runtime service definition and hardening controls.
- **FILE-004**: `config/instances.yaml` - Dual SQL instance connection configuration.
- **FILE-005**: `config/runtime-policy.yaml` - Write restrictions, limits, and safety policy.
- **FILE-006**: `config/rate-limit.yaml` - Actor/global quotas and burst settings.
- **FILE-007**: `policy/sql-allowlist.yaml` - Explicitly approved write operations/tools.
- **FILE-008**: `policy/sql-denylist.yaml` - Blocked patterns and unsafe operations.
- **FILE-009**: `src/server.py` - FastMCP app bootstrap and registration.
- **FILE-010**: `src/db/connection_manager.py` - Dual-instance pooled SQL connectivity.
- **FILE-011**: `src/tools/sql_tools.py` - Instance-bound MCP tool handlers.
- **FILE-012**: `src/tools/tool_registry.py` - Naming and registration rules.
- **FILE-013**: `src/middleware/write_guard.py` - Runtime write safety controls.
- **FILE-014**: `src/middleware/rate_limiter.py` - Throughput control enforcement.
- **FILE-015**: `src/middleware/audit_logger.py` - Immutable security event logging.
- **FILE-016**: `src/security/session_manager.py` - Session lifecycle controls.
- **FILE-017**: `src/diagnostics/routes.py` - Health, readiness, metrics, and security endpoints.
- **FILE-018**: `scripts/deploy-prod.ps1` - Production deployment automation.
- **FILE-019**: `scripts/collect-evidence.ps1` and `scripts/collect-evidence.sh` - Evidence bundle automation.
- **FILE-020**: `scripts/report-latency.ps1` and `scripts/report-latency.sh` - Performance report generation.
- **FILE-021**: `scripts/report-blocking-sessions.ps1` and `scripts/report-blocking-sessions.sh` - Operational blocking diagnostics.
- **FILE-022**: `tests/test_tool_naming.py` - Naming convention validation.
- **FILE-023**: `tests/test_write_restrictions.py` - Write guard test coverage.
- **FILE-024**: `tests/test_rate_limiting.py` - Rate limiting test coverage.
- **FILE-025**: `docs/runbooks/security-maintenance.md` - Security operations runbook.
- **FILE-026**: `docs/runbooks/scaling-strategy.md` - Growth and reliability playbook.

## 6. Testing

- **TEST-001**: Unit test configuration parser rejects missing instance fields and invalid TLS settings.
- **TEST-002**: Unit test tool naming format for all generated tools and disabled-instance behavior.
- **TEST-003**: Unit test write guard blocks non-allowlisted `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, `DROP` statements.
- **TEST-004**: Unit test rate limiter actor and global thresholds with deterministic rejection code.
- **TEST-005**: Integration test container startup with both instances enabled and one disabled scenario.
- **TEST-006**: Integration test diagnostics endpoints return HTTP 200 and required schema fields.
- **TEST-007**: Integration test audit logger output completeness and hash consistency.
- **TEST-008**: Performance smoke test verifies P95 latency target for read queries under defined load profile.
- **TEST-009**: Security test validates container runtime hardening flags are active (`read_only`, `cap_drop`, `no-new-privileges`).
- **TEST-010**: Compliance test verifies evidence archive contains signed checksum manifest and daily snapshots.

## 7. Risks & Assumptions

- **RISK-001**: Network latency variance between MCP container host and remote SQL instances may increase P95/P99 latency.
- **RISK-002**: Certificate chain issues may block secure SQL connectivity when `TrustServerCertificate=False` is enforced.
- **RISK-003**: Excessive audit logging volume may increase storage cost without retention policy tuning.
- **RISK-004**: Misconfigured allowlist can unintentionally block legitimate DBA operations during incident response.
- **RISK-005**: Shared deployment for both instances increases blast radius if server process fails.
- **ASSUMPTION-001**: Both SQL Server 2019 instances support encrypted connections and required login privileges.
- **ASSUMPTION-002**: Operations team has Docker deployment rights and access to secret injection mechanism.
- **ASSUMPTION-003**: Existing DBA workflows can consume generated CSV/JSON reports and scheduled evidence archives.
- **ASSUMPTION-004**: FastMCP 3.0 version selected supports middleware interception hooks used for safety controls.

## 8. Related Specifications / Further Reading

- FastMCP 3.0 runtime documentation and tool registration guide.
- Microsoft SQL Server 2019 security best practices and TLS encryption guidance.
- Docker security hardening benchmark (CIS Docker Benchmark).
- OWASP logging and monitoring recommendations.
- Prometheus exposition format reference for service metrics.

## Configuration Snippets

### Dual-instance configuration (`config/instances.yaml`)

```yaml
instances:
	- id: primary
		host: sql2019-primary.company.internal
		port: 1433
		database: AppDb
		auth_secret_ref: secret/sql/primary
		encrypt: true
		trust_server_certificate: false
		connect_timeout_sec: 5
		command_timeout_sec: 30
		pool_min: 2
		pool_max: 20
		enabled: true

	- id: secondary
		host: sql2019-secondary.company.internal
		port: 1433
		database: ReportingDb
		auth_secret_ref: secret/sql/secondary
		encrypt: true
		trust_server_certificate: false
		connect_timeout_sec: 5
		command_timeout_sec: 45
		pool_min: 2
		pool_max: 20
		enabled: true
```

### Runtime safety policy (`config/runtime-policy.yaml`)

```yaml
write_mode_default: deny
allowed_write_tools:
	- db_primary_sql2019_exec_proc
blocked_sql_patterns:
	- "(?i)\\b(drop|alter|truncate|create)\\b"
	- "(?i)\\bxp_cmdshell\\b"
max_result_rows: 5000
max_query_duration_ms: 15000
instance_enable_flags:
	primary: true
	secondary: true
```

### Rate limiting (`config/rate-limit.yaml`)

```yaml
global:
	requests_per_minute: 1200
	burst: 200
actor:
	requests_per_minute: 180
	burst: 30
session:
	concurrent_sessions_limit: 10
	session_ttl_minutes: 60
	inactivity_timeout_minutes: 15
```

### Docker Compose hardening (`docker/docker-compose.yml`)

```yaml
services:
	fastmcp-sql2019:
		image: ghcr.io/company/fastmcp-sql2019:1.0.0
		restart: always
		ports:
			- "8080:8080"
		read_only: true
		cap_drop:
			- ALL
		security_opt:
			- no-new-privileges:true
		tmpfs:
			- /tmp:size=64m
		volumes:
			- ./config:/app/config:ro
			- ./policy:/app/policy:ro
			- mcp-audit-log:/var/log/mcp
		environment:
			FASTMCP_CONFIG_PATH: /app/config/instances.yaml
			FASTMCP_POLICY_PATH: /app/config/runtime-policy.yaml
			FASTMCP_RATE_LIMIT_PATH: /app/config/rate-limit.yaml
			FASTMCP_LOG_LEVEL: INFO
		healthcheck:
			test: ["CMD", "curl", "-fsS", "http://localhost:8080/diagnostics/health"]
			interval: 30s
			timeout: 5s
			retries: 3
			start_period: 20s
volumes:
	mcp-audit-log:
```

## Deployment Scripts

### Build and run (PowerShell)

```powershell
docker build -f docker/Dockerfile -t ghcr.io/company/fastmcp-sql2019:1.0.0 .
docker compose -f docker/docker-compose.yml up -d
```

### Evidence collection (PowerShell)

```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$out = "evidence/evidence-$ts"
New-Item -ItemType Directory -Force -Path $out | Out-Null

docker inspect fastmcp-sql2019 | Out-File "$out/container-inspect.json" -Encoding utf8
Invoke-RestMethod http://localhost:8080/diagnostics/health | ConvertTo-Json -Depth 8 | Out-File "$out/health.json"
Invoke-RestMethod http://localhost:8080/diagnostics/security | ConvertTo-Json -Depth 8 | Out-File "$out/security.json"
Get-FileHash config/instances.yaml, config/runtime-policy.yaml, config/rate-limit.yaml -Algorithm SHA256 |
	Format-Table -AutoSize | Out-String | Out-File "$out/config-hashes.txt"

Compress-Archive -Path "$out/*" -DestinationPath "evidence/evidence-$ts.zip" -Force
```

### Performance tuning check (Bash)

```bash
curl -s http://localhost:8080/diagnostics/metrics > reports/latency/metrics-$(date -u +%Y%m%dT%H%M%SZ).prom
grep "mcp_query_latency_ms_bucket" reports/latency/*.prom | tail -n 20
```

## Diagnostic Endpoints and Report Utilities

- Endpoint: `GET /diagnostics/health` returns `status`, `version`, `uptime_seconds`, `instances.primary.state`, `instances.secondary.state`.
- Endpoint: `GET /diagnostics/readiness` returns policy/rate-limit/session-manager activation and per-instance pool readiness.
- Endpoint: `GET /diagnostics/metrics` exposes Prometheus counters and latency histograms per tool and instance.
- Endpoint: `GET /diagnostics/security` exposes policy checksum, current write mode, denied request counters, and last secret refresh timestamp.
- Utility: `db_primary_sql2019_latency_report` generates rolling 24h query latency summary for primary.
- Utility: `db_secondary_sql2019_block_report` enumerates blocking chains and lock wait durations.
- Utility: `db_primary_sql2019_audit_digest` generates signed digest from audit stream for compliance evidence.

## Ongoing Maintenance and Scalability Recommendations

- Weekly: verify secret freshness, failed-auth trend, and denied-write trend from audit logs.
- Monthly: review allowlist/denylist policy and retire unused privileged tools.
- Quarterly: run failover simulation where one instance is disabled and verify continued service for the other.
- Baseline scale trigger: add CPU/memory to container host when sustained CPU > 70% for 15 minutes or pool saturation > 80%.
- Horizontal scale trigger: move to multi-replica MCP service when sustained requests exceed 900 rpm and single-instance P95 latency exceeds target.
- Compliance retention: keep signed evidence bundles for minimum 365 days and audit logs per policy/legal requirement.

## Step-by-Step Execution Workflow

### Stage 0: Preflight and Access Validation

1. Confirm Docker runtime and compose plugin availability.
2. Confirm network reachability from deployment host to both SQL Server 2019 endpoints on TCP 1433.
3. Confirm SQL credentials exist in secret store and are mapped to `secret/sql/primary` and `secret/sql/secondary`.
4. Confirm certificates for SQL TLS validation are trusted on the container host.

```powershell
docker version
docker compose version
Test-NetConnection sql2019-primary.company.internal -Port 1433
Test-NetConnection sql2019-secondary.company.internal -Port 1433
```

Acceptance criteria:
- Both connectivity tests return `TcpTestSucceeded=True`.
- Docker commands return successful version output.

### Stage 1: Bootstrap Repository Layout

1. Create deterministic project folders required by Phase 1 tasks.
2. Add baseline config and policy files with environment-agnostic defaults.

```powershell
New-Item -ItemType Directory -Force -Path docker,config,scripts,reports,evidence,policy,docs/runbooks,src/tools,src/middleware,src/diagnostics,src/db,src/security,tests | Out-Null
```

Acceptance criteria:
- All required directories exist.
- `config/instances.yaml`, `config/runtime-policy.yaml`, `config/rate-limit.yaml`, `policy/sql-allowlist.yaml`, and `policy/sql-denylist.yaml` are present.

### Stage 2: Secure Build and Local Start

1. Build container image from hardened Dockerfile.
2. Start service using compose with mounted configs and policies.
3. Validate service health and readiness endpoints.

```powershell
docker build -f docker/Dockerfile -t ghcr.io/company/fastmcp-sql2019:1.0.0 .
docker compose -f docker/docker-compose.yml up -d
Invoke-RestMethod http://localhost:8080/diagnostics/health | ConvertTo-Json -Depth 8
Invoke-RestMethod http://localhost:8080/diagnostics/readiness | ConvertTo-Json -Depth 8
```

Acceptance criteria:
- Container is `Up` and healthy.
- Health/readiness endpoints return instance-level status for both `primary` and `secondary`.

### Stage 3: Safety Controls Verification

1. Execute read tool call against both instances.
2. Execute blocked write and blocked DDL test calls.
3. Confirm deterministic denials and audit entries.

```powershell
# Expected allow
Invoke-RestMethod -Method Post http://localhost:8080/mcp/tools/db_primary_sql2019_select -Body '{"sql":"SELECT TOP 1 1 AS ok"}' -ContentType 'application/json'

# Expected deny by write guard
Invoke-RestMethod -Method Post http://localhost:8080/mcp/tools/db_primary_sql2019_select -Body '{"sql":"UPDATE dbo.Users SET IsActive=0 WHERE 1=0"}' -ContentType 'application/json'

# Expected deny by SQL denylist
Invoke-RestMethod -Method Post http://localhost:8080/mcp/tools/db_primary_sql2019_select -Body '{"sql":"DROP TABLE dbo.TempTest"}' -ContentType 'application/json'
```

Acceptance criteria:
- Read operation succeeds.
- Write and DDL operations are denied with policy-aligned error payload.
- `/var/log/mcp/audit.log` contains three corresponding entries with decision values.

### Stage 4: Evidence Collection and Report Baseline

1. Run evidence bundle script.
2. Run latency and blocking report scripts.
3. Archive outputs and publish to compliance storage.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/collect-evidence.ps1
powershell -ExecutionPolicy Bypass -File scripts/report-latency.ps1
powershell -ExecutionPolicy Bypass -File scripts/report-blocking-sessions.ps1
```

Acceptance criteria:
- New archive exists under `evidence/` with timestamp suffix.
- New report files exist under `reports/latency/` and `reports/blocking/`.

### Stage 5: Production Rollout and Post-Deploy Validation

1. Pull pinned image digest and deploy using production compose profile.
2. Execute health, readiness, and security diagnostics checks.
3. Run short load smoke and verify latency thresholds.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/deploy-prod.ps1
Invoke-RestMethod http://localhost:8080/diagnostics/security | ConvertTo-Json -Depth 8
powershell -ExecutionPolicy Bypass -File scripts/perf-smoke.ps1
```

Acceptance criteria:
- Deployment succeeds without privilege escalation warnings.
- Security diagnostics report expected policy checksum and write mode.
- Perf smoke output includes P50/P95/P99 within agreed SLO target.

## Deployment Gate Checklist

| Gate | Control | Verification Command | Pass Condition |
| -------- | --------------------- | --------- | ---------- |
| GATE-001 | Container hardening active | `docker inspect fastmcp-sql2019` | `ReadonlyRootfs=true`, `CapDrop` contains `ALL`, `NoNewPrivileges=true` |
| GATE-002 | Dual-instance connectivity | `GET /diagnostics/health` | `instances.primary.state=healthy` and `instances.secondary.state=healthy` |
| GATE-003 | Write protection active | Blocked write test call | Response is denied and audit log decision is `deny` |
| GATE-004 | Rate limiting active | burst test script | At least one request rejected with `RATE_LIMIT_EXCEEDED` |
| GATE-005 | Audit completeness | parse `/var/log/mcp/audit.log` | Every request has `request_id`, `actor`, `tool`, `decision`, `latency_ms` |
| GATE-006 | Evidence pipeline active | `scripts/collect-evidence.ps1` | Archive generated with config hashes and diagnostics snapshots |

## Operational Rollback Procedure

1. Enable emergency read-only mode by overriding runtime policy env var or policy file.
2. Restart service and verify `GET /diagnostics/security` reports read-only mode.
3. If stability issue persists, redeploy previous pinned image digest.

```powershell
# Emergency read-only all mode (example)
$env:FASTMCP_EMERGENCY_READ_ONLY = "true"
docker compose -f docker/docker-compose.yml up -d --force-recreate

# Roll back image tag example
docker pull ghcr.io/company/fastmcp-sql2019:0.9.4
docker compose -f docker/docker-compose.yml up -d --force-recreate
```

Rollback completion criteria:
- Service healthy.
- No write operations accepted.
- Audit logs show controlled policy transition and post-rollback operation records.

## Security Compliance Mapping

| Control ID | Objective | Implementation Artifact | Validation |
| -------- | --------------------- | --------- | ---------- |
| CMP-001 | Encrypt SQL transport | `config/instances.yaml` (`encrypt: true`, `trust_server_certificate: false`) | connection startup logs + successful TLS connection |
| CMP-002 | Least-privilege database access | secret-backed SQL credentials and role-scoped grants | periodic SQL permission review report |
| CMP-003 | Write restriction by default | `config/runtime-policy.yaml` with `write_mode_default: deny` | blocked write test + audit decision logs |
| CMP-004 | Abuse protection | `config/rate-limit.yaml` and limiter middleware | quota exceedance test |
| CMP-005 | Immutable traceability | JSON audit logs in `/var/log/mcp/audit.log` forwarded to SIEM | daily digest and retention check |
| CMP-006 | Runtime hardening | compose `read_only`, `cap_drop`, `no-new-privileges`, `tmpfs` | container inspect evidence |
| CMP-007 | Repeatable evidence generation | `scripts/collect-evidence.ps1` and `.sh` | signed archive created daily |

## DBA Workflow Integration Pattern

1. DBA submits approved query through instance-bound tool name using convention `db_<instance>_sql2019_<toolname>`.
2. Service enforces policy and logs request decision.
3. DBA retrieves report artifact from `reports/` for incident or change records.
4. Compliance officer retrieves evidence archive from `evidence/` and verifies checksums.

Suggested scheduled jobs:
- Job `mcp_daily_evidence_utc_0100`: run `scripts/collect-evidence.ps1`.
- Job `mcp_hourly_latency_report`: run `scripts/report-latency.ps1`.
- Job `mcp_15min_blocking_report`: run `scripts/report-blocking-sessions.ps1`.

## Session Management Defaults

Use these baseline values unless policy requires stricter limits:

- `session_ttl_minutes = 60`
- `inactivity_timeout_minutes = 15`
- `concurrent_sessions_limit = 10`
- `max_query_duration_ms = 15000`
- `max_result_rows = 5000`

Tuning guidance:
- Decrease `session_ttl_minutes` for high-sensitivity environments.
- Lower `max_result_rows` for networks with constrained bandwidth.
- Raise pool limits only after confirming SQL server CPU headroom and lock profile.

