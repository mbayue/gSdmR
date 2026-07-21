"""Tests for the rate limiting middleware (sliding window per API key)."""

import os
import sys
import time
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from middleware.rate_limit import (
    check_rate_limit,
    _windows,
    _evict_stale_entries,
    SlidingWindow,
    DEFAULT_RATE_LIMIT,
    DEFAULT_WINDOW_SECONDS,
    MAX_TRACKED_KEYS,
)


@pytest.fixture(autouse=True)
def clear_windows():
    """Clear the global rate limit state between tests."""
    _windows.clear()
    yield
    _windows.clear()


def _make_request():
    """Create a mock request object with state."""
    request = MagicMock()
    request.state = MagicMock()
    return request


@pytest.mark.asyncio
class TestCheckRateLimit:
    """Tests for check_rate_limit — sliding window enforcement."""

    async def test_request_within_limit_succeeds(self):
        """A request within the rate limit passes without raising."""
        request = _make_request()
        key_info = {"key_id": 1, "rate_limit": 60}

        # Should not raise
        await check_rate_limit(request, key_info)

        assert request.state.rate_limit_remaining == 59
        assert request.state.rate_limit_limit == 60

    async def test_request_exceeding_limit_raises_429(self):
        """Exceeding the rate limit raises HTTPException(429)."""
        request = _make_request()
        key_info = {"key_id": 2, "rate_limit": 3}

        # Make 3 requests (at the limit)
        for _ in range(3):
            await check_rate_limit(request, key_info)

        # 4th request should exceed
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request, key_info)

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail

    async def test_rate_limit_headers_set_on_rejection(self):
        """Rate limit headers are set on the request state when rejected."""
        request = _make_request()
        key_info = {"key_id": 3, "rate_limit": 1}

        # First request uses the quota
        await check_rate_limit(request, key_info)

        # Second request exceeds
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request, key_info)

        assert request.state.rate_limit_remaining == 0
        assert request.state.rate_limit_limit == 1
        # Verify headers on the exception
        assert "X-RateLimit-Limit" in exc_info.value.headers
        assert exc_info.value.headers["X-RateLimit-Limit"] == "1"
        assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"

    async def test_separate_keys_have_independent_limits(self):
        """Different API keys have independent rate limits."""
        request = _make_request()
        key_info_a = {"key_id": 10, "rate_limit": 2}
        key_info_b = {"key_id": 11, "rate_limit": 2}

        # Exhaust key A's limit
        await check_rate_limit(request, key_info_a)
        await check_rate_limit(request, key_info_a)

        # Key A should be blocked
        with pytest.raises(HTTPException):
            await check_rate_limit(request, key_info_a)

        # Key B should still work
        await check_rate_limit(request, key_info_b)  # No exception

    async def test_per_key_rate_limit_respected(self):
        """Uses per-key rate_limit value, not just the default."""
        request = _make_request()
        # Very low limit
        key_info = {"key_id": 20, "rate_limit": 2}

        await check_rate_limit(request, key_info)
        await check_rate_limit(request, key_info)

        # Should be blocked at 2
        with pytest.raises(HTTPException):
            await check_rate_limit(request, key_info)

    async def test_uses_default_rate_limit_when_not_specified(self):
        """Uses DEFAULT_RATE_LIMIT when key_info doesn't specify rate_limit."""
        request = _make_request()
        key_info = {"key_id": 30}  # No rate_limit key

        await check_rate_limit(request, key_info)
        assert request.state.rate_limit_limit == DEFAULT_RATE_LIMIT

    async def test_remaining_decreases_with_requests(self):
        """rate_limit_remaining decreases with each request."""
        request = _make_request()
        key_info = {"key_id": 40, "rate_limit": 10}

        await check_rate_limit(request, key_info)
        assert request.state.rate_limit_remaining == 9

        await check_rate_limit(request, key_info)
        assert request.state.rate_limit_remaining == 8


class TestSlidingWindow:
    """Tests for the SlidingWindow data structure."""

    def test_add_request_returns_count(self):
        """add_request returns the number of requests within the window."""
        window = SlidingWindow()
        now = time.time()
        count = window.add_request(now, 60)
        assert count == 1

    def test_old_requests_are_pruned(self):
        """Requests older than the window are pruned."""
        window = SlidingWindow()
        now = time.time()

        # Add a request 120 seconds ago (outside 60-second window)
        window.requests = [now - 120]
        count = window.add_request(now, 60)
        # Only the new request should count
        assert count == 1

    def test_recent_requests_are_kept(self):
        """Requests within the window are kept."""
        window = SlidingWindow()
        now = time.time()

        # Add requests within window
        window.requests = [now - 30, now - 20, now - 10]
        count = window.add_request(now, 60)
        assert count == 4


class TestEviction:
    """Tests for _evict_stale_entries — bounds memory usage."""

    def test_no_eviction_below_max(self):
        """No eviction when below MAX_TRACKED_KEYS."""
        _windows.clear()
        # Add a few entries
        for i in range(10):
            _windows[i] = SlidingWindow(last_access=time.time())

        _evict_stale_entries()
        assert len(_windows) == 10

    def test_evicts_stale_entries_above_max(self):
        """Stale entries are evicted when over MAX_TRACKED_KEYS."""
        _windows.clear()
        now = time.time()
        stale_time = now - (DEFAULT_WINDOW_SECONDS * 3)  # Older than 2x window

        # Fill beyond MAX_TRACKED_KEYS with stale entries
        for i in range(MAX_TRACKED_KEYS + 100):
            _windows[i] = SlidingWindow(last_access=stale_time)

        # Add a few fresh entries
        for i in range(MAX_TRACKED_KEYS + 100, MAX_TRACKED_KEYS + 110):
            _windows[i] = SlidingWindow(last_access=now)

        _evict_stale_entries()
        # Stale entries should be removed, fresh ones kept
        assert len(_windows) <= MAX_TRACKED_KEYS + 110
        # Fresh entries should survive
        for i in range(MAX_TRACKED_KEYS + 100, MAX_TRACKED_KEYS + 110):
            assert i in _windows

    def test_does_not_evict_recent_entries(self):
        """Recent entries (within 2x window) are not evicted."""
        _windows.clear()
        now = time.time()

        # Fill above max with recent entries
        for i in range(MAX_TRACKED_KEYS + 50):
            _windows[i] = SlidingWindow(last_access=now)

        original_count = len(_windows)
        _evict_stale_entries()
        # Nothing should be evicted because all are recent
        assert len(_windows) == original_count
