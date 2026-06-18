"""
Structured request/response logging middleware.
Logs method, path, status code, and latency for every request.
"""

import time
import uuid

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "{method} {path} → {status} ({duration}ms) | req={req_id}",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration=duration_ms,
            req_id=request_id,
        )

        response.headers["X-Request-ID"] = request_id
        return response
