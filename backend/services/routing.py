"""Priority-based routing service with provider fallback logic."""

import logging
from typing import Any

from fastapi.responses import JSONResponse

from database import get_db

logger = logging.getLogger(__name__)


async def get_providers_for_model(model_name: str) -> list[dict]:
    """Query providers for a given model name, ordered by priority ASC.

    Returns a list of provider dicts with keys: id, name, base_url, api_key, provider_model.
    Returns an empty list if the model is not found or has no active providers.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT p.id, p.name, p.base_url, p.api_key, mp.provider_model
            FROM model_providers mp
            JOIN providers p ON p.id = mp.provider_id
            WHERE mp.model_id = (SELECT id FROM models WHERE name = ?)
            AND p.is_active = 1
            ORDER BY mp.priority ASC
            """,
            (model_name,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "base_url": row["base_url"],
                "api_key": row["api_key"],
                "provider_model": row["provider_model"],
            }
            for row in rows
        ]
    finally:
        await db.close()


def log_failure(provider_name: str, error_type: str, model_name: str) -> None:
    """Log a provider failure at WARNING level with required fields."""
    logger.warning(
        "Provider failure: provider=%s error_type=%s model=%s",
        provider_name,
        error_type,
        model_name,
    )


async def route_request(
    model_name: str,
    request_body: dict,
    endpoint_path: str,
    is_streaming: bool = False,
) -> Any:
    """Route a request to providers in priority order with fallback.

    Replaces the `model` field in the request body with the provider's actual
    model name before forwarding.
    """
    from services.proxy_client import forward_to_provider

    providers = await get_providers_for_model(model_name)

    if not providers:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "message": f"Model '{model_name}' not found or has no active providers",
                    "type": "model_not_found",
                    "code": 404,
                }
            },
        )

    attempted: set[int] = set()

    for provider in providers:
        if provider["id"] in attempted:
            continue
        attempted.add(provider["id"])

        # Replace model name with the provider's actual model
        forwarded_body = {**request_body, "model": provider["provider_model"]}

        success, result = await forward_to_provider(
            provider=provider,
            request_body=forwarded_body,
            endpoint_path=endpoint_path,
            is_streaming=is_streaming,
        )

        if success:
            return result

        error_type = result.get("error_type", "unknown") if isinstance(result, dict) else str(result)
        status_code = result.get("status_code") if isinstance(result, dict) else None

        if status_code and 400 <= status_code < 500 and status_code != 429:
            response_body = result.get("body", {"error": {"message": "Client error"}})
            return JSONResponse(status_code=status_code, content=response_body)

        log_failure(provider["name"], error_type, model_name)

    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "message": f"All providers for model '{model_name}' are unavailable",
                "type": "service_unavailable",
                "code": 503,
            }
        },
    )
