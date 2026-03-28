import os
import re
import sys
import json
import time
import base64
import logging
import threading
import contextlib
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import pyodbc
from flask import Flask, jsonify, request, Response, stream_with_context

# Initialize Flask app
app = Flask(__name__)
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants for health checks
MIN_FRAGMENTATION_PERCENT = 5.0
HIGH_FRAGMENTATION_THRESHOLD = 30.0
MEDIUM_FRAGMENTATION_THRESHOLD = 10.0
MIN_ROWS_FOR_STALE_STATS_CHECK = 500
STALE_STATS_MODIFICATION_PERCENT = 0.1
HIGH_CARDINALITY_THRESHOLD = 0.8
WIDE_COLUMN_MAX_LENGTH = 255
SMALLINT_MAX_VALUE = 32767

# --- Configuration Loading ---
def _load_settings() -> Dict[str, Any]:
    settings = {
        "connections": json.loads(os.environ.get("MCP_SQLSERVER_CONNECTIONS_JSON", "{}")),
        "default_instance_id": os.environ.get("MCP_SQLSERVER_DEFAULT_INSTANCE_ID", "1"),
        "sql_version": os.environ.get("MCP_SQLSERVER_SQL_VERSION", "2019"),
        "query_timeout": int(os.environ.get("MCP_SQLSERVER_QUERY_TIMEOUT", "30")),
        "log_level": os.environ.get("MCP_SQLSERVER_LOG_LEVEL", "INFO").upper(),
    }
    _configure_logging(settings["log_level"])
    return settings

def _configure_logging(log_level: str) -> None:
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

SETTINGS = _load_settings()

# --- Helper Functions ---
def get_instance_config(instance_id: str) -> Dict[str, Any]:
    config = SETTINGS["connections"].get(instance_id)
    if not config:
        raise ValueError(f"SQL Server instance '{instance_id}' not found in configuration.")
    return config

def get_connection_string(instance_config: Dict[str, Any], db_name: Optional[str] = None) -> str:
    conn_str_parts = [
        f"DRIVER={instance_config['driver']}",
        f"SERVER={instance_config['server']}",
    ]
    if db_name:
        conn_str_parts.append(f"DATABASE={db_name}")
    if instance_config.get("port"):
        conn_str_parts.append(f"PORT={instance_config['port']}")
    if instance_config.get("username"):
        conn_str_parts.append(f"UID={instance_config['username']}")
    if instance_config.get("password"):
        conn_str_parts.append(f"PWD={instance_config['password']}")
    if instance_config.get("encrypt"):
        conn_str_parts.append(f"Encrypt={instance_config['encrypt']}")
    if instance_config.get("trust_server_certificate"):
        conn_str_parts.append(f"TrustServerCertificate={instance_config['trust_server_certificate']}")
    if instance_config.get("connection_timeout"):
        conn_str_parts.append(f"Connection Timeout={instance_config['connection_timeout']}")
    return ";".join(conn_str_parts)

@contextlib.contextmanager
def get_connection(db_name: Optional[str] = None, instance: int = 1):
    instance_id = str(instance)
    instance_config = get_instance_config(instance_id)
    conn_str = get_connection_string(instance_config, db_name)
    logging.debug(f"Attempting to connect with connection string: {conn_str}")
    conn = None
    try:
        conn = pyodbc.connect(conn_str, timeout=SETTINGS["query_timeout"])
        yield conn
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        logging.error(f"Database connection error (SQLSTATE: {sqlstate}): {ex}")
        raise
    finally:
        if conn:
            conn.close()

def _execute_query(sql: str, db_name: Optional[str] = None, instance: int = 1, params: Optional[Tuple] = None, fetchall: bool = True) -> List[Dict[str, Any]]:
    logging.debug(f"Executing SQL query:
{sql}")
    if params:
        logging.debug(f"With parameters: {params}")
    with get_connection(db_name, instance) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or ())
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                if fetchall:
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                else:
                    # For operations that don't return results, like DDL/DML
                    return []
            else:
                conn.commit()  # Commit changes for DDL/DML
                return []
        except pyodbc.Error as ex:
            sqlstate = ex.args[0]
            logging.error(f"SQL execution error (SQLSTATE: {sqlstate}): {ex}
Query:
{sql}")
            raise

def _execute_safe(sql: str, db_name: Optional[str] = None, instance: int = 1, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
    """Executes a query, fetches results, and handles common errors."""
    try:
        return _execute_query(sql, db_name, instance, params)
    except pyodbc.ProgrammingError as e:
        logging.warning(f"Caught ProgrammingError: {e}. Attempting to proceed without results.")
        return []
    except Exception as e:
        logging.error(f"An unexpected error occurred during query execution: {e}")
        raise

def _normalize_db_name(db_name: str) -> str:
    """Normalizes database name for consistent use."""
    return db_name.strip().lower()

def _escape_sql_identifier(identifier: str) -> str:
    if identifier is None:
        return ""
    # Replace ']' with ']]' to escape it within square brackets
    escaped_identifier = identifier.replace("]", "]]")
    return escaped_identifier

_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def _validate_identifier(identifier: str, type_name: str) -> None:
    if not _SQL_IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Invalid {type_name} identifier: {identifier!r}. Contains unsafe characters or is improperly formatted.")

# --- API Endpoints ---
@app.route("/ping", methods=["GET"])
def ping():
    instance = request.args.get("instance", SETTINGS["default_instance_id"])
    try:
        with get_connection(instance=int(instance)):
            return jsonify({"status": "success", "message": f"Connected to instance {instance}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/list_databases", methods=["GET"])
def list_databases():
    instance = request.args.get("instance", SETTINGS["default_instance_id"])
    sql = "SELECT name AS DatabaseName FROM sys.databases WHERE state_desc = 'ONLINE'"
    try:
        databases = _execute_safe(sql, instance=int(instance))
        return jsonify(databases)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/list_tables", methods=["GET"])
def list_tables():
    db_name = request.args.get("database_name")
    schem-name = request.args.get("schem-name", "dbo")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400
    
    _validate_identifier(db_name, "database")
    _validate_identifier(schem_name, "schema")

    sql = f"""
    SELECT
        t.name AS TableName,
        s.name AS SchemaName,
        DB_NAME() AS DatabaseName
    FROM
        [{_escape_sql_identifier(db_name)}].sys.tables t
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.schemas s ON t.schem-id = s.schem-id
    WHERE
        s.name = ?
    ORDER BY
        s.name, t.name;
    """
    try:
        tables = _execute_safe(sql, db_name=db_name, instance=int(instance), params=(schem-name,))
        return jsonify(tables)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_schema", methods=["GET"])
def get_schema():
    db_name = request.args.get("database_name")
    schem-name = request.args.get("schem-name", "dbo")
    table_name = request.args.get("table_name")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name or not table_name:
        return jsonify({"status": "error", "message": "database_name and table_name parameters are required"}), 400

    _validate_identifier(db_name, "database")
    _validate_identifier(schem_name, "schema")
    _validate_identifier(table_name, "table")

    sql = f"""
    SELECT
        c.name AS ColumnName,
        ty.name AS DataType,
        c.max_length AS MaxLength,
        c.precision AS Precision,
        c.scale AS Scale,
        c.is_nullable AS IsNullable,
        ic.is_primary_key AS IsPrimaryKey,
        cc.definition AS DefaultValue,
        obj_desc.value AS Description
    FROM
        [{_escape_sql_identifier(db_name)}].sys.columns c
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.tables t ON c.object_id = t.object_id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.schemas s ON t.schem-id = s.schem-id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.types ty ON c.user_type_id = ty.user_type_id
    LEFT JOIN
        [{_escape_sql_identifier(db_name)}].sys.index_columns ic ON ic.object_id = c.object_id AND ic.column_id = c.column_id AND ic.is_included_column = 0
    LEFT JOIN
        [{_escape_sql_identifier(db_name)}].sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id AND i.is_primary_key = 1
    LEFT JOIN
        [{_escape_sql_identifier(db_name)}].sys.default_constraints dc ON c.default_object_id = dc.object_id
    LEFT JOIN
        [{_escape_sql_identifier(db_name)}].sys.check_constraints cc ON c.object_id = cc.parent_object_id AND c.column_id = cc.parent_column_id
    OUTER APPLY
        fn_listextendedproperty (N'MS_Description', N'SCHEMA', s.name, N'TABLE', t.name, N'COLUMN', c.name) AS obj_desc
    WHERE
        s.name = ? AND t.name = ?
    ORDER BY
        c.column_id;
    """
    try:
        schema = _execute_safe(sql, db_name=db_name, instance=int(instance), params=(schem-name, table_name))
        return jsonify(schema)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/execute_query", methods=["POST"])
def execute_query():
    data = request.get_json()
    sql = data.get("sql")
    db_name = data.get("database_name")
    _validate_identifier(db_name, "database")
    instance = data.get("instance", SETTINGS["default_instance_id"])
    params = data.get("params_json")

    if not sql:
        return jsonify({"status": "error", "message": "SQL query is required"}), 400

    try:
        parsed_params = json.loads(params) if params else None
        results = _execute_safe(sql, db_name=db_name, instance=int(instance), params=parsed_params)
        return jsonify(results)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/run_query", methods=["POST"])
def run_query():
    data = request.get_json()
    sql = data.get("arg1") or data.get("sql") # Legacy support for 'arg1'
    db_name = data.get("arg2") or data.get("database_name") # Legacy support for 'arg2'
    instance = data.get("instance", SETTINGS["default_instance_id"])
    params = data.get("params_json")

    if not sql:
        return jsonify({"status": "error", "message": "SQL query is required"}), 400

    try:
        parsed_params = json.loads(params) if params else None
        results = _execute_safe(sql, db_name=db_name, instance=int(instance), params=parsed_params)
        return jsonify(results)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/list_objects", methods=["GET"])
def list_objects():
    db_name = request.args.get("database_name")
    schem-name = request.args.get("schema", "dbo")
    object_type = request.args.get("object_type", "TABLE").upper()
    instance = request.args.get("instance", SETTINGS["default_instance_id"])
    object_name_filter = request.args.get("object_name")

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400
    
    _validate_identifier(db_name, "database")

    object_type_map = {
        "TABLE": "U", "VIEW": "V", "PROCEDURE": "P", "FUNCTION": "FN",
        "INDEX": "ALL_INDEXES", # Special handling for indexes
        "TRIGGER": "TR", "SEQUENCE": "SQ", "TYPE": "TT", "DEFAULT": "D",
        "RULE": "R", "SYNONYM": "SN", "XML_SCHEMA_COLLECTION": "XSC",
        "AGGREGATE_FUNCTION": "AF", "ASSEMBLY": "A", "SERVICE_QUEUE": "SQ",
        "SERVICE_CONTRACT": "SC", "SERVICE_MESSAGE_TYPE": "SMT",
        "SERVICE_ROUTE": "SR", "REMOTE_SERVICE_BINDING": "RSB",
        "FULLTEXT_CATALOG": "FTC", "FULLTEXT_STOPLIST": "FTS",
        "PARTITION_FUNCTION": "PF", "PARTITION_SCHEME": "PS",
        "PLAN_GUIDE": "PG", "CERTIFICATE": "CERT", "ASYMMETRIC_KEY": "AK",
        "SYMMETRIC_KEY": "SK", "DATABASE_ENCRYPTION_KEY": "DEK",
        "CREDENTIAL": "CR", "MASTER_KEY": "MK", "SIGNATURE": "SIG",
        "EVENT_SESSION": "ES", "EXTENDED_STORED_PROCEDURE": "X",
        "INTERNAL_TABLE": "IT", "REPLICATION_FILTER_STORED_PROCEDURE": "RF",
        "SERVICE_BROKER_PRIORITY": "SBP", "SQL_INLINE_TABLE_VALUED_FUNCTION": "IF",
        "SQL_SCALAR_FUNCTION": "FS", "SQL_STORED_PROCEDURE": "P",
        "SQL_TABLE_VALUED_FUNCTION": "TF", "CLR_SCALAR_FUNCTION": "FN",
        "CLR_STORED_PROCEDURE": "PC", "CLR_TABLE_VALUED_FUNCTION": "FT",
        "CLR_TRIGGER": "TR", "EXTENDED_STORED_PROCEDURE_XTYPE": "X"
    }

    if object_type == "ALL_INDEXES":
        sql = f"""
        SELECT
            i.name AS ObjectName,
            s.name AS SchemaName,
            t.name AS TableName,
            'INDEX' AS ObjectType,
            i.type_desc AS IndexType,
            CASE
                WHEN i.is_primary_key = 1 THEN 'PRIMARY KEY'
                WHEN i.is_unique_constraint = 1 THEN 'UNIQUE CONSTRAINT'
                ELSE 'NON-UNIQUE'
            END AS IndexConstraintType,
            STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS KeyColumns,
            STRING_AGG(inc.name, ', ') WITHIN GROUP (ORDER BY inc.index_column_id) AS IncludedColumns
        FROM
            [{_escape_sql_identifier(db_name)}].sys.indexes i
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.tables t ON i.object_id = t.object_id
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.schemas s ON t.schem-id = s.schem-id
        LEFT JOIN
            [{_escape_sql_identifier(db_name)}].sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id AND ic.is_included_column = 0
        LEFT JOIN
            [{_escape_sql_identifier(db_name)}].sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        LEFT JOIN
            [{_escape_sql_identifier(db_name)}].sys.index_columns inc ON i.object_id = inc.object_id AND i.index_id = inc.index_id AND inc.is_included_column = 1
        LEFT JOIN
            [{_escape_sql_identifier(db_name)}].sys.columns col_inc ON inc.object_id = col_inc.object_id AND inc.column_id = col_inc.column_id
        WHERE
            i.is_hypothetical = 0 AND i.is_disabled = 0
            AND s.name = ?
            {f"AND i.name LIKE '%{object_name_filter}%'" if object_name_filter else ""}
        GROUP BY
            i.name, s.name, t.name, i.type_desc, i.is_primary_key, i.is_unique_constraint
        ORDER BY
            s.name, t.name, i.name;
        """
        params = (schem-name,)
    else:
        obj_type_code = object_type_map.get(object_type)
        if not obj_type_code:
            return jsonify({"status": "error", "message": f"Unsupported object type: {object_type}"}), 400

        sql = f"""
        SELECT
            o.name AS ObjectName,
            s.name AS SchemaName,
            DB_NAME() AS DatabaseName,
            o.type_desc AS ObjectType
        FROM
            [{_escape_sql_identifier(db_name)}].sys.objects o
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.schemas s ON o.schem-id = s.schem-id
        WHERE
            o.type = ? AND s.name = ?
            {f"AND o.name LIKE '%{object_name_filter}%'" if object_name_filter else ""}
        ORDER BY
            s.name, o.name;
        """
        params = (obj_type_code, schem-name)

    try:
        objects = _execute_safe(sql, db_name=db_name, instance=int(instance), params=params)
        return jsonify(objects)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/index_fragmentation", methods=["GET"])
def index_fragmentation():
    db_name = request.args.get("database_name")
    schema = request.args.get("schema", "dbo")
    min_fragmentation = float(request.args.get("min_fragmentation", MIN_FRAGMENTATION_PERCENT))
    min_page_count = int(request.args.get("min_page_count", "100"))
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400

    sql = f"""
    SELECT
        OBJECT_NAME(ps.object_id) AS TableName,
        si.name AS IndexName,
        sch.name AS SchemaName,
        ps.avg_fragmentation_in_percent AS FragmentationPercentage,
        ps.page_count AS PageCount
    FROM
        [{_escape_sql_identifier(db_name)}].sys.dm_db_index_physical_stats(DB_ID('{_escape_sql_identifier(db_name)}'), NULL, NULL, NULL, 'DETAILED') ps
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.indexes si ON ps.object_id = si.object_id AND ps.index_id = si.index_id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.tables st ON ps.object_id = st.object_id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.schemas sch ON st.schem-id = sch.schem-id
    WHERE
        ps.avg_fragmentation_in_percent > ?
        AND ps.page_count > ?
        AND si.name IS NOT NULL
        AND sch.name = ?
    ORDER BY
        ps.avg_fragmentation_in_percent DESC;
    """
    try:
        fragmentation_data = _execute_safe(sql, db_name=db_name, instance=int(instance), params=(min_fragmentation, min_page_count, schema))
        return jsonify(fragmentation_data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/index_health", methods=["GET"])
def index_health():
    db_name = request.args.get("database_name")
    schema = request.args.get("schema", "dbo")
    min_fragmentation = float(request.args.get("min_fragmentation", MIN_FRAGMENTATION_PERCENT))
    min_page_count = int(request.args.get("min_page_count", "100"))
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400

    sql = f"""
    WITH IndexFragmentation AS (
        SELECT
            OBJECT_SCHEMA_NAME(ps.object_id, DB_ID('{_escape_sql_identifier(db_name)}')) AS SchemaName,
            OBJECT_NAME(ps.object_id) AS TableName,
            si.name AS IndexName,
            ps.avg_fragmentation_in_percent AS FragmentationPercentage,
            ps.page_count AS PageCount,
            si.index_id,
            si.object_id
        FROM
            [{_escape_sql_identifier(db_name)}].sys.dm_db_index_physical_stats(DB_ID('{_escape_sql_identifier(db_name)}'), NULL, NULL, NULL, 'DETAILED') ps
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.indexes si ON ps.object_id = si.object_id AND ps.index_id = si.index_id
        WHERE
            ps.alloc_unit_type_desc = 'IN_ROW_DATA' -- Focus on data pages
            AND si.name IS NOT NULL
            AND ps.page_count >= ?
            AND OBJECT_SCHEMA_NAME(ps.object_id, DB_ID('{_escape_sql_identifier(db_name)}')) = ?
    ),
    MissingIndexes AS (
        SELECT
            mi.database_id,
            DB_NAME(mi.database_id) AS DatabaseName,
            OBJECT_SCHEMA_NAME(mi.object_id, mi.database_id) AS SchemaName,
            OBJECT_NAME(mi.object_id) AS TableName,
            migs.avg_total_user_cost * (migs.avg_user_impact / 100.0) AS estimated_impact,
            migs.last_user_seek,
            'CREATE INDEX IX_' + OBJECT_NAME(mi.object_id) + '_' + REPLACE(REPLACE(REPLACE(ISNULL(mid.equality_columns, '') + ISNULL(mid.inequality_columns, ''), ', ', '_'), '[', ''), ']', '')
            + ' ON [' + OBJECT_SCHEMA_NAME(mi.object_id, mi.database_id) + '].[' + OBJECT_NAME(mi.object_id) + '] (' + ISNULL(mid.equality_columns, '')
            + CASE WHEN mid.equality_columns IS NOT NULL AND mid.inequality_columns IS NOT NULL THEN ',' ELSE '' END + ISNULL(mid.inequality_columns, '') + ')'
            + ISNULL(' INCLUDE (' + mid.included_columns + ')', '') AS CreateStatement,
            mid.equality_columns,
            mid.inequality_columns,
            mid.included_columns,
            migs.user_seeks,
            migs.user_scans,
            migs.last_user_seek,
            migs.avg_user_impact,
            migs.system_seeks,
            migs.system_scans,
            migs.last_system_seek
        FROM
            [{_escape_sql_identifier(db_name)}].sys.dm_db_missing_index_groups mig
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.dm_db_missing_index_details mid ON mig.index_handle = mid.index_handle
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.dm_db_missing_index_group_stats migs ON mig.index_group_handle = migs.group_handle
        WHERE
            mi.database_id = DB_ID('{_escape_sql_identifier(db_name)}')
            AND OBJECT_SCHEMA_NAME(mi.object_id, mi.database_id) = ?
    ),
    DuplicateIndexes AS (
        SELECT
            OBJECT_SCHEMA_NAME(t.object_id, DB_ID('{_escape_sql_identifier(db_name)}')) AS SchemaName,
            OBJECT_NAME(t.object_id) AS TableName,
            i1.name AS Index1Name,
            i2.name AS Index2Name,
            'Consider dropping ' + i2.name + ' as it appears to be a duplicate or redundant of ' + i1.name AS Recommendation
        FROM
            [{_escape_sql_identifier(db_name)}].sys.tables t
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.indexes i1 ON t.object_id = i1.object_id
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.indexes i2 ON t.object_id = i2.object_id
        WHERE
            i1.index_id < i2.index_id -- Compare each pair once
            AND i1.is_disabled = 0 AND i2.is_disabled = 0
            AND i1.is_hypothetical = 0 AND i2.is_hypothetical = 0
            AND OBJECT_SCHEMA_NAME(t.object_id, DB_ID('{_escape_sql_identifier(db_name)}')) = ?
            AND EXISTS (
                SELECT 1
                FROM
                    [{_escape_sql_identifier(db_name)}].sys.index_columns ic1
                INNER JOIN
                    [{_escape_sql_identifier(db_name)}].sys.index_columns ic2 ON ic1.object_id = ic2.object_id
                                                         AND ic1.index_id = i1.index_id
                                                         AND ic2.index_id = i2.index_id
                                                         AND ic1.column_id = ic2.column_id
                                                         AND ic1.key_ordinal = ic2.key_ordinal
                                                         AND ic1.is_included_column = ic2.is_included_column
                WHERE
                    ic1.object_id = t.object_id
                GROUP BY
                    ic1.object_id
                HAVING
                    COUNT(*) = (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.index_columns WHERE object_id = t.object_id AND index_id = i1.index_id)
                    AND COUNT(*) = (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.index_columns WHERE object_id = t.object_id AND index_id = i2.index_id)
            )
    ),
    RedundantIndexes AS (
        SELECT
            OBJECT_SCHEMA_NAME(RedundantIndex.object_id, DB_ID('{_escape_sql_identifier(db_name)}')) AS SchemaName,
            OBJECT_NAME(RedundantIndex.object_id) AS TableName,
            RedundantIndex.name AS RedundantIndexName,
            CoveringIndex.name AS CoveringIndexName,
            'Consider dropping ' + RedundantIndex.name + ' as it is a subset of ' + CoveringIndex.name AS Recommendation
        FROM
            [{_escape_sql_identifier(db_name)}].sys.indexes AS RedundantIndex
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.index_columns AS ric_first ON RedundantIndex.object_id = ric_first.object_id
                                                            AND RedundantIndex.index_id = ric_first.index_id
                                                            AND ric_first.key_ordinal = 1
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.indexes AS CoveringIndex ON RedundantIndex.object_id = CoveringIndex.object_id
        WHERE
            RedundantIndex.index_id <> CoveringIndex.index_id
            AND RedundantIndex.is_disabled = 0 AND CoveringIndex.is_disabled = 0
            AND RedundantIndex.is_hypothetical = 0 AND CoveringIndex.is_hypothetical = 0
            AND RedundantIndex.type_desc <> 'HEAP' AND CoveringIndex.type_desc <> 'HEAP'
            AND RedundantIndex.is_primary_key = 0 -- Don't drop PKs
            AND OBJECT_SCHEMA_NAME(RedundantIndex.object_id, DB_ID('{_escape_sql_identifier(db_name)}')) = ?
            AND EXISTS (
                SELECT 1
                FROM [{_escape_sql_identifier(db_name)}].sys.index_columns AS cic_first
                WHERE
                    CoveringIndex.object_id = cic_first.object_id
                    AND CoveringIndex.index_id = cic_first.index_id
                    AND cic_first.key_ordinal = 1
                    AND ric_first.column_id = cic_first.column_id
            )
            AND NOT EXISTS (
                SELECT 1
                FROM [{_escape_sql_identifier(db_name)}].sys.index_columns AS ric
                WHERE
                    ric.object_id = RedundantIndex.object_id
                    AND ric.index_id = RedundantIndex.index_id
                    AND ric.is_included_column = 0 -- Only key columns
                    AND NOT EXISTS (
                        SELECT 1
                        FROM [{_escape_sql_identifier(db_name)}].sys.index_columns AS cic
                        WHERE
                            cic.object_id = CoveringIndex.object_id
                            AND cic.index_id = CoveringIndex.index_id
                            AND cic.is_included_column = 0 -- Only key columns
                            AND cic.column_id = ric.column_id
                            AND cic.key_ordinal = ric.key_ordinal
                    )
            )
            AND (
                SELECT COUNT(*)
                FROM [{_escape_sql_identifier(db_name)}].sys.index_columns AS ric
                WHERE
                    ric.object_id = RedundantIndex.object_id
                    AND ric.index_id = RedundantIndex.index_id
                    AND ric.is_included_column = 0
            ) <= (
                SELECT COUNT(*)
                FROM [{_escape_sql_identifier(db_name)}].sys.index_columns AS cic
                WHERE
                    cic.object_id = CoveringIndex.object_id
                    AND cic.index_id = CoveringIndex.index_id
                    AND cic.is_included_column = 0
            )
    )
    SELECT
        'Fragmentation' AS IssueType,
        SchemaName,
        TableName,
        IndexName AS ObjectName,
        FragmentationPercentage,
        PageCount,
        'Consider rebuilding or reorganizing index ' + IndexName + ' on ' + TableName +
        CASE
            WHEN FragmentationPercentage > ? THEN ' (High Fragmentation)'
            WHEN FragmentationPercentage > ? THEN ' (Medium Fragmentation)'
            ELSE ''
        END AS Recommendation,
        CASE
            WHEN FragmentationPercentage > ? THEN 'ALTER INDEX [' + IndexName + '] ON [' + SchemaName + '].[' + TableName + '] REBUILD;'
            WHEN FragmentationPercentage > ? THEN 'ALTER INDEX [' + IndexName + '] ON [' + SchemaName + '].[' + TableName + '] REORGANIZE;'
            ELSE NULL
        END AS Action
    FROM
        IndexFragmentation
    WHERE
        FragmentationPercentage > ?

    UNION ALL

    SELECT
        'Missing Index' AS IssueType,
        SchemaName,
        TableName,
        'N/A' AS ObjectName,
        NULL AS FragmentationPercentage,
        NULL AS PageCount,
        'Missing index with estimated impact: ' + FORMAT(estimated_impact, 'N2') + '. ' + CreateStatement AS Recommendation,
        CreateStatement AS Action
    FROM
        MissingIndexes
    ORDER BY
        estimated_impact DESC;

    UNION ALL

    SELECT
        'Duplicate Index' AS IssueType,
        SchemaName,
        TableName,
        Index2Name AS ObjectName,
        NULL AS FragmentationPercentage,
        NULL AS PageCount,
        Recommendation,
        'DROP INDEX [' + Index2Name + '] ON [' + SchemaName + '].[' + TableName + '];' AS Action
    FROM
        DuplicateIndexes

    UNION ALL

    SELECT
        'Redundant Index' AS IssueType,
        SchemaName,
        TableName,
        RedundantIndexName AS ObjectName,
        NULL AS FragmentationPercentage,
        NULL AS PageCount,
        Recommendation,
        'DROP INDEX [' + RedundantIndexName + '] ON [' + SchemaName + '].[' + TableName + '];' AS Action
    FROM
        RedundantIndexes
    ORDER BY
        SchemaName, TableName, ObjectName;
    """
    try:
        health_data = _execute_safe(
            sql,
            db_name=db_name,
            instance=int(instance),
            params=(
                min_page_count, schema,  # IndexFragmentation
                schema,  # MissingIndexes
                schema,  # DuplicateIndexes
                schema, # RedundantIndexes
                HIGH_FRAGMENTATION_THRESHOLD, MEDIUM_FRAGMENTATION_THRESHOLD, HIGH_FRAGMENTATION_THRESHOLD,
                MEDIUM_FRAGMENTATION_THRESHOLD, MIN_FRAGMENTATION_PERCENT # Fragmentation thresholds
            )
        )
        return jsonify(health_data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/table_health", methods=["GET"])
def table_health():
    db_name = request.args.get("database_name")
    schem-name = request.args.get("schema", "dbo")
    table_name = request.args.get("table_name")
    view = request.args.get("view", "standard") # summary, standard, full
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name or not table_name:
        return jsonify({"status": "error", "message": "database_name and table_name parameters are required"}), 400

    _validate_identifier(db_name, "database")
    _validate_identifier(schem-name, "schema")
    _validate_identifier(table_name, "table")

    recommendations: List[Dict[str, Any]] = []

    # --- Table Info and Row Counts ---
    table_info_sql = f"""
    SELECT
        t.name AS TableName,
        s.name AS SchemaName,
        SUM(p.rows) AS RowCounts,
        SUM(au.data_pages) * 8 / 1024.0 AS DataSpaceMB,
        SUM(au.used_pages) * 8 / 1024.0 AS UsedSpaceMB
    FROM
        [{_escape_sql_identifier(db_name)}].sys.tables t
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.schemas s ON t.schem-id = s.schem-id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.partitions p ON t.object_id = p.object_id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.allocation_units au ON (p.partition_id = au.container_id AND au.type IN (1, 3))
            OR (p.partition_id = au.owner_id AND au.type IN (2, 4))
    WHERE
        t.name = ? AND s.name = ?
    GROUP BY
        t.name, s.name;
    """
    table_info_results = _execute_safe(table_info_sql, db_name=db_name, instance=int(instance), params=(table_name, schem-name))
    table_info = table_info_results[0] if table_info_results else {}
    recommendations.append({"type": "info", "message": f"Table: {schem-name}.{table_name}", "details": table_info})

    # --- Index Fragmentation Checks ---
    frag_sql = f"""
    SELECT
        si.name AS IndexName,
        ps.avg_fragmentation_in_percent AS FragmentationPercentage,
        ps.page_count AS PageCount,
        si.type_desc AS IndexType
    FROM
        [{_escape_sql_identifier(db_name)}].sys.dm_db_index_physical_stats(DB_ID('{_escape_sql_identifier(db_name)}'), OBJECT_ID(?), NULL, NULL, 'DETAILED') ps
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.indexes si ON ps.object_id = si.object_id AND ps.index_id = si.index_id
    WHERE
        ps.alloc_unit_type_desc = 'IN_ROW_DATA' -- Focus on data pages
        AND si.name IS NOT NULL
        AND ps.page_count >= ?;
    """
    index_fragmentation = _execute_safe(frag_sql, db_name=db_name, instance=int(instance), params=(f"{schem-name}.{table_name}", MIN_PAGE_COUNT))
    for frag in index_fragmentation:
        frag_percent = frag["FragmentationPercentage"]
        index_name = _escape_sql_identifier(frag["IndexName"])
        if frag_percent > HIGH_FRAGMENTATION_THRESHOLD:
            recommendations.append({
                "type": "warning",
                "message": f"High fragmentation ({frag_percent:.2f}%) on index '{frag['IndexName']}'. Consider rebuilding.",
                "action": f"ALTER INDEX [{index_name}] ON [{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}] REBUILD;",
                "details": frag
            })
        elif frag_percent > MEDIUM_FRAGMENTATION_THRESHOLD:
            recommendations.append({
                "type": "info",
                "message": f"Medium fragmentation ({frag_percent:.2f}%) on index '{frag['IndexName']}'. Consider reorganizing.",
                "action": f"ALTER INDEX [{index_name}] ON [{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}] REORGANIZE;",
                "details": frag
            })

    # --- Stale statistics checks ---
    row_count = table_info.get("RowCounts", 0) or 0
    stats_sql = f"""
    SELECT
        sp.name AS StatisticsName,
        sp.last_update AS LastUpdate,
        sp.rows AS RowsInStats,
        sp.rows_sampled AS RowsSampled,
        sp.unfiltered_rows AS UnfilteredRows,
        sp.modification_counter AS modification_counter
    FROM
        [{_escape_sql_identifier(db_name)}].sys.stats s
    OUTER APPLY
        [{_escape_sql_identifier(db_name)}].sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
    WHERE
        s.object_id = OBJECT_ID(?) AND s.user_created = 1;
    """
    statistics_sample = _execute_safe(stats_sql, db_name=db_name, instance=int(instance), params=(f"{schem-name}.{table_name}",))

    for stat in statistics_sample:
        mod_counter = stat.get("modification_counter", 0) or 0
        stats_name = _escape_sql_identifier(stat['StatisticsName'])
        if row_count > MIN_ROWS_FOR_STALE_STATS_CHECK and mod_counter > (row_count * STALE_STATS_MODIFICATION_PERCENT):
            recommendations.append({
                "type": "warning",
                "message": f"Statistics '{stat['StatisticsName']}' are stale ({mod_counter} modifications, {row_count} total rows). Consider updating.",
                "action": f"UPDATE STATISTICS [{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}] ([{stats_name}]);",
                "details": stat
            })

    # --- Missing Index Checks ---
    missing_index_sql = f"""
    SELECT
        migs.avg_total_user_cost * (migs.avg_user_impact / 100.0) AS estimated_impact,
        migs.last_user_seek,
        mid.equality_columns,
        mid.inequality_columns,
        mid.included_columns,
        migs.user_seeks,
        migs.user_scans,
        migs.avg_user_impact,
        mig.index_group_handle
    FROM
        [{_escape_sql_identifier(db_name)}].sys.dm_db_missing_index_groups mig
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.dm_db_missing_index_details mid ON mig.index_handle = mid.index_handle
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.dm_db_missing_index_group_stats migs ON mig.index_group_handle = migs.group_handle
    WHERE
        mid.object_id = OBJECT_ID(?);
    """
    missing_indexes = _execute_safe(missing_index_sql, db_name=db_name, instance=int(instance), params=(f"{schem-name}.{table_name}",))
    for mi in missing_indexes:
        columns_str = ""
        if mi['equality_columns']:
            columns_str += mi['equality_columns']
        if mi['inequality_columns']:
            if columns_str:
                columns_str += ", "
            columns_str += mi['inequality_columns']
        
        # Escape column names for CREATE INDEX statement
        escaped_columns_for_create = ", ".join([f"[{_escape_sql_identifier(col.strip())}]" for col in columns_str.split(',')]) if columns_str else ""

        include_str = ""
        if mi['included_columns']:
            include_str = f" INCLUDE ({mi['included_columns']})"
        
        # Escape included column names for CREATE INDEX statement
        escaped_include_str = ""
        if mi['included_columns']:
            escaped_include_str = " INCLUDE (" + ", ".join([f"[{_escape_sql_identifier(col.strip())}]" for col in mi['included_columns'].split(',')]) + ")"


        impact = mi.get('avg_user_impact', 0.0) # Handle None gracefully
        recommendations.append({
            "type": "suggestion",
            "message": f"Missing index detected. Estimated improvement: {impact:.2f}%.",
            "action": f"CREATE INDEX IX_{_escape_sql_identifier(table_name)}_{'_'.join(re.findall(r'\b\w+\b', columns_str))} ON [{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}] ({escaped_columns_for_create}){escaped_include_str};",
            "details": mi
        })
    
    # --- Column cardinality and data type checks (Batched) ---
    check_cardinality_and_datatypes = True # This can be made configurable
    if check_cardinality_and_datatypes:
        columns_sql = f"""
        SELECT
            c.name AS ColumnName,
            ty.name AS DataType,
            c.max_length AS MaxLength
        FROM
            [{_escape_sql_identifier(db_name)}].sys.columns c
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.tables t ON c.object_id = t.object_id
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.schemas s ON t.schem-id = s.schem-id
        INNER JOIN
            [{_escape_sql_identifier(db_name)}].sys.types ty ON c.user_type_id = ty.user_type_id
        WHERE
            s.name = ? AND t.name = ?
        ORDER BY
            c.column_id;
        """
        columns = _execute_safe(columns_sql, db_name=db_name, instance=int(instance), params=(schem-name, table_name))

        if columns:
            cardinality_queries = []
            index_membership_queries = []
            
            for col in columns:
                col_name_escaped = _escape_sql_identifier(col['ColumnName'])
                
                # Cardinality Query for batching
                cardinality_queries.append(f"""
                    SELECT
                        '{col_name_escaped}' AS ColumnName,
                        COUNT(DISTINCT [{col_name_escaped}]) AS DistinctCount,
                        (SELECT SUM(p.rows) FROM [{_escape_sql_identifier(db_name)}].sys.tables t JOIN [{_escape_sql_identifier(db_name)}].sys.partitions p ON t.object_id = p.object_id WHERE t.name = ? AND p.index_id IN (0, 1)) AS TotalRows
                    FROM
                        [{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}];
                """)

                # Index Membership Query for batching
                index_membership_queries.append(f"""
                    SELECT
                        '{col_name_escaped}' AS ColumnName,
                        COUNT(DISTINCT i.name) AS NumIndexes
                    FROM
                        [{_escape_sql_identifier(db_name)}].sys.index_columns ic
                    INNER JOIN
                        [{_escape_sql_identifier(db_name)}].sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                    INNER JOIN
                        [{_escape_sql_identifier(db_name)}].sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                    WHERE
                        ic.object_id = OBJECT_ID(?)
                        AND c.name = ?
                        AND i.is_hypothetical = 0 AND i.is_disabled = 0;
                """)

            if cardinality_queries:
                batched_cardinality_sql = " UNION ALL ".join(cardinality_queries)
                cardinality_results = _execute_safe(batched_cardinality_sql, db_name=db_name, instance=int(instance), params=[table_name] * len(cardinality_queries))
                
                for res in cardinality_results:
                    col_name = res['ColumnName']
                    distinct_count = res['DistinctCount']
                    total_rows = res['TotalRows'] or 1 # Avoid division by zero
                    cardinality = distinct_count / total_rows if total_rows > 0 else 0

                    if cardinality > HIGH_CARDINALITY_THRESHOLD and total_rows > MIN_ROWS_FOR_STALE_STATS_CHECK:
                        recommendations.append({
                            "type": "info",
                            "message": f"Column '{col_name}' has high cardinality ({cardinality:.2f}). Consider indexing if frequently used in WHERE/JOIN clauses.",
                            "details": {"ColumnName": col_name, "Cardinality": cardinality}
                        })
            
            if index_membership_queries:
                batched_index_membership_sql = " UNION ALL ".join(index_membership_queries)
                index_membership_params = []
                for col in columns:
                    index_membership_params.append(f"{schem-name}.{table_name}")
                    index_membership_params.append(col['ColumnName'])

                index_membership_results = _execute_safe(batched_index_membership_sql, db_name=db_name, instance=int(instance), params=tuple(index_membership_params))

                for res in index_membership_results:
                    col_name = res['ColumnName']
                    num_indexes = res['NumIndexes']
                    if num_indexes == 0:
                        recommendations.append({
                            "type": "suggestion",
                            "message": f"Column '{col_name}' is not part of any index. Consider indexing if frequently used in WHERE/JOIN clauses.",
                            "action": f"CREATE INDEX IX_{_escape_sql_identifier(table_name)}_{_escape_sql_identifier(col_name)} ON [{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}] ([{_escape_sql_identifier(col_name)}]);",
                            "details": {"ColumnName": col_name, "NumIndexes": num_indexes}
                        })

            for col in columns:
                col_name = col['ColumnName']
                data_type = col['DataType']
                max_length = col['MaxLength']
                
                # Check for wide string columns
                if data_type in ['varchar', 'nvarchar'] and max_length > WIDE_COLUMN_MAX_LENGTH:
                    recommendations.append({
                        "type": "info",
                        "message": f"Column '{col_name}' is a wide {data_type} ({max_length} chars). Consider alternative data types or limiting length if possible for performance.",
                        "details": col
                    })
                
                # Check for smallint/tinyint used for boolean or limited choices
                if data_type in ['smallint', 'tinyint'] and max_length > 1 and max_length < SMALLINT_MAX_VALUE: # heuristic
                    # Further check if values are actually limited (e.g., 0/1 or a few values)
                    # This would require another query to get distinct values, which might be expensive.
                    # For now, just a general suggestion based on type.
                     recommendations.append({
                        "type": "suggestion",
                        "message": f"Column '{col_name}' is a {data_type}. If it stores only a few distinct values (e.g., boolean 0/1), consider 'bit' for storage optimization.",
                        "details": col
                    })


    # --- Foreign Key Checks (for orphaned records - simplified) ---
    fk_check_sql = f"""
    SELECT
        fk.name AS ForeignKeyName,
        OBJECT_NAME(fkc.parent_object_id) AS ReferencingTable,
        COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS ReferencingColumn,
        OBJECT_NAME(fkc.referenced_object_id) AS ReferencedTable,
        COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS ReferencedColumn
    FROM
        [{_escape_sql_identifier(db_name)}].sys.foreign_keys fk
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
    WHERE
        OBJECT_NAME(fkc.referenced_object_id) = ? AND OBJECT_SCHEMA_NAME(fkc.referenced_object_id) = ?;
    """
    referencing_fks = _execute_safe(fk_check_sql, db_name=db_name, instance=int(instance), params=(table_name, schem-name))

    for fk in referencing_fks:
        # A more thorough check would involve querying for actual orphaned records.
        # This is a placeholder to indicate the presence of FKs.
        recommendations.append({
            "type": "info",
            "message": f"Table is referenced by foreign key '{fk['ForeignKeyName']}' from '{fk['ReferencingTable']}'. Ensure referential integrity is maintained.",
            "details": fk
        })

    # Filter recommendations based on view level
    if view == "summary":
        # Only critical warnings and high-impact suggestions
        recommendations = [r for r in recommendations if r["type"] in ["error", "warning"]]
    elif view == "standard":
        # All warnings and suggestions, but perhaps less detail
        pass # currently 'standard' is default and includes everything
    elif view == "full":
        # All recommendations with full details
        pass

    return jsonify(recommendations)


@app.route("/db_stats", methods=["GET"])
def db_stats():
    db_name = request.args.get("database")
    _validate_identifier(db_name, "database")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name:
        return jsonify({"status": "error", "message": "database parameter is required"}), 400

    sql = f"""
    SELECT
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.tables) AS TableCount,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.views) AS ViewCount,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.procedures) AS StoredProcedureCount,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.functions) AS FunctionCount,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.indexes WHERE is_hypothetical = 0 AND is_disabled = 0) AS IndexCount,
        (SELECT SUM(size_on_disk_bytes) FROM [{_escape_sql_identifier(db_name)}].sys.database_files) AS TotalSizeOnDiskBytes;
    """
    try:
        stats = _execute_safe(sql, db_name=db_name, instance=int(instance))
        return jsonify(stats[0] if stats else {})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/server_info_mcp", methods=["GET"])
def server_info_mcp():
    instance = request.args.get("instance", SETTINGS["default_instance_id"])
    try:
        instance_config = get_instance_config(str(instance))
        sql_version_query = "SELECT @@VERSION AS SqlServerVersion;"
        version_info = _execute_safe(sql_version_query, instance=int(instance))

        info = {
            "mcp_service_version": "1.0.0", # Hardcoded for now
            "sql_server_version": version_info[0]["SqlServerVersion"] if version_info else "Unknown",
            "configured_instance_id": instance,
            "server_address": instance_config.get("server"),
            "database_driver": instance_config.get("driver"),
            "query_timeout_seconds": SETTINGS["query_timeout"],
            "log_level": SETTINGS["log_level"],
            "current_utc_time": datetime.now(timezone.utc).isoformat()
        }
        return jsonify(info)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/show_top_queries", methods=["GET"])
def show_top_queries():
    db_name = request.args.get("database_name")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])
    metric = request.args.get("metric", "cpu").lower() # cpu, io, execution_count, duration
    limit = int(request.args.get("limit", "10"))

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400

    order_by_clause = {
        "cpu": "total_worker_time",
        "io": "total_logical_reads + total_logical_writes",
        "execution_count": "execution_count",
        "duration": "total_elapsed_time"
    }.get(metric, "total_worker_time")

    sql = f"""
    SELECT TOP (?)
        qt.query_text_id,
        SUBSTRING(qt.query_sql_text, 1, 500) AS query_sql_text,
        q.query_id,
        q.initial_plan_handle,
        qs.creation_time,
        qs.last_execution_time,
        qs.execution_count,
        qs.total_worker_time / 1000 AS total_cpu_time_ms,
        qs.total_elapsed_time / 1000 AS total_duration_ms,
        qs.total_logical_reads,
        qs.total_logical_writes,
        qs.total_physical_reads,
        q.object_id,
        OBJECT_SCHEMA_NAME(q.object_id, DB_ID('{_escape_sql_identifier(db_name)}')) AS SchemaName,
        OBJECT_NAME(q.object_id) AS ObjectName,
        q.is_function,
        q.is_proc,
        q.is_trigger,
        q.is_plan_forcing_enabled,
        q.force_failure_count,
        q.last_force_failure_reason
    FROM
        [{_escape_sql_identifier(db_name)}].sys.query_store_query_text qt
    JOIN
        [{_escape_sql_identifier(db_name)}].sys.query_store_query q ON qt.query_text_id = q.query_text_id
    JOIN
        [{_escape_sql_identifier(db_name)}].sys.query_store_plan p ON q.query_id = p.query_id
    JOIN
        [{_escape_sql_identifier(db_name)}].sys.query_store_runtime_stats qs ON p.plan_id = qs.plan_id
    WHERE
        q.object_id IS NOT NULL -- Only include queries associated with objects
    ORDER BY
        {order_by_clause} DESC;
    """
    # Note: Query Store might not be enabled by default. Fallback to dm_exec_query_stats if QS is empty.
    dm_exec_sql = f"""
    SELECT TOP (?)
        SUBSTRING(st.text, (qs.statement_start_offset / 2) + 1,
            ((CASE qs.statement_end_offset
                WHEN -1 THEN DATALENGTH(st.text)
                ELSE qs.statement_end_offset
            END - qs.statement_start_offset) / 2) + 1) AS query_sql_text,
        qs.execution_count,
        qs.total_worker_time / 1000 AS total_cpu_time_ms,
        qs.total_elapsed_time / 1000 AS total_duration_ms,
        qs.total_logical_reads,
        qs.total_logical_writes,
        qs.total_physical_reads,
        qs.creation_time,
        qs.last_execution_time,
        DB_NAME(st.dbid) AS DatabaseName,
        OBJECT_SCHEMA_NAME(st.objectid, st.dbid) AS SchemaName,
        OBJECT_NAME(st.objectid) AS ObjectName
    FROM
        sys.dm_exec_query_stats qs
    CROSS APPLY
        sys.dm_exec_sql_text(qs.sql_handle) st
    WHERE
        st.dbid = DB_ID('{_escape_sql_identifier(db_name)}')
    ORDER BY
        {order_by_clause} DESC;
    """
    try:
        queries = _execute_safe(sql, db_name=db_name, instance=int(instance), params=(limit,))
        if not queries: # Fallback if Query Store is not enabled or empty
            logging.info(f"Query Store returned no results for {db_name}. Falling back to dm_exec_query_stats.")
            queries = _execute_safe(dm_exec_sql, db_name=db_name, instance=int(instance), params=(limit,))

        return jsonify(queries)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/check_fragmentation", methods=["GET"])
def check_fragmentation():
    db_name = request.args.get("database_name")
    schem-name = request.args.get("schem-name", "dbo")
    table_name = request.args.get("table_name")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400

    object_id_clause = f"OBJECT_ID('[{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}]')" if table_name else "NULL"

    sql = f"""
    SELECT
        OBJECT_NAME(ps.object_id) AS TableName,
        si.name AS IndexName,
        sch.name AS SchemaName,
        ps.avg_fragmentation_in_percent AS FragmentationPercentage,
        ps.page_count AS PageCount
    FROM
        [{_escape_sql_identifier(db_name)}].sys.dm_db_index_physical_stats(DB_ID('{_escape_sql_identifier(db_name)}'), {object_id_clause}, NULL, NULL, 'DETAILED') ps
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.indexes si ON ps.object_id = si.object_id AND ps.index_id = si.index_id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.tables st ON ps.object_id = st.object_id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.schemas sch ON st.schem-id = sch.schem-id
    WHERE
        ps.alloc_unit_type_desc = 'IN_ROW_DATA' -- Focus on data pages
        AND si.name IS NOT NULL
        AND sch.name = ?
        AND ps.avg_fragmentation_in_percent > {MIN_FRAGMENTATION_PERCENT} -- Only show significant fragmentation
        AND ps.page_count > 8 -- Ignore very small indexes
    ORDER BY
        ps.avg_fragmentation_in_percent DESC;
    """
    try:
        fragmentation_data = _execute_safe(sql, db_name=db_name, instance=int(instance), params=(schem-name,))
        return jsonify(fragmentation_data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/db_sec_perf_metrics", methods=["GET"])
def db_sec_perf_metrics():
    db_name = request.args.get("database_name")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400

    sql = f"""
    SELECT
        DB_NAME() AS DatabaseName,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.database_principals WHERE type = 'S') AS SqlUserCount,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.database_principals WHERE type = 'U') AS WindowsUserCount,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.database_role_members) AS RoleMemberCount,
        (SELECT SUM(size * 8 / 1024) FROM [{_escape_sql_identifier(db_name)}].sys.database_files WHERE type_desc = 'ROWS') AS DataFileSizeMB,
        (SELECT SUM(size * 8 / 1024) FROM [{_escape_sql_identifier(db_name)}].sys.database_files WHERE type_desc = 'LOG') AS LogFileSizeMB,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.dm_exec_query_stats) AS CachedQueryPlanCount,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.dm_db_missing_index_details) AS MissingIndexCount;
    """
    try:
        metrics = _execute_safe(sql, db_name=db_name, instance=int(instance))
        return jsonify(metrics[0] if metrics else {})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/explain_query", methods=["POST"])
def explain_query():
    data = request.get_json()
    sql = data.get("sql")
    db_name = data.get("database_name")
    _validate_identifier(db_name, "database")
    instance = data.get("instance", SETTINGS["default_instance_id"])

    _validate_identifier(db_name, "database")

    if not sql:
        return jsonify({"status": "error", "message": "SQL query is required"}), 400

    try:
        # Prepend SET SHOWPLAN_ALL ON to the query
        explain_sql = f"SET SHOWPLAN_ALL ON;
{sql}"
        results = _execute_safe(explain_sql, db_name=db_name, instance=int(instance))
        return jsonify(results)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/analyze_logical_data_model", methods=["GET"])
def analyze_logical_data_model():
    db_name = request.args.get("database_name")
    schema = request.args.get("schema", "dbo")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])
    view = request.args.get("view", "standard") # summary, standard, full

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400

    _validate_identifier(db_name, "database")
    _validate_identifier(schema, "schema")

    # This is a placeholder for a complex data model analysis.
    # A real implementation would involve checking for:
    # - Tables without Primary Keys
    # - Tables without Foreign Keys (potential isolated islands)
    # - Naming convention inconsistencies
    # - Data type consistency across related columns
    # - Overly wide tables
    # - Tables with no indexes
    # - Circular relationships (if graph analysis is done)

    # For now, let's just return some basic structural info
    sql = f"""
    SELECT
        t.name AS TableName,
        s.name AS SchemaName,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.columns c WHERE c.object_id = t.object_id) AS ColumnCount,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.indexes i WHERE i.object_id = t.object_id AND i.is_primary_key = 1) AS HasPrimaryKey,
        (SELECT COUNT(*) FROM [{_escape_sql_identifier(db_name)}].sys.foreign_keys fk WHERE fk.parent_object_id = t.object_id OR fk.referenced_object_id = t.object_id) AS ForeignKeyCount
    FROM
        [{_escape_sql_identifier(db_name)}].sys.tables t
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.schemas s ON t.schem-id = s.schem-id
    WHERE
        s.name = ?
    ORDER BY
        s.name, t.name;
    """
    try:
        analysis_results = _execute_safe(sql, db_name=db_name, instance=int(instance), params=(schema,))
        recommendations = []

        for table in analysis_results:
            table_name = table["TableName"]
            schem-name = table["SchemaName"]
            if not table["HasPrimaryKey"]:
                recommendations.append({
                    "type": "warning",
                    "message": f"Table '{schem-name}.{table_name}' has no Primary Key. Consider adding one for data integrity and performance.",
                    "action": f"ALTER TABLE [{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}] ADD PRIMARY KEY (ColumnName);"
                })
            if not table["ForeignKeyCount"] and view == "full": # Only suggest for full view
                recommendations.append({
                    "type": "info",
                    "message": f"Table '{schem-name}.{table_name}' has no Foreign Keys. Ensure it's not an isolated table if relationships are expected.",
                    "details": "Lack of foreign keys can lead to data inconsistency."
                })
        
        # Combine basic info and recommendations
        final_result = {"tables_overview": analysis_results, "recommendations": recommendations}

        return jsonify(final_result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/open_logical_model", methods=["GET"])
def open_logical_model():
    db_name = request.args.get("database_name")
    schema = request.args.get("schema", "dbo")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name:
        return jsonify({"status": "error", "message": "database_name parameter is required"}), 400

    _validate_identifier(db_name, "database")
    _validate_identifier(schema, "schema")

    # This endpoint would typically generate an HTML representation of the ERD.
    # For a placeholder, we'll return a simple HTML structure.
    # A real implementation would use a library like `SchemaCrawler` or custom logic
    # to query metadata and build a graph, then render it using `mermaid.js` or `d3.js`.

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Logical Data Model for {db_name}.{schema}</title>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.js';
            mermaid.initialize({{ startOnLoad: true }});
        </script>
        <style>
            body {{ font-family: sans-serif; }}
            .mermaid {{ margin: 20px; }}
        </style>
    </head>
    <body>
        <h1>Logical Data Model for {db_name}.{schema}</h1>
        <p>This is a simplified representation. A full ERD would be dynamically generated.</p>
        <div class="mermaid">
            graph TD
                A[Table A] --> B(Table B);
                B --> C{Table C};
                C -- has a --> A;
                D[Another Table]
        </div>
        <p><i>Note: Actual model generation requires querying detailed schema and relationships.</i></p>
    </body>
    </html>
    """
    return Response(html_content, mimetype="text/html")

@app.route("/generate_ddl", methods=["GET"])
def generate_ddl():
    db_name = request.args.get("database_name")
    schem-name = request.args.get("schem-name", "dbo")
    table_name = request.args.get("table_name")
    instance = request.args.get("instance", SETTINGS["default_instance_id"])

    if not db_name or not table_name:
        return jsonify({"status": "error", "message": "database_name and table_name parameters are required"}), 400

    # This is a simplified DDL generation. A robust solution would use SQL Server's
    # built-in `sp_helptext` or query `sys.columns`, `sys.tables`, `sys.types`,
    # `sys.indexes`, `sys.foreign_keys`, etc., to reconstruct the full DDL.
    # For now, we'll construct a basic CREATE TABLE statement.

    columns_sql = f"""
    SELECT
        c.name AS ColumnName,
        ty.name AS DataType,
        c.max_length AS MaxLength,
        c.precision AS Precision,
        c.scale AS Scale,
        c.is_nullable AS IsNullable,
        ic.is_primary_key AS IsPrimaryKey,
        cc.definition AS DefaultValue
    FROM
        [{_escape_sql_identifier(db_name)}].sys.columns c
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.tables t ON c.object_id = t.object_id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.schemas s ON t.schem-id = s.schem-id
    INNER JOIN
        [{_escape_sql_identifier(db_name)}].sys.types ty ON c.user_type_id = ty.user_type_id
    LEFT JOIN
        [{_escape_sql_identifier(db_name)}].sys.index_columns ic ON ic.object_id = c.object_id AND ic.column_id = c.column_id AND ic.is_included_column = 0
    LEFT JOIN
        [{_escape_sql_identifier(db_name)}].sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id AND i.is_primary_key = 1
    LEFT JOIN
        [{_escape_sql_identifier(db_name)}].sys.default_constraints dc ON c.default_object_id = dc.object_id
    LEFT JOIN
        [{_escape_sql_identifier(db_name)}].sys.check_constraints cc ON c.object_id = cc.parent_object_id AND c.column_id = cc.parent_column_id
    WHERE
        s.name = ? AND t.name = ?
    ORDER BY
        c.column_id;
    """
    try:
        columns_data = _execute_safe(columns_sql, db_name=db_name, instance=int(instance), params=(schem-name, table_name))

        if not columns_data:
            return jsonify({"status": "error", "message": f"Table '{schem-name}.{table_name}' not found or has no columns."}), 404

        ddl_statements = [f"CREATE TABLE [{_escape_sql_identifier(schem-name)}].[{_escape_sql_identifier(table_name)}] ("]
        pk_columns = []

        for col in columns_data:
            col_name = _escape_sql_identifier(col['ColumnName'])
            data_type = col['DataType']
            max_length = col['MaxLength']
            precision = col['Precision']
            scale = col['Scale']
            is_nullable = "NULL" if col['IsNullable'] else "NOT NULL"
            default_value = f"DEFAULT {col['DefaultValue']}" if col['DefaultValue'] else ""

            type_def = data_type
            if data_type in ["varchar", "nvarchar", "varbinary"]:
                type_def += f"({max_length if max_length != -1 else 'MAX'})"
            elif data_type in ["char", "nchar", "binary"]:
                type_def += f"({max_length})"
            elif data_type in ["decimal", "numeric"]:
                type_def += f"({precision},{scale})"

            ddl_statements.append(f"    [{col_name}] {type_def} {default_value} {is_nullable},")

            if col['IsPrimaryKey']:
                pk_columns.append(f"[{col_name}]")

        # Remove trailing comma from the last column definition
        if ddl_statements:
            ddl_statements[-1] = ddl_statements[-1].rstrip(',')

        if pk_columns:
            ddl_statements.append(f"    PRIMARY KEY ({', '.join(pk_columns)})")

        ddl_statements.append(");")

        return jsonify({"ddl": "
".join(ddl_statements)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- DDL/DML Operations (Requires write_mode_enabled) ---
@app.route("/create_db_user", methods=["POST"])
def create_db_user():
    data = request.get_json()
    db_name = data.get("database_name")
    username = data.get("username")
    password = data.get("password")
    instance = data.get("instance", SETTINGS["default_instance_id"])

    if not db_name or not username or not password:
        return jsonify({"status": "error", "message": "database_name, username, and password parameters are required"}), 400

    # Basic validation for username to prevent SQL injection
    if not re.match(r"^[A-Za-z0-9_]+$", username):
        return jsonify({"status": "error", "message": "Invalid username format. Only alphanumeric and underscore allowed."}), 400

    # Important: This creates a login AND a user. For a more secure approach,
    # consider creating the login separately with more robust password policies,
    # and then mapping the login to a user in the specific database.
    # This also assumes sysadmin or db_owner privileges for the connection.
    sql_login = f"CREATE LOGIN [{username}] WITH PASSWORD = '{password}', CHECK_POLICY = ON;"
    sql_user = f"CREATE USER [{username}] FOR LOGIN [{username}];"
    sql_grant = f"ALTER ROLE db_datareader ADD MEMBER [{username}]; ALTER ROLE db_datawriter ADD MEMBER [{username}];"

    try:
        _execute_query(sql_login, instance=int(instance), fetchall=False)
        _execute_query(sql_user, db_name=db_name, instance=int(instance), fetchall=False)
        _execute_query(sql_grant, db_name=db_name, instance=int(instance), fetchall=False)
        return jsonify({"status": "success", "message": f"User '{username}' created and granted data reader/writer in '{db_name}'."})
    except pyodbc.ProgrammingError as e:
        # Handle cases where login/user already exists or permission issues
        return jsonify({"status": "error", "message": f"Failed to create user: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/drop_db_user", methods=["POST"])
def drop_db_user():
    data = request.get_json()
    db_name = data.get("database_name")
    username = data.get("username")
    instance = data.get("instance", SETTINGS["default_instance_id"])

    if not db_name or not username:
        return jsonify({"status": "error", "message": "database_name and username parameters are required"}), 400

    if not re.match(r"^[A-Za-z0-9_]+$", username):
        return jsonify({"status": "error", "message": "Invalid username format."}), 400

    # Drop user from database first, then drop login from server
    sql_drop_user = f"DROP USER [{username}];"
    sql_drop_login = f"DROP LOGIN [{username}];"

    try:
        _execute_query(sql_drop_user, db_name=db_name, instance=int(instance), fetchall=False)
        _execute_query(sql_drop_login, instance=int(instance), fetchall=False)
        return jsonify({"status": "success", "message": f"User '{username}' and associated login dropped."})
    except pyodbc.ProgrammingError as e:
        return jsonify({"status": "error", "message": f"Failed to drop user: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/kill_session", methods=["POST"])
def kill_session():
    data = request.get_json()
    session_id = data.get("session_id")
    _validate_identifier(str(session_id), "session ID")
    instance = data.get("instance", SETTINGS["default_instance_id"])

    if not session_id:
        return jsonify({"status": "error", "message": "session_id parameter is required"}), 400

    try:
        session_id = int(session_id)
        sql = f"KILL {session_id};"
        _execute_query(sql, instance=int(instance), fetchall=False)
        return jsonify({"status": "success", "message": f"Session ID {session_id} killed."})
    except ValueError:
        return jsonify({"status": "error", "message": "session_id must be an integer"}), 400
    except pyodbc.ProgrammingError as e:
        return jsonify({"status": "error", "message": f"Failed to kill session: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/create_object", methods=["POST"])
def create_object():
    data = request.get_json()
    sql = data.get("sql")
    db_name = data.get("database_name")
    instance = data.get("instance", SETTINGS["default_instance_id"])

    if not sql:
        return jsonify({"status": "error", "message": "SQL statement is required"}), 400
    if not sql.strip().upper().startswith("CREATE"):
        return jsonify({"status": "error", "message": "Only CREATE statements are allowed for this endpoint."}), 400

    try:
        _execute_query(sql, db_name=db_name, instance=int(instance), fetchall=False)
        return jsonify({"status": "success", "message": "Object created successfully."})
    except pyodbc.ProgrammingError as e:
        return jsonify({"status": "error", "message": f"Failed to create object: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/alter_object", methods=["POST"])
def alter_object():
    data = request.get_json()
    sql = data.get("sql")
    db_name = data.get("database_name")
    instance = data.get("instance", SETTINGS["default_instance_id"])

    if not sql:
        return jsonify({"status": "error", "message": "SQL statement is required"}), 400
    if not sql.strip().upper().startswith("ALTER"):
        return jsonify({"status": "error", "message": "Only ALTER statements are allowed for this endpoint."}), 400

    try:
        _execute_query(sql, db_name=db_name, instance=int(instance), fetchall=False)
        return jsonify({"status": "success", "message": "Object altered successfully."})
    except pyodbc.ProgrammingError as e:
        return jsonify({"status": "error", "message": f"Failed to alter object: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/drop_object", methods=["POST"])
def drop_object():
    data = request.get_json()
    sql = data.get("sql")
    db_name = data.get("database_name")
    instance = data.get("instance", SETTINGS["default_instance_id"])

    if not sql:
        return jsonify({"status": "error", "message": "SQL statement is required"}), 400
    if not sql.strip().upper().startswith("DROP"):
        return jsonify({"status": "error", "message": "Only DROP statements are allowed for this endpoint."}), 400

    try:
        _execute_query(sql, db_name=db_name, instance=int(instance), fetchall=False)
        return jsonify({"status": "success", "message": "Object dropped successfully."})
    except pyodbc.ProgrammingError as e:
        return jsonify({"status": "error", "message": f"Failed to drop object: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Main Entry Point ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
