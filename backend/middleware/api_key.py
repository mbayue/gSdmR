"""API key authentication middleware (FastAPI dependency).

Extracts the API key from the Authorization Bearer header or x-api-key header
and validates it against active keys in the api_keys table.
Also checks per-key model restrictions.
"""

from fastapi import HTTPException, Request

from database import get_db


def _extract_key_from_headers(headers) -> str | None:
    """Extract API key from request headers.

    Checks in order:
    1. Authorization: Bearer <key>
    2. x-api-key: <key>

    Returns the key string or None if not found.
    """
    auth_header = headers.get("authorization")
    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()

    api_key_header = headers.get("x-api-key")
    if api_key_header:
        return api_key_header.strip()

    return None


async def _get_key_info(key: str) -> dict | None:
    """Get API key info from database. Returns dict with id, is_active or None."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, is_active FROM api_keys WHERE key_value = ?",
        (key,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return {"id": row["id"], "is_active": bool(row["is_active"])}


async def _get_allowed_model_names(api_key_id: int) -> list[str] | None:
    """Get allowed model names for a key. Returns None if no restrictions (all allowed)."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT m.name FROM api_key_models akm
        JOIN models m ON m.id = akm.model_id
        WHERE akm.api_key_id = ?
        """,
        (api_key_id,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return None  # No restrictions = all models allowed
    return [row["name"] for row in rows]


async def validate_api_key(request: Request) -> dict:
    """FastAPI dependency that validates API key authentication.

    Returns a dict with key info: {"key_id": int, "allowed_models": list|None}
    allowed_models is None if all models are allowed, or a list of allowed model names.
    """
    key = _extract_key_from_headers(request.headers)
    if not key:
        raise HTTPException(status_code=401, detail="API key required")

    key_info = await _get_key_info(key)
    if not key_info:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not key_info["is_active"]:
        raise HTTPException(status_code=401, detail="API key is disabled")

    allowed_models = await _get_allowed_model_names(key_info["id"])

    return {"key_id": key_info["id"], "allowed_models": allowed_models}
