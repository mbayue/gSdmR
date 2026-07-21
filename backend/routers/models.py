"""Model CRUD API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from models.model import ModelCreate, ModelResponse, ModelUpdate
from services.auth import get_current_user

router = APIRouter(prefix="/api/models", tags=["models"])


async def _get_model_providers(db, model_id: int) -> list[dict]:
    """Fetch provider mappings for a model, sorted by priority."""
    cursor = await db.execute(
        """
        SELECT mp.provider_id, p.name AS provider_name, mp.provider_model, mp.priority
        FROM model_providers mp
        JOIN providers p ON p.id = mp.provider_id
        WHERE mp.model_id = ?
        ORDER BY mp.priority ASC
        """,
        (model_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "provider_id": row["provider_id"],
            "provider_name": row["provider_name"],
            "provider_model": row["provider_model"],
            "priority": row["priority"],
        }
        for row in rows
    ]


async def _build_model_response(db, model_row) -> ModelResponse:
    """Build a ModelResponse from a model row with its provider mappings."""
    providers = await _get_model_providers(db, model_row["id"])
    return ModelResponse(
        id=model_row["id"],
        name=model_row["name"],
        providers=providers,
        created_at=datetime.fromisoformat(model_row["created_at"]),
        updated_at=datetime.fromisoformat(model_row["updated_at"]),
    )


async def _validate_providers(db, providers) -> None:
    """Validate provider mappings: unique priorities and existing provider_ids."""
    priorities = [p.priority for p in providers]
    if len(priorities) != len(set(priorities)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate priority values are not allowed for the same model",
        )

    for mapping in providers:
        cursor = await db.execute(
            "SELECT id FROM providers WHERE id = ?", (mapping.provider_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"Provider with id {mapping.provider_id} does not exist",
            )


@router.get("", response_model=list[ModelResponse])
async def list_models(username: str = Depends(get_current_user)):
    """List all models with their provider mappings sorted by priority."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM models ORDER BY id")
    rows = await cursor.fetchall()
    return [await _build_model_response(db, row) for row in rows]


@router.post("", response_model=ModelResponse, status_code=201)
async def create_model(
    body: ModelCreate, username: str = Depends(get_current_user)
):
    """Create a new model with provider mappings."""
    db = await get_db()
    # Check for duplicate name
    cursor = await db.execute(
        "SELECT id FROM models WHERE name = ?", (body.name,)
    )
    if await cursor.fetchone():
        raise HTTPException(
            status_code=409, detail=f"Model '{body.name}' already exists"
        )

    await _validate_providers(db, body.providers)

    cursor = await db.execute(
        "INSERT INTO models (name) VALUES (?)",
        (body.name,),
    )
    model_id = cursor.lastrowid

    for mapping in body.providers:
        await db.execute(
            """
            INSERT INTO model_providers (model_id, provider_id, provider_model, priority)
            VALUES (?, ?, ?, ?)
            """,
            (model_id, mapping.provider_id, mapping.provider_model, mapping.priority),
        )

    await db.commit()

    cursor = await db.execute(
        "SELECT * FROM models WHERE id = ?", (model_id,)
    )
    row = await cursor.fetchone()
    return await _build_model_response(db, row)


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: int,
    body: ModelUpdate,
    username: str = Depends(get_current_user),
):
    """Update an existing model (name and/or provider mappings)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM models WHERE id = ?", (model_id,)
    )
    existing = await cursor.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")

    has_updates = False

    if body.name is not None:
        cursor = await db.execute(
            "SELECT id FROM models WHERE name = ? AND id != ?",
            (body.name, model_id),
        )
        if await cursor.fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"Model '{body.name}' already exists",
            )
        await db.execute(
            "UPDATE models SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (body.name, model_id),
        )
        has_updates = True

    if body.providers is not None:
        if len(body.providers) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one provider mapping is required",
            )
        await _validate_providers(db, body.providers)

        await db.execute(
            "DELETE FROM model_providers WHERE model_id = ?", (model_id,)
        )
        for mapping in body.providers:
            await db.execute(
                """
                INSERT INTO model_providers (model_id, provider_id, provider_model, priority)
                VALUES (?, ?, ?, ?)
                """,
                (model_id, mapping.provider_id, mapping.provider_model, mapping.priority),
            )
        has_updates = True

    if has_updates:
        await db.execute(
            "UPDATE models SET updated_at = datetime('now') WHERE id = ?",
            (model_id,),
        )
        await db.commit()

    cursor = await db.execute(
        "SELECT * FROM models WHERE id = ?", (model_id,)
    )
    row = await cursor.fetchone()
    return await _build_model_response(db, row)


@router.delete("/{model_id}")
async def delete_model(
    model_id: int, username: str = Depends(get_current_user)
):
    """Delete a model. CASCADE removes associated model_providers entries."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id FROM models WHERE id = ?", (model_id,)
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Model not found")

    await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
    await db.commit()
    return {"message": "deleted"}
