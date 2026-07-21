"""Rate limiting middleware using in-memory sliding window per API key."""

import time
from dataclasses import dataclass, field
from fastapi import HTTPException, Request

# Default: 60 requests per minute per key
DEFAULT_RATE_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60
MAX_TRACKED_KEYS = 10000  # Evict oldest entries beyond this


@dataclass
class SlidingWindow:
    """Sliding window counter for rate limiting."""

    requests: list[float] = field(default_factory=list)
    last_access: float = 0.0

    def add_request(self, now: float, window: int) -> int:
        """Add a request timestamp and return current count within window."""
        cutoff = now - window
        self.requests = [t for t in self.requests if t > cutoff]
        self.requests.append(now)
        self.last_access = now
        return len(self.requests)


# Global shared sliding windows (keyed by API key ID)
_windows: dict[int, SlidingWindow] = {}


def _evict_stale_entries() -> None:
    """Remove entries not accessed in 2x window to bound memory."""
    if len(_windows) <= MAX_TRACKED_KEYS:
        return
    now = time.time()
    stale_cutoff = now - (DEFAULT_WINDOW_SECONDS * 2)
    stale_keys = [k for k, v in _windows.items() if v.last_access < stale_cutoff]
    for k in stale_keys:
        del _windows[k]


async def check_rate_limit(request: Request, key_info: dict) -> None:
    """Check rate limit for the current API key. Raises 429 if exceeded.

    Uses the per-key rate_limit value (requests per minute).
    """
    key_id = key_info["key_id"]
    max_requests = key_info.get("rate_limit", DEFAULT_RATE_LIMIT)

    # Get or create window for this key
    if key_id not in _windows:
        _windows[key_id] = SlidingWindow()
        _evict_stale_entries()

    now = time.time()
    window = _windows[key_id]
    count = window.add_request(now, DEFAULT_WINDOW_SECONDS)

    if count > max_requests:
        # Deny — remove the request we just added
        window.requests.pop()
        request.state.rate_limit_remaining = 0
        request.state.rate_limit_limit = max_requests
        request.state.rate_limit_window = DEFAULT_WINDOW_SECONDS
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please slow down.",
            headers={
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(DEFAULT_WINDOW_SECONDS),
                "Retry-After": str(DEFAULT_WINDOW_SECONDS),
            },
        )

    # Allow
    remaining = max_requests - count
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_limit = max_requests
    request.state.rate_limit_window = DEFAULT_WINDOW_SECONDS
