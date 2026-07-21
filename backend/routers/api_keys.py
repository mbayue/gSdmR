"""API Key management CRUD routes."""

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from database import get_db
from services.auth import get_current_user

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1)
    model_ids: List[int] = []  # empty = all models allowed


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None
    model_ids: Optional[List[int]] = None


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_preview: str  # first 8 chars + "..."
    is_active: bool
    allowed_models: List[dict]  # [{id, name}] or empty = all
    created_at: str


def generate_api_key() -> str:
    """Generate a random API key with 'sk-gsdm' prefix."""
    return "sk-gsdm" + secrets.token_hex(24)


async def _get_allowed_models(db, api_key_id: int) -> list[dict]:
    """Get models allowed for an API key."""
    cursor = await db.execute(
        """
        SELECT m.id, m.name
        FROM api_key_models akm
        JOIN models m ON m.id = akm.model_id
        WHERE akm.api_key_id = ?
        ORDER BY m.name
        """,
        (api_key_id,),
    )
    rows = await cursor.fetchall()
    return [{"id": row["id"], "name": row["name"]} for row in rows]


async def _build_key_response(db, row) -> dict:
    """Build API key response with allowed models."""
    allowed_models = await _get_allowed_models(db, row["id"])
    key_value = row["key_value"]
    preview = key_value[:12] + "..." if len(key_value) > 12 else key_value
    return {
        "id": row["id"],
        "name": row["name"],
        "key_preview": preview,
        "is_active": bool(row["is_active"]),
        "allowed_models": allowed_models,
        "created_at": row["created_at"],
    }


@router.get("")
async def list_api_keys(username: str = Depends(get_current_user)):
    """List all API keys with their allowed models."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM api_keys ORDER BY id")
        rows = await cursor.fetchall()
        return [await _build_key_response(db, row) for row in rows]
    finally:
        await db.close()


@router.post("", status_code=201)
async def create_api_key(
    body: ApiKeyCreate, username: str = Depends(get_current_user)
):
    """Create a new API key. Returns the full key value (only shown once)."""
    db = await get_db()
    try:
        key_value = generate_api_key()

        cursor = await db.execute(
            "INSERT INTO api_keys (key_value, name) VALUES (?, ?)",
            (key_value, body.name),
        )
        key_id = cursor.lastrowid

        # Insert model restrictions
        for model_id in body.model_ids:
            # Verify model exists
            check = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
            if not await check.fetchone():
                raise HTTPException(status_code=400, detail=f"Model with id {model_id} does not exist")
            await db.execute(
                "INSERT INTO api_key_models (api_key_id, model_id) VALUES (?, ?)",
                (key_id, model_id),
            )

        await db.commit()

        # Return full key (only time it's shown)
        cursor = await db.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
        row = await cursor.fetchone()
        allowed_models = await _get_allowed_models(db, key_id)

        return {
            "id": row["id"],
            "name": row["name"],
            "key_value": key_value,  # full key shown once
            "is_active": True,
            "allowed_models": allowed_models,
            "created_at": row["created_at"],
        }
    finally:
        await db.close()


@router.put("/{key_id}")
async def update_api_key(
    key_id: int, body: ApiKeyUpdate, username: str = Depends(get_current_user)
):
    """Update an API key's name, active status, or model restrictions."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
        existing = await cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="API key not found")

        if body.name is not None:
            await db.execute("UPDATE api_keys SET name = ? WHERE id = ?", (body.name, key_id))

        if body.is_active is not None:
            await db.execute("UPDATE api_keys SET is_active = ? WHERE id = ?", (int(body.is_active), key_id))

        if body.model_ids is not None:
            # Replace model restrictions
            await db.execute("DELETE FROM api_key_models WHERE api_key_id = ?", (key_id,))
            for model_id in body.model_ids:
                check = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
                if not await check.fetchone():
                    raise HTTPException(status_code=400, detail=f"Model with id {model_id} does not exist")
                await db.execute(
                    "INSERT INTO api_key_models (api_key_id, model_id) VALUES (?, ?)",
                    (key_id, model_id),
                )

        await db.commit()

        cursor = await db.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
        row = await cursor.fetchone()
        return await _build_key_response(db, row)
    finally:
        await db.close()


@router.delete("/{key_id}")
async def delete_api_key(
    key_id: int, username: str = Depends(get_current_user)
):
    """Delete an API key."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM api_keys WHERE id = ?", (key_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="API key not found")

        await db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        await db.commit()
        return {"message": "deleted"}
    finally:
        await db.close()
