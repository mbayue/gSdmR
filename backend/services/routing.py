"""Priority-based routing service with provider fallback and load balancing."""

import asyncio
import logging
import random
from typing import Any

from fastapi.responses import JSONResponse

from database import get_db

logger = logging.getLogger(__name__)

# Round-robin state (model_name -> last used index)
_round_robin_index: dict[str, int] = {}
_round_robin_lock = asyncio.Lock()


async def get_providers_for_model(model_name: str) -> tuple[list[dict], str]:
    """Query providers for a given model name or alias, ordered by priority ASC.

    Returns (providers_list, load_balance_mode).
    """
    db = await get_db()

    # First try direct model name
    cursor = await db.execute(
        "SELECT id, load_balance FROM models WHERE name = ?",
        (model_name,),
    )
    model_row = await cursor.fetchone()

    # If not found, try as alias
    if not model_row:
        cursor = await db.execute(
            "SELECT model_id FROM model_aliases WHERE alias = ?",
            (model_name,),
        )
        alias_row = await cursor.fetchone()
        if alias_row:
            cursor = await db.execute(
                "SELECT id, load_balance FROM models WHERE id = ?",
                (alias_row["model_id"],),
            )
            model_row = await cursor.fetchone()

    if not model_row:
        return [], "priority"

    load_balance = model_row["load_balance"] or "priority"

    cursor = await db.execute(
        """
        SELECT p.id, p.name, p.base_url, p.api_key, mp.provider_model, mp.priority
        FROM model_providers mp
        JOIN providers p ON p.id = mp.provider_id
        WHERE mp.model_id = ?
        AND p.is_active = 1
        ORDER BY mp.priority ASC
        """,
        (model_row["id"],),
    )
    rows = await cursor.fetchall()
    providers = [
        {
            "id": row["id"],
            "name": row["name"],
            "base_url": row["base_url"],
            "api_key": row["api_key"],
            "provider_model": row["provider_model"],
            "priority": row["priority"],
        }
        for row in rows
    ]
    return providers, load_balance


async def _order_providers(providers: list[dict], mode: str, model_name: str) -> list[dict]:
    """Order providers based on load balancing mode."""
    if not providers or len(providers) <= 1:
        return providers

    if mode == "round-robin":
        async with _round_robin_lock:
            idx = _round_robin_index.get(model_name, -1) + 1
            if idx >= len(providers):
                idx = 0
            _round_robin_index[model_name] = idx
        return providers[idx:] + providers[:idx]

    elif mode == "weighted-random":
        # Weight by inverse priority (lower priority number = higher weight)
        max_priority = max(p["priority"] for p in providers)
        weights = [max_priority - p["priority"] + 1 for p in providers]
        # Shuffle based on weights — pick first randomly, rest as fallback
        ordered = []
        remaining = list(zip(providers, weights))
        while remaining:
            total = sum(w for _, w in remaining)
            r = random.uniform(0, total)
            cumulative = 0
            for i, (provider, weight) in enumerate(remaining):
                cumulative += weight
                if r <= cumulative:
                    ordered.append(provider)
                    remaining.pop(i)
                    break
        return ordered

    # Default: priority (already sorted)
    return providers


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
    """Route a request to providers with load balancing and fallback.

    Supports three modes:
    - priority: always try highest priority first, fall back in order
    - round-robin: rotate starting provider across requests
    - weighted-random: randomly select based on priority weights, fall back to rest
    """
    from services.proxy_client import forward_to_provider

    providers, load_balance = await get_providers_for_model(model_name)

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

    # Order providers based on load balancing mode
    ordered = await _order_providers(providers, load_balance, model_name)

    attempted: set[int] = set()

    for provider in ordered:
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
            provider_body = result.get("body", {})
            if isinstance(provider_body, dict) and "error" in provider_body:
                msg = provider_body["error"].get("message", "Provider returned an error")
            elif isinstance(provider_body, dict) and "message" in provider_body:
                msg = provider_body["message"]
            else:
                msg = str(provider_body) if provider_body else "Provider returned an error"

            return JSONResponse(
                status_code=status_code,
                content={
                    "error": {
                        "message": msg,
                        "type": "provider_error",
                        "code": status_code,
                        "provider": provider["name"],
                    }
                },
            )

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
