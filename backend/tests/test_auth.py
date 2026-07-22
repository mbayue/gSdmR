"""Tests for authentication routes: login, logout, and /me."""

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

    db_path = str(tmp_path / "test_auth.db")
    config.DB_PATH = db_path
    database.DB_PATH = db_path

    async def patched_get_db():
        import aiosqlite

        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    database.get_db = patched_get_db

    from routers import providers, models, api_keys, backup, proxy, auth
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
class TestLogin:
    """Tests for POST /api/auth/login."""

    async def test_login_success(self, client):
        """Login with correct credentials returns 200 and access token."""
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 0

    async def test_login_wrong_password(self, client):
        """Login with wrong password returns 401."""
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client):
        """Login with non-existent user returns 401."""
        response = await client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "whatever"},
        )
        assert response.status_code == 401

    async def test_login_missing_fields(self, client):
        """Login with missing fields returns 422."""
        response = await client.post("/api/auth/login", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
class TestLogout:
    """Tests for POST /api/auth/logout."""

    async def test_logout_returns_message(self, client):
        """Logout returns 200 with logged out message."""
        response = await client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json() == {"message": "logged out"}


@pytest.mark.asyncio
class TestGetMe:
    """Tests for GET /api/auth/me."""

    async def test_me_with_valid_token(self, client, auth_headers):
        """GET /me with valid token returns username."""
        response = await client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == {"username": "admin"}

    async def test_me_without_token(self, client):
        """GET /me without token returns 401."""
        response = await client.get("/api/auth/me")
        assert response.status_code == 401

    async def test_me_with_invalid_token(self, client):
        """GET /me with invalid token returns 401."""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid-token-here"},
        )
        assert response.status_code == 401

    async def test_me_with_expired_token(self, client):
        """GET /me with expired token returns 401."""
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone
        from config import JWT_SECRET, JWT_ALGORITHM

        # Create an already-expired token
        payload = {
            "sub": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    async def test_me_with_token_from_login(self, client):
        """Full flow: login then use token for /me."""
        login_resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        token = login_resp.json()["access_token"]

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"username": "admin"}


@pytest.mark.asyncio
class TestChangePassword:
    """Tests for PUT /api/auth/password."""

    async def test_change_password_success(self, client, auth_headers):
        """Changing password with correct current password succeeds."""
        response = await client.put(
            "/api/auth/password",
            headers=auth_headers,
            json={"current_password": "admin", "new_password": "newpass123"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Password updated successfully"

        # Verify new password works for login
        login_resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "newpass123"},
        )
        assert login_resp.status_code == 200

    async def test_change_password_wrong_current(self, client, auth_headers):
        """Changing password with wrong current password returns 401."""
        response = await client.put(
            "/api/auth/password",
            headers=auth_headers,
            json={"current_password": "wrongpass", "new_password": "newpass123"},
        )
        assert response.status_code == 401

    async def test_change_password_too_short(self, client, auth_headers):
        """New password shorter than 4 chars returns 422."""
        response = await client.put(
            "/api/auth/password",
            headers=auth_headers,
            json={"current_password": "admin", "new_password": "ab"},
        )
        assert response.status_code == 422

    async def test_change_password_requires_auth(self, client):
        """PUT /api/auth/password without auth returns 401."""
        response = await client.put(
            "/api/auth/password",
            json={"current_password": "admin", "new_password": "newpass"},
        )
        assert response.status_code == 401
