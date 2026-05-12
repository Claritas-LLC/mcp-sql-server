import json

from src.middleware.audit_logger import AuditLogger


def test_audit_logger_writes_auth_context_fields(tmp_path) -> None:
    audit_path = tmp_path / "audit.log"
    logger = AuditLogger(str(audit_path))

    logger.log_event(
        request_id="req-1",
        actor="user@example.com",
        tool="db_primary_sql2019_select",
        instance="primary",
        sql="SELECT 1",
        decision="allow",
        latency_ms=12,
        rows=1,
        error_code=None,
        auth_mode="azure_token_verifier",
        auth_subject="user@example.com",
        privilege_level="read",
        group_match_result={
            "group_authorization_enabled": True,
            "matched_read_groups": ["group-read"],
            "matched_write_groups": [],
        },
    )

    payload = json.loads(audit_path.read_text(encoding="utf-8").strip())

    assert payload["auth_mode"] == "azure_token_verifier"
    assert payload["auth_subject"] == "user@example.com"
    assert payload["privilege_level"] == "read"
    assert payload["group_match_result"]["matched_read_groups"] == ["group-read"]
