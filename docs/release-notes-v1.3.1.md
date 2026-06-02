# Release Notes - v1.3.1

Release date: 2026-06-02

## Highlights

- Corrected and normalized MCP tool catalog documentation.
- Updated runtime and Azure deployment docs for MCP streamable HTTP session requirements.
- Added production deployment, operations, DR, observability, and configuration baseline documents.

## Documentation Fixes

- Replaced corrupted/duplicated sections in [mcp-tool-catalog.md](mcp-tool-catalog.md).
- Updated [run-mcp-server-with-docker.md](run-mcp-server-with-docker.md) with:
  - Redis backend verification commands
  - MCP initialize/session call flow examples
- Updated [azure-container-apps-deployment.md](azure-container-apps-deployment.md) and [DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md) to validate `/mcp/` using `initialize` + `Mcp-Session-Id`.

## New Production Documents

- [index.md](index.md)
- [production-deployment-runbook.md](production-deployment-runbook.md)
- [production-operations-runbook.md](production-operations-runbook.md)
- [disaster-recovery-and-rollback.md](disaster-recovery-and-rollback.md)
- [production-configuration-matrix.md](production-configuration-matrix.md)
- [observability-and-alerting-baseline.md](observability-and-alerting-baseline.md)

## Notes

- This release note documents documentation and operational guidance updates.
- Runtime source behavior remains unchanged in this documentation release.
