"""Tests for proxy endpoints (chat/completions, messages, responses, models)."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi.responses import JSONResponse

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

    db_path = str(tmp_path / "test_proxy.db")
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

    # Create a model and provider mapping for testing
    db = await patched_get_db()
    try:
        cursor = await db.execute("INSERT INTO models (name) VALUES (?)", ("gpt-4",))
        model_id = cursor.lastrowid
        cursor = await db.execute("INSERT INTO models (name) VALUES (?)", ("claude-3",))
        model2_id = cursor.lastrowid

        cursor = await db.execute(
            "SELECT id FROM providers WHERE name = ?", ("bluesminds",)
        )
        provider_row = await cursor.fetchone()
        provider_id = provider_row["id"]

        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (model_id, provider_id, "gpt-4-turbo", 1),
        )
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (model2_id, provider_id, "claude-3-sonnet", 1),
        )

        # Create an API key with model restriction (only gpt-4)
        await db.execute(
            "INSERT INTO api_keys (key_value, name, is_active) VALUES (?, ?, ?)",
            ("sk-gsdm-restricted-key", "restricted", 1),
        )
        cursor = await db.execute(
            "SELECT id FROM api_keys WHERE key_value = ?",
            ("sk-gsdm-restricted-key",),
        )
        restricted_key_id = (await cursor.fetchone())["id"]
        await db.execute(
            "INSERT INTO api_key_models (api_key_id, model_id) VALUES (?, ?)",
            (restricted_key_id, model_id),
        )

        await db.commit()
    finally:
        await db.close()

    yield db_path


@pytest_asyncio.fixture
async def client(setup_db):
    """Async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
def api_key_header():
    """Return headers with default API key."""
    return {"Authorization": "Bearer sk-gsdm-default-key-change-me"}


@pytest_asyncio.fixture
def restricted_key_header():
    """Return headers with restricted API key."""
    return {"Authorization": "Bearer sk-gsdm-restricted-key"}


@pytest.mark.asyncio
class TestChatCompletions:
    """Tests for POST /v1/chat/completions."""

    async def test_without_api_key_returns_401(self, client):
        """Request without API key returns 401."""
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 401

    async def test_without_model_field_returns_400(self, client, api_key_header):
        """Request without model field returns 400."""
        response = await client.post(
            "/v1/chat/completions",
            headers=api_key_header,
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 422  # Pydantic validation

    @patch("routers.proxy.route_request")
    async def test_valid_request_calls_route_request(
        self, mock_route, client, api_key_header
    ):
        """Valid request routes to route_request."""
        mock_route.return_value = JSONResponse(
            status_code=200, content={"choices": [{"message": {"content": "hello"}}]}
        )
        response = await client.post(
            "/v1/chat/completions",
            headers=api_key_header,
            json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 200
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs["model_name"] == "gpt-4"
        assert call_kwargs.kwargs["endpoint_path"] == "chat/completions"

    async def test_model_access_denied_returns_403(self, client, restricted_key_header):
        """Request for model not allowed by key returns 403."""
        response = await client.post(
            "/v1/chat/completions",
            headers=restricted_key_header,
            json={
                "model": "claude-3",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert response.status_code == 403
        assert "permission_denied" in response.json()["error"]["type"]

    @patch("routers.proxy.route_request")
    async def test_restricted_key_allows_permitted_model(
        self, mock_route, client, restricted_key_header
    ):
        """Restricted key can access its allowed model."""
        mock_route.return_value = JSONResponse(
            status_code=200, content={"choices": []}
        )
        response = await client.post(
            "/v1/chat/completions",
            headers=restricted_key_header,
            json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 200
        mock_route.assert_called_once()


@pytest.mark.asyncio
class TestAnthropicMessages:
    """Tests for POST /v1/messages."""

    async def test_without_api_key_returns_401(self, client):
        """Request without API key returns 401."""
        response = await client.post(
            "/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 401

    @patch("routers.proxy.route_request")
    async def test_valid_request_calls_route_request(
        self, mock_route, client, api_key_header
    ):
        """Valid request routes to route_request with messages endpoint."""
        mock_route.return_value = JSONResponse(
            status_code=200, content={"content": [{"text": "hello"}]}
        )
        response = await client.post(
            "/v1/messages",
            headers=api_key_header,
            json={
                "model": "claude-3",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1024,
            },
        )
        assert response.status_code == 200
        mock_route.assert_called_once()
        assert mock_route.call_args.kwargs["endpoint_path"] == "messages"

    async def test_model_access_denied_returns_403(self, client, restricted_key_header):
        """Request for model not allowed returns 403."""
        response = await client.post(
            "/v1/messages",
            headers=restricted_key_header,
            json={
                "model": "claude-3",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 100,
            },
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestOpenAIResponses:
    """Tests for POST /v1/responses."""

    async def test_without_api_key_returns_401(self, client):
        """Request without API key returns 401."""
        response = await client.post(
            "/v1/responses",
            json={"model": "gpt-4", "input": "hello"},
        )
        assert response.status_code == 401

    @patch("routers.proxy.route_request")
    async def test_valid_request_calls_route_request(
        self, mock_route, client, api_key_header
    ):
        """Valid request routes to route_request with responses endpoint."""
        mock_route.return_value = JSONResponse(
            status_code=200, content={"output": [{"text": "hello"}]}
        )
        response = await client.post(
            "/v1/responses",
            headers=api_key_header,
            json={"model": "gpt-4", "input": "hello"},
        )
        assert response.status_code == 200
        mock_route.assert_called_once()
        assert mock_route.call_args.kwargs["endpoint_path"] == "responses"

    async def test_model_access_denied_returns_403(self, client, restricted_key_header):
        """Request for model not allowed returns 403."""
        response = await client.post(
            "/v1/responses",
            headers=restricted_key_header,
            json={"model": "claude-3", "input": "hi"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestListModels:
    """Tests for GET /v1/models."""

    async def test_without_api_key_returns_401(self, client):
        """Request without API key returns 401."""
        response = await client.get("/v1/models")
        assert response.status_code == 401

    async def test_returns_models_list(self, client, api_key_header):
        """Returns all models in OpenAI-compatible format."""
        response = await client.get("/v1/models", headers=api_key_header)
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)
        model_ids = [m["id"] for m in data["data"]]
        assert "gpt-4" in model_ids
        assert "claude-3" in model_ids

    async def test_respects_key_restrictions(self, client, restricted_key_header):
        """Restricted key only sees allowed models."""
        response = await client.get("/v1/models", headers=restricted_key_header)
        assert response.status_code == 200
        data = response.json()
        model_ids = [m["id"] for m in data["data"]]
        assert "gpt-4" in model_ids
        assert "claude-3" not in model_ids

    async def test_model_format(self, client, api_key_header):
        """Each model has expected fields."""
        response = await client.get("/v1/models", headers=api_key_header)
        data = response.json()
        for model in data["data"]:
            assert "id" in model
            assert model["object"] == "model"
            assert "created" in model
            assert model["owned_by"] == "router"

    async def test_disabled_key_returns_401(self, client, setup_db):
        """Disabled API key returns 401."""
        import aiosqlite

        # Disable the default key
        db = await aiosqlite.connect(setup_db)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            await db.execute(
                "UPDATE api_keys SET is_active = 0 WHERE key_value = ?",
                ("sk-gsdm-default-key-change-me",),
            )
            await db.commit()
        finally:
            await db.close()

        response = await client.get(
            "/v1/models",
            headers={"Authorization": "Bearer sk-gsdm-default-key-change-me"},
        )
        assert response.status_code == 401

    async def test_invalid_key_returns_401(self, client):
        """Invalid API key returns 401."""
        response = await client.get(
            "/v1/models",
            headers={"Authorization": "Bearer sk-invalid-key-xyz"},
        )
        assert response.status_code == 401

    async def test_x_api_key_header_works(self, client, setup_db):
        """x-api-key header works as an alternative."""
        response = await client.get(
            "/v1/models",
            headers={"x-api-key": "sk-gsdm-default-key-change-me"},
        )
        assert response.status_code == 200
