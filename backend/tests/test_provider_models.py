"""Tests for GET /api/providers/{id}/models endpoint (fetches models from provider)."""

import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DB_PATH", ":memory:")

from main import app
from database import init_db
from services.auth import create_access_token


@pytest_asyncio.fixture
async def setup_db(tmp_path):
    """Set up a temporary database for testing."""
    import config
    import database

    db_path = str(tmp_path / "test_provider_models.db")
    config.DB_PATH = db_path
    database.DB_PATH = db_path

    async def patched_get_db():
        import aiosqlite

        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    database.get_db = patched_get_db

    from routers import providers, models, api_keys, backup, proxy
    from middleware import api_key
    from services import routing

    providers.get_db = patched_get_db
    models.get_db = patched_get_db
    api_keys.get_db = patched_get_db
    backup.get_db = patched_get_db
    api_key.get_db = patched_get_db
    routing.get_db = patched_get_db

    await database.init_db()
    yield db_path


@pytest_asyncio.fixture
async def auth_headers():
    """Get authorization headers with a valid JWT token."""
    token = create_access_token("admin")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(setup_db):
    """Async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestListProviderModels:
    """Tests for GET /api/providers/{id}/models."""

    @patch("httpx.AsyncClient")
    async def test_fetches_models_from_provider(
        self, mock_client_cls, client, auth_headers
    ):
        """Fetches models list from provider's /v1/models endpoint."""
        # Mock the httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4-turbo"},
                {"id": "gpt-3.5-turbo"},
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        # Get a provider id (bluesminds is seeded)
        list_resp = await client.get("/api/providers", headers=auth_headers)
        provider = next(
            p for p in list_resp.json() if p["name"] == "bluesminds"
        )
        provider_id = provider["id"]

        response = await client.get(
            f"/api/providers/{provider_id}/models", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == "gpt-4-turbo"
        assert data[1]["id"] == "gpt-3.5-turbo"

    @patch("httpx.AsyncClient")
    async def test_provider_returns_error_status(
        self, mock_client_cls, client, auth_headers
    ):
        """Returns error when provider returns non-200."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        list_resp = await client.get("/api/providers", headers=auth_headers)
        provider = list_resp.json()[0]

        response = await client.get(
            f"/api/providers/{provider['id']}/models", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "500" in data["error"]

    @patch("httpx.AsyncClient")
    async def test_provider_connection_error(
        self, mock_client_cls, client, auth_headers
    ):
        """Returns error when provider is unreachable."""
        import httpx as real_httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=real_httpx.RequestError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        list_resp = await client.get("/api/providers", headers=auth_headers)
        provider = list_resp.json()[0]

        response = await client.get(
            f"/api/providers/{provider['id']}/models", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "Could not reach provider" in data["error"]

    async def test_nonexistent_provider_returns_404(self, client, auth_headers):
        """Fetching models for non-existent provider returns 404."""
        response = await client.get(
            "/api/providers/99999/models", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_requires_auth(self, client):
        """GET /api/providers/{id}/models without auth returns 401."""
        response = await client.get("/api/providers/1/models")
        assert response.status_code == 401
