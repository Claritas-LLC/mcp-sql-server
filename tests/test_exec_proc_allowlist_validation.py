"""
Integration tests for exec_proc tool with allowlist validation.
Tests the full flow of procedure execution with allowlist checks.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.models import RuntimePolicy
from src.middleware.write_guard import WriteGuard
from src.middleware.rate_limiter import RateLimiter
from src.security.session_manager import SessionManager
from src.middleware.audit_logger import AuditLogger


class TestExecProcAllowlistValidation:
    """Integration tests for procedure allowlist validation in exec_proc."""

    @pytest.fixture
    def policy_with_allowlist(self):
        """RuntimePolicy with procedure allowlist."""
        return RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": ["dbo.usp_RunApprovedMaintenance", "dbo.usp_RefreshMaterializedView"]
                }
            }
        )

    @pytest.fixture
    def policy_empty_allowlist(self):
        """RuntimePolicy with empty allowlist (deny all)."""
        return RuntimePolicy(
            allowed_tools={
                "db_primary_sql2019_exec_proc": {
                    "allowed_procedures": []
                }
            }
        )

    @pytest.fixture
    def policy_no_tool_config(self):
        """RuntimePolicy with no tool configuration."""
        return RuntimePolicy(allowed_tools={})

    def test_allowed_procedure_validation_passes(self, policy_with_allowlist):
        """Allowed procedure should pass validation without raising."""
        guard = WriteGuard(policy_with_allowlist)
        # Should not raise
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_RunApprovedMaintenance")

    def test_disallowed_procedure_validation_fails(self, policy_with_allowlist):
        """Disallowed procedure should fail validation."""
        guard = WriteGuard(policy_with_allowlist)
        with pytest.raises(PermissionError, match="not in the allowed procedures list"):
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_Unauthorized")

    def test_empty_allowlist_denies_all_procedures(self, policy_empty_allowlist):
        """Empty allowlist should deny all procedure executions."""
        guard = WriteGuard(policy_empty_allowlist)
        with pytest.raises(PermissionError, match="not in the allowed procedures list"):
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_AnyProc")

    def test_missing_tool_config_denies_procedure(self, policy_no_tool_config):
        """Missing tool config should deny procedure execution."""
        guard = WriteGuard(policy_no_tool_config)
        with pytest.raises(PermissionError, match="Procedure execution not configured for tool"):
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_AnyProc")

    def test_case_insensitive_procedure_matching(self, policy_with_allowlist):
        """Procedure name matching should be case-insensitive."""
        guard = WriteGuard(policy_with_allowlist)
        # All case variations should pass
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_RunApprovedMaintenance")
        guard.validate_procedure("db_primary_sql2019_exec_proc", "DBO.usp_RunApprovedMaintenance")
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.USP_RUNAPPROVEDMAINTENANCE")

    def test_schema_qualified_and_unqualified_mixing(self, policy_with_allowlist):
        """Mixing schema-qualified and unqualified names should work."""
        guard = WriteGuard(policy_with_allowlist)
        # Allowlist has dbo.usp_RunApprovedMaintenance
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_RunApprovedMaintenance")
        guard.validate_procedure("db_primary_sql2019_exec_proc", "usp_RunApprovedMaintenance")

    def test_validation_error_message_clarity(self, policy_with_allowlist):
        """Error message should clearly indicate what was denied."""
        guard = WriteGuard(policy_with_allowlist)
        with pytest.raises(PermissionError) as exc_info:
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_BadProc")
        error_msg = str(exc_info.value)
        assert "dbo.usp_BadProc" in error_msg
        assert "db_primary_sql2019_exec_proc" in error_msg
        assert "not in the allowed procedures list" in error_msg

    def test_multiple_procedures_in_allowlist(self, policy_with_allowlist):
        """All procedures in allowlist should be allowed."""
        guard = WriteGuard(policy_with_allowlist)
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_RunApprovedMaintenance")
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_RefreshMaterializedView")

    def test_partial_name_match_rejected(self, policy_with_allowlist):
        """Partial name matches should be rejected."""
        guard = WriteGuard(policy_with_allowlist)
        with pytest.raises(PermissionError):
            # Similar but not exact
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_RunApprovedMaintenance_v2")

    def test_allowlist_isolation_between_tools(self):
        """Different tools should have isolated allowlists."""
        policy = RuntimePolicy(
            allowed_tools={
                "tool_a": {"allowed_procedures": ["dbo.proc_a"]},
                "tool_b": {"allowed_procedures": ["dbo.proc_b"]},
            }
        )
        guard = WriteGuard(policy)
        # tool_a can only call proc_a
        guard.validate_procedure("tool_a", "dbo.proc_a")
        with pytest.raises(PermissionError):
            guard.validate_procedure("tool_a", "dbo.proc_b")
        # tool_b can only call proc_b
        guard.validate_procedure("tool_b", "dbo.proc_b")
        with pytest.raises(PermissionError):
            guard.validate_procedure("tool_b", "dbo.proc_a")

    def test_validation_audit_trail(self, policy_with_allowlist):
        """Validation errors should be traceable for audit purposes."""
        guard = WriteGuard(policy_with_allowlist)
        # Allowed procedure validation succeeds silently
        guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_RunApprovedMaintenance")
        # Disallowed procedure raises traceable error
        with pytest.raises(PermissionError) as exc_info:
            guard.validate_procedure("db_primary_sql2019_exec_proc", "dbo.usp_Forbidden")
        # Error should be informative for audit logs
        error_msg = str(exc_info.value)
        assert "Forbidden" in error_msg
        assert "db_primary_sql2019_exec_proc" in error_msg
