from src.security.privilege_mapper import resolve_group_privilege


def test_write_group_takes_precedence_over_read() -> None:
    level, meta = resolve_group_privilege(
        principal_groups=["group-read", "group-write"],
        read_groups=["group-read"],
        write_groups=["group-write"],
        group_authorization_enabled=True,
    )

    assert level == "write"
    assert meta["matched_write_groups"] == ["group-write"]


def test_read_group_allows_read_only() -> None:
    level, meta = resolve_group_privilege(
        principal_groups=["group-read"],
        read_groups=["group-read"],
        write_groups=["group-write"],
        group_authorization_enabled=True,
    )

    assert level == "read"
    assert meta["matched_read_groups"] == ["group-read"]


def test_no_group_denied_when_group_auth_enabled() -> None:
    level, _meta = resolve_group_privilege(
        principal_groups=["other-group"],
        read_groups=["group-read"],
        write_groups=["group-write"],
        group_authorization_enabled=True,
    )

    assert level == "none"


def test_group_authorization_disabled_grants_access() -> None:
    level, meta = resolve_group_privilege(
        principal_groups=[],
        read_groups=["group-read"],
        write_groups=["group-write"],
        group_authorization_enabled=False,
    )

    assert level == "write"
    assert meta["group_authorization_enabled"] is False
