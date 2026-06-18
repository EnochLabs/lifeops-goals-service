"""
Global IP-level rate limiting middleware (sliding window, per minute).
Per-user, per-action limits are handled separately in core/dependencies/rate_limit.py.
"""

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config.redis import redis_client
from app.config.settings import settings

_WINDOW_SECONDS = 60


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting on health checks
        if request.url.path in ("/health", "/health/live", "/health/ready"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        key = f"goals:global_rate:{ip}"

        try:
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, _WINDOW_SECONDS)

            if count > settings.GLOBAL_RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please slow down."},
                )
        except Exception as exc:
            # Fail-open: never block on Redis unavailability
            logger.warning(f"Global rate limit Redis error: {exc}")

        return await call_next(request)
