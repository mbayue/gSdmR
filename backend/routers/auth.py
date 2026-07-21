"""Dashboard authentication routes: login, logout, and current user."""

from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from models.user import LoginRequest, TokenResponse
from services.auth import create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate with username/password and return a JWT token."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT username, password_hash FROM users WHERE username = ?",
        (body.username,),
    )
    user = await cursor.fetchone()

    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user["username"])
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout():
    """Logout endpoint. Stateless JWT — client discards token."""
    return {"message": "logged out"}


@router.get("/me")
async def get_me(username: str = Depends(get_current_user)):
    """Return the current authenticated user's info."""
    return {"username": username}
