"""Tests for routing load balance modes (round-robin, weighted-random)."""

import os
import sys
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DB_PATH", ":memory:")

from services.routing import (
    get_providers_for_model,
    route_request,
    _order_providers,
    _round_robin_index,
)


@pytest_asyncio.fixture
async def setup_db(tmp_path):
    """Set up a temporary database with models using different load balance modes."""
    import config
    import database

    db_path = str(tmp_path / "test_routing_modes.db")
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

    db = await patched_get_db()
    try:
        # Create providers
        await db.execute(
            "INSERT INTO providers (id, name, base_url, api_key, is_active) VALUES (?, ?, ?, ?, ?)",
            (200, "provider-a", "https://a.test/v1", "sk-a", 1),
        )
        await db.execute(
            "INSERT INTO providers (id, name, base_url, api_key, is_active) VALUES (?, ?, ?, ?, ?)",
            (201, "provider-b", "https://b.test/v1", "sk-b", 1),
        )
        await db.execute(
            "INSERT INTO providers (id, name, base_url, api_key, is_active) VALUES (?, ?, ?, ?, ?)",
            (202, "provider-c", "https://c.test/v1", "sk-c", 1),
        )

        # Round-robin model
        await db.execute(
            "INSERT INTO models (id, name, load_balance) VALUES (?, ?, ?)",
            (300, "rr-model", "round-robin"),
        )
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (300, 200, "rr-model-a", 1),
        )
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (300, 201, "rr-model-b", 2),
        )
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (300, 202, "rr-model-c", 3),
        )

        # Weighted-random model
        await db.execute(
            "INSERT INTO models (id, name, load_balance) VALUES (?, ?, ?)",
            (301, "wr-model", "weighted-random"),
        )
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (301, 200, "wr-model-a", 1),
        )
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (301, 201, "wr-model-b", 2),
        )
        await db.execute(
            "INSERT INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
            (301, 202, "wr-model-c", 3),
        )

        await db.commit()
    finally:
        await db.close()

    # Clear round-robin state
    _round_robin_index.clear()

    yield db_path


@pytest.mark.asyncio
class TestRoundRobinMode:
    """Tests for round-robin load balancing."""

    async def test_returns_correct_load_balance_mode(self, setup_db):
        """Model with round-robin returns the correct mode."""
        providers, mode = await get_providers_for_model("rr-model")
        assert mode == "round-robin"
        assert len(providers) == 3

    async def test_rotates_starting_provider(self, setup_db):
        """Round-robin rotates which provider is tried first."""
        providers, _ = await get_providers_for_model("rr-model")

        # First call should start at index 0
        ordered1 = await _order_providers(providers, "round-robin", "rr-model")
        assert ordered1[0]["name"] == "provider-a"

        # Second call should start at index 1
        ordered2 = await _order_providers(providers, "round-robin", "rr-model")
        assert ordered2[0]["name"] == "provider-b"

        # Third call should start at index 2
        ordered3 = await _order_providers(providers, "round-robin", "rr-model")
        assert ordered3[0]["name"] == "provider-c"

    async def test_wraps_around_at_end(self, setup_db):
        """Round-robin wraps back to first provider after reaching the end."""
        providers, _ = await get_providers_for_model("rr-model")

        # Advance through all 3 providers
        await _order_providers(providers, "round-robin", "rr-model")  # 0
        await _order_providers(providers, "round-robin", "rr-model")  # 1
        await _order_providers(providers, "round-robin", "rr-model")  # 2

        # Fourth call wraps back to 0
        ordered = await _order_providers(providers, "round-robin", "rr-model")
        assert ordered[0]["name"] == "provider-a"

    async def test_includes_all_providers_as_fallback(self, setup_db):
        """Round-robin includes all providers in the ordered list (for fallback)."""
        providers, _ = await get_providers_for_model("rr-model")
        ordered = await _order_providers(providers, "round-robin", "rr-model")
        assert len(ordered) == 3
        # All providers present
        names = {p["name"] for p in ordered}
        assert names == {"provider-a", "provider-b", "provider-c"}

    @patch("services.proxy_client.forward_to_provider")
    async def test_route_request_uses_round_robin(self, mock_forward, setup_db):
        """route_request with round-robin model rotates starting provider."""
        success_response = JSONResponse(status_code=200, content={"ok": True})
        mock_forward.return_value = (True, success_response)

        # First request
        await route_request("rr-model", {"model": "rr-model", "messages": []}, "chat/completions")
        first_call_body = mock_forward.call_args.kwargs["request_body"]
        first_model = first_call_body["model"]

        mock_forward.reset_mock()

        # Second request
        await route_request("rr-model", {"model": "rr-model", "messages": []}, "chat/completions")
        second_call_body = mock_forward.call_args.kwargs["request_body"]
        second_model = second_call_body["model"]

        # Should have rotated
        assert first_model != second_model


@pytest.mark.asyncio
class TestWeightedRandomMode:
    """Tests for weighted-random load balancing."""

    async def test_returns_correct_load_balance_mode(self, setup_db):
        """Model with weighted-random returns the correct mode."""
        providers, mode = await get_providers_for_model("wr-model")
        assert mode == "weighted-random"
        assert len(providers) == 3

    async def test_returns_all_providers(self, setup_db):
        """Weighted-random returns all providers (order varies)."""
        providers, _ = await get_providers_for_model("wr-model")
        ordered = await _order_providers(providers, "weighted-random", "wr-model")
        assert len(ordered) == 3
        # All providers present regardless of order
        names = {p["name"] for p in ordered}
        assert names == {"provider-a", "provider-b", "provider-c"}

    async def test_order_varies_across_calls(self, setup_db):
        """Weighted-random produces varying orders (statistical test)."""
        providers, _ = await get_providers_for_model("wr-model")

        # Run enough iterations to see variation
        first_providers = set()
        for _ in range(50):
            ordered = await _order_providers(providers, "weighted-random", "wr-model")
            first_providers.add(ordered[0]["name"])

        # With 50 iterations and 3 providers, we should see at least 2 different first choices
        assert len(first_providers) >= 2

    @patch("services.proxy_client.forward_to_provider")
    async def test_falls_back_on_failure(self, mock_forward, setup_db):
        """Weighted-random falls back to next provider on failure."""
        success_response = JSONResponse(status_code=200, content={"ok": True})
        mock_forward.side_effect = [
            (False, {"error_type": "http_500", "status_code": 500, "body": {}}),
            (True, success_response),
        ]

        result = await route_request(
            "wr-model",
            {"model": "wr-model", "messages": []},
            "chat/completions",
        )
        assert result == success_response
        assert mock_forward.call_count == 2


@pytest.mark.asyncio
class TestOrderProvidersSingleProvider:
    """Edge cases for _order_providers with 0 or 1 providers."""

    async def test_empty_list_returns_empty(self, setup_db):
        """Empty provider list returns empty regardless of mode."""
        result = await _order_providers([], "round-robin", "test")
        assert result == []

    async def test_single_provider_returns_as_is(self, setup_db):
        """Single provider returns unchanged regardless of mode."""
        single = [{"id": 1, "name": "only", "priority": 1}]
        for mode in ["round-robin", "weighted-random", "priority"]:
            result = await _order_providers(single, mode, "test-single")
            assert result == single

    async def test_priority_mode_preserves_order(self, setup_db):
        """Priority mode returns providers in original (priority) order."""
        providers = [
            {"id": 1, "name": "first", "priority": 1},
            {"id": 2, "name": "second", "priority": 2},
            {"id": 3, "name": "third", "priority": 3},
        ]
        result = await _order_providers(providers, "priority", "test-priority")
        assert result[0]["name"] == "first"
        assert result[1]["name"] == "second"
        assert result[2]["name"] == "third"
