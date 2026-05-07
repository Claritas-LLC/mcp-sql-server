import pytest

from src.middleware.rate_limiter import SlidingWindowRateLimiter, build_rate_limiter


def test_build_rate_limiter_local_backend() -> None:
    limiter = build_rate_limiter(
        backend="local",
        actor_rpm=10,
        actor_burst=2,
        global_rpm=100,
        global_burst=10,
    )
    assert isinstance(limiter, SlidingWindowRateLimiter)


def test_build_rate_limiter_redis_requires_url() -> None:
    with pytest.raises(ValueError, match="FASTMCP_REDIS_URL"):
        build_rate_limiter(
            backend="redis",
            actor_rpm=10,
            actor_burst=2,
            global_rpm=100,
            global_burst=10,
            redis_url=None,
        )
