"""Public status page endpoint — no authentication required."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from database import get_db
from services.health import get_health_status

router = APIRouter(tags=["status"])

_start_time = time.time()


@router.get("/api/status", include_in_schema=False)
async def get_status():
    """Public status page data — shows system health with uptime history."""
    db = await get_db()

    # Provider statuses with health history
    cursor = await db.execute("SELECT id, name, is_active FROM providers ORDER BY name")
    provider_rows = await cursor.fetchall()

    providers_status = []
    for prow in provider_rows:
        pid = prow["id"]

        # Get last 90 health checks for the bar chart
        cursor = await db.execute(
            """
            SELECT status, latency_ms, created_at
            FROM health_checks
            WHERE provider_id = ?
            ORDER BY created_at DESC
            LIMIT 90
            """,
            (pid,),
        )
        checks = await cursor.fetchall()
        history = [
            {"status": c["status"], "latency_ms": c["latency_ms"], "time": c["created_at"]}
            for c in reversed(checks)  # oldest first for left-to-right display
        ]

        # Current status from health service
        health_data = get_health_status()
        current = next((h for h in health_data if h["provider_id"] == pid), None)

        if current:
            status = current["status"]
            last_check = datetime.fromtimestamp(current["last_check"], tz=timezone.utc).isoformat() if current["last_check"] > 0 else None
        else:
            status = "active" if prow["is_active"] else "inactive"
            last_check = None

        # Calculate uptime percentage from history
        total_checks = len(history)
        healthy_checks = sum(1 for h in history if h["status"] == "healthy")
        uptime_pct = round((healthy_checks / total_checks) * 100, 1) if total_checks > 0 else 100.0

        # Average latency from recent healthy checks
        healthy_latencies = [h["latency_ms"] for h in history if h["status"] == "healthy" and h["latency_ms"] > 0]
        avg_latency = round(sum(healthy_latencies) / len(healthy_latencies)) if healthy_latencies else 0

        providers_status.append({
            "name": prow["name"],
            "status": status,
            "uptime_pct": uptime_pct,
            "avg_latency_ms": avg_latency,
            "last_check": last_check,
            "history": history,
        })

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
            "requests_last_hour": recent["total"],
            "success_rate_last_hour": round(recent["successful"] / recent["total"] * 100) if recent["total"] > 0 else 100,
            "avg_latency_ms": round(recent["avg_latency"]),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
