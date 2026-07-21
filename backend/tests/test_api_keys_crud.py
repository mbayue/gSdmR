"""Tests for API key management CRUD routes."""

import os
import sys

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

    db_path = str(tmp_path / "test_api_keys.db")
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


@pytest_asyncio.fixture
async def sample_model(setup_db):
    """Create a sample model in the database and return its id."""
    import aiosqlite

    db = await aiosqlite.connect(setup_db)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        cursor = await db.execute("INSERT INTO models (name) VALUES (?)", ("gpt-4",))
        await db.commit()
        model_id = cursor.lastrowid
        return model_id
    finally:
        await db.close()


@pytest.mark.asyncio
class TestListApiKeys:
    """Tests for GET /api/keys."""

    async def test_list_keys_returns_seeded_default(self, client, auth_headers):
        """List keys returns the seeded default key."""
        response = await client.get("/api/keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        default_key = next((k for k in data if k["name"] == "default"), None)
        assert default_key is not None
        assert default_key["is_active"] is True
        # key_preview should be masked
        assert "..." in default_key["key_preview"]

    async def test_list_keys_requires_auth(self, client):
        """GET /api/keys without auth returns 401."""
        response = await client.get("/api/keys")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestCreateApiKey:
    """Tests for POST /api/keys."""

    async def test_create_key_returns_full_value(self, client, auth_headers):
        """Creating a key returns the full key_value (starts with sk-gsdm)."""
        response = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": "test-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-key"
        assert data["key_value"].startswith("sk-gsdm")
        assert len(data["key_value"]) > 10
        assert data["is_active"] is True
        assert data["allowed_models"] == []

    async def test_create_key_with_model_restrictions(
        self, client, auth_headers, sample_model
    ):
        """Creating a key with model_ids sets model restrictions."""
        response = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": "restricted-key", "model_ids": [sample_model]},
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data["allowed_models"]) == 1
        assert data["allowed_models"][0]["name"] == "gpt-4"

    async def test_create_key_with_nonexistent_model_returns_400(
        self, client, auth_headers
    ):
        """Creating a key with non-existent model_id returns 400."""
        response = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": "bad-key", "model_ids": [99999]},
        )
        assert response.status_code == 400

    async def test_create_key_empty_name_returns_422(self, client, auth_headers):
        """Creating a key with empty name returns 422."""
        response = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": ""},
        )
        assert response.status_code == 422

    async def test_create_key_requires_auth(self, client):
        """POST /api/keys without auth returns 401."""
        response = await client.post("/api/keys", json={"name": "test"})
        assert response.status_code == 401


@pytest.mark.asyncio
class TestUpdateApiKey:
    """Tests for PUT /api/keys/{id}."""

    async def test_update_key_name(self, client, auth_headers):
        """Updating a key name works."""
        # Create a key
        create_resp = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": "original-name"},
        )
        key_id = create_resp.json()["id"]

        # Update name
        response = await client.put(
            f"/api/keys/{key_id}",
            headers=auth_headers,
            json={"name": "new-name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "new-name"

    async def test_toggle_key_inactive(self, client, auth_headers):
        """Toggling a key to inactive works."""
        create_resp = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": "toggle-test"},
        )
        key_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/keys/{key_id}",
            headers=auth_headers,
            json={"is_active": False},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    async def test_toggle_key_active(self, client, auth_headers):
        """Re-enabling an inactive key works."""
        create_resp = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": "reactivate-test"},
        )
        key_id = create_resp.json()["id"]

        # Disable then re-enable
        await client.put(
            f"/api/keys/{key_id}",
            headers=auth_headers,
            json={"is_active": False},
        )
        response = await client.put(
            f"/api/keys/{key_id}",
            headers=auth_headers,
            json={"is_active": True},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is True

    async def test_update_key_model_restrictions(
        self, client, auth_headers, sample_model
    ):
        """Updating model restrictions replaces existing ones."""
        create_resp = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": "model-restrict-test"},
        )
        key_id = create_resp.json()["id"]

        # Add restriction
        response = await client.put(
            f"/api/keys/{key_id}",
            headers=auth_headers,
            json={"model_ids": [sample_model]},
        )
        assert response.status_code == 200
        assert len(response.json()["allowed_models"]) == 1

        # Remove restriction
        response = await client.put(
            f"/api/keys/{key_id}",
            headers=auth_headers,
            json={"model_ids": []},
        )
        assert response.status_code == 200
        assert response.json()["allowed_models"] == []

    async def test_update_nonexistent_key_returns_404(self, client, auth_headers):
        """Updating a non-existent key returns 404."""
        response = await client.put(
            "/api/keys/99999",
            headers=auth_headers,
            json={"name": "ghost"},
        )
        assert response.status_code == 404

    async def test_update_key_requires_auth(self, client):
        """PUT /api/keys/{id} without auth returns 401."""
        response = await client.put("/api/keys/1", json={"name": "hack"})
        assert response.status_code == 401


@pytest.mark.asyncio
class TestDeleteApiKey:
    """Tests for DELETE /api/keys/{id}."""

    async def test_delete_key_success(self, client, auth_headers):
        """Deleting a key returns success and removes it."""
        create_resp = await client.post(
            "/api/keys",
            headers=auth_headers,
            json={"name": "delete-me"},
        )
        key_id = create_resp.json()["id"]

        response = await client.delete(f"/api/keys/{key_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == {"message": "deleted"}

        # Verify it's gone
        list_resp = await client.get("/api/keys", headers=auth_headers)
        ids = [k["id"] for k in list_resp.json()]
        assert key_id not in ids

    async def test_delete_nonexistent_key_returns_404(self, client, auth_headers):
        """Deleting a non-existent key returns 404."""
        response = await client.delete("/api/keys/99999", headers=auth_headers)
        assert response.status_code == 404

    async def test_delete_key_requires_auth(self, client):
        """DELETE /api/keys/{id} without auth returns 401."""
        response = await client.delete("/api/keys/1")
        assert response.status_code == 401
