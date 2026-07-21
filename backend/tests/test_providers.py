"""Tests for provider CRUD API endpoints."""

import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure backend directory is on the path
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

    db_path = str(tmp_path / "test_providers.db")
    config.DB_PATH = db_path
    database.DB_PATH = db_path

    original_get_db = database.get_db

    async def patched_get_db():
        import aiosqlite

        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    database.get_db = patched_get_db

    # Patch get_db in the providers router module
    from routers import providers

    providers.get_db = patched_get_db

    await database.init_db()
    yield db_path

    database.get_db = original_get_db
    providers.get_db = original_get_db


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
class TestListProviders:
    """Tests for GET /api/providers."""

    async def test_list_providers_returns_seeded_providers(self, client, auth_headers):
        """Lists all seeded providers on startup."""
        response = await client.get("/api/providers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4
        names = [p["name"] for p in data]
        assert "bluesminds" in names
        assert "freemodel" in names
        assert "forge-gateway" in names
        assert "iamhc" in names

    async def test_list_providers_masks_api_keys(self, client, auth_headers):
        """Provider API keys are masked in list response."""
        # First create a provider with a known key
        await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "test-provider", "base_url": "http://test.com", "api_key": "sk-secret-key-1234"},
        )
        response = await client.get("/api/providers", headers=auth_headers)
        data = response.json()
        test_provider = next(p for p in data if p["name"] == "test-provider")
        # "sk-secret-key-1234" is 18 chars, so masked = 14 asterisks + "1234"
        assert test_provider["api_key_masked"] == "*" * 14 + "1234"
        assert "sk-secret-key-1234" not in str(test_provider)

    async def test_list_providers_requires_auth(self, client):
        """GET /api/providers without auth returns 401."""
        response = await client.get("/api/providers")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestCreateProvider:
    """Tests for POST /api/providers."""

    async def test_create_provider_success(self, client, auth_headers):
        """Creating a provider returns the new provider with masked key."""
        response = await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "new-provider", "base_url": "http://new.com/v1/", "api_key": "sk-newkey123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-provider"
        assert data["base_url"] == "http://new.com/v1/"
        assert data["api_key_masked"].endswith("y123")
        assert data["is_active"] is True
        assert "id" in data

    async def test_create_provider_duplicate_name_returns_409(self, client, auth_headers):
        """Creating a provider with an existing name returns 409."""
        response = await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "bluesminds", "base_url": "http://dupe.com", "api_key": "sk-key"},
        )
        assert response.status_code == 409

    async def test_create_provider_empty_name_rejected(self, client, auth_headers):
        """Creating a provider with empty name returns 422."""
        response = await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "", "base_url": "http://test.com", "api_key": "sk-key"},
        )
        assert response.status_code == 422

    async def test_create_provider_empty_base_url_rejected(self, client, auth_headers):
        """Creating a provider with empty base_url returns 422."""
        response = await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "valid-name", "base_url": "", "api_key": "sk-key"},
        )
        assert response.status_code == 422

    async def test_create_provider_requires_auth(self, client):
        """POST /api/providers without auth returns 401."""
        response = await client.post(
            "/api/providers",
            json={"name": "test", "base_url": "http://test.com", "api_key": "sk-key"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestUpdateProvider:
    """Tests for PUT /api/providers/{id}."""

    async def test_update_provider_name(self, client, auth_headers):
        """Updating a provider name works."""
        # Create a provider
        create_resp = await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "update-test", "base_url": "http://test.com", "api_key": "sk-key123456"},
        )
        provider_id = create_resp.json()["id"]

        # Update it
        response = await client.put(
            f"/api/providers/{provider_id}",
            headers=auth_headers,
            json={"name": "updated-name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated-name"
        assert response.json()["base_url"] == "http://test.com"

    async def test_update_provider_partial(self, client, auth_headers):
        """Partial update only changes provided fields."""
        create_resp = await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "partial-test", "base_url": "http://original.com", "api_key": "sk-original1234"},
        )
        provider_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/providers/{provider_id}",
            headers=auth_headers,
            json={"base_url": "http://updated.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "partial-test"
        assert data["base_url"] == "http://updated.com"

    async def test_update_provider_not_found(self, client, auth_headers):
        """Updating a non-existent provider returns 404."""
        response = await client.put(
            "/api/providers/99999",
            headers=auth_headers,
            json={"name": "ghost"},
        )
        assert response.status_code == 404

    async def test_update_provider_requires_auth(self, client):
        """PUT /api/providers/{id} without auth returns 401."""
        response = await client.put(
            "/api/providers/1",
            json={"name": "hack"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestDeleteProvider:
    """Tests for DELETE /api/providers/{id}."""

    async def test_delete_provider_success(self, client, auth_headers):
        """Deleting a provider returns success message."""
        create_resp = await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "delete-me", "base_url": "http://bye.com", "api_key": "sk-byebye123"},
        )
        provider_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/providers/{provider_id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json() == {"message": "deleted"}

        # Verify it's gone
        list_resp = await client.get("/api/providers", headers=auth_headers)
        names = [p["name"] for p in list_resp.json()]
        assert "delete-me" not in names

    async def test_delete_provider_not_found(self, client, auth_headers):
        """Deleting a non-existent provider returns 404."""
        response = await client.delete("/api/providers/99999", headers=auth_headers)
        assert response.status_code == 404

    async def test_delete_provider_cascades_to_model_providers(self, client, auth_headers, setup_db):
        """Deleting a provider removes associated model_providers entries."""
        from routers.providers import get_db

        # Create a provider
        create_resp = await client.post(
            "/api/providers",
            headers=auth_headers,
            json={"name": "cascade-test", "base_url": "http://cascade.com", "api_key": "sk-cascade123"},
        )
        provider_id = create_resp.json()["id"]

        # Manually insert a model and model_providers mapping
        db = await get_db()
        try:
            await db.execute("INSERT INTO models (name) VALUES (?)", ("test-model",))
            await db.commit()
            cursor = await db.execute("SELECT id FROM models WHERE name = ?", ("test-model",))
            model_row = await cursor.fetchone()
            model_id = model_row["id"]

            await db.execute(
                "INSERT INTO model_providers (model_id, provider_id, priority) VALUES (?, ?, ?)",
                (model_id, provider_id, 1),
            )
            await db.commit()

            # Verify mapping exists
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM model_providers WHERE provider_id = ?",
                (provider_id,),
            )
            assert (await cursor.fetchone())["cnt"] == 1
        finally:
            await db.close()

        # Delete the provider
        response = await client.delete(
            f"/api/providers/{provider_id}", headers=auth_headers
        )
        assert response.status_code == 200

        # Verify cascade removed model_providers entry
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM model_providers WHERE provider_id = ?",
                (provider_id,),
            )
            assert (await cursor.fetchone())["cnt"] == 0
        finally:
            await db.close()

    async def test_delete_provider_requires_auth(self, client):
        """DELETE /api/providers/{id} without auth returns 401."""
        response = await client.delete("/api/providers/1")
        assert response.status_code == 401
