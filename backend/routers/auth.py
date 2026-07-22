"""Dashboard authentication routes: login, logout, and current user."""

from fastapi import APIRouter, Depends, HTTPException, Request

from database import get_db
from models.user import LoginRequest, TokenResponse
from services.auth import create_access_token, get_current_user, verify_password, revoke_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Login rate limiting: 5 attempts per minute per IP
_login_attempts: dict[str, list[float]] = {}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60


def _check_login_rate(ip: str) -> bool:
    """Returns True if allowed, False if rate limited."""
    import time
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if t > now - LOGIN_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        return False
    attempts.append(now)
    return True


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    """Authenticate with username/password and return a JWT token."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_login_rate(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    db = await get_db()
    cursor = await db.execute(
        "SELECT username, password_hash FROM users WHERE username = ?",
        (body.username,),
    )
    user = await cursor.fetchone()

    # Always run bcrypt to prevent timing-based username enumeration
    dummy_hash = "$2b$12$000000000000000000000uGmWs0X8Y1GKqGKcVnRTCYVqKM1JxKi"
    password_hash = user["password_hash"] if user else dummy_hash
    password_valid = verify_password(body.password, password_hash)

    if user is None or not password_valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user["username"])
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(request: Request):
    """Logout — revokes the current token."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        revoke_token(token)
    return {"message": "logged out"}


@router.get("/me")
async def get_me(username: str = Depends(get_current_user)):
    """Return the current authenticated user's info."""
    return {"username": username}


from pydantic import BaseModel, Field
import bcrypt


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=4)


@router.put("/password")
async def change_password(body: ChangePasswordRequest, username: str = Depends(get_current_user)):
    """Change the current user's password."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT password_hash FROM users WHERE username = ?",
        (username,),
    )
    user = await cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = bcrypt.hashpw(
        body.new_password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    await db.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (new_hash, username),
    )
    await db.commit()

    return {"message": "Password updated successfully"}
