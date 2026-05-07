from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Protocol


class RateLimiter(Protocol):
    def allow(self, actor: str) -> None:
        ...


class SlidingWindowRateLimiter:
    def __init__(self, actor_rpm: int, actor_burst: int, global_rpm: int, global_burst: int):
        self._actor_rpm = actor_rpm
        self._actor_burst = actor_burst
        self._global_rpm = global_rpm
        self._global_burst = global_burst
        self._actor_events: dict[str, deque[float]] = {}
        self._global_events: deque[float] = deque()
        self._lock = threading.RLock()

    @staticmethod
    def _prune(bucket: deque[float], now: float) -> None:
        cutoff = now - 60.0
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def allow(self, actor: str) -> None:
        now = time.time()
        with self._lock:
            actor_bucket = self._actor_events.setdefault(actor, deque())
            self._prune(actor_bucket, now)
            self._prune(self._global_events, now)

            if len(actor_bucket) >= self._actor_rpm + self._actor_burst:
                raise PermissionError("RATE_LIMIT_EXCEEDED: actor quota exceeded")

            if len(self._global_events) >= self._global_rpm + self._global_burst:
                raise PermissionError("RATE_LIMIT_EXCEEDED: global quota exceeded")

            actor_bucket.append(now)
            self._global_events.append(now)


class RedisSlidingWindowRateLimiter:
    """Shared rate limiter using Redis sorted sets and an atomic Lua script."""

    _LUA = """
local actor_key = KEYS[1]
local global_key = KEYS[2]

local actor_limit = tonumber(ARGV[1])
local global_limit = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local window_ms = tonumber(ARGV[4])
local member = ARGV[5]
local ttl_sec = tonumber(ARGV[6])

local cutoff = now_ms - window_ms

redis.call('ZREMRANGEBYSCORE', actor_key, 0, cutoff)
redis.call('ZREMRANGEBYSCORE', global_key, 0, cutoff)

local actor_count = redis.call('ZCARD', actor_key)
if actor_count >= actor_limit then
  return 2
end

local global_count = redis.call('ZCARD', global_key)
if global_count >= global_limit then
  return 3
end

redis.call('ZADD', actor_key, now_ms, member)
redis.call('ZADD', global_key, now_ms, member)

redis.call('EXPIRE', actor_key, ttl_sec)
redis.call('EXPIRE', global_key, ttl_sec)

return 1
"""

    def __init__(
        self,
        redis_url: str,
        actor_rpm: int,
        actor_burst: int,
        global_rpm: int,
        global_burst: int,
        namespace: str = "mcp:ratelimit",
    ):
        try:
            from redis import Redis
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Redis backend requested but redis package is not installed") from exc

        self._redis = Redis.from_url(redis_url, decode_responses=False)
        self._actor_limit = actor_rpm + actor_burst
        self._global_limit = global_rpm + global_burst
        self._namespace = namespace
        self._window_ms = 60_000
        self._ttl_sec = 120
        self._script = self._redis.register_script(self._LUA)

    def allow(self, actor: str) -> None:
        now_ms = int(time.time() * 1000)
        member = f"{now_ms}:{uuid.uuid4().hex}"
        actor_key = f"{self._namespace}:actor:{actor}"
        global_key = f"{self._namespace}:global"

        code = int(
            self._script(
                keys=[actor_key, global_key],
                args=[
                    self._actor_limit,
                    self._global_limit,
                    now_ms,
                    self._window_ms,
                    member,
                    self._ttl_sec,
                ],
            )
        )

        if code == 2:
            raise PermissionError("RATE_LIMIT_EXCEEDED: actor quota exceeded")
        if code == 3:
            raise PermissionError("RATE_LIMIT_EXCEEDED: global quota exceeded")
        if code != 1:
            raise PermissionError("RATE_LIMIT_EXCEEDED: backend returned unknown result")


def build_rate_limiter(
    *,
    backend: str,
    actor_rpm: int,
    actor_burst: int,
    global_rpm: int,
    global_burst: int,
    redis_url: str | None = None,
    redis_namespace: str = "mcp:ratelimit",
) -> RateLimiter:
    normalized = backend.strip().lower()
    if normalized == "redis":
        if not redis_url:
            raise ValueError("FASTMCP_REDIS_URL is required when FASTMCP_RATE_LIMIT_BACKEND=redis")
        return RedisSlidingWindowRateLimiter(
            redis_url=redis_url,
            actor_rpm=actor_rpm,
            actor_burst=actor_burst,
            global_rpm=global_rpm,
            global_burst=global_burst,
            namespace=redis_namespace,
        )

    return SlidingWindowRateLimiter(
        actor_rpm=actor_rpm,
        actor_burst=actor_burst,
        global_rpm=global_rpm,
        global_burst=global_burst,
    )
