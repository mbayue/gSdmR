"""Provider CRUD API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from models.provider import ProviderCreate, ProviderResponse, ProviderUpdate
from services.auth import get_current_user
from services.masking import mask_api_key

router = APIRouter(prefix="/api/providers", tags=["providers"])


def row_to_provider_response(row) -> ProviderResponse:
    """Convert a database row to a ProviderResponse with masked API key."""
    return ProviderResponse(
        id=row["id"],
        name=row["name"],
        base_url=row["base_url"],
        api_key_masked=mask_api_key(row["api_key"]),
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


@router.get("", response_model=list[ProviderResponse])
async def list_providers(username: str = Depends(get_current_user)):
    """List all providers with masked API keys."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM providers ORDER BY id")
    rows = await cursor.fetchall()
    return [row_to_provider_response(row) for row in rows]


@router.post("", response_model=ProviderResponse, status_code=201)
async def create_provider(
    body: ProviderCreate, username: str = Depends(get_current_user)
):
    """Create a new provider."""
    db = await get_db()
    # Check for duplicate name
    cursor = await db.execute(
        "SELECT id FROM providers WHERE name = ?", (body.name,)
    )
    if await cursor.fetchone():
        raise HTTPException(
            status_code=409, detail=f"Provider '{body.name}' already exists"
        )

    cursor = await db.execute(
        """
        INSERT INTO providers (name, base_url, api_key)
        VALUES (?, ?, ?)
        """,
        (body.name, body.base_url, body.api_key),
    )
    await db.commit()

    # Fetch the created row
    cursor = await db.execute(
        "SELECT * FROM providers WHERE id = ?", (cursor.lastrowid,)
    )
    row = await cursor.fetchone()
    return row_to_provider_response(row)


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: int,
    body: ProviderUpdate,
    username: str = Depends(get_current_user),
):
    """Update an existing provider (partial update)."""
    db = await get_db()
    # Check provider exists
    cursor = await db.execute(
        "SELECT * FROM providers WHERE id = ?", (provider_id,)
    )
    existing = await cursor.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Build update fields
    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.base_url is not None:
        updates.append("base_url = ?")
        params.append(body.base_url)
    if body.api_key is not None:
        updates.append("api_key = ?")
        params.append(body.api_key)
    if body.is_active is not None:
        updates.append("is_active = ?")
        params.append(int(body.is_active))

    if not updates:
        # Nothing to update, return existing
        return row_to_provider_response(existing)

    updates.append("updated_at = datetime('now')")
    params.append(provider_id)

    await db.execute(
        f"UPDATE providers SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    await db.commit()

    # Fetch updated row
    cursor = await db.execute(
        "SELECT * FROM providers WHERE id = ?", (provider_id,)
    )
    row = await cursor.fetchone()
    return row_to_provider_response(row)


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int, username: str = Depends(get_current_user)
):
    """Delete a provider. Cascade removes associated model_providers entries."""
    db = await get_db()
    # Check provider exists
    cursor = await db.execute(
        "SELECT id FROM providers WHERE id = ?", (provider_id,)
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Provider not found")

    await db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
    await db.commit()
    return {"message": "deleted"}


@router.get("/{provider_id}/models")
async def list_provider_models(
    provider_id: int, username: str = Depends(get_current_user)
):
    """Fetch available models from a provider's /v1/models endpoint."""
    import httpx

    db = await get_db()
    cursor = await db.execute(
        "SELECT base_url, api_key FROM providers WHERE id = ?", (provider_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    base_url = row["base_url"].rstrip("/")
    api_key = row["api_key"]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                # OpenAI format: {"data": [{"id": "model-name", ...}]}
                models = data.get("data", [])
                return [{"id": m.get("id", m.get("name", "unknown"))} for m in models]
            else:
                return {"error": f"Provider returned {response.status_code}", "models": []}
    except httpx.RequestError as e:
        return {"error": f"Could not reach provider: {str(e)}", "models": []}


@router.get("/health-status")
async def get_provider_health(username: str = Depends(get_current_user)):
    """Get health check status for all providers."""
    from services.health import get_health_status
    return get_health_status()
