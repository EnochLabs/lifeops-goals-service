"""
Per-user, per-action rate limiting via Redis.

Uses a simple fixed-window counter (1-hour window).
Fail-open on Redis outage — we never block users due to infrastructure issues.
"""

from typing import Callable

from fastapi import Depends
from loguru import logger

from app.config.redis import redis_client
from app.core.dependencies.auth import CurrentUser, get_current_user
from app.core.exceptions import RateLimitExceededError

_WINDOW_SECONDS = 3600  # 1 hour


def rate_limit(action: str, limit: int) -> Callable:
    """
    Dependency factory for per-user rate limiting.

    Usage:
        @router.post("/goals")
        async def create_goal(
            user: CurrentUser = Depends(rate_limit("create_goal", CREATE_GOAL_RATE_LIMIT)),
        ):
    """

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        key = f"goals:rate:{action}:{user.user_id}"
        try:
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, _WINDOW_SECONDS)
            if count > limit:
                raise RateLimitExceededError(
                    f"Rate limit for '{action}' exceeded ({limit}/hour). Try again later."
                )
        except RateLimitExceededError:
            raise
        except Exception as exc:
            # Fail-open: Redis unavailable should never block the user
            logger.warning(f"Rate limit check failed for {action}: {exc}")

        return user

    return _check
