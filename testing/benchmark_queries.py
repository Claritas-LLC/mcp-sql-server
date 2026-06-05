"""Benchmark all query_catalog SQL statements against US_RT_User_800."""
import sys, time, os
sys.path.insert(0, r"c:\Users\HarryValdez\OneDrive\Documents\trae\mcp-sql-server")
os.environ["PYTHONPATH"] = r"c:\Users\HarryValdez\OneDrive\Documents\trae\mcp-sql-server"

from src.models import SqlInstanceConfig
from src.db.connection_manager import ConnectionManager
from src.tools.query_catalog import (
    table_size_query, fragmented_indexes_query, missing_pk_query,
    heap_tables_query, disabled_indexes_query, stale_statistics_query,
    statistics_never_updated_query, low_sampled_statistics_query,
    missing_statistics_coverage_candidate_query, duplicate_key_candidate_query,
    missing_index_dmv_query, unused_indexes_query, redundant_indexes_query,
    update_heavy_tables_query, guest_access_query, excessive_permissions_query,
    top_statements_object_pressure_query, backup_recency_query, orphan_user_query,
    elevated_roles_query, database_statistics_settings_query,
)

INST = [SqlInstanceConfig(
    id="secondary", host="10.125.1.8", port=1433, database="master",
    auth_secret_ref="secret/sql/secondary", encrypt=False,
    trust_server_certificate=True, connect_timeout_sec=5, command_timeout_sec=120,
    pool_min=1, pool_max=5, pool_enabled=False, pool_idle_timeout_sec=300,
    pool_acquire_timeout_sec=10, enabled=True,
)]

def sr(ref):
    if ref == "secret/sql/secondary":
        return {"username": "mcp_readonly", "password": "***REMOVED***"}
    return {"username": "", "password": ""}

cm = ConnectionManager(INST, secret_resolver=sr)

queries = [
    ("1-table_size", table_size_query(50)),
    ("2-frag_indexes", fragmented_indexes_query(50)),
    ("3-missing_pk", missing_pk_query()),
    ("4-heap_tables", heap_tables_query()),
    ("5-disabled_idx", disabled_indexes_query()),
    ("6-stale_stats", stale_statistics_query(50)),
    ("7-stats_never_upd", statistics_never_updated_query(50)),
    ("8-low_sampled_stats", low_sampled_statistics_query(50)),
    ("9-missing_stats_cov", missing_statistics_coverage_candidate_query(50)),
    ("10-dup_key", duplicate_key_candidate_query(50)),
    ("11-missing_idx_dmv", missing_index_dmv_query(50)),
    ("12-unused_idx", unused_indexes_query(50)),
    ("13-redundant_idx", redundant_indexes_query(50)),
    ("14-update_heavy", update_heavy_tables_query(50)),
    ("15-guest_access", guest_access_query()),
    ("16-excessive_perm", excessive_permissions_query(50)),
    ("17-obj_pressure", top_statements_object_pressure_query(50)),
    ("18-orphan_user", orphan_user_query()),
    ("19-elevated_roles", elevated_roles_query()),
    ("20-db_stats_sett", database_statistics_settings_query()),
    ("21-backup_recency", backup_recency_query()),
]

print("%-25s %10s %10s %10s %6s" % ("Query","Best(s)","Avg(s)","Worst(s)","Rows"))
print("-" * 65)
results = []
for name, sql in queries:
    times = []
    rc = 0
    for run in range(3):
        t0 = time.perf_counter()
        r = cm.execute_catalog_query("secondary", "US_RT_User_800", sql, 50)
        t = time.perf_counter() - t0
        times.append(t)
        rc = r.get("row_count", 0)
    best = min(times)
    avg = sum(times) / len(times)
    worst = max(times)
    results.append((name, best, avg, worst, rc))
    print("%-25s %10.3f %10.3f %10.3f %6d" % (name, best, avg, worst, rc))

print("\n--- Ranked by Avg (slowest first) ---")
print("%-25s %10s %10s %10s %6s" % ("Query","Best(s)","Avg(s)","Worst(s)","Rows"))
print("-" * 65)
for name, best, avg, worst, rows in sorted(results, key=lambda r: r[2], reverse=True):
    print("%-25s %10.3f %10.3f %10.3f %6d" % (name, best, avg, worst, rows))
