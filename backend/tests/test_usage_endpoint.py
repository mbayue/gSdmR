"""Tests for the usage statistics API endpoint."""

import os
import sys
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-for-usage-tests")


@pytest_asyncio.fixture
async def setup_db(tmp_path):
    """Set up a temporary database with usage data."""
    import config
    import database

    db_path = str(tmp_path / "test_usage.db")
    config.DB_PATH = db_path
    database.DB_PATH = db_path

    async def patched_get_db():
        import aiosqlite

        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    database.get_db = patched_get_db

    from routers import providers, models, api_keys, backup, proxy, usage
    from middleware import api_key
    from services import routing, health

    providers.get_db = patched_get_db
    models.get_db = patched_get_db
    api_keys.get_db = patched_get_db
    backup.get_db = patched_get_db
    api_key.get_db = patched_get_db
    routing.get_db = patched_get_db
    usage.get_db = patched_get_db
    health.get_db = patched_get_db

    await database.init_db()

    # Insert test usage data
    db = await patched_get_db()
    try:
        # Get default API key id
        cursor = await db.execute("SELECT id FROM api_keys LIMIT 1")
        key_row = await cursor.fetchone()
        key_id = key_row["id"]

        # Insert a second API key for filtering tests
        await db.execute(
            "INSERT INTO api_keys (id, key_value, name) VALUES (?, ?, ?)",
            (99, "sk-gsdm-test-usage-key", "test-usage-key"),
        )

        # Insert usage logs (recent - within 7 days)
        for i in range(5):
            await db.execute(
                """INSERT INTO usage_logs
                   (api_key_id, model_name, provider_name, endpoint, status_code,
                    latency_ms, prompt_tokens, completion_tokens, total_tokens, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', ?))""",
                (
                    key_id,
                    "gpt-4",
                    "openai",
                    "/v1/chat/completions",
                    200,
                    100 + i * 10,
                    50,
                    30,
                    80,
                    f"-{i} hours",
                ),
            )

        # Insert usage logs for second key
        for i in range(3):
            await db.execute(
                """INSERT INTO usage_logs
                   (api_key_id, model_name, provider_name, endpoint, status_code,
                    latency_ms, prompt_tokens, completion_tokens, total_tokens, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', ?))""",
                (
                    99,
                    "claude-3",
                    "anthropic",
                    "/v1/messages",
                    200,
                    200,
                    100,
                    50,
                    150,
                    f"-{i} hours",
                ),
            )

        # Insert a failed request
        await db.execute(
            """INSERT INTO usage_logs
               (api_key_id, model_name, provider_name, endpoint, status_code,
                latency_ms, prompt_tokens, completion_tokens, total_tokens, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-1 hours'))""",
            (key_id, "gpt-4", "openai", "/v1/chat/completions", 500, 50, 0, 0, 0),
        )

        # Insert an old log (outside 7-day window but within 90 days)
        await db.execute(
            """INSERT INTO usage_logs
               (api_key_id, model_name, provider_name, endpoint, status_code,
                latency_ms, prompt_tokens, completion_tokens, total_tokens, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-30 days'))""",
            (key_id, "gpt-4", "openai", "/v1/chat/completions", 200, 300, 100, 50, 150),
        )

        await db.commit()
    finally:
        await db.close()

    yield patched_get_db


@pytest_asyncio.fixture
async def client(setup_db):
    """Create an async test client with auth patched."""
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    """Generate valid JWT auth headers for tests."""
    from services.auth import create_access_token

    token = create_access_token("admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestUsageEndpoint:
    """Tests for GET /api/usage."""

    async def test_returns_summary_with_correct_fields(self, client, auth_headers):
        """GET /api/usage returns summary with all expected fields."""
        response = await client.get("/api/usage", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert "period_days" in data
        assert "summary" in data
        assert "by_model" in data
        assert "by_key" in data
        assert "recent" in data

        summary = data["summary"]
        assert "total_requests" in summary
        assert "total_prompt_tokens" in summary
        assert "total_completion_tokens" in summary
        assert "total_tokens" in summary
        assert "avg_latency_ms" in summary
        assert "successful" in summary
        assert "failed" in summary

    async def test_default_period_is_7_days(self, client, auth_headers):
        """Default period is 7 days, excluding older logs."""
        response = await client.get("/api/usage", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["period_days"] == 7
        # 5 gpt-4 + 3 claude-3 + 1 failed = 9 recent, excludes the 30-day-old one
        assert data["summary"]["total_requests"] == 9

    async def test_days_filter_narrows_results(self, client, auth_headers):
        """GET /api/usage?days=1 filters to last 24 hours."""
        response = await client.get("/api/usage?days=1", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["period_days"] == 1
        # All test data is within last few hours, so should include most
        assert data["summary"]["total_requests"] >= 1

    async def test_api_key_id_filter(self, client, auth_headers):
        """GET /api/usage?api_key_id=99 filters by specific key."""
        response = await client.get("/api/usage?api_key_id=99", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # Only the 3 claude-3 requests from key 99
        assert data["summary"]["total_requests"] == 3
        # All should be claude-3
        if data["by_model"]:
            assert data["by_model"][0]["model"] == "claude-3"

    async def test_model_name_filter(self, client, auth_headers):
        """GET /api/usage?model_name=gpt-4 filters by model."""
        response = await client.get("/api/usage?model_name=gpt-4", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # 5 successful + 1 failed gpt-4 requests
        assert data["summary"]["total_requests"] == 6

    async def test_requires_auth(self, client):
        """GET /api/usage without auth returns 401."""
        response = await client.get("/api/usage")
        assert response.status_code == 401

    async def test_by_model_breakdown(self, client, auth_headers):
        """Response includes per-model breakdown with correct fields."""
        response = await client.get("/api/usage", headers=auth_headers)
        data = response.json()

        assert len(data["by_model"]) >= 2
        for entry in data["by_model"]:
            assert "model" in entry
            assert "requests" in entry
            assert "tokens" in entry
            assert "avg_latency_ms" in entry

    async def test_by_key_breakdown(self, client, auth_headers):
        """Response includes per-key breakdown with correct fields."""
        response = await client.get("/api/usage", headers=auth_headers)
        data = response.json()

        assert len(data["by_key"]) >= 1
        for entry in data["by_key"]:
            assert "key_id" in entry
            assert "key_name" in entry
            assert "requests" in entry
            assert "tokens" in entry

    async def test_recent_requests_list(self, client, auth_headers):
        """Response includes recent requests (max 20)."""
        response = await client.get("/api/usage", headers=auth_headers)
        data = response.json()

        assert len(data["recent"]) <= 20
        assert len(data["recent"]) >= 1
        for entry in data["recent"]:
            assert "model" in entry
            assert "provider" in entry
            assert "endpoint" in entry
            assert "status" in entry
            assert "latency_ms" in entry
            assert "tokens" in entry
            assert "time" in entry

    async def test_counts_successful_and_failed(self, client, auth_headers):
        """Summary correctly counts successful and failed requests."""
        response = await client.get("/api/usage", headers=auth_headers)
        data = response.json()

        summary = data["summary"]
        assert summary["successful"] >= 8  # 5 gpt-4 + 3 claude-3
        assert summary["failed"] >= 1  # 1 failed request
