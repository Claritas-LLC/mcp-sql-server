---
goal: Resolve FastMCP server startup dependency failures in Docker runtime image
version: 1.0
date_created: 2026-06-08
last_updated: 2026-06-08
owner: MCP SQL Server Team
status: Completed
tags: [debug, docker, fastmcp, dependencies, packaging, runtime]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines deterministic steps to eliminate Docker startup failures caused by missing Python runtime dependencies (`packaging`) and incomplete FastMCP server support resolution in the container image. The plan enforces dependency lock consistency between local package metadata and installed container runtime artifacts, then validates startup through automated container health and import checks.

## 1. Requirements & Constraints

- **REQ-001**: Container startup command `python -m src.server` must complete import phase without `ModuleNotFoundError` for `packaging`.
- **REQ-002**: `from fastmcp import FastMCP` in `src/server.py` must resolve server support dependencies at runtime.
- **REQ-003**: Runtime image must preserve current security posture (non-root user `mcpuser`, read-only compatible filesystem layout).
- **REQ-004**: Final image must remain based on `python:3.14-alpine` unless rollback is explicitly approved.
- **REQ-005**: Plan must include deterministic reproduction, fix verification, and regression prevention tests.
- **SEC-001**: Do not add broad wildcard or unpinned transitive installs in Docker stages that bypass project dependency declarations.
- **SEC-002**: Do not log secrets from `.env` or SQL connection strings during validation.
- **CON-001**: Existing ODBC 18 extraction path in `docker/Dockerfile` must remain functional.
- **CON-002**: Existing tool/runtime contracts in `src/` and `config/` must not be changed as part of dependency-only remediation.
- **GUD-001**: Prefer fixing root cause in dependency declaration/build process before adding fallback runtime pip installs.
- **PAT-001**: Use fail-fast validation gates after each phase (`docker build`, `docker run`, import probe, health probe).

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Reproduce and baseline the dependency/import failure with deterministic evidence.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Capture baseline error by running `docker logs mcp-sqlserver --tail 200` and store the exact traceback in diagnostic notes at `plan/debug-fix-fastmcp-server-dependencies-1.md` Appendix section. | ✅ | 2026-06-08 |
| TASK-002 | Validate currently installed FastMCP-related distributions inside running image using `docker run --rm --entrypoint python harryvaldez/mcp-sql-server:latest -c "import importlib.metadata as m; print(m.version('fastmcp')); print('packaging' in [d.metadata['Name'].lower() for d in m.distributions()])"`. | ✅ | 2026-06-08 |
| TASK-003 | Confirm project dependency intent by reading `pyproject.toml` and noting whether `packaging` is direct or only transitive. Record findings in plan notes. | ✅ | 2026-06-08 |

### Implementation Phase 2

- GOAL-002: Apply dependency-manifest and build-process correction to guarantee runtime presence of required modules.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-004 | Update `pyproject.toml` `[project].dependencies` to include explicit `packaging>=24.0` to remove transitive ambiguity from FastMCP import chain. | ✅ | 2026-06-08 |
| TASK-005 | Update `docker/Dockerfile` builder install command to enforce deterministic wheel build/install ordering and dependency installation from project metadata only (no ad-hoc runtime-only pip add). | ✅ | 2026-06-08 |
| TASK-006 | Rebuild image with `docker build -t harryvaldez/mcp-sql-server:latest -f docker/Dockerfile .` and require successful completion before next phase. | ✅ | 2026-06-08 |

### Implementation Phase 3

- GOAL-003: Validate fixed image behavior and prevent regression.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-007 | Run import probe: `docker run --rm --entrypoint python harryvaldez/mcp-sql-server:latest -c "import packaging; from fastmcp import FastMCP; print('ok')"` and assert output equals `ok`. | ✅ | 2026-06-08 |
| TASK-008 | Start container with existing runtime args and verify `docker logs` shows no FastMCP server support import error for 60s observation window. | ✅ | 2026-06-08 |
| TASK-009 | Verify health endpoint responds: `curl -fsS http://localhost:8085/diagnostics/health` (or configured port mapping) with successful HTTP response. | ✅ | 2026-06-08 |
| TASK-010 | Add regression test in `tests/` that imports `src.server` in isolated process and fails if `ImportError` includes FastMCP server-support hints. | ✅ | 2026-06-08 |

## 3. Alternatives

- **ALT-001**: Add `pip install packaging` directly in runtime Docker stage. Rejected because it bypasses project dependency source-of-truth and creates drift.
- **ALT-002**: Pin `fastmcp-slim[server]` directly instead of `fastmcp`. Rejected initially to avoid broad package identity change without compatibility review.
- **ALT-003**: Revert to `python:3.11-slim` image. Rejected because issue is dependency resolution integrity, not Python base image capability.

## 4. Dependencies

- **DEP-001**: Docker engine and Docker Desktop must be running for build/run validation.
- **DEP-002**: Python package index/network access required during image build for dependency resolution.
- **DEP-003**: Existing SQL/OIDC runtime configuration in `.env` required only for full startup validation, not for import probe.

## 5. Files

- **FILE-001**: `pyproject.toml` - add explicit `packaging` dependency.
- **FILE-002**: `docker/Dockerfile` - ensure deterministic dependency installation path remains aligned with project metadata.
- **FILE-003**: `tests/` (new or updated test module) - add startup import regression test.
- **FILE-004**: `plan/debug-fix-fastmcp-server-dependencies-1.md` - record execution evidence and completion state.

## 6. Testing

- **TEST-001**: Container import smoke test for `packaging` and `FastMCP`.
- **TEST-002**: Container startup log scan for absence of `ModuleNotFoundError: No module named 'packaging'`.
- **TEST-003**: Health endpoint readiness check after container boot.
- **TEST-004**: `pytest -q` execution including new regression import test.

## 7. Risks & Assumptions

- **RISK-001**: FastMCP dependency graph may change across releases and reintroduce implicit requirements.
- **RISK-002**: Alpine-specific wheel availability for Python 3.14 may vary, increasing build-time source compilation variance.
- **RISK-003**: Local container logs may contain stale errors from prior failed runs, causing false negatives during validation.
- **ASSUMPTION-001**: `fastmcp>=3.2.0` remains compatible with current server initialization code in `src/server.py`.
- **ASSUMPTION-002**: Runtime command remains `ENTRYPOINT ["python", "-m", "src.server"]`.

## 8. Related Specifications / Further Reading

- `docs/run-mcp-server-with-docker.md`
- `docs/production-deployment-runbook.md`
- `AGENTS.md`
