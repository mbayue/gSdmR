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


# Global shared sliding windows (keyed by API key ID)
_windows: dict[int, SlidingWindow] = defaultdict(SlidingWindow)


class RateLimiter:
    """In-memory sliding window rate limiter keyed by API key ID."""

    def __init__(self, max_requests: int = DEFAULT_RATE_LIMIT, window_seconds: int = DEFAULT_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def check(self, key_id: int) -> tuple[bool, int, int]:
        """Check if request is allowed.

        Returns: (allowed, remaining, reset_seconds)
        """
        now = time.time()
        window = _windows[key_id]
        count = window.add_request(now, self.window_seconds)

        if count > self.max_requests:
            # Remove the request we just added (it's denied)
            window.requests.pop()
            remaining = 0
            return False, remaining, self.window_seconds
        else:
            remaining = self.max_requests - count
            return True, remaining, self.window_seconds


# Global rate limiter instance (used as fallback)
rate_limiter = RateLimiter()


async def check_rate_limit(request: Request, key_info: dict) -> None:
    """Check rate limit for the current API key. Raises 429 if exceeded.

    Uses the per-key rate_limit value (requests per minute).
    """
    key_id = key_info["key_id"]
    max_requests = key_info.get("rate_limit", DEFAULT_RATE_LIMIT)

    # Create a per-key limiter if needed with custom limit
    limiter = RateLimiter(max_requests=max_requests, window_seconds=DEFAULT_WINDOW_SECONDS)
    allowed, remaining, window = limiter.check(key_id)

    # Store rate limit info for response headers
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_limit = max_requests
    request.state.rate_limit_window = window

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please slow down.",
            headers={
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(window),
                "Retry-After": str(window),
            },
        )
