from __future__ import annotations


def table_size_query(top_n: int) -> str:
    return (
        f"SELECT TOP {top_n} s.name AS schema_name, t.name AS table_name, "
        "SUM(p.rows) AS row_count, "
        "CAST(SUM(a.total_pages) * 8.0 / 1024 AS DECIMAL(18,2)) AS total_space_mb "
        "FROM sys.tables t "
        "JOIN sys.schemas s ON t.schema_id = s.schema_id "
        "JOIN sys.indexes i ON t.object_id = i.object_id "
        "JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id "
        "JOIN sys.allocation_units a ON p.partition_id = a.container_id "
        "GROUP BY s.name, t.name "
        "ORDER BY total_space_mb DESC"
    )


def fragmented_indexes_query(top_n: int) -> str:
    return (
        f"SELECT TOP {top_n} OBJECT_SCHEMA_NAME(ps.object_id) AS schema_name, "
        "OBJECT_NAME(ps.object_id) AS table_name, i.name AS index_name, "
        "ps.avg_fragmentation_in_percent, ps.page_count "
        "FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ps "
        "JOIN sys.indexes i ON ps.object_id = i.object_id AND ps.index_id = i.index_id "
        "WHERE ps.index_id > 0 AND ps.page_count >= 100 "
        "ORDER BY ps.avg_fragmentation_in_percent DESC"
    )


def missing_pk_query() -> str:
    return (
        "SELECT s.name AS schema_name, t.name AS table_name "
        "FROM sys.tables t "
        "JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "LEFT JOIN sys.key_constraints k ON k.parent_object_id = t.object_id AND k.type = 'PK' "
        "WHERE k.object_id IS NULL "
        "ORDER BY s.name, t.name"
    )


def fk_graph_query() -> str:
    return (
        "SELECT fk.name AS fk_name, "
        "OBJECT_SCHEMA_NAME(fk.parent_object_id) AS parent_schema, "
        "OBJECT_NAME(fk.parent_object_id) AS parent_table, "
        "OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS referenced_schema, "
        "OBJECT_NAME(fk.referenced_object_id) AS referenced_table "
        "FROM sys.foreign_keys fk"
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
        "SELECT d.name AS database_name, MAX(b.backup_finish_date) AS last_backup_finish_date "
        "FROM master.sys.databases d "
        "LEFT JOIN msdb.dbo.backupset b ON b.database_name = d.name AND b.type = 'D' "
        "GROUP BY d.name"
    )


def active_sessions_query(top_n: int) -> str:
    return (
        f"SELECT TOP {top_n} s.session_id, s.login_name, s.host_name, s.program_name, s.status, "
        "r.command, r.wait_type, r.wait_time, r.cpu_time, r.blocking_session_id "
        "FROM sys.dm_exec_sessions s "
        "LEFT JOIN sys.dm_exec_requests r ON s.session_id = r.session_id "
        "WHERE s.is_user_process = 1 "
        "ORDER BY r.wait_time DESC, s.session_id"
    )


def lock_chain_query(top_n: int) -> str:
    return (
        f"SELECT TOP {top_n} wt.session_id, wt.blocking_session_id, wt.wait_type, wt.wait_duration_ms "
        "FROM sys.dm_os_waiting_tasks wt "
        "WHERE wt.blocking_session_id IS NOT NULL "
        "ORDER BY wt.wait_duration_ms DESC"
    )


# ---------------------------------------------------------------------------
# analyze_tab_health – additional checks
# ---------------------------------------------------------------------------


def heap_tables_query() -> str:
    """Tables with no clustered index (heap storage)."""
    return (
        "SELECT s.name AS schema_name, t.name AS table_name, p.rows AS row_count "
        "FROM sys.tables t "
        "JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id = 0 "
        "WHERE p.rows > 0 "
        "ORDER BY p.rows DESC"
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
    """Top N tables/indexes with the most out-of-date statistics."""
    return (
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
        "ORDER BY sp.modification_counter DESC, sp.last_updated ASC"
    )


def duplicate_key_candidate_query(top_n: int) -> str:
    """Tables with multiple single-column non-unique indexes on the same column
    (duplicate index candidates)."""
    return (
        f"SELECT TOP {top_n} "
        "OBJECT_SCHEMA_NAME(i.object_id) AS schema_name, "
        "OBJECT_NAME(i.object_id) AS table_name, "
        "COL_NAME(ic.object_id, ic.column_id) AS column_name, "
        "COUNT(*) AS index_count "
        "FROM sys.indexes i "
        "JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
        "WHERE i.is_unique = 0 AND ic.key_ordinal = 1 "
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
        "SELECT d.name AS database_name "
        "FROM sys.databases d "
        "WHERE d.state_desc = 'ONLINE' "
        "AND EXISTS ("
        "  SELECT 1 FROM sys.database_permissions dp "
        "  JOIN sys.database_principals guest ON guest.principal_id = dp.grantee_principal_id AND guest.name = 'guest' "
        "  WHERE dp.permission_name = 'CONNECT' AND dp.state_desc = 'GRANT'"
        ") "
        "ORDER BY d.name"
    )


def excessive_permissions_query(top_n: int) -> str:
    """Top N principals with the most explicit database-level GRANT permissions."""
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
