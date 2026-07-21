"""Export/Import endpoints for providers, models, and API keys."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from database import get_db
from services.auth import get_current_user

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/export")
async def export_all(username: str = Depends(get_current_user)):
    """Export all providers, models (with mappings), and API keys as JSON.

    Use this to back up configuration or migrate to another instance.
    """
    db = await get_db()
    try:
        # Export providers
        cursor = await db.execute("SELECT id, name, base_url, api_key, is_active FROM providers ORDER BY id")
        provider_rows = await cursor.fetchall()
        providers = [
            {
                "name": row["name"],
                "base_url": row["base_url"],
                "api_key": row["api_key"],
                "is_active": bool(row["is_active"]),
            }
            for row in provider_rows
        ]

        # Export models with provider mappings
        cursor = await db.execute("SELECT id, name FROM models ORDER BY id")
        model_rows = await cursor.fetchall()
        models = []
        for model_row in model_rows:
            cursor = await db.execute(
                """
                SELECT p.name AS provider_name, mp.provider_model, mp.priority
                FROM model_providers mp
                JOIN providers p ON p.id = mp.provider_id
                WHERE mp.model_id = ?
                ORDER BY mp.priority ASC
                """,
                (model_row["id"],),
            )
            mapping_rows = await cursor.fetchall()
            models.append({
                "name": model_row["name"],
                "providers": [
                    {
                        "provider_name": m["provider_name"],
                        "provider_model": m["provider_model"],
                        "priority": m["priority"],
                    }
                    for m in mapping_rows
                ],
            })

        # Export API keys with model restrictions
        cursor = await db.execute("SELECT id, key_value, name, is_active FROM api_keys ORDER BY id")
        key_rows = await cursor.fetchall()
        api_keys = []
        for key_row in key_rows:
            cursor = await db.execute(
                """
                SELECT m.name FROM api_key_models akm
                JOIN models m ON m.id = akm.model_id
                WHERE akm.api_key_id = ?
                """,
                (key_row["id"],),
            )
            model_names = [r["name"] for r in await cursor.fetchall()]
            api_keys.append({
                "key_value": key_row["key_value"],
                "name": key_row["name"],
                "is_active": bool(key_row["is_active"]),
                "allowed_models": model_names,  # empty = all
            })

        return {
            "version": "1.0",
            "providers": providers,
            "models": models,
            "api_keys": api_keys,
        }
    finally:
        await db.close()


@router.post("/import")
async def import_all(username: str = Depends(get_current_user), file: UploadFile = File(...)):
    """Import providers, models, and API keys from a JSON file.

    This merges with existing data:
    - Providers: insert or update by name
    - Models: insert or update by name (replaces provider mappings)
    - API keys: insert or update by key_value

    Use the JSON from /api/backup/export.
    """
    import json

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    if "version" not in data:
        raise HTTPException(status_code=400, detail="Missing version field — is this a valid export file?")

    db = await get_db()
    try:
        stats = {"providers": 0, "models": 0, "api_keys": 0}

        # Import providers
        for p in data.get("providers", []):
            cursor = await db.execute("SELECT id FROM providers WHERE name = ?", (p["name"],))
            existing = await cursor.fetchone()
            if existing:
                await db.execute(
                    "UPDATE providers SET base_url = ?, api_key = ?, is_active = ?, updated_at = datetime('now') WHERE name = ?",
                    (p["base_url"], p["api_key"], int(p.get("is_active", True)), p["name"]),
                )
            else:
                await db.execute(
                    "INSERT INTO providers (name, base_url, api_key, is_active) VALUES (?, ?, ?, ?)",
                    (p["name"], p["base_url"], p["api_key"], int(p.get("is_active", True))),
                )
            stats["providers"] += 1

        await db.commit()

        # Import models
        for m in data.get("models", []):
            cursor = await db.execute("SELECT id FROM models WHERE name = ?", (m["name"],))
            existing = await cursor.fetchone()
            if existing:
                model_id = existing["id"]
                # Replace mappings
                await db.execute("DELETE FROM model_providers WHERE model_id = ?", (model_id,))
                await db.execute(
                    "UPDATE models SET updated_at = datetime('now') WHERE id = ?", (model_id,)
                )
            else:
                cursor = await db.execute("INSERT INTO models (name) VALUES (?)", (m["name"],))
                model_id = cursor.lastrowid

            for mapping in m.get("providers", []):
                # Look up provider by name
                cursor = await db.execute(
                    "SELECT id FROM providers WHERE name = ?", (mapping["provider_name"],)
                )
                provider_row = await cursor.fetchone()
                if provider_row:
                    await db.execute(
                        "INSERT OR IGNORE INTO model_providers (model_id, provider_id, provider_model, priority) VALUES (?, ?, ?, ?)",
                        (model_id, provider_row["id"], mapping.get("provider_model", ""), mapping["priority"]),
                    )
            stats["models"] += 1

        await db.commit()

        # Import API keys
        for k in data.get("api_keys", []):
            cursor = await db.execute("SELECT id FROM api_keys WHERE key_value = ?", (k["key_value"],))
            existing = await cursor.fetchone()
            if existing:
                key_id = existing["id"]
                await db.execute(
                    "UPDATE api_keys SET name = ?, is_active = ? WHERE id = ?",
                    (k["name"], int(k.get("is_active", True)), key_id),
                )
                # Replace model restrictions
                await db.execute("DELETE FROM api_key_models WHERE api_key_id = ?", (key_id,))
            else:
                cursor = await db.execute(
                    "INSERT INTO api_keys (key_value, name, is_active) VALUES (?, ?, ?)",
                    (k["key_value"], k["name"], int(k.get("is_active", True))),
                )
                key_id = cursor.lastrowid

            # Set model restrictions
            for model_name in k.get("allowed_models", []):
                cursor = await db.execute("SELECT id FROM models WHERE name = ?", (model_name,))
                model_row = await cursor.fetchone()
                if model_row:
                    await db.execute(
                        "INSERT OR IGNORE INTO api_key_models (api_key_id, model_id) VALUES (?, ?)",
                        (key_id, model_row["id"]),
                    )
            stats["api_keys"] += 1

        await db.commit()

        return {
            "message": "Import successful",
            "imported": stats,
        }
    finally:
        await db.close()
