"""Usage logging service — records API request metrics to the database."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from database import get_db


@dataclass
class UsageRecord:
    """A single API usage record to be logged."""

    api_key_id: int
    model_name: str
    provider_name: Optional[str]
    endpoint: str
    status_code: int
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


async def log_usage(record: UsageRecord) -> None:
    """Insert a usage record into the database. Fire-and-forget."""
    db = await get_db()
    await db.execute(
        """
        INSERT INTO usage_logs
            (api_key_id, model_name, provider_name, endpoint, status_code,
             latency_ms, prompt_tokens, completion_tokens, total_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.api_key_id,
            record.model_name,
            record.provider_name,
            record.endpoint,
            record.status_code,
            record.latency_ms,
            record.prompt_tokens,
            record.completion_tokens,
            record.total_tokens,
        ),
    )
    await db.commit()


def extract_token_usage(response_body: dict) -> tuple[int, int, int]:
    """Extract token usage from an OpenAI/Anthropic response body.

    Returns (prompt_tokens, completion_tokens, total_tokens).
    """
    usage = response_body.get("usage", {})
    if usage:
        return (
            usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0),
            usage.get("completion_tokens", 0) or usage.get("output_tokens", 0),
            usage.get("total_tokens", 0),
        )
    return (0, 0, 0)


class RequestTimer:
    """Context manager to measure request latency."""

    def __init__(self) -> None:
        self.start_time: float = 0
        self.elapsed_ms: int = 0

    def __enter__(self) -> "RequestTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.elapsed_ms = int((time.perf_counter() - self.start_time) * 1000)
