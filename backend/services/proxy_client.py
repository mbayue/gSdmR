"""Proxy client for forwarding requests to backend providers.

Handles request forwarding with timeout, streaming support,
response classification, and failure logging.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)


def _log_failure(provider_name: str, error_type: str) -> None:
    """Log a provider failure with provider name, error type, and timestamp."""
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.warning(
        "Provider failure: provider=%s error_type=%s timestamp=%s",
        provider_name,
        error_type,
        timestamp,
    )


async def forward_to_provider(
    provider: dict,
    request_body: dict,
    endpoint_path: str,
    is_streaming: bool = False,
    timeout: float = 30.0,
) -> tuple[bool, Any]:
    """Forward a request to a provider and return the result.

    Constructs the outgoing URL from provider base_url + endpoint_path,
    sets the Authorization header with the provider's API key, and
    classifies the response:
      - 2xx: success, returns (True, response)
      - 429 / 5xx: failure triggering fallback
      - Other 4xx: failure returned as-is to client
      - Timeout / connection error: failure triggering fallback

    Args:
        provider: Dict with keys id, name, base_url, api_key.
        request_body: The request body to forward as JSON.
        endpoint_path: The API path (e.g., "/chat/completions").
        is_streaming: Whether to use streaming response.
        timeout: Request timeout in seconds (default 30s).

    Returns:
        A tuple of (success: bool, result: Any).
        On success (2xx): (True, JSONResponse or StreamingResponse)
        On failure: (False, {"error_type": str, "status_code": int | None, "body": dict | None})
    """
    # Build the full URL
    base_url = provider["base_url"].rstrip("/")
    url = f"{base_url}/{endpoint_path.lstrip('/')}"

    # Construct outgoing headers with provider API key
    outgoing_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {provider['api_key']}",
    }

    try:
        if is_streaming:
            return await _forward_streaming(url, request_body, outgoing_headers, timeout, provider["name"])
        else:
            return await _forward_non_streaming(url, request_body, outgoing_headers, timeout, provider["name"])
    except httpx.TimeoutException:
        _log_failure(provider["name"], "timeout")
        return (False, {"error_type": "timeout", "status_code": None, "body": None})
    except httpx.RequestError:
        _log_failure(provider["name"], "connection_error")
        return (False, {"error_type": "connection_error", "status_code": None, "body": None})


async def _forward_non_streaming(
    url: str,
    request_body: dict,
    headers: dict,
    timeout: float,
    provider_name: str,
) -> tuple[bool, Any]:
    """Forward a non-streaming request and return classified result."""
    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
        response = await client.post(url, json=request_body, headers=headers)
        status = response.status_code

        # Parse body
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            body = {"raw": response.text}

        if 200 <= status < 300:
            return (True, JSONResponse(status_code=status, content=body))

        # Classify failure
        error_type = f"http_{status}"

        if status == 429 or status >= 500:
            # Retriable failures
            _log_failure(provider_name, error_type)
            return (False, {"error_type": error_type, "status_code": status, "body": body})

        # Other 4xx (not 429) - return as-is
        return (False, {"error_type": error_type, "status_code": status, "body": body})


async def _forward_streaming(
    url: str,
    request_body: dict,
    headers: dict,
    timeout: float,
    provider_name: str,
) -> tuple[bool, Any]:
    """Forward a streaming request.

    Opens a persistent connection, checks the status code, and if successful
    returns a StreamingResponse that streams chunks to the client.
    On error, reads the body and returns a failure tuple.
    """
    # Create a persistent client for the streaming connection
    client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0), verify=False)

    try:
        request = client.build_request("POST", url, json=request_body, headers=headers)
        response = await client.send(request, stream=True)
        status = response.status_code

        if 200 <= status < 300:
            # Success - return StreamingResponse that yields chunks and cleans up
            async def stream_generator():
                try:
                    async for chunk in response.aiter_bytes():
                        yield chunk
                finally:
                    await response.aclose()
                    await client.aclose()

            streaming_resp = StreamingResponse(
                stream_generator(),
                media_type="text/event-stream",
                status_code=status,
            )
            return (True, streaming_resp)

        # Non-success: read full error body and close
        body_bytes = await response.aread()
        await response.aclose()
        await client.aclose()

        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, ValueError):
            body = {"error": body_bytes.decode(errors="replace")}

        error_type = f"http_{status}"

        if status == 429 or status >= 500:
            _log_failure(provider_name, error_type)
            return (False, {"error_type": error_type, "status_code": status, "body": body})

        # Other 4xx - return as-is
        return (False, {"error_type": error_type, "status_code": status, "body": body})

    except httpx.TimeoutException:
        await client.aclose()
        _log_failure(provider_name, "timeout")
        return (False, {"error_type": "timeout", "status_code": None, "body": None})
    except httpx.RequestError:
        await client.aclose()
        _log_failure(provider_name, "connection_error")
        return (False, {"error_type": "connection_error", "status_code": None, "body": None})
