"""Tests for the health check service (provider health monitoring and auto-disable)."""

import os
import sys
import time
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DB_PATH", ":memory:")

from services.health import (
    check_provider,
    run_health_checks,
    get_health_status,
    _health_state,
    FAILURE_THRESHOLD,
    CHECK_INTERVAL_SECONDS,
    RECOVERY_CHECK_INTERVAL,
    ProviderHealth,
)


@pytest_asyncio.fixture
async def setup_db(tmp_path):
    """Set up a temporary database with providers for health check testing."""
    import config
    import database

    db_path = str(tmp_path / "test_health.db")
    config.DB_PATH = db_path
    database.DB_PATH = db_path

    async def patched_get_db():
        import aiosqlite

        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    database.get_db = patched_get_db

    from services import health

    health.get_db = patched_get_db

    await database.init_db()

    # Clear health state between tests
    _health_state.clear()

    yield patched_get_db

    _health_state.clear()


@pytest_asyncio.fixture
async def db_with_providers(setup_db):
    """Create test providers in the database."""
    db = await setup_db()
    try:
        # Active provider
        await db.execute(
            "INSERT INTO providers (id, name, base_url, api_key, is_active, auto_disabled) VALUES (?, ?, ?, ?, ?, ?)",
            (100, "healthy-provider", "https://api.healthy.com/v1", "sk-healthy", 1, 0),
        )
        # Active provider that will fail
        await db.execute(
            "INSERT INTO providers (id, name, base_url, api_key, is_active, auto_disabled) VALUES (?, ?, ?, ?, ?, ?)",
            (101, "failing-provider", "https://api.failing.com/v1", "sk-failing", 1, 0),
        )
        # Auto-disabled provider (can be re-enabled)
        await db.execute(
            "INSERT INTO providers (id, name, base_url, api_key, is_active, auto_disabled) VALUES (?, ?, ?, ?, ?, ?)",
            (102, "auto-disabled-provider", "https://api.auto.com/v1", "sk-auto", 0, 1),
        )
        # Manually disabled provider (should NOT be re-enabled)
        await db.execute(
            "INSERT INTO providers (id, name, base_url, api_key, is_active, auto_disabled) VALUES (?, ?, ?, ?, ?, ?)",
            (103, "manual-disabled-provider", "https://api.manual.com/v1", "sk-manual", 0, 0),
        )
        await db.commit()
    finally:
        await db.close()

    return setup_db


class TestCheckProvider:
    """Tests for check_provider — pings a single provider."""

    @pytest.mark.asyncio
    async def test_returns_true_for_healthy_provider(self):
        """check_provider returns True when provider responds with 200."""
        mock_response = httpx.Response(status_code=200, json={"data": []})
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await check_provider(1, "test", "https://api.test.com/v1", "sk-key")
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_4xx_non_server_error(self):
        """check_provider returns True for 4xx (provider is alive, just rejecting)."""
        mock_response = httpx.Response(status_code=401, json={"error": "unauthorized"})
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await check_provider(1, "test", "https://api.test.com/v1", "sk-key")
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_server_error(self):
        """check_provider returns False for 5xx server errors."""
        mock_response = httpx.Response(status_code=500, json={"error": "server error"})
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await check_provider(1, "test", "https://api.test.com/v1", "sk-key")
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self):
        """check_provider returns False when provider times out."""
        with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("timed out")):
            result = await check_provider(1, "test", "https://api.test.com/v1", "sk-key")
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self):
        """check_provider returns False on connection error."""
        with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("connection refused")):
            result = await check_provider(1, "test", "https://api.test.com/v1", "sk-key")
            assert result is False

    @pytest.mark.asyncio
    async def test_constructs_correct_url(self):
        """check_provider pings /models endpoint."""
        mock_response = httpx.Response(status_code=200, json={})
        with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            await check_provider(1, "test", "https://api.test.com/v1/", "sk-key")
            call_args = mock_get.call_args
            assert call_args[0][0] == "https://api.test.com/v1/models"


class TestRunHealthChecks:
    """Tests for run_health_checks — full round of checking all providers."""

    @pytest.mark.asyncio
    async def test_auto_disables_after_threshold_failures(self, db_with_providers):
        """Provider is auto-disabled after FAILURE_THRESHOLD consecutive failures."""
        # Pre-set the health state to just below threshold with stale last_check
        _health_state[101] = ProviderHealth(
            provider_id=101,
            name="failing-provider",
            consecutive_failures=FAILURE_THRESHOLD - 1,
            last_check=0,  # Force re-check
        )

        with patch("services.health.check_provider", return_value=False):
            await run_health_checks()

        # Verify provider was disabled in DB
        db = await db_with_providers()
        try:
            cursor = await db.execute(
                "SELECT is_active, auto_disabled FROM providers WHERE id = ?", (101,)
            )
            row = await cursor.fetchone()
            assert row["is_active"] == 0
            assert row["auto_disabled"] == 1
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_re_enables_auto_disabled_on_recovery(self, db_with_providers):
        """Auto-disabled providers are re-enabled when they recover."""
        # Set stale last_check so it will be re-checked
        _health_state[102] = ProviderHealth(
            provider_id=102,
            name="auto-disabled-provider",
            consecutive_failures=3,
            last_check=0,  # Force re-check
        )

        with patch("services.health.check_provider", return_value=True):
            await run_health_checks()

        # Verify provider was re-enabled
        db = await db_with_providers()
        try:
            cursor = await db.execute(
                "SELECT is_active, auto_disabled FROM providers WHERE id = ?", (102,)
            )
            row = await cursor.fetchone()
            assert row["is_active"] == 1
            assert row["auto_disabled"] == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_does_not_re_enable_manually_disabled(self, db_with_providers):
        """Manually disabled providers are NOT re-enabled even if healthy."""
        with patch("services.health.check_provider", return_value=True):
            await run_health_checks()

        # Verify manually disabled provider is still disabled
        db = await db_with_providers()
        try:
            cursor = await db.execute(
                "SELECT is_active, auto_disabled FROM providers WHERE id = ?", (103,)
            )
            row = await cursor.fetchone()
            assert row["is_active"] == 0
            assert row["auto_disabled"] == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_healthy_check_resets_failure_counter(self, db_with_providers):
        """A healthy response resets consecutive_failures to 0."""
        _health_state[100] = ProviderHealth(
            provider_id=100,
            name="healthy-provider",
            consecutive_failures=2,
            last_check=0,
        )

        with patch("services.health.check_provider", return_value=True):
            await run_health_checks()

        assert _health_state[100].consecutive_failures == 0
        assert _health_state[100].last_status == "healthy"


class TestGetHealthStatus:
    """Tests for get_health_status — returns current in-memory state."""

    def test_returns_empty_when_no_state(self):
        """Returns empty list when no providers have been checked."""
        _health_state.clear()
        result = get_health_status()
        assert result == []

    def test_returns_provider_statuses(self):
        """Returns status for all tracked providers."""
        _health_state.clear()
        _health_state[1] = ProviderHealth(
            provider_id=1,
            name="provider-a",
            consecutive_failures=0,
            last_check=time.time(),
            last_status="healthy",
        )
        _health_state[2] = ProviderHealth(
            provider_id=2,
            name="provider-b",
            consecutive_failures=2,
            last_check=time.time(),
            last_status="unhealthy",
        )

        result = get_health_status()
        assert len(result) == 2
        names = [r["name"] for r in result]
        assert "provider-a" in names
        assert "provider-b" in names

    def test_status_contains_required_fields(self):
        """Each status entry contains provider_id, name, status, consecutive_failures, last_check."""
        _health_state.clear()
        _health_state[1] = ProviderHealth(
            provider_id=1,
            name="test-provider",
            consecutive_failures=1,
            last_check=123456.0,
            last_status="unhealthy",
        )

        result = get_health_status()
        entry = result[0]
        assert entry["provider_id"] == 1
        assert entry["name"] == "test-provider"
        assert entry["status"] == "unhealthy"
        assert entry["consecutive_failures"] == 1
        assert entry["last_check"] == 123456.0
