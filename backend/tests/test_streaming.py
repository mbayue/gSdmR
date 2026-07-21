"""Tests for the streaming path in proxy_client (_forward_streaming)."""

import json
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import httpx
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.proxy_client import _forward_streaming, forward_to_provider


@pytest.fixture
def provider():
    return {
        "id": 1,
        "name": "stream-provider",
        "base_url": "https://api.stream.com/v1",
        "api_key": "sk-stream-key",
    }


@pytest.fixture
def request_body():
    return {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }


@pytest.fixture
def headers():
    return {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-stream-key",
    }


class TestForwardStreaming:
    """Tests for _forward_streaming — streaming response path."""

    @pytest.mark.asyncio
    async def test_streaming_200_returns_streaming_response(self, request_body, headers):
        """A streaming 200 response returns (True, StreamingResponse)."""
        # Mock the async client and response
        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_bytes():
            yield b"data: {\"choices\": []}\n\n"
            yield b"data: [DONE]\n\n"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            success, result = await _forward_streaming(
                "https://api.stream.com/v1/chat/completions",
                request_body,
                headers,
                30.0,
                "stream-provider",
            )

        assert success is True
        assert isinstance(result, StreamingResponse)
        assert result.status_code == 200
        assert result.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_streaming_500_returns_failure(self, request_body, headers):
        """A streaming 500 response returns (False, error dict)."""
        error_body = json.dumps({"error": {"message": "Internal server error"}}).encode()

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.aread = AsyncMock(return_value=error_body)
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            success, result = await _forward_streaming(
                "https://api.stream.com/v1/chat/completions",
                request_body,
                headers,
                30.0,
                "stream-provider",
            )

        assert success is False
        assert result["error_type"] == "http_500"
        assert result["status_code"] == 500
        assert result["body"]["error"]["message"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_streaming_429_returns_failure(self, request_body, headers):
        """A streaming 429 response returns (False, error dict) for retry."""
        error_body = json.dumps({"error": {"message": "Rate limited"}}).encode()

        mock_response = AsyncMock()
        mock_response.status_code = 429
        mock_response.aread = AsyncMock(return_value=error_body)
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            success, result = await _forward_streaming(
                "https://api.stream.com/v1/chat/completions",
                request_body,
                headers,
                30.0,
                "stream-provider",
            )

        assert success is False
        assert result["error_type"] == "http_429"
        assert result["status_code"] == 429

    @pytest.mark.asyncio
    async def test_streaming_400_returns_failure_as_is(self, request_body, headers):
        """A streaming 400 response returns failure (not retriable)."""
        error_body = json.dumps({"error": {"message": "Bad request"}}).encode()

        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.aread = AsyncMock(return_value=error_body)
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            success, result = await _forward_streaming(
                "https://api.stream.com/v1/chat/completions",
                request_body,
                headers,
                30.0,
                "stream-provider",
            )

        assert success is False
        assert result["error_type"] == "http_400"
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_streaming_timeout_returns_failure(self, request_body, headers):
        """Timeout during streaming connection returns failure."""
        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            success, result = await _forward_streaming(
                "https://api.stream.com/v1/chat/completions",
                request_body,
                headers,
                30.0,
                "stream-provider",
            )

        assert success is False
        assert result["error_type"] == "timeout"
        assert result["status_code"] is None

    @pytest.mark.asyncio
    async def test_streaming_connection_error_returns_failure(self, request_body, headers):
        """Connection error during streaming returns failure."""
        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            success, result = await _forward_streaming(
                "https://api.stream.com/v1/chat/completions",
                request_body,
                headers,
                30.0,
                "stream-provider",
            )

        assert success is False
        assert result["error_type"] == "connection_error"
        assert result["status_code"] is None

    @pytest.mark.asyncio
    async def test_streaming_invalid_json_body_handled(self, request_body, headers):
        """Non-JSON error body in streaming is handled gracefully."""
        mock_response = AsyncMock()
        mock_response.status_code = 502
        mock_response.aread = AsyncMock(return_value=b"Bad Gateway")
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            success, result = await _forward_streaming(
                "https://api.stream.com/v1/chat/completions",
                request_body,
                headers,
                30.0,
                "stream-provider",
            )

        assert success is False
        assert result["error_type"] == "http_502"
        assert result["body"]["error"] == "Bad Gateway"


class TestForwardToProviderStreamingIntegration:
    """Integration tests: forward_to_provider with is_streaming=True."""

    @pytest.mark.asyncio
    async def test_forward_to_provider_calls_streaming_path(self, provider, request_body):
        """forward_to_provider with is_streaming=True routes to _forward_streaming."""
        with patch("services.proxy_client._forward_streaming") as mock_stream:
            mock_stream.return_value = (True, StreamingResponse(iter([b""]), media_type="text/event-stream"))
            success, result = await forward_to_provider(
                provider, request_body, "chat/completions", is_streaming=True
            )
            mock_stream.assert_called_once()
            assert success is True

    @pytest.mark.asyncio
    async def test_forward_to_provider_non_streaming_calls_correct_path(self, provider, request_body):
        """forward_to_provider with is_streaming=False routes to _forward_non_streaming."""
        with patch("services.proxy_client._forward_non_streaming") as mock_non_stream:
            from fastapi.responses import JSONResponse
            mock_non_stream.return_value = (True, JSONResponse(status_code=200, content={}))
            success, result = await forward_to_provider(
                provider, request_body, "chat/completions", is_streaming=False
            )
            mock_non_stream.assert_called_once()
            assert success is True
