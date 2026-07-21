"""Public status page endpoint — no authentication required."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from database import get_db
from services.health import get_health_status

router = APIRouter(tags=["status"])

# Track app start time for uptime calculation
_start_time = time.time()


@router.get("/status", include_in_schema=False)
async def get_status():
    """Public status page data — shows system health without exposing secrets."""
    db = await get_db()

    # Provider statuses
    health = get_health_status()
    providers_status = []
    for h in health:
        providers_status.append({
            "name": h["name"],
            "status": h["status"],
            "last_check": datetime.fromtimestamp(h["last_check"], tz=timezone.utc).isoformat() if h["last_check"] > 0 else None,
        })

    # If no health data yet, pull from DB
    if not providers_status:
        cursor = await db.execute("SELECT name, is_active FROM providers ORDER BY name")
        rows = await cursor.fetchall()
        providers_status = [
            {"name": row["name"], "status": "active" if row["is_active"] else "inactive", "last_check": None}
            for row in rows
        ]

    # Count models and keys
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM models")
    model_count = (await cursor.fetchone())["cnt"]

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM api_keys WHERE is_active = 1")
    active_keys = (await cursor.fetchone())["cnt"]

    # Recent request stats (last hour)
    cursor = await db.execute(
        """
        SELECT
            COUNT(*) as total,
            COALESCE(SUM(CASE WHEN status_code < 300 THEN 1 ELSE 0 END), 0) as successful,
            COALESCE(AVG(latency_ms), 0) as avg_latency
        FROM usage_logs
        WHERE created_at >= datetime('now', '-1 hour')
        """
    )
    recent = await cursor.fetchone()

    # Uptime
    uptime_seconds = int(time.time() - _start_time)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60

    # Overall status
    all_healthy = all(p["status"] == "healthy" for p in providers_status) if providers_status else True
    some_down = any(p["status"] in ("unhealthy", "disabled") for p in providers_status)

    if all_healthy:
        overall = "operational"
    elif some_down:
        overall = "degraded"
    else:
        overall = "operational"

    return {
        "status": overall,
        "uptime": f"{hours}h {minutes}m",
        "uptime_seconds": uptime_seconds,
        "providers": providers_status,
        "stats": {
            "models_configured": model_count,
            "active_api_keys": active_keys,
            "requests_last_hour": recent["total"],
            "success_rate_last_hour": round(recent["successful"] / recent["total"] * 100) if recent["total"] > 0 else 100,
            "avg_latency_ms": round(recent["avg_latency"]),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
