"""Security headers middleware — adds X-Request-ID, timing, and hardening headers."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("gsdm_r.request")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security and observability headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate unique request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Track timing
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Structured request log
        logger.info(
            "%s %s %d %dms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={
                "request_id": request_id,
                "extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "latency_ms": elapsed_ms,
                    "client_ip": request.client.host if request.client else None,
                },
            },
        )

        # Request tracking
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{elapsed_ms}ms"

        # Security hardening headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # Rate limit headers (if set by rate limiter)
        if hasattr(request.state, "rate_limit_limit"):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
            response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_window)

        return response
