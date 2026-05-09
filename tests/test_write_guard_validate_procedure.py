"""
Unit tests for WriteGuard.validate_procedure method.
Tests procedure allowlist validation with various inputs.
"""

import pytest
from src.middleware.write_guard import WriteGuard
from src.models import RuntimePolicy


class TestWriteGuardValidateProcedure:
    """Unit tests for procedure allowlist validation."""

    def test_allowed_procedure_succeeds(self):
        """Allowed procedures should not raise an exception."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": [
                        "dbo.usp_RunApprovedMaintenance",
                        "dbo.usp_RefreshView",
                    ]
                }
            }
        )
        guard = WriteGuard(policy)
        # Should not raise
        guard.validate_procedure(
            "db_primary_sql2019_exec_proc", "dbo.usp_RunApprovedMaintenance"
        )

    def test_disallowed_procedure_raises_permission_error(self):
        """Procedures not in allowlist should raise PermissionError."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_Approved"]
                }
            }
        )
        guard = WriteGuard(policy)
        with pytest.raises(PermissionError, match="not in the allowed procedures list"):
            guard.validate_procedure(
                "db_primary_sql2019_exec_proc", "dbo.usp_Unauthorized"
            )

    def test_empty_allowlist_denies_all(self):
        """Empty procedure allowlist should deny all procedures."""
        policy = RuntimePolicy(
            allowed_tools={"db_primary_sql2019_exec_proc": {"allowed_procedures": []}}
        )
        guard = WriteGuard(policy)
        with pytest.raises(PermissionError, match="not in the allowed procedures list"):
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_AnyProc")

    def test_missing_tool_in_allowed_tools_denies(self):
        """Tool not in allowed_tools should deny execution."""
        policy = RuntimePolicy(allowed_tools={})
        guard = WriteGuard(policy)
        with pytest.raises(
            PermissionError, match="Procedure execution not configured for tool"
        ):
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_AnyProc")

    def test_case_insensitive_matching(self):
        """Procedure names should be matched case-insensitively."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_RunApprovedMaintenance"]
                }
            }
        )
        guard = WriteGuard(policy)
        # All these should succeed (case variations)
        guard.validate_procedure(
            "db_primary_sql2019_exec_proc", "dbo.USP_RUNAPPROVEDMAINTENANCE"
        )
        guard.validate_procedure(
            "db_primary_sql2019_exec_proc", "DBO.usp_RunApprovedMaintenance"
        )
        guard.validate_procedure(
            "db_primary_sql2019_exec_proc", "dbo.usp_runapprovedmaintenance"
        )

    def test_schema_qualified_names_normalized(self):
        """Schema-qualified names (e.g., dbo.usp_X) should be handled correctly."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_Approved"]
                }
            }
        )
        guard = WriteGuard(policy)
        # All should succeed
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_Approved")
        guard.validate_procedure("db_primary_sql2019_exec_proc", "DBO.usp_Approved")
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.USP_APPROVED")

    def test_unqualified_name_matches_qualified_allowlist(self):
        """Unqualified procedure name should match schema-qualified allowlist entry."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_Approved"]
                }
            }
        )
        guard = WriteGuard(policy)
        # Call with unqualified name should match allowlist entry
        guard.validate_procedure("db_primary_sql2019_exec_proc", "usp_Approved")

    def test_qualified_name_matches_unqualified_allowlist(self):
        """Schema-qualified procedure name should match unqualified allowlist entry."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {"allowed_procedures": ["usp_Approved"]}
            }
        )
        guard = WriteGuard(policy)
        # Call with qualified name should match allowlist entry
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_Approved")

    def test_multiple_schemas_allowed(self):
        """Allowlist should support procedures from multiple schemas."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_Proc1", "custom_schema.usp_Proc2"]
                }
            }
        )
        guard = WriteGuard(policy)
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_Proc1")
        guard.validate_procedure(
            "db_primary_sql2019_exec_proc", "custom_schema.usp_Proc2"
        )
        with pytest.raises(PermissionError):
            guard.validate_procedure(
                "db_primary_sql2019_exec_proc", "other_schema.usp_Proc3"
            )

    def test_similar_procedure_names_not_confused(self):
        """Similar procedure names should not be confused."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_Approved"]
                }
            }
        )
        guard = WriteGuard(policy)
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_Approved")
        with pytest.raises(PermissionError):
            guard.validate_procedure(
                "db_primary_sql2019_exec_proc", "dbo.usp_ApprovedX"
            )
        with pytest.raises(PermissionError):
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_Approve")

    def test_different_tool_has_own_allowlist(self):
        """Different tools should have independent allowlists."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_PrimaryProc"]
                },
                "db_secondary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_SecondaryProc"]
                },
            }
        )
        guard = WriteGuard(policy)
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_PrimaryProc")
        guard.validate_procedure(
            "db_secondary_sql2019_exec_proc", "dbo.usp_SecondaryProc"
        )
        with pytest.raises(PermissionError):
            guard.validate_procedure(
                "db_primary_sql2019_exec_proc", "dbo.usp_SecondaryProc"
            )
        with pytest.raises(PermissionError):
            guard.validate_procedure(
                "db_secondary_sql2019_exec_proc", "dbo.usp_PrimaryProc"
            )

    def test_error_message_includes_procedure_name(self):
        """Error message should include the procedure name for clarity."""
        policy = RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_Approved"]
                }
            }
        )
        guard = WriteGuard(policy)
        with pytest.raises(PermissionError) as exc_info:
            guard.validate_procedure(
                "db_primary_sql2019_exec_proc", "dbo.usp_Unauthorized"
            )
        assert "dbo.usp_Unauthorized" in str(exc_info.value)
        assert "db_primary_sql2019_exec_proc" in str(exc_info.value)
