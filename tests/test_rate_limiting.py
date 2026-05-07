import pytest

from src.middleware.rate_limiter import SlidingWindowRateLimiter


def test_actor_limit_enforced() -> None:
    limiter = SlidingWindowRateLimiter(actor_rpm=1, actor_burst=0, global_rpm=100, global_burst=0)
    limiter.allow("alice")
    with pytest.raises(PermissionError, match="RATE_LIMIT_EXCEEDED"):
        limiter.allow("alice")


def test_global_limit_enforced() -> None:
    limiter = SlidingWindowRateLimiter(actor_rpm=100, actor_burst=0, global_rpm=1, global_burst=0)
    limiter.allow("alice")
    with pytest.raises(PermissionError, match="RATE_LIMIT_EXCEEDED"):
        limiter.allow("bob")
