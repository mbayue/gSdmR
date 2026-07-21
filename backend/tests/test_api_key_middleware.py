"""Tests for API key authentication middleware."""

import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure backend directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Use a temporary test database
os.environ.setdefault("DB_PATH", ":memory:")

from fastapi import Depends, FastAPI
from middleware.api_key import validate_api_key, _extract_key_from_headers
from database import get_db, init_db
from config import DEFAULT_API_KEY


# Create a test app with a protected endpoint
test_app = FastAPI()


@test_app.get("/protected")
async def protected_endpoint(authenticated: bool = Depends(validate_api_key)):
    return {"status": "ok"}


@test_app.get("/public")
async def public_endpoint():
    return {"status": "public"}


@pytest_asyncio.fixture
async def setup_db(tmp_path):
    """Set up a temporary database for testing."""
    import config
    import database

    db_path = str(tmp_path / "test.db")
    config.DB_PATH = db_path
    database.DB_PATH = db_path

    # Patch the module-level DB_PATH that get_db uses
    original_get_db = database.get_db

    async def patched_get_db():
        import aiosqlite

        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    database.get_db = patched_get_db

    # Also patch it in middleware.api_key since it imported get_db
    from middleware import api_key

    api_key.get_db = patched_get_db

    await database.init_db()
    yield db_path

    database.get_db = original_get_db
    api_key.get_db = original_get_db


@pytest_asyncio.fixture
async def client(setup_db):
    """Async HTTP client for testing."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestExtractKeyFromHeaders:
    """Unit tests for header extraction logic."""

    def test_bearer_token_extraction(self):
        """Authorization Bearer header is extracted correctly."""
        headers = {"authorization": "Bearer sk-test-key-123"}
        assert _extract_key_from_headers(headers) == "sk-test-key-123"

    def test_bearer_token_case_insensitive(self):
        """Bearer prefix is case-insensitive."""
        headers = {"authorization": "bearer sk-test-key-123"}
        assert _extract_key_from_headers(headers) == "sk-test-key-123"

    def test_x_api_key_extraction(self):
        """x-api-key header is extracted correctly."""
        headers = {"x-api-key": "sk-test-key-456"}
        assert _extract_key_from_headers(headers) == "sk-test-key-456"

    def test_bearer_takes_priority_over_x_api_key(self):
        """Authorization Bearer is checked before x-api-key."""
        headers = {
            "authorization": "Bearer sk-bearer-key",
            "x-api-key": "sk-header-key",
        }
        assert _extract_key_from_headers(headers) == "sk-bearer-key"

    def test_no_key_returns_none(self):
        """Returns None when no API key header is present."""
        headers = {"content-type": "application/json"}
        assert _extract_key_from_headers(headers) is None

    def test_invalid_auth_header_falls_to_x_api_key(self):
        """Non-Bearer auth header falls through to x-api-key."""
        headers = {
            "authorization": "Basic dXNlcjpwYXNz",
            "x-api-key": "sk-fallback",
        }
        assert _extract_key_from_headers(headers) == "sk-fallback"

    def test_empty_bearer_returns_empty(self):
        """Bearer with only whitespace returns empty after strip."""
        headers = {"authorization": "Bearer   "}
        result = _extract_key_from_headers(headers)
        assert result == ""

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace is trimmed from key values."""
        headers = {"x-api-key": "  sk-key-with-spaces  "}
        assert _extract_key_from_headers(headers) == "sk-key-with-spaces"


@pytest.mark.asyncio
class TestValidateApiKey:
    """Integration tests for the validate_api_key dependency."""

    async def test_valid_bearer_key_returns_200(self, client):
        """Request with valid Bearer key succeeds."""
        response = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {DEFAULT_API_KEY}"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_valid_x_api_key_returns_200(self, client):
        """Request with valid x-api-key header succeeds."""
        response = await client.get(
            "/protected",
            headers={"x-api-key": DEFAULT_API_KEY},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_missing_key_returns_401(self, client):
        """Request without any API key returns 401."""
        response = await client.get("/protected")
        assert response.status_code == 401
        assert "API key required" in response.json()["detail"]

    async def test_invalid_key_returns_401(self, client):
        """Request with wrong API key returns 401."""
        response = await client.get(
            "/protected",
            headers={"Authorization": "Bearer invalid-key-xyz"},
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    async def test_inactive_key_returns_401(self, client, setup_db):
        """Request with inactive API key returns 401."""
        from middleware.api_key import get_db

        db = await get_db()
        try:
            # Insert an inactive key
            await db.execute(
                "INSERT INTO api_keys (key_value, name, is_active) VALUES (?, ?, ?)",
                ("sk-inactive-key", "inactive-test", 0),
            )
            await db.commit()
        finally:
            await db.close()

        response = await client.get(
            "/protected",
            headers={"Authorization": "Bearer sk-inactive-key"},
        )
        assert response.status_code == 401
        assert "API key is disabled" in response.json()["detail"]

    async def test_public_endpoint_no_auth_needed(self, client):
        """Public endpoint without dependency works without key."""
        response = await client.get("/public")
        assert response.status_code == 200
        assert response.json() == {"status": "public"}
