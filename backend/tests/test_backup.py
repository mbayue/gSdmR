"""Tests for backup export/import endpoints."""

import io
import json
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

    db_path = str(tmp_path / "test_backup.db")
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
async def db_with_models(setup_db):
    """Set up database with models and provider mappings for export tests."""
    import aiosqlite

    db = await aiosqlite.connect(setup_db)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        # Create a model
        cursor = await db.execute("INSERT INTO models (name) VALUES (?)", ("gpt-4",))
        model_id = cursor.lastrowid

        # Get bluesminds provider id
        cursor = await db.execute(
            "SELECT id FROM providers WHERE name = ?", ("bluesminds",)
        )
        provider_row = await cursor.fetchone()
        provider_id = provider_row["id"]

        # Create model-provider mapping
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (model_id, provider_id, "gpt-4-turbo", 1),
        )

        # Create an API key with model restriction
        await db.execute(
            "INSERT INTO api_keys (key_value, name, is_active) VALUES (?, ?, ?)",
            ("sk-gsdm-test-export-key", "export-test-key", 1),
        )
        cursor = await db.execute(
            "SELECT id FROM api_keys WHERE key_value = ?",
            ("sk-gsdm-test-export-key",),
        )
        key_row = await cursor.fetchone()
        await db.execute(
            "INSERT INTO api_key_models (api_key_id, model_id) VALUES (?, ?)",
            (key_row["id"], model_id),
        )

        await db.commit()
    finally:
        await db.close()

    return setup_db


@pytest.mark.asyncio
class TestExport:
    """Tests for GET /api/backup/export."""

    async def test_export_returns_valid_structure(self, client, auth_headers):
        """Export returns JSON with version, providers, models, api_keys."""
        response = await client.get("/api/backup/export?password=admin", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0"
        assert "providers" in data
        assert "models" in data
        assert "api_keys" in data
        assert isinstance(data["providers"], list)
        assert isinstance(data["models"], list)
        assert isinstance(data["api_keys"], list)

    async def test_export_includes_provider_api_keys_unmasked(
        self, client, auth_headers
    ):
        """Export includes full (not masked) provider API keys."""
        response = await client.get("/api/backup/export?password=admin", headers=auth_headers)
        data = response.json()
        # Check that at least one provider has a full api_key (not masked)
        for provider in data["providers"]:
            assert "api_key" in provider
            # Should not contain asterisks (masked values)
            assert "*" not in provider["api_key"]

    async def test_export_includes_model_provider_mappings(
        self, client, auth_headers, db_with_models
    ):
        """Export includes model provider mappings with provider_model."""
        response = await client.get("/api/backup/export?password=admin", headers=auth_headers)
        data = response.json()
        gpt4 = next((m for m in data["models"] if m["name"] == "gpt-4"), None)
        assert gpt4 is not None
        assert len(gpt4["providers"]) >= 1
        mapping = gpt4["providers"][0]
        assert "provider_name" in mapping
        assert "provider_model" in mapping
        assert "priority" in mapping
        assert mapping["provider_model"] == "gpt-4-turbo"

    async def test_export_includes_api_key_restrictions(
        self, client, auth_headers, db_with_models
    ):
        """Export includes api key model restrictions."""
        response = await client.get("/api/backup/export?password=admin", headers=auth_headers)
        data = response.json()
        test_key = next(
            (k for k in data["api_keys"] if k["name"] == "export-test-key"), None
        )
        assert test_key is not None
        assert "gpt-4" in test_key["allowed_models"]

    async def test_export_requires_auth(self, client):
        """GET /api/backup/export without auth returns 401."""
        response = await client.get("/api/backup/export?password=admin")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestImport:
    """Tests for POST /api/backup/import."""

    async def test_import_creates_new_providers(self, client, auth_headers):
        """Importing a valid file creates new providers."""
        import_data = {
            "version": "1.0",
            "providers": [
                {
                    "name": "new-import-provider",
                    "base_url": "http://import.test/v1",
                    "api_key": "sk-imported-key",
                    "is_active": True,
                }
            ],
            "models": [],
            "api_keys": [],
        }
        files = {"file": ("backup.json", json.dumps(import_data).encode(), "application/json")}
        response = await client.post(
            "/api/backup/import", headers=auth_headers, files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"]["providers"] == 1

        # Verify provider was created
        export_resp = await client.get("/api/backup/export?password=admin", headers=auth_headers)
        provider_names = [p["name"] for p in export_resp.json()["providers"]]
        assert "new-import-provider" in provider_names

    async def test_import_updates_existing_providers(self, client, auth_headers):
        """Importing updates existing providers by name."""
        import_data = {
            "version": "1.0",
            "providers": [
                {
                    "name": "bluesminds",
                    "base_url": "http://updated-url.com/v1",
                    "api_key": "sk-updated-key",
                    "is_active": False,
                }
            ],
            "models": [],
            "api_keys": [],
        }
        files = {"file": ("backup.json", json.dumps(import_data).encode(), "application/json")}
        response = await client.post(
            "/api/backup/import", headers=auth_headers, files=files
        )
        assert response.status_code == 200

        # Verify provider was updated
        export_resp = await client.get("/api/backup/export?password=admin", headers=auth_headers)
        bluesminds = next(
            p for p in export_resp.json()["providers"] if p["name"] == "bluesminds"
        )
        assert bluesminds["base_url"] == "http://updated-url.com/v1"
        assert bluesminds["api_key"] == "sk-updated-key"

    async def test_import_creates_models_with_mappings(self, client, auth_headers):
        """Importing creates models with provider mappings."""
        import_data = {
            "version": "1.0",
            "providers": [],
            "models": [
                {
                    "name": "imported-model",
                    "providers": [
                        {
                            "provider_name": "bluesminds",
                            "provider_model": "gpt-4-imported",
                            "priority": 1,
                        }
                    ],
                }
            ],
            "api_keys": [],
        }
        files = {"file": ("backup.json", json.dumps(import_data).encode(), "application/json")}
        response = await client.post(
            "/api/backup/import", headers=auth_headers, files=files
        )
        assert response.status_code == 200
        assert response.json()["imported"]["models"] == 1

        # Verify model with mappings
        export_resp = await client.get("/api/backup/export?password=admin", headers=auth_headers)
        model = next(
            (m for m in export_resp.json()["models"] if m["name"] == "imported-model"),
            None,
        )
        assert model is not None
        assert len(model["providers"]) == 1
        assert model["providers"][0]["provider_model"] == "gpt-4-imported"

    async def test_import_creates_api_keys_with_restrictions(
        self, client, auth_headers
    ):
        """Importing creates API keys with model restrictions."""
        # First import a model
        import_data = {
            "version": "1.0",
            "providers": [],
            "models": [{"name": "restricted-model", "providers": []}],
            "api_keys": [
                {
                    "key_value": "sk-gsdm-imported-key-123",
                    "name": "imported-key",
                    "is_active": True,
                    "allowed_models": ["restricted-model"],
                }
            ],
        }
        files = {"file": ("backup.json", json.dumps(import_data).encode(), "application/json")}
        response = await client.post(
            "/api/backup/import", headers=auth_headers, files=files
        )
        assert response.status_code == 200
        assert response.json()["imported"]["api_keys"] == 1

        # Verify key with restrictions
        export_resp = await client.get("/api/backup/export?password=admin", headers=auth_headers)
        imp_key = next(
            (k for k in export_resp.json()["api_keys"] if k["name"] == "imported-key"),
            None,
        )
        assert imp_key is not None
        assert "restricted-model" in imp_key["allowed_models"]

    async def test_import_invalid_json_returns_400(self, client, auth_headers):
        """Importing invalid JSON returns 400."""
        files = {"file": ("backup.json", b"not valid json {{{", "application/json")}
        response = await client.post(
            "/api/backup/import", headers=auth_headers, files=files
        )
        assert response.status_code == 400

    async def test_import_missing_version_returns_400(self, client, auth_headers):
        """Importing JSON without version field returns 400."""
        import_data = {"providers": [], "models": [], "api_keys": []}
        files = {"file": ("backup.json", json.dumps(import_data).encode(), "application/json")}
        response = await client.post(
            "/api/backup/import", headers=auth_headers, files=files
        )
        assert response.status_code == 400

    async def test_import_requires_auth(self, client):
        """POST /api/backup/import without auth returns 401."""
        import_data = {"version": "1.0", "providers": [], "models": [], "api_keys": []}
        files = {"file": ("backup.json", json.dumps(import_data).encode(), "application/json")}
        response = await client.post("/api/backup/import", files=files)
        assert response.status_code == 401

