# FastMCP Guidance Notes Applied

Date: 2026-05-06

References consulted:
- https://gofastmcp.com/v2/patterns/testing#testing-your-fastmcp-server
- https://gofastmcp.com/v2/servers/logging#client-logging

Applied practices in implementation:
- Structured, deterministic tool outputs with explicit fields for instance metadata and timestamps.
- Context logging via `ctx.info(...)` in tool handlers for traceability.
- Security-first execution path in handlers:
  1. session check
  2. rate limit check
  3. SQL policy/write guard
  4. execution
  5. audit logging
- Streamable HTTP mounting retained in server bootstrap for remote operation compatibility.
- Deterministic error-code style payloads for diagnostics and query execution paths.
