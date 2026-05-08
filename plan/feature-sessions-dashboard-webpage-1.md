---
goal: Modify db_{instance_number}_sql2019_sessions_dashboard to create a webpage and return a link to it when the tool is called
version: 1.0
date_created: 2026-05-08
last_updated: 2026-05-08
owner: MCP SQL Server Team
status: 'Completed'
tags: [feature, dashboard, html, sessions, blocking, frontend, sql-server]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

The `db_{instance_number}_sql2019_sessions_dashboard` MCP tool currently returns a URL to an external FastMCPApp interactive view plus a raw JSON payload (`sessions`, `locks`, `blockers`, `head_blockers`, `recommendations`). The HTML fragment in `build_sessions_dashboard_full()` is a bare `<section>` with three lines of text and is not exposed via a dedicated first-party page link contract.

This plan upgrades the tool so each invocation creates a rendered webpage and returns a stable `dashboard_url` link to that page in the tool response. The response continues to include `html` and structured `data`, but the URL becomes the primary consumption path.

The linked page renders two primary views:

1. **Sessions table** — one row per user session, columns for status badge, session ID, login, host, program, database, command, wait type, wait time ms, CPU time ms, open transactions, and a "blocking" badge when `blocking_session_id IS NOT NULL`.
2. **Session chain section** — for every distinct blocking chain, a tree-style collapsible group listing the head blocker row and each blocked descendant, with chain depth, cumulative wait, and resource description sourced from `sys.dm_os_waiting_tasks` and `sys.dm_tran_locks`.

The JSON `data` envelope is preserved so downstream LLM consumers still get structured data.

## 1. Requirements & Constraints

- **REQ-001**: When `db_{instance_number}_sql2019_sessions_dashboard` is called, the tool response must include `dashboard_url` pointing to the generated webpage.
- **REQ-002**: `dashboard_url` must be an HTTPS link using the server base URL and a request-unique path segment (example: `/diagnostics/dashboards/{request_id}`).
- **REQ-003**: The `html` field in the tool response must still be a complete `<!DOCTYPE html>` document renderable in any modern browser without external resources.
- **REQ-004**: Sessions table must distinguish `active` (status = `running`/`suspended`) from `idle` (status = `sleeping`) rows using a colored status badge column.
- **REQ-005**: Sessions that are blocked (have a non-null, non-zero `blocking_session_id`) must use a `row-blocked` CSS class for visual highlighting in the sessions table.
- **REQ-006**: Head blocker rows (session IDs present in `head_blockers`) must use a `row-head-blocker` CSS class distinct from normal active rows.
- **REQ-007**: The session chaining section must render each blocking chain as a `<details open>` element: head blocker as `<summary>`, blocked children indented below in a nested table.
- **REQ-008**: All four DMV data sources must continue to be queried: `sys.dm_exec_sessions`, `sys.dm_exec_requests`, `sys.dm_tran_locks`, `sys.dm_os_waiting_tasks`. A fifth query (`blocking_chain_query`) is added for the chain-tree view.
- **REQ-009**: `active_sessions_query` must be extended to return `DB_NAME(s.database_id) AS session_database_name` and `s.open_transaction_count`.
- **REQ-010**: A metadata header bar must show instance number, database, generated timestamp, and stat pills for Sessions / Lock Holders / Waiting Tasks / Chain Rows.
- **REQ-011**: No external CSS framework, JS library, or CDN resource may be loaded. All styling and interactivity must be inside `<style>` / `<script>` blocks.
- **REQ-012**: A `recommendations` panel must appear at the bottom of the page using priority-colored cards.
- **SEC-001**: All SQL string columns inserted into HTML (`login_name`, `host_name`, `program_name`, `command`, `wait_type`, `resource_description`) must pass through `html.escape()` to prevent stored XSS.
- **SEC-002**: No session credential, password hash, or secret column may be selected or rendered.
- **CON-001**: `build_sessions_dashboard_full()` in `src/tools/dashboard_payloads.py` remains the single source of truth for HTML generation; `_sessions_dashboard` in `sql_tools.py` calls it and publishes the generated HTML under a retrievable URL.
- **CON-002**: `sessions_dashboard_app.py` (FastMCPApp provider) must continue to function; it uses its own `fetch_sessions_dashboard_data` app-tool independently.
- **CON-003**: All 78 existing tests must continue to pass after changes.
- **GUD-001**: Use Python stdlib `html.escape()` — no third-party templating library.
- **GUD-002**: Keep `build_sessions_dashboard_full()` a pure function (no I/O, no imports beyond stdlib and typing).
- **PAT-001**: Extract HTML sub-builders as private module-level functions (`_html_inline_styles`, `_html_header`, `_html_sessions_table`, `_html_chain_section`, `_html_recommendations`, `_html_footer`) to keep the main function readable and testable.

## 2. Implementation Steps

### Implementation Phase 1 — Extend SQL queries for richer session data

- **GOAL-001**: Add the columns required by the webpage (database name, open transactions, resource description, chain tree) to existing and new query templates in `src/tools/query_catalog.py`.

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-001 | Extend `active_sessions_query(top_n)` to also `SELECT DB_NAME(s.database_id) AS session_database_name, s.open_transaction_count` from `sys.dm_exec_sessions`. Retain all existing column aliases and `WHERE s.is_user_process = 1` filter. | Yes | 2026-05-08 |
| TASK-002 | Extend `lock_chain_query(top_n)` to also `SELECT wt.resource_description` so each waiting-task row carries a human-readable lock resource string for the chain-tree view. | Yes | 2026-05-08 |
| TASK-003 | Add `blocking_chain_query(top_n: int) -> str` to `query_catalog.py`. Query: `SELECT TOP {top_n} r.session_id, r.blocking_session_id, r.wait_type, r.wait_time, s.status, s.login_name, s.host_name, r.command FROM sys.dm_exec_requests r JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id WHERE r.blocking_session_id > 0 ORDER BY r.blocking_session_id, r.wait_time DESC`. This gives the complete blocked-session set; head blockers are derived in Python from the existing `lock_chain_query` head-blocker logic. | Yes | 2026-05-08 |

### Implementation Phase 2 — HTML page builder (`dashboard_payloads.py`)

- **GOAL-002**: Replace the three-line HTML stub in `build_sessions_dashboard_full()` with a full self-contained HTML document composed from private helper functions.

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-004 | Add `import html as _html_mod` at the top of `src/tools/dashboard_payloads.py`. Create private `_esc(value: Any) -> str` that returns `_html_mod.escape(str(value) if value is not None else "—")`. | Yes | 2026-05-08 |
| TASK-005 | Create `_html_inline_styles() -> str` returning a `<style>` block with: CSS custom properties for status colors (`--c-active: #22c55e`, `--c-idle: #94a3b8`, `--c-blocked: #ef4444`, `--c-blocker: #f97316`); table reset styles (`border-collapse: collapse; width: 100%; font-family: ui-monospace, monospace; font-size: .82rem`); `.badge` pill with `border-radius: 9999px; padding: .15em .55em; font-size: .75rem; font-weight: 600`; row classes `.row-active { background: #f0fdf4 }`, `.row-idle { background: #f8fafc }`, `.row-blocked { background: #fef2f2 }`, `.row-head-blocker { background: #fff7ed; font-weight: 700 }`; `.rec-card` flex card with left border accent; `@media (prefers-color-scheme: dark)` override inverting backgrounds. | Yes | 2026-05-08 |
| TASK-006 | Create `_html_header(instance_number: int, database_name: str, generated_at_utc: str, session_count: int, lock_count: int, wait_count: int, chain_count: int) -> str` returning a `<header>` with `<h1>SQL Server Sessions Dashboard</h1>`, metadata line (`Instance {n} · {database_name}`), generated timestamp, and four `<span class="badge">` stat pills. | Yes | 2026-05-08 |
| TASK-007 | Create `_html_sessions_table(sessions: list[dict], head_blockers: list[int]) -> str` returning `<section id="sessions"><h2>Sessions</h2><table>`. Columns (in order): Status, SID, Login, Host, Program, Database, Command, Wait Type, Wait (ms), CPU (ms), Txns, Blocking SID. Row CSS class selection: apply `row-head-blocker` if `session_id` in `head_blockers`; else `row-blocked` if `blocking_session_id` is non-null and > 0; else `row-active` if `status` in `("running", "suspended")`; else `row-idle`. Apply `_esc()` to all string columns. Render `—` for NULL numeric/string fields. Include `<caption>` with counts. | Yes | 2026-05-08 |
| TASK-008 | Create `_html_chain_section(blocking_chains: list[dict], waiting_tasks: list[dict]) -> str` returning `<section id="chains"><h2>Session Chains</h2>`. If `blocking_chains` is empty, return `<p>No blocking chains detected.</p>`. Otherwise group rows by `blocking_session_id` value — each unique blocker becomes a `<details open>` with `<summary>` showing head-blocker SID, chain depth (count of rows with that blocker), and max wait. Inside each group render a `<table>` with columns: Blocked SID, Login, Host, Command, Wait Type, Wait (ms), and Resource Description (from `waiting_tasks` joined by `session_id`). Indent child rows via `padding-left: {depth * 16}px` on the first `<td>`. | Yes | 2026-05-08 |
| TASK-009 | Create `_html_recommendations(recommendations: list[dict]) -> str` returning `<section id="recommendations"><h2>Recommendations</h2>`. For each recommendation render `<div class="rec-card rec-{priority}"><strong>[{PRIORITY}]</strong> {action} — <em>{rationale}</em></div>`. Priority-specific border-left colors defined in the style block from TASK-005: `high` → `#ef4444`, `medium` → `#f97316`, `info` → `#3b82f6`. Apply `_esc()` to `action` and `rationale`. | Yes | 2026-05-08 |
| TASK-010 | Create `_html_footer(generated_at_utc: str) -> str` returning `<footer style="..."><small>MCP SQL Server · Generated {generated_at_utc} · Point-in-time DMV snapshot — data does not persist.</small></footer>`. | Yes | 2026-05-08 |
| TASK-011 | Update `build_sessions_dashboard_full()` signature to accept `blocking_chains: list[dict[str, Any]] = ()` as a new keyword-only parameter with empty-list default (backward compatible). Replace the current three-line `html` string with the full document assembly: `"<!DOCTYPE html>\n<html lang='en'>\n<head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Sessions Dashboard — Instance {instance_number}</title>" + _html_inline_styles() + "</head>\n<body>" + _html_header(...) + _html_sessions_table(sessions, head_blockers) + _html_chain_section(blocking_chains, waiting_tasks) + _html_recommendations(recommendations) + _html_footer(generated_at_utc) + "\n</body></html>"`. Add `"blocking_chains": blocking_chains` to the `"widgets"` dict in the returned `data`. | Yes | 2026-05-08 |
| TASK-012 | Update `DASHBOARD_STATE_SCHEMA` to add `"blocking_chains"` array property with items schema `{session_id, blocking_session_id, wait_type, wait_time, status, login_name, host_name, command}` (all nullable except `session_id`). Add `"blocking_chains"` to the schema's `"required"` list. | Yes | 2026-05-08 |
| TASK-013 | Add `src/tools/dashboard_page_store.py` implementing in-memory page registration API: `register_dashboard_page(request_id: str, html: str, ttl_seconds: int) -> str` and `get_dashboard_page(request_id: str) -> str | None`. `register_dashboard_page` must return the final `dashboard_url` link. | Yes | 2026-05-08 |

### Implementation Phase 3 — Wire new query through sql_tools and sessions app

- **GOAL-003**: Propagate `blocking_chain_query` and the new `blocking_chains` parameter through the tool layer without changing error-handling or audit logging paths.

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-014 | In `src/tools/sql_tools.py`, add `blocking_chain_query` to the `from src.tools.query_catalog import (...)` block. | Yes | 2026-05-08 |
| TASK-015 | In `_sessions_dashboard` in `src/tools/sql_tools.py`, add `blocking_chain_rows = {"rows": []}` before the `if include_locks:` block and add `blocking_chain_rows = state.connection_manager.execute_catalog_query(_instance, db_name, blocking_chain_query(200), 200)` inside `if include_locks:`. Update the `rows` counter to include `len(blocking_chain_rows["rows"])`. Pass `blocking_chains=blocking_chain_rows["rows"]` to `build_sessions_dashboard_full(...)`. | Yes | 2026-05-08 |
| TASK-016 | In `_sessions_dashboard` in `src/tools/sql_tools.py`, after `full_payload` is built, call `register_dashboard_page(request_id, full_payload["html"], ttl_seconds=900)` and set response keys: `dashboard_url`, `request_id`, `expires_at_utc`, then include `content_type/html/data` from `full_payload`. | Yes | 2026-05-08 |
| TASK-017 | Add diagnostics route in `src/diagnostics/routes.py`: `GET /diagnostics/dashboards/{request_id}` returning stored HTML with `Content-Type: text/html`; return 404 when key absent/expired. | Yes | 2026-05-08 |
| TASK-018 | In `src/tools/sessions_dashboard_app.py`, add `blocking_chain_query` to the `from src.tools.query_catalog import` line. Inside `fetch_sessions_dashboard_data`, declare `blocking_chain_rows = {"rows": []}` and populate it inside `if include_locks:`. Add `"blocking_chains": blocking_chain_rows["rows"]` to the returned dict. | Yes | 2026-05-08 |

### Implementation Phase 4 — Tests

- **GOAL-004**: Validate HTML output contract, XSS safety, row classification logic, and query structure.

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-019 | In `tests/test_sessions_dashboard.py`, extend `test_build_sessions_dashboard_full_required_sections` to assert `"blocking_chains"` is present in `result["data"]["widgets"]`. | Yes | 2026-05-08 |
| TASK-020 | Add `test_html_document_is_complete_page`: assert `result["html"]` starts with `"<!DOCTYPE html>"` and ends with `"</html>"` (strip trailing whitespace). | Yes | 2026-05-08 |
| TASK-021 | Add `test_html_contains_sessions_table`: call with a single session row `{session_id: 55, login_name: "sa", host_name: "SVRA", program_name: "SSMS", status: "running", command: "SELECT", wait_type: None, wait_time: None, cpu_time: None, blocking_session_id: None}` and assert HTML contains `"55"` and `">sa<"` (or escaped equivalent). | Yes | 2026-05-08 |
| TASK-022 | Add `test_html_xss_escaping`: call with `login_name="<script>alert(1)</script>"`. Assert the raw string `<script>alert(1)</script>` does **not** appear in `result["html"]`. | Yes | 2026-05-08 |
| TASK-023 | Add `test_html_blocked_session_row_class`: call with a session where `blocking_session_id=42`, assert `"row-blocked"` appears in HTML. | Yes | 2026-05-08 |
| TASK-024 | Add `test_html_head_blocker_row_class`: call with `sessions=[{session_id: 10, ...}]` and `head_blockers=[10]`, assert `"row-head-blocker"` appears in HTML. | Yes | 2026-05-08 |
| TASK-025 | Add `test_html_chain_section_with_data`: call with `blocking_chains=[{session_id: 7, blocking_session_id: 3, wait_type: "LCK_M_X", wait_time: 3200, status: "suspended", login_name: "appuser", host_name: "APPSVR", command: "UPDATE"}]`. Assert HTML contains `id="chains"` and `"3200"`. | Yes | 2026-05-08 |
| TASK-026 | Add `test_html_chain_section_empty_message`: call with `blocking_chains=[]`. Assert HTML contains `"No blocking chains detected"`. | Yes | 2026-05-08 |
| TASK-027 | Add `test_html_recommendations_high_priority_card`: call with `head_blockers=[5]`. Assert HTML contains `"rec-high"`. | Yes | 2026-05-08 |
| TASK-028 | Add `test_blocking_chain_query_structure` in `tests/test_advanced_analysis_tools.py`: import `blocking_chain_query`, call with `top_n=20`, assert `"TOP 20"` in SQL, `"blocking_session_id"` in SQL, `"dm_exec_requests"` in SQL. | Yes | 2026-05-08 |
| TASK-029 | Add `test_active_sessions_query_extended_columns`: import `active_sessions_query`, assert `"session_database_name"` in result SQL and `"open_transaction_count"` in result SQL after TASK-001 is applied. | Yes | 2026-05-08 |
| TASK-030 | Add `test_sessions_dashboard_response_includes_dashboard_url` in `tests/test_sessions_dashboard.py`: mock `_sessions_dashboard` dependencies and assert response includes non-empty `dashboard_url` and `request_id`. | Yes | 2026-05-08 |
| TASK-031 | Add route test in `tests/test_diagnostics_tool_usage_summary.py` or a new diagnostics route test file: `GET /diagnostics/dashboards/{request_id}` returns 200 and exact stored HTML; non-existent ID returns 404. | Yes | 2026-05-08 |

### Implementation Phase 5 — Documentation

- **GOAL-005**: Update developer-facing docs to reflect new HTML output contract and `blocking_chains` state section.

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-032 | In `docs/run-mcp-server-with-docker.md` **State sections returned** table, add row: `dashboard_url` — "Link to generated HTML page for this request (TTL-backed)" and keep `blocking_chains` row. | Yes | 2026-05-08 |
| TASK-033 | In `docs/runbooks/scaling-strategy.md` **Interactive App Architecture** table, update the **State model** row to note `blocking_chains` section addition and add a **Page delivery** row documenting `/diagnostics/dashboards/{request_id}` TTL behavior. | Yes | 2026-05-08 |

## 3. Alternatives

- **ALT-001**: Return only inline HTML in the tool response (no link). Rejected — user requirement requires a link to the generated webpage when the tool is called.
- **ALT-002**: Use Jinja2 templates stored as `.html` files. Rejected — adds a runtime dependency and file-system coupling; Python string composition with `html.escape()` is sufficient and fully testable.
- **ALT-003**: Add a dedicated HTTP route (`/sessions-dashboard/{instance}`) served by the FastMCP process. Deferred — valid follow-on; the self-contained document can be saved as `.html` by the caller if persistent URL access is needed.
- **ALT-004**: Load Tailwind CSS or Bootstrap via CDN. Rejected by REQ-009 (no external network resources).
- **ALT-005**: Use a recursive CTE in `blocking_chain_query` to compute tree depth in SQL. Viable for SQL Server 2019 but adds parse complexity. Chosen approach (flat SELECT + Python grouping) is simpler and fully testable without a live DB.

## 4. Dependencies

- **DEP-001**: `html` (Python stdlib `html.escape`) — XSS escaping; no install required.
- **DEP-002**: `src.tools.query_catalog` — three modified/new functions: extended `active_sessions_query`, extended `lock_chain_query`, new `blocking_chain_query`.
- **DEP-003**: `src.tools.dashboard_payloads` — modified `build_sessions_dashboard_full`; new private helpers; updated `DASHBOARD_STATE_SCHEMA`.
- **DEP-004**: `src.tools.dashboard_page_store` (new) — request_id keyed temporary storage + URL builder.
- **DEP-005**: `src.tools.sql_tools` — `_sessions_dashboard` closure receives `blocking_chains` and publishes page link.
- **DEP-006**: `src.diagnostics.routes` — new read-only route to retrieve generated HTML by request_id.
- **DEP-007**: `src.tools.sessions_dashboard_app` — `fetch_sessions_dashboard_data` returns new `blocking_chains` key.

## 5. Files

- **FILE-001**: `src/tools/query_catalog.py` — extend `active_sessions_query`, extend `lock_chain_query`, add `blocking_chain_query`.
- **FILE-002**: `src/tools/dashboard_payloads.py` — add `_esc`, six `_html_*` helpers; update `build_sessions_dashboard_full`; update `DASHBOARD_STATE_SCHEMA`.
- **FILE-003**: `src/tools/dashboard_page_store.py` (new) — in-memory page registry + URL minting.
- **FILE-004**: `src/tools/sql_tools.py` — add `blocking_chain_query` import; update `_sessions_dashboard`; return `dashboard_url` for created page.
- **FILE-005**: `src/diagnostics/routes.py` — add dashboard retrieval route `GET /diagnostics/dashboards/{request_id}`.
- **FILE-006**: `src/tools/sessions_dashboard_app.py` — add `blocking_chain_query` import; update `fetch_sessions_dashboard_data`.
- **FILE-007**: `tests/test_sessions_dashboard.py` — new test cases for URL presence, HTML contract, and section rendering.
- **FILE-008**: `tests/test_advanced_analysis_tools.py` — query structure tests.
- **FILE-009**: `docs/run-mcp-server-with-docker.md` — `dashboard_url` and `blocking_chains` rows in state table.
- **FILE-010**: `docs/runbooks/scaling-strategy.md` — updated Interactive App Architecture and Page delivery notes.

## 6. Testing

- **TEST-001**: `test_sessions_dashboard_response_includes_dashboard_url` — tool response contains non-empty URL and request ID.
- **TEST-002**: `test_dashboard_route_returns_html_for_valid_request` — retrieval route returns 200 and exact page HTML.
- **TEST-003**: `test_dashboard_route_returns_404_for_unknown_or_expired_request` — retrieval route denies invalid link.
- **TEST-004**: `test_html_document_is_complete_page` — `<!DOCTYPE html>` open and `</html>` close present.
- **TEST-005**: `test_html_contains_sessions_table` — known session SID value visible in rendered HTML.
- **TEST-006**: `test_html_xss_escaping` — `<script>` in SQL column is HTML-escaped; raw tag absent.
- **TEST-007**: `test_html_blocked_session_row_class` — `row-blocked` class present for blocked row.
- **TEST-008**: `test_html_head_blocker_row_class` — `row-head-blocker` class present for head blocker.
- **TEST-009**: `test_html_chain_section_with_data` — `id="chains"` and wait-time value visible.
- **TEST-010**: `test_html_chain_section_empty_message` — no-chains message present when list is empty.
- **TEST-011**: `test_html_recommendations_high_priority_card` — `rec-high` class present when blockers exist.
- **TEST-012**: `test_blocking_chain_query_structure` — new query references correct DMV and columns.
- **TEST-013**: `test_active_sessions_query_extended_columns` — new columns `session_database_name`, `open_transaction_count` in query SQL.

## 7. Risks & Assumptions

- **RISK-001**: `blocking_chain_query` on a busy instance with 200 blocked sessions generates a large result set. Mitigation: `TOP 200` cap; existing connection-timeout policy ceiling enforced.
- **RISK-002**: New columns from TASK-001 (`session_database_name`, `open_transaction_count`) may be `None` for sessions with no active request. Mitigation: `_esc()` renders `None` as `"—"`.
- **RISK-003**: Self-contained HTML document may reach 40–60 KB for 200-session instances (200 rows × ~200 bytes/row + styles). Mitigation: response now returns `dashboard_url`; clients may fetch page lazily instead of parsing large inline payloads.
- **RISK-005**: In-memory URL store may lose pages on process restart. Mitigation: TTL behavior is documented; response includes `expires_at_utc`; restart-safe persistence can be added later if needed.
- **RISK-004**: `sessions_dashboard_app.py` `fetch_sessions_dashboard_data` currently returns `active_sessions` / `lock_chains` keys that differ from `sessions` / `blockers` / `locks` in `DASHBOARD_STATE_SCHEMA`. TASK-015 adds `blocking_chains` but does not rename existing keys; the ForEach bindings in the app UI must be verified to avoid referencing stale key names.
- **ASSUMPTION-001**: `html.escape()` is sufficient for XSS mitigation — the output is a static document with no `<form>` POST targets and no `eval()` / `innerHTML` write paths in the inline `<script>` block.
- **ASSUMPTION-002**: SQL Server 2019 exposes `database_id` and `open_transaction_count` on `sys.dm_exec_sessions` without additional grants beyond `VIEW SERVER STATE`.
- **ASSUMPTION-003**: The generated HTML page is consumed by an LLM client or saved to disk; it does not need to be served over HTTP.

## 8. Related Specifications / Further Reading

- [plan/feature-advanced-sql-monitoring-tools-1.md](feature-advanced-sql-monitoring-tools-1.md) — parent feature plan for all four monitoring tools
- [plan/feature-sessions-dashboard-interactive-app-1.md](feature-sessions-dashboard-interactive-app-1.md) — FastMCPApp interactive layer plan
- [src/tools/dashboard_payloads.py](../src/tools/dashboard_payloads.py) — current payload builder (primary target of Phase 2)
- [src/tools/query_catalog.py](../src/tools/query_catalog.py) — all parameterized SQL templates (target of Phase 1)
- [src/tools/sessions_dashboard_app.py](../src/tools/sessions_dashboard_app.py) — FastMCPApp provider (target of TASK-015)
- [docs/run-mcp-server-with-docker.md](../docs/run-mcp-server-with-docker.md) — operator guide (updated in Phase 5)
- [SQL Server DMV: sys.dm_exec_sessions](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-exec-sessions-transact-sql)
- [SQL Server DMV: sys.dm_exec_requests](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-exec-requests-transact-sql)
- [SQL Server DMV: sys.dm_tran_locks](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-tran-locks-transact-sql)
- [SQL Server DMV: sys.dm_os_waiting_tasks](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-os-waiting-tasks-transact-sql)
