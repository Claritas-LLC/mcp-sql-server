---
goal: Normalize MCP stored-procedure execution policy and document runtime-policy workflows
version: 1.0
date_created: 2026-05-18
last_updated: 2026-05-18
owner: MCP SQL Server Team
status: Completed
tags: [feature, configuration, documentation, security, sql-server, fastmcp, controlled-write]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines the work needed to make allowlisted stored-procedure execution behave consistently with the runtime policy model, remove misleading configuration drift, and publish a durable guide for future policy updates. It also captures the current gap discovered during validation: policy allowlisting can permit a procedure, but SQL Server EXECUTE permission is still required for the MCP service principal before the call can succeed.

## 1. Requirements & Constraints

- **REQ-001**: `config/runtime-policy.yaml` remains the authoritative runtime policy source loaded through `FASTMCP_POLICY_PATH`.
- **REQ-002**: When a procedure is listed under `allowed_tools.db_primary_sql2019_exec_proc.allowed_procedures` or `allowed_tools.db_secondary_sql2019_exec_proc.allowed_procedures`, and the instance-specific tool flag is enabled, the MCP server must permit the procedure call.
- **REQ-003**: The `db_primary_sql2019_exec_proc` and `db_secondary_sql2019_exec_proc` tool responses must surface procedure output rows when the underlying stored procedure returns a result set; if no result set is returned, the tool may return status and rowcount metadata only.
- **REQ-004**: The documentation must explain the role of every YAML file in `config/` and how those files relate to the policy files in `policy/`.
- **REQ-005**: Redundant or misleading configuration must be removed or clearly isolated so operators do not infer that a non-authoritative file is part of runtime enforcement.
- **SEC-001**: Preserve denylist enforcement, audit logging, rate limiting, and instance-level enablement checks.
- **SEC-002**: Preserve procedure-name normalization, including case-insensitive matching and schema-qualified names.
- **CON-001**: Production policy guidance must prefer `write_mode_default: deny`; the guide may include an `allow` example for demonstration, but it must be clearly labeled as non-production.
- **CON-002**: The policy and docs must distinguish policy authorization from SQL Server permissions; allowlisting alone does not grant database EXECUTE rights.
- **GUD-001**: The guide must include exact steps to update the policy, restart the runtime, and verify the change using diagnostics and a procedure execution smoke test.
- **PAT-001**: Keep the execution path deterministic: policy check first, SQL permission second, output capture last.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Normalize the policy sources, remove misleading configuration, and align the runtime posture with the documented controlled-write model.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-001 | Update [config/runtime-policy.yaml](../config/runtime-policy.yaml) so `write_mode_default` uses the production-safe value `deny`, while keeping `allowed_write_tools` limited to `db_primary_sql2019_exec_proc` and `db_secondary_sql2019_exec_proc`, and keeping procedure names under `allowed_tools` for the exact instance-scoped tool. Remove any query-tool allowlist entry that tries to whitelist `EXEC` statements through `db_1_sql2019_execute_query`, because that path is confusing and does not represent the true controlled-write gate. | Yes | 2026-05-18 |
| TASK-002 | Reconcile [policy/sql-allowlist.yaml](../policy/sql-allowlist.yaml) with the runtime policy so it mirrors only the approved procedures that are actually intended for review. Add or update surrounding documentation so this file is presented as a reference or evidence artifact, not as a second hidden runtime source of truth. | Yes | 2026-05-18 |
| TASK-003 | Clean [config/tool-flags.override.example.json](../config/tool-flags.override.example.json) so instance-scoped `exec_proc` settings are not shown as global flags. Keep `exec_proc` examples only in [config/instance-tool-flags.override.example.json](../config/instance-tool-flags.override.example.json), and update the example environment comments in [README.md](../README.md) or [.env.example](../.env.example) if they still imply the wrong scope. | Yes | 2026-05-18 |

### Implementation Phase 2

- **GOAL-002**: Make allowlisted procedure calls return their output payload, not only execution status, while keeping security and telemetry intact.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-004 | Update [src/db/connection_manager.py](../src/db/connection_manager.py) in `execute_proc` so it captures the first result set when `cursor.description` is present, returns `columns`, `rows`, and a `has_result_set` indicator, and preserves `status`, `procedure`, and `rowcount` for procedures that do not emit rows. Keep transaction handling, commit behavior, and error propagation unchanged. | Yes | 2026-05-18 |
| TASK-005 | Update the `exec_proc` branch in [src/tools/sql_tools.py](../src/tools/sql_tools.py) so the tool response forwards the enhanced payload from `execute_proc`. The tool must still call `_resolve_actor_and_authorize`, `session_manager.touch`, `rate_limiter.allow`, `write_guard.validate_procedure`, and `write_guard.enforce` in the same order before execution. | Yes | 2026-05-18 |
| TASK-006 | Add regression tests that prove an allowlisted procedure returns rows through the MCP tool, a denylisted procedure is blocked, procedure-name matching remains case-insensitive, and a non-row-returning procedure still returns a deterministic status payload. Extend [tests/test_exec_proc_allowlist_validation.py](../tests/test_exec_proc_allowlist_validation.py) or add a focused companion test file if the output-shape assertions are easier to isolate there. | Yes | 2026-05-18 |

### Implementation Phase 3

- **GOAL-003**: Publish the guide and update the existing docs so operators can modify runtime policy safely and repeatably.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-007 | Create a new guide document under [docs](../docs) that explains how to modify `runtime-policy.yaml`, the role of each YAML file in `config/`, the relationship between `config/` and `policy/`, and the exact steps for applying changes in Docker and local development. The guide must include a worked example that uses `write_mode_default: allow` in a demonstration environment, adds a procedure under `allowed_tools`, restarts the server, and verifies successful execution. It must also include a production note that recommends `write_mode_default: deny` and explicit procedure allowlists. | Yes | 2026-05-18 |
| TASK-008 | Update [docs/access-levels-and-controlled-write.md](../docs/access-levels-and-controlled-write.md) to reflect the real enforcement order: policy allowlist, instance tool enablement, SQL Server EXECUTE permission, and audit/logging. Add a clear note that runtime policy does not grant SQL rights. | Yes | 2026-05-18 |
| TASK-009 | Update [docs/run-mcp-server-with-docker.md](../docs/run-mcp-server-with-docker.md), [docs/mcp-tool-catalog.md](../docs/mcp-tool-catalog.md), and [README.md](../README.md) so they point to the new guide, explain which files are authoritative, and show the restart-and-verify flow after policy changes. | Yes | 2026-05-18 |
| TASK-010 | Add an operations note that explains the SQL Server permission requirement for approved procedures. The note must tell operators to grant EXECUTE only on approved procedures or approved schemas to the MCP service principal, and to verify the permission before treating a policy allowlist change as complete. | Yes | 2026-05-18 |
| TASK-011 | Run the validation sweep: `ruff check .`, `pytest -q`, and one container smoke test that reloads the runtime with the modified configuration, calls an allowlisted procedure through `db_primary_sql2019_exec_proc`, and confirms that the returned payload contains the expected output rows. | Yes | 2026-05-18 |

## 3. Alternatives

- **ALT-001**: Keep `write_mode_default` as `allow` in production. Rejected because it weakens the controlled-write model and makes the policy docs harder to trust.
- **ALT-002**: Keep using `db_1_sql2019_execute_query` as a hidden execution path for stored procedures. Rejected because it conflates read and write semantics and produces confusing policy behavior.
- **ALT-003**: Treat `policy/sql-allowlist.yaml` as the live runtime source of truth. Rejected because the server currently loads `config/runtime-policy.yaml` through `FASTMCP_POLICY_PATH`, so two active sources of truth would increase drift.
- **ALT-004**: Return only rowcount and execution status from `exec_proc`. Rejected because the requested behavior is to surface procedure output successfully when rows are returned.

## 4. Dependencies

- **DEP-001**: The server must continue to load policy from [config/runtime-policy.yaml](../config/runtime-policy.yaml) via `FASTMCP_POLICY_PATH`.
- **DEP-002**: The MCP service principal must have SQL Server EXECUTE rights on each approved procedure, or on a tightly scoped schema that contains only approved procedures.
- **DEP-003**: Existing runtime middleware in [src/middleware/write_guard.py](../src/middleware/write_guard.py), rate limiting, session tracking, and audit logging must remain intact.
- **DEP-004**: Docker bind mounts or equivalent file mounts must expose the edited config and policy files to the running container.
- **DEP-005**: The current tool flag override flow in [src/config_loader.py](../src/config_loader.py) and [src/tools/tool_flags.py](../src/tools/tool_flags.py) must remain compatible with the example files.

## 5. Files

- **FILE-001**: [config/runtime-policy.yaml](../config/runtime-policy.yaml) - authoritative runtime policy, procedure allowlists, instance enablement, and write-mode baseline.
- **FILE-002**: [policy/sql-allowlist.yaml](../policy/sql-allowlist.yaml) - mirrored or reference procedure list used for review and evidence.
- **FILE-003**: [config/tool-flags.override.example.json](../config/tool-flags.override.example.json) - global tool flag example; should not show instance-scoped exec settings.
- **FILE-004**: [config/instance-tool-flags.override.example.json](../config/instance-tool-flags.override.example.json) - instance-scoped tool flag example; should own `exec_proc`.
- **FILE-005**: [src/db/connection_manager.py](../src/db/connection_manager.py) - procedure execution helper that needs result-set capture support.
- **FILE-006**: [src/tools/sql_tools.py](../src/tools/sql_tools.py) - MCP tool registration and exec-proc response shaping.
- **FILE-007**: [src/middleware/write_guard.py](../src/middleware/write_guard.py) - current procedure validation and policy enforcement logic.
- **FILE-008**: [src/config_loader.py](../src/config_loader.py) - runtime policy loading and environment override behavior.
- **FILE-009**: [docs/access-levels-and-controlled-write.md](../docs/access-levels-and-controlled-write.md) - access model and write-guard documentation.
- **FILE-010**: [docs/run-mcp-server-with-docker.md](../docs/run-mcp-server-with-docker.md) - restart and deployment instructions for mounted config changes.
- **FILE-011**: [docs/mcp-tool-catalog.md](../docs/mcp-tool-catalog.md) - tool contract reference and security notes.
- **FILE-012**: [README.md](../README.md) - top-level setup and documentation entrypoint.
- **FILE-013**: [tests/test_exec_proc_allowlist_validation.py](../tests/test_exec_proc_allowlist_validation.py) - allowlist validation coverage.
- **FILE-014**: [tests/test_policy_env_overrides.py](../tests/test_policy_env_overrides.py) - environment override coverage.
- **FILE-015**: [tests/test_tool_flags.py](../tests/test_tool_flags.py) - instance-vs-global enablement coverage.
- **FILE-016**: [tests/test_tool_authorization.py](../tests/test_tool_authorization.py) - authorization and group gating coverage.

## 6. Testing

- **TEST-001**: Validate that `runtime-policy.yaml` loads cleanly and that `write_mode_default` is the intended production value after the cleanup.
- **TEST-002**: Validate that allowlisted procedures are accepted for the correct tool and rejected for the wrong tool.
- **TEST-003**: Validate that `execute_proc` returns rows when a stored procedure emits a result set, and still returns deterministic metadata when it does not.
- **TEST-004**: Validate that the tool response remains case-insensitive for procedure names and still honors schema-qualified names.
- **TEST-005**: Validate that environment overrides for global and instance tool flags still parse correctly after the example-file cleanup.
- **TEST-006**: Run `ruff check .` and `pytest -q` successfully after the code and documentation updates.
- **TEST-007**: Run a container smoke test that restarts the runtime after a policy change and confirms the allowlisted procedure executes only after the policy and SQL permission conditions are satisfied.
- **TEST-008**: Confirm the new guide and the updated docs explicitly mention the SQL Server EXECUTE permission requirement.

## 7. Risks & Assumptions

- **RISK-001**: The SQL Server login used by the MCP container may not have EXECUTE permission on the approved procedure, which will produce SQL error 229 even when policy allows the call.
- **RISK-002**: Procedure output shapes may differ across stored procedures, so result-set capture must preserve deterministic behavior without assuming a single schema.
- **RISK-003**: Confusing override examples can reintroduce policy drift if the example JSON files and `.env` comments are not cleaned together.
- **RISK-004**: Docker bind mounts can keep stale configuration in the running container if the service is not restarted after policy edits.
- **ASSUMPTION-001**: The service should keep supporting both instance-bound exec-proc tools and read-only diagnostics tools without changing the tool naming scheme.
- **ASSUMPTION-002**: The guide should document the demo case with `write_mode_default: allow`, but production operators will follow the deny-by-default recommendation.
- **ASSUMPTION-003**: `policy/sql-allowlist.yaml` will remain a reviewable mirror unless the repository owners later choose a single-policy-file strategy.

## 8. Related Specifications / Further Reading

- [docs/access-levels-and-controlled-write.md](../docs/access-levels-and-controlled-write.md)
- [docs/run-mcp-server-with-docker.md](../docs/run-mcp-server-with-docker.md)
- [docs/mcp-tool-catalog.md](../docs/mcp-tool-catalog.md)
- [README.md](../README.md)
- [docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md](../docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md)
- [plan/feature-remote-mcp-tools-1.md](feature-remote-mcp-tools-1.md)