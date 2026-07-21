"""Usage statistics API routes."""

from fastapi import APIRouter, Depends, Query
from typing import Optional

from database import get_db
from services.auth import get_current_user

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def get_usage_stats(
    username: str = Depends(get_current_user),
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    api_key_id: Optional[int] = Query(None, description="Filter by API key ID"),
    model_name: Optional[str] = Query(None, description="Filter by model name"),
):
    """Get aggregated usage statistics.

    Returns total requests, tokens, and per-model/per-key breakdowns.
    """
    db = await get_db()
    # Build WHERE clause
    conditions = ["created_at >= datetime('now', ?)"]
    params: list = [f"-{days} days"]
    if api_key_id:
        conditions.append("api_key_id = ?")
        params.append(api_key_id)
    if model_name:
        conditions.append("model_name = ?")
        params.append(model_name)

    where = " AND ".join(conditions)

    # Total stats
    cursor = await db.execute(
        f"""
        SELECT
            COUNT(*) as total_requests,
            COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
            COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(AVG(latency_ms), 0) as avg_latency_ms,
            COALESCE(SUM(CASE WHEN status_code >= 200 AND status_code < 300 THEN 1 ELSE 0 END), 0) as successful,
            COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) as failed
        FROM usage_logs
        WHERE {where}
        """,
        params,
    )
    row = await cursor.fetchone()
    summary = {
        "total_requests": row["total_requests"],
        "total_prompt_tokens": row["total_prompt_tokens"],
        "total_completion_tokens": row["total_completion_tokens"],
        "total_tokens": row["total_tokens"],
        "avg_latency_ms": round(row["avg_latency_ms"]),
        "successful": row["successful"],
        "failed": row["failed"],
    }

    # Per-model breakdown
    cursor = await db.execute(
        f"""
        SELECT
            model_name,
            COUNT(*) as requests,
            COALESCE(SUM(total_tokens), 0) as tokens,
            COALESCE(AVG(latency_ms), 0) as avg_latency_ms
        FROM usage_logs
        WHERE {where}
        GROUP BY model_name
        ORDER BY requests DESC
        """,
        params,
    )
    by_model = [
        {
            "model": r["model_name"],
            "requests": r["requests"],
            "tokens": r["tokens"],
            "avg_latency_ms": round(r["avg_latency_ms"]),
        }
        for r in await cursor.fetchall()
    ]

    # Per-key breakdown
    cursor = await db.execute(
        f"""
        SELECT
            ul.api_key_id,
            ak.name as key_name,
            COUNT(*) as requests,
            COALESCE(SUM(ul.total_tokens), 0) as tokens
        FROM usage_logs ul
        LEFT JOIN api_keys ak ON ak.id = ul.api_key_id
        WHERE {where.replace('created_at', 'ul.created_at').replace('api_key_id', 'ul.api_key_id').replace('model_name', 'ul.model_name')}
        GROUP BY ul.api_key_id
        ORDER BY requests DESC
        """,
        params,
    )
    by_key = [
        {
            "key_id": r["api_key_id"],
            "key_name": r["key_name"] or "unknown",
            "requests": r["requests"],
            "tokens": r["tokens"],
        }
        for r in await cursor.fetchall()
    ]

    # Recent requests (last 20)
    cursor = await db.execute(
        f"""
        SELECT
            model_name, provider_name, endpoint, status_code,
            latency_ms, total_tokens, created_at
        FROM usage_logs
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT 20
        """,
        params,
    )
    recent = [
        {
            "model": r["model_name"],
            "provider": r["provider_name"],
            "endpoint": r["endpoint"],
            "status": r["status_code"],
            "latency_ms": r["latency_ms"],
            "tokens": r["total_tokens"],
            "time": r["created_at"],
        }
        for r in await cursor.fetchall()
    ]

    return {
        "period_days": days,
        "summary": summary,
        "by_model": by_model,
        "by_key": by_key,
        "recent": recent,
    }
