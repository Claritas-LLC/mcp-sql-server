from __future__ import annotations

from pydantic import BaseModel, Field


class SqlInstanceConfig(BaseModel):
    id: str = Field(..., pattern="^(primary|secondary)$")
    host: str
    port: int = 1433
    database: str
    auth_secret_ref: str
    encrypt: bool = True
    trust_server_certificate: bool = False
    connect_timeout_sec: int = 5
    command_timeout_sec: int = 30
    pool_min: int = 2
    pool_max: int = 20
    enabled: bool = True


class RuntimePolicy(BaseModel):
    write_mode_default: str = Field(default="deny", pattern="^(allow|deny)$")
    allowed_write_tools: list[str] = Field(default_factory=list)
    blocked_sql_patterns: list[str] = Field(default_factory=list)
    max_result_rows: int = 5000
    max_query_duration_ms: int = 15000
    instance_enable_flags: dict[str, bool] = Field(default_factory=dict)
    tool_enable_flags: dict[str, bool] = Field(default_factory=dict)
    instance_tool_enable_flags: dict[str, dict[str, bool]] = Field(default_factory=dict)


class RateLimitSection(BaseModel):
    requests_per_minute: int
    burst: int


class SessionLimits(BaseModel):
    concurrent_sessions_limit: int = 10
    session_ttl_minutes: int = 60
    inactivity_timeout_minutes: int = 15


class RateLimitConfig(BaseModel):
    global_: RateLimitSection = Field(alias="global")
    actor: RateLimitSection
    session: SessionLimits
