"""Rate limiting middleware using in-memory sliding window per API key."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from fastapi import HTTPException, Request

# Default: 60 requests per minute per key
DEFAULT_RATE_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60


@dataclass
class SlidingWindow:
    """Sliding window counter for rate limiting."""

    requests: list[float] = field(default_factory=list)

    def add_request(self, now: float, window: int) -> int:
        """Add a request timestamp and return current count within window."""
        # Remove expired entries
        cutoff = now - window
        self.requests = [t for t in self.requests if t > cutoff]
        self.requests.append(now)
        return len(self.requests)


class RateLimiter:
    """In-memory sliding window rate limiter keyed by API key ID."""

    def __init__(self, max_requests: int = DEFAULT_RATE_LIMIT, window_seconds: int = DEFAULT_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: dict[int, SlidingWindow] = defaultdict(SlidingWindow)

    def check(self, key_id: int) -> tuple[bool, int, int]:
        """Check if request is allowed.

        Returns: (allowed, remaining, reset_seconds)
        """
        now = time.time()
        window = self._windows[key_id]
        count = window.add_request(now, self.window_seconds)

        if count > self.max_requests:
            # Remove the request we just added (it's denied)
            window.requests.pop()
            remaining = 0
            return False, remaining, self.window_seconds
        else:
            remaining = self.max_requests - count
            return True, remaining, self.window_seconds


# Global rate limiter instance
rate_limiter = RateLimiter()


async def check_rate_limit(request: Request, key_info: dict) -> None:
    """Check rate limit for the current API key. Raises 429 if exceeded.

    Call this after validate_api_key in proxy endpoints.
    Sets rate limit headers on the response.
    """
    key_id = key_info["key_id"]
    allowed, remaining, window = rate_limiter.check(key_id)

    # Store rate limit info for response headers
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_limit = rate_limiter.max_requests
    request.state.rate_limit_window = window

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please slow down.",
            headers={
                "X-RateLimit-Limit": str(rate_limiter.max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(window),
                "Retry-After": str(window),
            },
        )
