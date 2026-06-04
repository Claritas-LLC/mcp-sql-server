from __future__ import annotations


def _validate_top_n(top_n: int) -> int:
    try:
        value = int(top_n)
    except (TypeError, ValueError) as exc:
        raise ValueError("top_n must be an integer between 1 and 10000") from exc
    if value < 1 or value > 10000:
        raise ValueError("top_n must be between 1 and 10000")
    return value


def _validate_lookback_minutes(lookback_minutes: int) -> int:
    try:
        value = int(lookback_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("lookback_minutes must be an integer between 1 and 10080") from exc
    if value < 1 or value > 10080:
        raise ValueError("lookback_minutes must be between 1 and 10080")
    return value


def table_size_query(top_n: int) -> str:
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} s.name AS schema_name, t.name AS table_name, "
        "SUM(ps.row_count) AS row_count, "
        "CAST(SUM(ps.used_page_count) * 8.0 / 1024 AS DECIMAL(18,2)) AS total_space_mb "
        "FROM sys.tables t "
        "JOIN sys.schemas s ON t.schema_id = s.schema_id "
        "JOIN sys.dm_db_partition_stats ps ON t.object_id = ps.object_id AND ps.index_id IN (0,1) "
        "GROUP BY s.name, t.name "
        "ORDER BY total_space_mb DESC"
    )


def fragmented_indexes_query(top_n: int) -> str:
    """Top N indexes with highest fragmentation, scoped to the largest tables first.

    The CTE restricts the expensive dm_db_index_physical_stats scan to the
    top {top_n} * 4 candidate tables (ordered by row count) to avoid a
    full-database index scan on databases with thousands of objects.
    """
    top_n = _validate_top_n(top_n)
    return (
        f"WITH candidate_tables AS ("
        f"SELECT TOP {top_n * 4} t.object_id "
        "FROM sys.tables t "
        "JOIN sys.dm_db_partition_stats p ON t.object_id = p.object_id AND p.index_id IN (0,1) "
        "GROUP BY t.object_id "
        "ORDER BY SUM(p.row_count) DESC"
        f") "
        f"SELECT TOP {top_n} OBJECT_SCHEMA_NAME(ps.object_id) AS schema_name, "
        "OBJECT_NAME(ps.object_id) AS table_name, i.name AS index_name, "
        "ps.avg_fragmentation_in_percent, ps.page_count "
        "FROM candidate_tables ct "
        "CROSS APPLY sys.dm_db_index_physical_stats(DB_ID(), ct.object_id, NULL, NULL, 'LIMITED') ps "
        "JOIN sys.indexes i ON ps.object_id = i.object_id AND ps.index_id = i.index_id "
        "WHERE ps.index_id > 0 AND ps.index_level = 0 AND ps.page_count >= 100 "
        "AND OBJECTPROPERTY(ps.object_id, 'IsUserTable') = 1 "
        "ORDER BY ps.avg_fragmentation_in_percent DESC, ps.page_count DESC"
    )


def missing_pk_query() -> str:
    return (
        "SELECT s.name AS schema_name, t.name AS table_name "
        "FROM sys.tables t "
        "INNER JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "WHERE NOT EXISTS ( SELECT 1 FROM sys.key_constraints k WHERE k.parent_object_id = t.object_id "
        "AND k.type = 'PK' ) "
        "ORDER BY s.name, t.name"
    )


def fk_graph_query() -> str:
    return (
        "SELECT fk.name AS fk_name, "
        "OBJECT_SCHEMA_NAME(fk.parent_object_id) AS parent_schema, "
        "OBJECT_NAME(fk.parent_object_id) AS parent_table, "
        "OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS referenced_schema, "
        "OBJECT_NAME(fk.referenced_object_id) AS referenced_table "
        "FROM sys.foreign_keys fk "
        "WHERE OBJECTPROPERTY(fk.parent_object_id, 'IsUserTable') = 1"
    )


def orphan_user_query() -> str:
    return (
        "SELECT dp.name AS user_name "
        "FROM sys.database_principals dp "
        "LEFT JOIN sys.server_principals sp ON dp.sid = sp.sid "
        "WHERE dp.type IN ('S','U','G') AND dp.principal_id > 4 AND sp.sid IS NULL"
    )


def elevated_roles_query() -> str:
    return (
        "SELECT r.name AS role_name, m.name AS member_name "
        "FROM sys.database_role_members drm "
        "JOIN sys.database_principals r ON drm.role_principal_id = r.principal_id "
        "JOIN sys.database_principals m ON drm.member_principal_id = m.principal_id "
        "WHERE r.name IN ('db_owner','db_securityadmin','db_accessadmin')"
    )


def backup_recency_query() -> str:
    return (
        "SELECT d.name AS database_name, b.last_backup_finish_date "
        "FROM master.sys.databases d "
        "OUTER APPLY ("
        "  SELECT TOP 1 bs.backup_finish_date AS last_backup_finish_date "
        "  FROM msdb.dbo.backupset bs "
        "  WHERE bs.database_name = d.name AND bs.type = 'D' "
        "  ORDER BY bs.backup_finish_date DESC"
        ") b "
        "ORDER BY d.name"
    )


def active_sessions_query(top_n: int) -> str:
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} s.session_id, s.login_name, s.host_name, s.program_name, s.status, "
        "DB_NAME(s.database_id) AS session_database_name, "
        "s.open_transaction_count, s.login_time, s.last_request_start_time, "
        "r.command, r.wait_type, r.wait_time, r.cpu_time, r.blocking_session_id, r.start_time, "
        "SUBSTRING(st.text, 1, 500) AS sql_command "
        "FROM sys.dm_exec_sessions s "
        "LEFT JOIN sys.dm_exec_requests r ON s.session_id = r.session_id "
        "OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) st "
        "WHERE s.is_user_process = 1 "
        "ORDER BY r.wait_time DESC, s.session_id"
    )


def lock_chain_query(top_n: int) -> str:
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} wt.session_id, wt.blocking_session_id, wt.wait_type, wt.wait_duration_ms, wt.resource_description "
        "FROM sys.dm_os_waiting_tasks wt "
        "WHERE wt.blocking_session_id IS NOT NULL "
        "ORDER BY wt.wait_duration_ms DESC"
    )


def blocking_chain_query(top_n: int) -> str:
    """Blocked-session rows used to render chaining details in webpage view."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "r.session_id, "
        "r.blocking_session_id, "
        "r.wait_type, "
        "r.wait_time, "
        "s.status, "
        "s.login_name, "
        "s.host_name, "
        "r.command "
        "FROM sys.dm_exec_requests r "
        "JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id "
        "WHERE r.blocking_session_id > 0 "
        "ORDER BY r.blocking_session_id, r.wait_time DESC"
    )


def tran_locks_query(top_n: int) -> str:
    """Active lock holders from sys.dm_tran_locks with resource and mode details."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "tl.request_session_id AS session_id, "
        "tl.resource_type, "
        "tl.resource_database_id, "
        "tl.resource_associated_entity_id, "
        "tl.request_mode, "
        "tl.request_status, "
        "tl.request_owner_type "
        "FROM sys.dm_tran_locks tl "
        "WHERE tl.request_status IN ('GRANT', 'WAIT') "
        "ORDER BY tl.request_status DESC, tl.request_session_id"
    )


def waiting_tasks_query(top_n: int) -> str:
    """All waiting tasks from sys.dm_os_waiting_tasks with full wait context."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "wt.session_id, "
        "wt.blocking_session_id, "
        "wt.wait_type, "
        "wt.wait_duration_ms, "
        "wt.resource_description "
        "FROM sys.dm_os_waiting_tasks wt "
        "ORDER BY wt.wait_duration_ms DESC"
    )


# ---------------------------------------------------------------------------
# analyze_tab_health – additional checks
# ---------------------------------------------------------------------------


def heap_tables_query() -> str:
    """Tables with no clustered index (heap storage).

    Uses sys.dm_db_partition_stats (fast DMV) instead of sys.partitions
    (heavy system table) for row counts.
    """
    return (
        "SELECT s.name AS schema_name, t.name AS table_name, "
        "SUM(ps.row_count) AS row_count "
        "FROM sys.tables t "
        "JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "JOIN sys.dm_db_partition_stats ps ON t.object_id = ps.object_id AND ps.index_id = 0 "
        "WHERE ps.row_count > 0 "
        "GROUP BY s.name, t.name "
        "ORDER BY SUM(ps.row_count) DESC"
    )


def disabled_indexes_query() -> str:
    """Non-clustered indexes that are currently disabled."""
    return (
        "SELECT OBJECT_SCHEMA_NAME(i.object_id) AS schema_name, "
        "OBJECT_NAME(i.object_id) AS table_name, "
        "i.name AS index_name, i.type_desc "
        "FROM sys.indexes i "
        "WHERE i.is_disabled = 1 AND i.index_id > 0 "
        "ORDER BY schema_name, table_name, index_name"
    )


def stale_statistics_query(top_n: int) -> str:
    """Top N tables/indexes with the most out-of-date statistics.

    Scoped to top {top_n} * 4 largest tables to avoid full catalog scan
    on databases with thousands of statistics objects.
    """
    top_n = _validate_top_n(top_n)
    return (
        f"WITH top_tables AS ("
        f"SELECT TOP {top_n * 4} t.object_id "
        "FROM sys.tables t "
        "JOIN sys.dm_db_partition_stats p ON t.object_id = p.object_id AND p.index_id IN (0,1) "
        "GROUP BY t.object_id ORDER BY SUM(p.row_count) DESC"
        f") "
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(s.object_id) AS schema_name, "
        "OBJECT_NAME(s.object_id) AS table_name, "
        "s.name AS stat_name, "
        "sp.last_updated, "
        "sp.rows, "
        "sp.rows_sampled, "
        "sp.modification_counter "
        "FROM sys.stats s "
        "CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp "
        "WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1 "
        "AND s.object_id IN (SELECT object_id FROM top_tables) "
        "ORDER BY sp.modification_counter DESC, sp.last_updated ASC"
    )


def statistics_never_updated_query(top_n: int) -> str:
    """Top N user-table statistics with no update timestamp yet.

    Scoped to top {top_n} * 4 largest tables.
    """
    top_n = _validate_top_n(top_n)
    return (
        f"WITH top_tables AS ("
        f"SELECT TOP {top_n * 4} t.object_id "
        "FROM sys.tables t "
        "JOIN sys.dm_db_partition_stats p ON t.object_id = p.object_id AND p.index_id IN (0,1) "
        "GROUP BY t.object_id ORDER BY SUM(p.row_count) DESC"
        f") "
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(s.object_id) AS schema_name, "
        "OBJECT_NAME(s.object_id) AS table_name, "
        "s.name AS stat_name, "
        "sp.last_updated, "
        "sp.rows, "
        "sp.rows_sampled, "
        "sp.modification_counter "
        "FROM sys.stats s "
        "CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp "
        "WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1 "
        "AND sp.last_updated IS NULL "
        "AND s.object_id IN (SELECT object_id FROM top_tables) "
        "ORDER BY sp.rows DESC, sp.modification_counter DESC"
    )


def low_sampled_statistics_query(top_n: int) -> str:
    """Top N user-table statistics with weakest sample ratio.

    Scoped to top {top_n} * 4 largest tables.
    """
    top_n = _validate_top_n(top_n)
    return (
        f"WITH top_tables AS ("
        f"SELECT TOP {top_n * 4} t.object_id "
        "FROM sys.tables t "
        "JOIN sys.dm_db_partition_stats p ON t.object_id = p.object_id AND p.index_id IN (0,1) "
        "GROUP BY t.object_id ORDER BY SUM(p.row_count) DESC"
        f") "
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(s.object_id) AS schema_name, "
        "OBJECT_NAME(s.object_id) AS table_name, "
        "s.name AS stat_name, "
        "sp.last_updated, "
        "sp.rows, "
        "sp.rows_sampled, "
        "sp.modification_counter, "
        "CASE WHEN sp.rows > 0 "
        "THEN CAST(sp.rows_sampled AS FLOAT) / CAST(sp.rows AS FLOAT) "
        "ELSE 0 END AS sample_ratio "
        "FROM sys.stats s "
        "CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp "
        "WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1 "
        "AND sp.rows > 0 "
        "AND s.object_id IN (SELECT object_id FROM top_tables) "
        "ORDER BY sample_ratio ASC, sp.rows DESC"
    )


def database_statistics_settings_query() -> str:
    """Database-level automatic statistics maintenance settings."""
    return (
        "SELECT "
        "name AS database_name, "
        "is_auto_create_stats_on AS auto_create_statistics_on, "
        "is_auto_update_stats_on AS auto_update_statistics_on, "
        "is_auto_update_stats_async_on AS auto_update_statistics_async_on "
        "FROM sys.databases "
        "WHERE name = DB_NAME()"
    )


def missing_statistics_coverage_candidate_query(top_n: int) -> str:
    """Top N user tables that appear to have limited usable stats coverage.

    This is heuristic metadata-based analysis and does not inspect query plans.
    Scoped to top {top_n} * 4 largest tables.
    """
    top_n = _validate_top_n(top_n)
    return (
        f"WITH top_tables AS ("
        f"SELECT TOP {top_n * 4} t.object_id "
        "FROM sys.tables t "
        "JOIN sys.dm_db_partition_stats p ON t.object_id = p.object_id AND p.index_id IN (0,1) "
        "GROUP BY t.object_id ORDER BY SUM(p.row_count) DESC"
        f"), table_rows AS ("
        "SELECT p.object_id, SUM(p.row_count) AS row_count "
        "FROM sys.dm_db_partition_stats p "
        "WHERE p.index_id IN (0, 1) "
        "GROUP BY p.object_id"
        "), table_stats AS ("
        "SELECT st.object_id, COUNT(*) AS usable_stats_count "
        "FROM sys.stats st "
        "WHERE st.stats_id > 0 "
        "GROUP BY st.object_id"
        f") "
        f"SELECT TOP {top_n} "
        "s.name AS schema_name, "
        "t.name AS table_name, "
        "ISNULL(ts.usable_stats_count, 0) AS usable_stats_count, "
        "ISNULL(tr.row_count, 0) AS row_count "
        "FROM top_tables tt "
        "JOIN sys.tables t ON t.object_id = tt.object_id "
        "JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "LEFT JOIN table_stats ts ON ts.object_id = t.object_id "
        "LEFT JOIN table_rows tr ON tr.object_id = t.object_id "
        "WHERE ISNULL(ts.usable_stats_count, 0) = 0 "
        "ORDER BY row_count DESC, s.name, t.name"
    )


def statistics_histogram_query(schema_name: str, table_name: str, stat_name: str) -> str:
    """Read histogram distribution for one specific statistic (read-only)."""
    safe_schema = schema_name.replace("'", "''")
    safe_table = table_name.replace("'", "''")
    safe_stat = stat_name.replace("'", "''")
    return (
        "SELECT "
        "h.step_number, "
        "TRY_CAST(h.range_high_key AS nvarchar(256)) AS range_high_key_text, "
        "h.range_rows, "
        "h.equal_rows, "
        "h.distinct_range_rows, "
        "h.average_range_rows "
        "FROM sys.stats st "
        "CROSS APPLY sys.dm_db_stats_histogram(st.object_id, st.stats_id) h "
        "WHERE st.object_id = OBJECT_ID('"
        + safe_schema
        + "."
        + safe_table
        + "') "
        "AND st.name = '"
        + safe_stat
        + "' "
        "ORDER BY h.step_number"
    )


def duplicate_key_candidate_query(top_n: int) -> str:
    """Tables with multiple single-column non-unique indexes on the same column
    (duplicate index candidates). Scoped to user tables only."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(i.object_id) AS schema_name, "
        "OBJECT_NAME(i.object_id) AS table_name, "
        "COL_NAME(ic.object_id, ic.column_id) AS column_name, "
        "COUNT(*) AS index_count "
        "FROM sys.indexes i "
        "JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
        "WHERE i.is_unique = 0 AND i.is_hypothetical = 0 AND ic.key_ordinal = 1 "
        "AND OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1 "
        "GROUP BY i.object_id, ic.object_id, ic.column_id "
        "HAVING COUNT(*) > 1 "
        "ORDER BY index_count DESC"
    )


# ---------------------------------------------------------------------------
# analyze_db_data_model – additional checks
# ---------------------------------------------------------------------------


def tables_without_fk_query() -> str:
    """User tables that have no outgoing or incoming foreign-key relationships."""
    return (
        "SELECT s.name AS schema_name, t.name AS table_name "
        "FROM sys.tables t "
        "JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM sys.foreign_keys fk "
        "  WHERE fk.parent_object_id = t.object_id OR fk.referenced_object_id = t.object_id"
        ") "
        "ORDER BY s.name, t.name"
    )


def nullable_fk_columns_query() -> str:
    """FK columns that allow NULL, which may cause silently unresolved references."""
    return (
        "SELECT "
        "OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS parent_schema, "
        "OBJECT_NAME(fkc.parent_object_id) AS parent_table, "
        "COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS fk_column, "
        "fk.name AS fk_constraint_name "
        "FROM sys.foreign_key_columns fkc "
        "JOIN sys.foreign_keys fk ON fk.object_id = fkc.constraint_object_id "
        "JOIN sys.columns c ON c.object_id = fkc.parent_object_id AND c.column_id = fkc.parent_column_id "
        "WHERE c.is_nullable = 1 "
        "ORDER BY parent_schema, parent_table"
    )


def missing_fk_index_query() -> str:
    """FK columns that have no supporting index on the child table (lookup penalty)."""
    return (
        "SELECT "
        "OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS parent_schema, "
        "OBJECT_NAME(fkc.parent_object_id) AS parent_table, "
        "COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS fk_column, "
        "fk.name AS fk_constraint_name "
        "FROM sys.foreign_key_columns fkc "
        "JOIN sys.foreign_keys fk ON fk.object_id = fkc.constraint_object_id "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM sys.index_columns ic "
        "  WHERE ic.object_id = fkc.parent_object_id "
        "    AND ic.column_id = fkc.parent_column_id "
        "    AND ic.key_ordinal = 1"
        ") "
        "ORDER BY parent_schema, parent_table"
    )


def missing_index_dmv_query(top_n: int) -> str:
    """Top missing indexes by estimated improvement impact (SQL Server optimizer DMVs)."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(mid.object_id) AS schema_name, "
        "OBJECT_NAME(mid.object_id) AS table_name, "
        "mid.equality_columns, "
        "mid.inequality_columns, "
        "mid.included_columns, "
        "migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans) AS estimated_impact, "
        "migs.user_seeks, "
        "migs.user_scans "
        "FROM sys.dm_db_missing_index_details mid "
        "JOIN sys.dm_db_missing_index_groups mig ON mig.index_handle = mid.index_handle "
        "JOIN sys.dm_db_missing_index_group_stats migs ON migs.group_handle = mig.index_group_handle "
        "WHERE mid.database_id = DB_ID() "
        "ORDER BY estimated_impact DESC"
    )


def unused_indexes_query(top_n: int) -> str:
    """Nonclustered indexes that incur write overhead but have never been read since last restart."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(i.object_id) AS schema_name, "
        "OBJECT_NAME(i.object_id) AS table_name, "
        "i.name AS index_name, "
        "i.type_desc, "
        "ISNULL(ius.user_seeks + ius.user_scans + ius.user_lookups, 0) AS total_reads, "
        "ISNULL(ius.user_updates, 0) AS total_writes, "
        "o.create_date AS table_create_date "
        "FROM sys.indexes i "
        "JOIN sys.objects o ON o.object_id = i.object_id "
        "LEFT JOIN sys.dm_db_index_usage_stats ius "
        "  ON ius.object_id = i.object_id AND ius.index_id = i.index_id AND ius.database_id = DB_ID() "
        "WHERE i.type_desc = 'NONCLUSTERED' "
        "  AND i.is_disabled = 0 "
        "  AND OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1 "
        "  AND ISNULL(ius.user_seeks + ius.user_scans + ius.user_lookups, 0) = 0 "
        "  AND ISNULL(ius.user_updates, 0) > 10 "
        "  AND o.create_date < DATEADD(DAY, -7, GETDATE()) "
        "ORDER BY total_writes DESC, i.name"
    )


def redundant_indexes_query(top_n: int) -> str:
    """Index pairs on the same table that share the same leading key column (redundancy candidates)."""
    top_n = _validate_top_n(top_n)
    return (
        "WITH leading_keys AS ("
        "  SELECT i.object_id, i.index_id, i.name, ic.column_id "
        "  FROM sys.indexes i "
        "  JOIN sys.index_columns ic "
        "    ON ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.key_ordinal = 1 "
        "  WHERE i.type_desc = 'NONCLUSTERED' "
        "    AND i.is_disabled = 0 "
        "    AND i.is_hypothetical = 0 "
        "    AND OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1"
        ") "
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(a.object_id) AS schema_name, "
        "OBJECT_NAME(a.object_id) AS table_name, "
        "a.name AS index_a, "
        "b.name AS index_b, "
        "COL_NAME(a.object_id, a.column_id) AS shared_leading_key_column "
        "FROM leading_keys a "
        "JOIN leading_keys b "
        "  ON b.object_id = a.object_id "
        " AND b.column_id = a.column_id "
        " AND b.index_id > a.index_id "
        "ORDER BY schema_name, table_name, index_a"
    )


def datatype_inconsistency_query(top_n: int) -> str:
    """FK relationships where parent and child column base types, length, or precision differ."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "fk.name AS fk_name, "
        "OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS child_schema, "
        "OBJECT_NAME(fkc.parent_object_id) AS child_table, "
        "c_child.name AS child_column, "
        "tp_child.name AS child_type, "
        "c_child.max_length AS child_max_length, "
        "c_child.precision AS child_precision, "
        "OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS parent_schema, "
        "OBJECT_NAME(fkc.referenced_object_id) AS parent_table, "
        "c_parent.name AS parent_column, "
        "tp_parent.name AS parent_type, "
        "c_parent.max_length AS parent_max_length, "
        "c_parent.precision AS parent_precision "
        "FROM sys.foreign_key_columns fkc "
        "JOIN sys.foreign_keys fk ON fk.object_id = fkc.constraint_object_id "
        "JOIN sys.columns c_child "
        "  ON c_child.object_id = fkc.parent_object_id AND c_child.column_id = fkc.parent_column_id "
        "JOIN sys.types tp_child ON tp_child.user_type_id = c_child.user_type_id "
        "JOIN sys.columns c_parent "
        "  ON c_parent.object_id = fkc.referenced_object_id AND c_parent.column_id = fkc.referenced_column_id "
        "JOIN sys.types tp_parent ON tp_parent.user_type_id = c_parent.user_type_id "
        "WHERE tp_child.name != tp_parent.name "
        "   OR ("
        "      tp_child.name IN ('char','varchar','nchar','nvarchar','binary','varbinary') "
        "      AND tp_parent.name IN ('char','varchar','nchar','nvarchar','binary','varbinary') "
        "      AND c_child.max_length != c_parent.max_length"
        "   ) "
        "   OR ("
        "      tp_child.name IN ('decimal','numeric') "
        "      AND tp_parent.name IN ('decimal','numeric') "
        "      AND (c_child.precision != c_parent.precision OR c_child.scale != c_parent.scale)"
        "   ) "
        "ORDER BY child_schema, child_table, child_column"
    )


def soft_delete_columns_query() -> str:
    """Tables with soft-delete marker columns but no corresponding audit/history table in same schema."""
    return (
        "SELECT "
        "s.name AS schema_name, "
        "t.name AS table_name, "
        "c.name AS soft_delete_column, "
        "tp.name AS column_type "
        "FROM sys.columns c "
        "JOIN sys.tables t ON t.object_id = c.object_id "
        "JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "JOIN sys.types tp ON tp.user_type_id = c.user_type_id "
        "WHERE LOWER(c.name) IN ("
        "  N'isdeleted', N'is_deleted', N'deleted', N'deletedflag', N'deleteflag',"
        "  N'deletedat', N'deleted_at', N'isactive', N'is_active', N'activeflag', N'active_flag',"
        "  N'archived', N'isarchived', N'is_archived'"
        ") "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM sys.tables t2 "
        "  JOIN sys.schemas s2 ON s2.schema_id = t2.schema_id "
        "  WHERE s2.schema_id = s.schema_id "
        "    AND (LOWER(t2.name) LIKE LOWER(t.name) + N'%hist%' "
        "      OR LOWER(t2.name) LIKE LOWER(t.name) + N'%audit%' "
        "      OR LOWER(t2.name) LIKE LOWER(t.name) + N'%log%')"
        ") "
        "ORDER BY s.name, t.name"
    )


def update_heavy_tables_query(top_n: int) -> str:
    """Tables where writes significantly outnumber reads (update anomaly / over-normalisation risk)."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(i.object_id) AS schema_name, "
        "OBJECT_NAME(i.object_id) AS table_name, "
        "SUM(ius.user_seeks + ius.user_scans + ius.user_lookups) AS total_reads, "
        "SUM(ius.user_updates) AS total_writes, "
        "CAST(SUM(ius.user_updates) AS FLOAT) "
        "  / NULLIF(SUM(ius.user_seeks + ius.user_scans + ius.user_lookups), 0) AS write_read_ratio "
        "FROM sys.indexes i "
        "JOIN sys.dm_db_index_usage_stats ius "
        "  ON ius.object_id = i.object_id AND ius.index_id = i.index_id AND ius.database_id = DB_ID() "
        "WHERE i.index_id = 1 AND OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1 "
        "GROUP BY i.object_id "
        "HAVING SUM(ius.user_updates) > 100 "
        "  AND (SUM(ius.user_seeks + ius.user_scans + ius.user_lookups) = 0 "
        "    OR CAST(SUM(ius.user_updates) AS FLOAT) "
        "       / NULLIF(SUM(ius.user_seeks + ius.user_scans + ius.user_lookups), 0) > 5) "
        "ORDER BY write_read_ratio DESC, total_writes DESC"
    )


def normalization_column_overlap_query() -> str:
    """Child tables that copy non-key columns from their referenced parent (transitive dependency / 3NF violation)."""
    return (
        "SELECT "
        "OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS child_schema, "
        "OBJECT_NAME(fkc.parent_object_id) AS child_table, "
        "OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS parent_schema, "
        "OBJECT_NAME(fkc.referenced_object_id) AS parent_table, "
        "fk.name AS fk_constraint_name, "
        "c_child.name AS overlapping_column "
        "FROM sys.foreign_key_columns fkc "
        "JOIN sys.foreign_keys fk ON fk.object_id = fkc.constraint_object_id "
        "JOIN sys.columns c_child ON c_child.object_id = fkc.parent_object_id "
        "JOIN sys.columns c_parent "
        "  ON c_parent.object_id = fkc.referenced_object_id AND c_parent.name = c_child.name "
        "WHERE c_child.column_id != fkc.parent_column_id "
        "  AND c_parent.column_id != fkc.referenced_column_id "
        "ORDER BY child_schema, child_table, overlapping_column"
    )


# ---------------------------------------------------------------------------
# analyze_sec_config – additional checks
# ---------------------------------------------------------------------------


def server_config_flags_query() -> str:
    """Key server-level configuration flags: TRUSTWORTHY, xp_cmdshell, CLR, cross-db chaining."""
    return (
        "SELECT name, value_in_use "
        "FROM sys.configurations "
        "WHERE name IN ('xp_cmdshell','clr enabled','cross db ownership chaining','Ole Automation Procedures') "
        "ORDER BY name"
    )


def trustworthy_databases_query() -> str:
    """Databases with the TRUSTWORTHY flag enabled (potential privilege escalation vector)."""
    return (
        "SELECT name AS database_name, is_trustworthy_on "
        "FROM sys.databases "
        "WHERE is_trustworthy_on = 1 AND name NOT IN ('msdb') "
        "ORDER BY name"
    )


def guest_access_query() -> str:
    """Databases where the guest user has CONNECT permission."""
    return (
        "SELECT DB_NAME() AS database_name "
        "WHERE EXISTS ("
        "  SELECT 1 FROM sys.database_permissions dp "
        "  JOIN sys.database_principals guest ON guest.principal_id = dp.grantee_principal_id AND guest.name = 'guest' "
        "  WHERE dp.permission_name = 'CONNECT' AND dp.state_desc = 'GRANT'"
        ")"
    )


def excessive_permissions_query(top_n: int) -> str:
    """Top N principals with the most explicit database-level GRANT permissions."""
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "dp.name AS principal_name, dp.type_desc, "
        "COUNT(*) AS explicit_grant_count "
        "FROM sys.database_permissions perm "
        "JOIN sys.database_principals dp ON dp.principal_id = perm.grantee_principal_id "
        "WHERE perm.state_desc = 'GRANT' AND dp.principal_id > 4 "
        "GROUP BY dp.name, dp.type_desc "
        "ORDER BY explicit_grant_count DESC"
    )


# ---------------------------------------------------------------------------
# top_statements – query-store and DMV fallback queries
# ---------------------------------------------------------------------------


def top_statements_query_store_query(top_n: int, lookback_minutes: int) -> str:
    """Top N longest-running statements from Query Store aggregated by query_id.

    Uses Query Store runtime stats and query text for database-scoped analysis.
    """
    top_n = _validate_top_n(top_n)
    lookback_minutes = _validate_lookback_minutes(lookback_minutes)
    return (
        f"SELECT TOP {top_n} "
        "qsq.query_id, "
        "CAST(SUM(rs.avg_duration * rs.count_executions) "
        "  / NULLIF(SUM(rs.count_executions), 0) AS BIGINT) AS weighted_avg_duration_us, "
        "CAST(MAX(rs.max_duration) AS BIGINT) AS max_duration_us, "
        "SUM(rs.count_executions) AS execution_count, "
        "CAST(SUM(rs.avg_cpu_time * rs.count_executions) "
        "  / NULLIF(SUM(rs.count_executions), 0) AS FLOAT) AS weighted_avg_cpu_time_us, "
        "CAST(SUM(rs.avg_logical_io_reads * rs.count_executions) "
        "  / NULLIF(SUM(rs.count_executions), 0) AS FLOAT) AS weighted_avg_logical_reads, "
        "CAST(SUM(rs.avg_physical_io_reads * rs.count_executions) "
        "  / NULLIF(SUM(rs.count_executions), 0) AS FLOAT) AS weighted_avg_physical_reads, "
        "CAST(SUM(rs.avg_log_bytes_used * rs.count_executions) "
        "  / NULLIF(SUM(rs.count_executions), 0) AS FLOAT) AS weighted_avg_log_bytes, "
        "MAX(rsi.end_time) AS last_exec_time, "
        "LEFT(TRIM(qt.query_sql_text), 4000) AS query_sql_text, "
        "qsq.object_id AS containing_object_id, "
        "OBJECT_SCHEMA_NAME(qsq.object_id) AS containing_schema, "
        "OBJECT_NAME(qsq.object_id) AS containing_object "
        "FROM sys.query_store_query qsq "
        "JOIN sys.query_store_query_text qt "
        "  ON qsq.query_text_id = qt.query_text_id "
        "JOIN sys.query_store_plan qsp "
        "  ON qsq.query_id = qsp.query_id "
        "JOIN sys.query_store_runtime_stats rs "
        "  ON qsp.plan_id = rs.plan_id "
        "JOIN sys.query_store_runtime_stats_interval rsi "
        "  ON rs.runtime_stats_interval_id = rsi.runtime_stats_interval_id "
        "WHERE rsi.start_time >= DATEADD(minute, -{lookback_minutes}, SYSUTCDATETIME()) "
        "GROUP BY qsq.query_id, qt.query_sql_text, qsq.object_id "
        "ORDER BY weighted_avg_duration_us DESC"
    )


def top_statements_dmv_fallback_query(top_n: int) -> str:
    """Top N longest-running cached statements from plan cache DMVs.

    Used when Query Store views are unavailable (42S02 fallback).
    """
    top_n = _validate_top_n(top_n)
    return (
        f"SELECT TOP {top_n} "
        "NULL AS query_id, "
        "qs.total_elapsed_time / NULLIF(qs.execution_count, 0) AS weighted_avg_duration_us, "
        "qs.max_elapsed_time AS max_duration_us, "
        "qs.execution_count, "
        "qs.total_worker_time / NULLIF(qs.execution_count, 0) AS weighted_avg_cpu_time_us, "
        "qs.total_logical_reads / NULLIF(qs.execution_count, 0) AS weighted_avg_logical_reads, "
        "qs.total_physical_reads / NULLIF(qs.execution_count, 0) AS weighted_avg_physical_reads, "
        "0 AS weighted_avg_log_bytes, "
        "qs.last_execution_time AS last_exec_time, "
        "LEFT(TRIM(TRY_CAST(st.text AS nvarchar(max))), 4000) AS query_sql_text, "
        "NULL AS containing_object_id, "
        "NULL AS containing_schema, "
        "NULL AS containing_object "
        "FROM sys.dm_exec_query_stats qs "
        "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st "
        "WHERE qs.execution_count > 0 "
        "ORDER BY weighted_avg_duration_us DESC"
    )


def top_statements_object_pressure_query(top_n: int) -> str:
    """Top N user objects with high scan-to-seek pressure and row counts.

    Used by recommendation engine for index and partition strategy heuristics.
    """
    top_n = _validate_top_n(top_n)
    return (
        "WITH table_row_counts AS ("
        "  SELECT ps.object_id, SUM(ps.row_count) AS row_count "
        "  FROM sys.dm_db_partition_stats ps "
        "  WHERE ps.index_id IN (0, 1) "
        "  GROUP BY ps.object_id"
        "), table_usage AS ("
        "  SELECT ius.object_id, "
        "         SUM(ius.user_seeks) AS user_seeks, "
        "         SUM(ius.user_scans) AS user_scans, "
        "         SUM(ius.user_lookups) AS user_lookups, "
        "         SUM(ius.user_updates) AS user_updates "
        "  FROM sys.dm_db_index_usage_stats ius "
        "  WHERE ius.database_id = DB_ID() AND ius.index_id IN (0, 1) "
        "  GROUP BY ius.object_id"
        ") "
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(tr.object_id) AS schema_name, "
        "OBJECT_NAME(tr.object_id) AS table_name, "
        "ISNULL(tu.user_seeks, 0) AS user_seeks, "
        "ISNULL(tu.user_scans, 0) AS user_scans, "
        "ISNULL(tu.user_lookups, 0) AS user_lookups, "
        "ISNULL(tu.user_updates, 0) AS user_updates, "
        "tr.row_count, "
        "CAST(ISNULL(tu.user_scans, 0) AS FLOAT) "
        "  / NULLIF(ISNULL(tu.user_seeks, 0) + ISNULL(tu.user_scans, 0), 0) AS scan_ratio "
        "FROM table_row_counts tr "
        "LEFT JOIN table_usage tu ON tu.object_id = tr.object_id "
        "WHERE OBJECTPROPERTY(tr.object_id, 'IsUserTable') = 1 "
        "  AND tr.row_count > 0 "
        "ORDER BY scan_ratio DESC, tr.row_count DESC"
    )
