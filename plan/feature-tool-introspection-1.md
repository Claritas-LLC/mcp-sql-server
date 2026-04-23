---
goal: Create a tool to display all available tools, descriptions, parameters, and usage for both instance 1 and 2
version: 1.0
date_created: 2026-04-23
owner: mcp-sql-server team
status: 'Planned'
tags: [feature, documentation, introspection, usability]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan describes the implementation of a tool for both instance 1 and instance 2 of the MCP SQL Server system. The tool will enumerate all registered tools, display their descriptions, required and optional parameters, and provide usage instructions for invoking each tool. This will improve discoverability, usability, and documentation for users and integrators.

## 1. Requirements & Constraints

- **REQ-001**: The tool must work identically on both instance 1 and instance 2.
- **REQ-002**: The tool must enumerate all currently registered tools dynamically at runtime.
- **REQ-003**: For each tool, display:
  - Name/identifier
  - Description
  - Required parameters (with types and descriptions)
  - Optional parameters (with types and descriptions)
  - Example or usage instructions
- **REQ-004**: Output must be structured (JSON and human-readable text).
- **REQ-005**: The tool must be callable via the MCP API and CLI.
- **REQ-006**: The tool must not expose sensitive information.
- **CON-001**: Must not require server restart to reflect new/removed tools.
- **CON-002**: Must be compatible with FastMCP/Starlette and current codebase.
- **SEC-001**: Must not leak secrets or internal implementation details.
- **GUD-001**: Follow code hygiene and documentation standards.
- **PAT-001**: Use existing tool registration/introspection patterns.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Design and implement the tool introspection logic.

| Task     | Description                                                                                  | Completed | Date       |
| -------- | --------------------------------------------------------------------------------------------| --------- | ---------- |
| TASK-001 | Analyze current tool registration and metadata storage in server.py/runtime_server.py        |           |            |
| TASK-002 | Design a function/class to enumerate all registered tools and extract metadata               |           |            |
| TASK-003 | Implement logic to collect tool name, description, parameters (required/optional), and usage |           |            |
| TASK-004 | Ensure output is available in both JSON and human-readable formats                           |           |            |

### Implementation Phase 2

- GOAL-002: Integrate the introspection tool as a callable endpoint/tool and document usage.

| Task     | Description                                                                                  | Completed | Date |
| -------- | --------------------------------------------------------------------------------------------| --------- | ---- |
| TASK-005 | Register the introspection tool for both instance 1 and 2                                    |           |      |
| TASK-006 | Add API and CLI entry points for calling the tool                                            |           |      |
| TASK-007 | Write or update documentation in users-manual.md with usage instructions and sample output   |           |      |
| TASK-008 | Add tests to verify correct output and security (no secrets exposed)                         |           |      |

## 3. Alternatives

- **ALT-001**: Hardcode tool metadata in documentation (rejected: not dynamic, error-prone).
- **ALT-002**: Use static code analysis to extract tool info (rejected: less reliable, not runtime-aware).

## 4. Dependencies

- **DEP-001**: FastMCP/Starlette tool registration and metadata APIs
- **DEP-002**: Existing tool registration patterns in server.py/runtime_server.py

## 5. Files

- **FILE-001**: mcp_sqlserver/server.py (main tool registration and logic)
- **FILE-002**: mcp_sqlserver/runtime_server.py (if tool registry is here)
- **FILE-003**: users-manual.md (documentation)
- **FILE-004**: tests/test_integration_tools.py (or new test file for introspection tool)

## 6. Testing

- **TEST-001**: Test that the tool lists all registered tools with correct metadata on both instances
- **TEST-002**: Test that required/optional parameters are correctly identified
- **TEST-003**: Test that no secrets or sensitive info are exposed
- **TEST-004**: Test API and CLI invocation and output formats

## 7. Risks & Assumptions

- **RISK-001**: Tool registry may not contain all required metadata (may need to enhance registration)
- **ASSUMPTION-001**: All tools are registered using a consistent pattern with accessible metadata

## 8. Related Specifications / Further Reading

- [users-manual.md](docs/users-manual.md)
- [FastMCP documentation](https://github.com/microsoft/fastmcp)
- [Starlette documentation](https://www.starlette.io/)
