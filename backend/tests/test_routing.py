"""Tests for the routing service (priority-based provider fallback)."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DB_PATH", ":memory:")

from services.routing import get_providers_for_model, route_request


@pytest_asyncio.fixture
async def setup_db(tmp_path):
    """Set up a temporary database for testing."""
    import config
    import database

    db_path = str(tmp_path / "test_routing.db")
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

    # Create models and providers with mappings
    db = await patched_get_db()
    try:
        # Create models
        cursor = await db.execute("INSERT INTO models (name) VALUES (?)", ("gpt-4",))
        model_id = cursor.lastrowid
        cursor = await db.execute(
            "INSERT INTO models (name) VALUES (?)", ("no-providers",)
        )

        # Get provider ids
        cursor = await db.execute(
            "SELECT id FROM providers WHERE name = ?", ("bluesminds",)
        )
        provider1_id = (await cursor.fetchone())["id"]

        cursor = await db.execute(
            "SELECT id FROM providers WHERE name = ?", ("freemodel",)
        )
        provider2_id = (await cursor.fetchone())["id"]

        # Create an inactive provider
        await db.execute(
            "INSERT INTO providers (name, base_url, api_key, is_active) VALUES (?, ?, ?, ?)",
            ("inactive-provider", "http://inactive.test/v1", "sk-inactive", 0),
        )
        cursor = await db.execute(
            "SELECT id FROM providers WHERE name = ?", ("inactive-provider",)
        )
        inactive_id = (await cursor.fetchone())["id"]

        # Map gpt-4 to multiple providers with priorities
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (model_id, provider1_id, "gpt-4-turbo", 1),
        )
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (model_id, provider2_id, "gpt-4-free", 2),
        )
        # Inactive provider at priority 3
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (model_id, inactive_id, "gpt-4-inactive", 3),
        )

        await db.commit()
    finally:
        await db.close()

    yield db_path


@pytest.mark.asyncio
class TestGetProvidersForModel:
    """Tests for get_providers_for_model."""

    async def test_returns_providers_ordered_by_priority(self, setup_db):
        """Returns providers for existing model ordered by priority ASC."""
        providers, mode = await get_providers_for_model("gpt-4")
        assert len(providers) == 2  # excludes inactive
        assert providers[0]["name"] == "bluesminds"
        assert providers[0]["provider_model"] == "gpt-4-turbo"
        assert providers[1]["name"] == "freemodel"
        assert providers[1]["provider_model"] == "gpt-4-free"
        assert mode == "priority"

    async def test_nonexistent_model_returns_empty(self, setup_db):
        """Non-existent model returns empty list."""
        providers, mode = await get_providers_for_model("nonexistent-model")
        assert providers == []

    async def test_model_with_no_providers_returns_empty(self, setup_db):
        """Model with no provider mappings returns empty list."""
        providers, mode = await get_providers_for_model("no-providers")
        assert providers == []

    async def test_skips_inactive_providers(self, setup_db):
        """Inactive providers are excluded from results."""
        providers, _ = await get_providers_for_model("gpt-4")
        provider_names = [p["name"] for p in providers]
        assert "inactive-provider" not in provider_names

    async def test_provider_dict_has_required_keys(self, setup_db):
        """Each provider dict has id, name, base_url, api_key, provider_model."""
        providers, _ = await get_providers_for_model("gpt-4")
        for p in providers:
            assert "id" in p
            assert "name" in p
            assert "base_url" in p
            assert "api_key" in p
            assert "provider_model" in p


@pytest.mark.asyncio
class TestRouteRequest:
    """Tests for route_request."""

    @patch("services.proxy_client.forward_to_provider")
    async def test_no_providers_returns_404(self, mock_forward, setup_db):
        """When no providers are available for a model, returns 404."""
        result = await route_request(
            model_name="nonexistent",
            request_body={"model": "nonexistent", "messages": []},
            endpoint_path="chat/completions",
        )
        assert isinstance(result, JSONResponse)
        assert result.status_code == 404
        mock_forward.assert_not_called()

    @patch("services.proxy_client.forward_to_provider")
    async def test_successful_provider_returns_response(self, mock_forward, setup_db):
        """Successful provider call returns the response."""
        expected_response = JSONResponse(
            status_code=200, content={"choices": [{"message": {"content": "hi"}}]}
        )
        mock_forward.return_value = (True, expected_response)

        result = await route_request(
            model_name="gpt-4",
            request_body={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
            endpoint_path="chat/completions",
        )
        assert result == expected_response
        mock_forward.assert_called_once()

    @patch("services.proxy_client.forward_to_provider")
    async def test_failed_provider_falls_back_to_next(self, mock_forward, setup_db):
        """When first provider fails with retriable error, falls back to next."""
        success_response = JSONResponse(status_code=200, content={"choices": []})
        mock_forward.side_effect = [
            (False, {"error_type": "http_500", "status_code": 500, "body": {}}),
            (True, success_response),
        ]

        result = await route_request(
            model_name="gpt-4",
            request_body={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
            endpoint_path="chat/completions",
        )
        assert result == success_response
        assert mock_forward.call_count == 2

    @patch("services.proxy_client.forward_to_provider")
    async def test_all_providers_fail_returns_503(self, mock_forward, setup_db):
        """When all providers fail, returns 503."""
        mock_forward.return_value = (
            False,
            {"error_type": "timeout", "status_code": None, "body": None},
        )

        result = await route_request(
            model_name="gpt-4",
            request_body={"model": "gpt-4", "messages": []},
            endpoint_path="chat/completions",
        )
        assert isinstance(result, JSONResponse)
        assert result.status_code == 503
        assert mock_forward.call_count == 2  # 2 active providers

    @patch("services.proxy_client.forward_to_provider")
    async def test_replaces_model_name_with_provider_model(
        self, mock_forward, setup_db
    ):
        """The model field in request body is replaced with provider_model."""
        mock_forward.return_value = (True, JSONResponse(status_code=200, content={}))

        await route_request(
            model_name="gpt-4",
            request_body={"model": "gpt-4", "messages": []},
            endpoint_path="chat/completions",
        )

        # Check the body passed to forward_to_provider has provider_model
        call_kwargs = mock_forward.call_args
        forwarded_body = call_kwargs.kwargs["request_body"]
        assert forwarded_body["model"] == "gpt-4-turbo"  # first provider's model

    @patch("services.proxy_client.forward_to_provider")
    async def test_4xx_error_not_429_returns_immediately(
        self, mock_forward, setup_db
    ):
        """4xx errors (not 429) are returned immediately without fallback."""
        mock_forward.return_value = (
            False,
            {
                "error_type": "http_400",
                "status_code": 400,
                "body": {"error": {"message": "bad request from provider"}},
            },
        )

        result = await route_request(
            model_name="gpt-4",
            request_body={"model": "gpt-4", "messages": []},
            endpoint_path="chat/completions",
        )
        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
        # Should NOT fall back to the second provider
        assert mock_forward.call_count == 1

    @patch("services.proxy_client.forward_to_provider")
    async def test_429_error_triggers_fallback(self, mock_forward, setup_db):
        """429 errors trigger fallback to the next provider."""
        success_response = JSONResponse(status_code=200, content={"choices": []})
        mock_forward.side_effect = [
            (False, {"error_type": "http_429", "status_code": 429, "body": {}}),
            (True, success_response),
        ]

        result = await route_request(
            model_name="gpt-4",
            request_body={"model": "gpt-4", "messages": []},
            endpoint_path="chat/completions",
        )
        assert result == success_response
        assert mock_forward.call_count == 2

    @patch("services.proxy_client.forward_to_provider")
    async def test_streaming_flag_passed_through(self, mock_forward, setup_db):
        """is_streaming flag is passed to forward_to_provider."""
        mock_forward.return_value = (True, JSONResponse(status_code=200, content={}))

        await route_request(
            model_name="gpt-4",
            request_body={"model": "gpt-4", "messages": [], "stream": True},
            endpoint_path="chat/completions",
            is_streaming=True,
        )

        call_kwargs = mock_forward.call_args
        assert call_kwargs.kwargs["is_streaming"] is True
