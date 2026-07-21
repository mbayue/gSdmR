"""Provider health check service — periodic ping with auto-disable on repeated failures."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from database import get_db

logger = logging.getLogger("gsdm_r.health")

# Config
CHECK_INTERVAL_SECONDS = 60  # check every 60 seconds
FAILURE_THRESHOLD = 3  # disable after 3 consecutive failures
RECOVERY_CHECK_INTERVAL = 300  # re-check disabled providers every 5 min


@dataclass
class ProviderHealth:
    """Track health state for a single provider."""

    provider_id: int
    name: str
    consecutive_failures: int = 0
    last_check: float = 0
    last_status: str = "unknown"  # "healthy", "unhealthy", "disabled"


# In-memory health state
_health_state: dict[int, ProviderHealth] = {}
_health_task: asyncio.Task | None = None


async def check_provider(provider_id: int, name: str, base_url: str, api_key: str) -> bool:
    """Ping a provider's /models endpoint to check if it's alive.

    Returns True if healthy, False if unhealthy.
    """
    url = f"{base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return 200 <= response.status_code < 500  # Any non-server-error means alive
    except (httpx.RequestError, httpx.TimeoutException):
        return False


async def run_health_checks() -> None:
    """Run a single round of health checks for all active providers."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, base_url, api_key, is_active FROM providers"
    )
    providers = await cursor.fetchall()

    now = time.time()

    for row in providers:
        provider_id = row["id"]
        is_active = bool(row["is_active"])
        auto_disabled = bool(row["auto_disabled"]) if "auto_disabled" in row.keys() else False

        # Initialize health state if new
        if provider_id not in _health_state:
            _health_state[provider_id] = ProviderHealth(
                provider_id=provider_id, name=row["name"]
            )

        state = _health_state[provider_id]

        # Skip recently checked
        if is_active and (now - state.last_check) < CHECK_INTERVAL_SECONDS:
            continue
        # Only re-check disabled providers that were auto-disabled
        if not is_active and not auto_disabled:
            continue
        if not is_active and (now - state.last_check) < RECOVERY_CHECK_INTERVAL:
            continue

        # Perform check
        healthy = await check_provider(
            provider_id, row["name"], row["base_url"], row["api_key"]
        )
        state.last_check = now

        if healthy:
            if state.consecutive_failures > 0:
                logger.info("Provider %s recovered (was at %d failures)", row["name"], state.consecutive_failures)
            state.consecutive_failures = 0
            state.last_status = "healthy"

            # Re-enable if it was auto-disabled by health checks
            if not is_active and auto_disabled:
                await db.execute(
                    "UPDATE providers SET is_active = 1, auto_disabled = 0, updated_at = datetime('now') WHERE id = ?",
                    (provider_id,),
                )
                await db.commit()
                logger.info("Provider %s auto-enabled after recovery", row["name"])
        else:
            state.consecutive_failures += 1
            state.last_status = "unhealthy"
            logger.warning(
                "Provider %s failed health check (%d/%d)",
                row["name"],
                state.consecutive_failures,
                FAILURE_THRESHOLD,
            )

            # Auto-disable on threshold
            if is_active and state.consecutive_failures >= FAILURE_THRESHOLD:
                await db.execute(
                    "UPDATE providers SET is_active = 0, auto_disabled = 1, updated_at = datetime('now') WHERE id = ?",
                    (provider_id,),
                )
                await db.commit()
                state.last_status = "disabled"
                logger.warning("Provider %s auto-disabled after %d failures", row["name"], FAILURE_THRESHOLD)


async def _health_check_loop() -> None:
    """Background loop that runs health checks periodically."""
    while True:
        try:
            await run_health_checks()
        except Exception as e:
            logger.error("Health check loop error: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def start_health_checks() -> None:
    """Start the background health check loop. Call during app startup."""
    global _health_task
    if _health_task is None or _health_task.done():
        _health_task = asyncio.create_task(_health_check_loop())
        logger.info("Health check loop started (interval=%ds, threshold=%d)", CHECK_INTERVAL_SECONDS, FAILURE_THRESHOLD)


def stop_health_checks() -> None:
    """Stop the background health check loop. Call during app shutdown."""
    global _health_task
    if _health_task and not _health_task.done():
        _health_task.cancel()
        _health_task = None
        logger.info("Health check loop stopped")


def get_health_status() -> list[dict]:
    """Get current health status for all tracked providers."""
    return [
        {
            "provider_id": s.provider_id,
            "name": s.name,
            "status": s.last_status,
            "consecutive_failures": s.consecutive_failures,
            "last_check": s.last_check,
        }
        for s in _health_state.values()
    ]
