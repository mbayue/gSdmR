"""Tests for model CRUD API endpoints."""

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

    db_path = str(tmp_path / "test_models.db")
    config.DB_PATH = db_path
    database.DB_PATH = db_path

    async def patched_get_db():
        import aiosqlite

        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    database.get_db = patched_get_db

    # Patch get_db in the router modules
    from routers import providers, models

    providers.get_db = patched_get_db
    models.get_db = patched_get_db

    await database.init_db()
    yield db_path

    # Restore original
    original_get_db = database.get_db
    database.get_db = original_get_db
    providers.get_db = original_get_db
    models.get_db = original_get_db


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
class TestListModels:
    """Tests for GET /api/models."""

    async def test_list_models_empty_initially(self, client, auth_headers):
        """Models list is empty when no models have been created."""
        response = await client.get("/api/models", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_models_requires_auth(self, client):
        """GET /api/models without auth returns 401."""
        response = await client.get("/api/models")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestCreateModel:
    """Tests for POST /api/models."""

    async def test_create_model_success(self, client, auth_headers):
        """Creating a model with valid data returns the model with providers."""
        # Get a provider ID from seeded data
        providers_resp = await client.get("/api/providers", headers=auth_headers)
        provider_id = providers_resp.json()[0]["id"]

        response = await client.post(
            "/api/models",
            headers=auth_headers,
            json={
                "name": "gpt-4",
                "providers": [{"provider_id": provider_id, "provider_model": "gpt-4o", "priority": 1}],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "gpt-4"
        assert len(data["providers"]) == 1
        assert data["providers"][0]["provider_id"] == provider_id
        assert data["providers"][0]["priority"] == 1
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_model_multiple_providers(self, client, auth_headers):
        """Creating a model with multiple providers returns them sorted by priority."""
        providers_resp = await client.get("/api/providers", headers=auth_headers)
        providers = providers_resp.json()
        pid1, pid2 = providers[0]["id"], providers[1]["id"]

        response = await client.post(
            "/api/models",
            headers=auth_headers,
            json={
                "name": "multi-provider-model",
                "providers": [
                    {"provider_id": pid2, "provider_model": "gpt-5", "priority": 2},
                    {"provider_id": pid1, "provider_model": "gpt-4o", "priority": 1},
                ],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data["providers"]) == 2
        # Should be sorted by priority
        assert data["providers"][0]["priority"] == 1
        assert data["providers"][1]["priority"] == 2

    async def test_create_model_duplicate_name_returns_409(self, client, auth_headers):
        """Creating a model with an existing name returns 409."""
        providers_resp = await client.get("/api/providers", headers=auth_headers)
        provider_id = providers_resp.json()[0]["id"]

        await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "dup-model", "providers": [{"provider_id": provider_id, "provider_model": "gpt-4o", "priority": 1}]},
        )
        response = await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "dup-model", "providers": [{"provider_id": provider_id, "provider_model": "gpt-4o", "priority": 1}]},
        )
        assert response.status_code == 409

    async def test_create_model_duplicate_priorities_returns_400(self, client, auth_headers):
        """Creating a model with duplicate priorities returns 400."""
        providers_resp = await client.get("/api/providers", headers=auth_headers)
        providers = providers_resp.json()
        pid1, pid2 = providers[0]["id"], providers[1]["id"]

        response = await client.post(
            "/api/models",
            headers=auth_headers,
            json={
                "name": "dup-priority-model",
                "providers": [
                    {"provider_id": pid1, "provider_model": "gpt-4o", "priority": 1},
                    {"provider_id": pid2, "provider_model": "gpt-5", "priority": 1},
                ],
            },
        )
        assert response.status_code == 400
        assert "Duplicate priority" in response.json()["error"]["message"]

    async def test_create_model_nonexistent_provider_returns_400(self, client, auth_headers):
        """Creating a model with a non-existent provider returns 400."""
        response = await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "bad-model", "providers": [{"provider_id": 99999, "provider_model": "gpt-4o", "priority": 1}]},
        )
        assert response.status_code == 400
        assert "does not exist" in response.json()["error"]["message"]

    async def test_create_model_empty_providers_returns_422(self, client, auth_headers):
        """Creating a model with empty providers list returns 422 (Pydantic validation)."""
        response = await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "no-providers", "providers": []},
        )
        assert response.status_code == 422

    async def test_create_model_requires_auth(self, client):
        """POST /api/models without auth returns 401."""
        response = await client.post(
            "/api/models",
            json={"name": "test", "providers": [{"provider_id": 1, "provider_model": "gpt-4o", "priority": 1}]},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestUpdateModel:
    """Tests for PUT /api/models/{id}."""

    async def test_update_model_name(self, client, auth_headers):
        """Updating a model name works."""
        providers_resp = await client.get("/api/providers", headers=auth_headers)
        provider_id = providers_resp.json()[0]["id"]

        create_resp = await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "update-me", "providers": [{"provider_id": provider_id, "provider_model": "gpt-4o", "priority": 1}]},
        )
        model_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/models/{model_id}",
            headers=auth_headers,
            json={"name": "updated-name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated-name"
        # Providers should remain unchanged
        assert len(response.json()["providers"]) == 1

    async def test_update_model_providers(self, client, auth_headers):
        """Updating model provider mappings replaces them entirely."""
        providers_resp = await client.get("/api/providers", headers=auth_headers)
        providers = providers_resp.json()
        pid1, pid2 = providers[0]["id"], providers[1]["id"]

        create_resp = await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "update-providers", "providers": [{"provider_id": pid1, "provider_model": "gpt-4o", "priority": 1}]},
        )
        model_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/models/{model_id}",
            headers=auth_headers,
            json={
                "providers": [
                    {"provider_id": pid1, "provider_model": "gpt-4o", "priority": 1},
                    {"provider_id": pid2, "provider_model": "gpt-5", "priority": 2},
                ]
            },
        )
        assert response.status_code == 200
        assert len(response.json()["providers"]) == 2

    async def test_update_model_empty_providers_returns_400(self, client, auth_headers):
        """Updating model with empty providers list returns 400."""
        providers_resp = await client.get("/api/providers", headers=auth_headers)
        provider_id = providers_resp.json()[0]["id"]

        create_resp = await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "empty-update", "providers": [{"provider_id": provider_id, "provider_model": "gpt-4o", "priority": 1}]},
        )
        model_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/models/{model_id}",
            headers=auth_headers,
            json={"providers": []},
        )
        assert response.status_code == 400
        assert "at least one" in response.json()["error"]["message"].lower()

    async def test_update_model_not_found(self, client, auth_headers):
        """Updating a non-existent model returns 404."""
        response = await client.put(
            "/api/models/99999",
            headers=auth_headers,
            json={"name": "ghost"},
        )
        assert response.status_code == 404

    async def test_update_model_requires_auth(self, client):
        """PUT /api/models/{id} without auth returns 401."""
        response = await client.put(
            "/api/models/1",
            json={"name": "hack"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestDeleteModel:
    """Tests for DELETE /api/models/{id}."""

    async def test_delete_model_success(self, client, auth_headers):
        """Deleting a model returns success message."""
        providers_resp = await client.get("/api/providers", headers=auth_headers)
        provider_id = providers_resp.json()[0]["id"]

        create_resp = await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "delete-me", "providers": [{"provider_id": provider_id, "provider_model": "gpt-4o", "priority": 1}]},
        )
        model_id = create_resp.json()["id"]

        response = await client.delete(f"/api/models/{model_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == {"message": "deleted"}

        # Verify it's gone
        list_resp = await client.get("/api/models", headers=auth_headers)
        model_ids = [m["id"] for m in list_resp.json()]
        assert model_id not in model_ids

    async def test_delete_model_cascades_to_model_providers(self, client, auth_headers, setup_db):
        """Deleting a model removes associated model_providers entries."""
        from routers.models import get_db

        providers_resp = await client.get("/api/providers", headers=auth_headers)
        provider_id = providers_resp.json()[0]["id"]

        create_resp = await client.post(
            "/api/models",
            headers=auth_headers,
            json={"name": "cascade-model", "providers": [{"provider_id": provider_id, "provider_model": "gpt-4o", "priority": 1}]},
        )
        model_id = create_resp.json()["id"]

        # Verify mapping exists
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM model_providers WHERE model_id = ?",
                (model_id,),
            )
            assert (await cursor.fetchone())["cnt"] == 1
        finally:
            await db.close()

        # Delete the model
        response = await client.delete(f"/api/models/{model_id}", headers=auth_headers)
        assert response.status_code == 200

        # Verify cascade removed model_providers entries
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM model_providers WHERE model_id = ?",
                (model_id,),
            )
            assert (await cursor.fetchone())["cnt"] == 0
        finally:
            await db.close()

    async def test_delete_model_not_found(self, client, auth_headers):
        """Deleting a non-existent model returns 404."""
        response = await client.delete("/api/models/99999", headers=auth_headers)
        assert response.status_code == 404

    async def test_delete_model_requires_auth(self, client):
        """DELETE /api/models/{id} without auth returns 401."""
        response = await client.delete("/api/models/1")
        assert response.status_code == 401





