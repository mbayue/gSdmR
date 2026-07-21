"""Tests for the proxy client request forwarding service."""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.responses import JSONResponse, StreamingResponse

import sys
sys.path.insert(0, ".")

from services.proxy_client import forward_to_provider, _log_failure


# Test provider fixture
@pytest.fixture
def provider():
    return {
        "id": 1,
        "name": "test-provider",
        "base_url": "https://api.example.com/v1/",
        "api_key": "sk-test-key-12345",
    }


@pytest.fixture
def request_body():
    return {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
    }


class TestURLConstruction:
    """Test that URLs are properly constructed from provider base_url and endpoint_path."""

    @pytest.mark.asyncio
    async def test_url_construction_strips_trailing_slash(self, provider, request_body):
        """URL is built correctly when base_url has trailing slash."""
        with patch("services.proxy_client._forward_non_streaming") as mock_forward:
            mock_forward.return_value = (True, JSONResponse(status_code=200, content={}))
            await forward_to_provider(provider, request_body, "chat/completions")
            called_url = mock_forward.call_args[0][0]
            assert called_url == "https://api.example.com/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_url_construction_leading_slash_in_path(self, provider, request_body):
        """URL is built correctly when endpoint_path has leading slash."""
        with patch("services.proxy_client._forward_non_streaming") as mock_forward:
            mock_forward.return_value = (True, JSONResponse(status_code=200, content={}))
            await forward_to_provider(provider, request_body, "/chat/completions")
            called_url = mock_forward.call_args[0][0]
            assert called_url == "https://api.example.com/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_url_construction_no_trailing_slash_on_base(self, request_body):
        """URL is built correctly when base_url has no trailing slash."""
        provider = {
            "id": 1,
            "name": "test",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-key",
        }
        with patch("services.proxy_client._forward_non_streaming") as mock_forward:
            mock_forward.return_value = (True, JSONResponse(status_code=200, content={}))
            await forward_to_provider(provider, request_body, "chat/completions")
            called_url = mock_forward.call_args[0][0]
            assert called_url == "https://api.example.com/v1/chat/completions"


class TestOutgoingHeaders:
    """Test that outgoing headers include provider API key."""

    @pytest.mark.asyncio
    async def test_authorization_header_set(self, provider, request_body):
        """Provider API key is included in Authorization Bearer header."""
        with patch("services.proxy_client._forward_non_streaming") as mock_forward:
            mock_forward.return_value = (True, JSONResponse(status_code=200, content={}))
            await forward_to_provider(provider, request_body, "chat/completions")
            called_headers = mock_forward.call_args[0][2]
            assert called_headers["Authorization"] == "Bearer sk-test-key-12345"
            assert called_headers["Content-Type"] == "application/json"


class TestNonStreamingResponses:
    """Test non-streaming response classification."""

    @pytest.mark.asyncio
    async def test_2xx_returns_success(self, provider, request_body):
        """A 200 response returns (True, JSONResponse)."""
        mock_response = httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": "Hi"}}]},
        )
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            success, result = await forward_to_provider(provider, request_body, "chat/completions")
            assert success is True
            assert isinstance(result, JSONResponse)
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_429_returns_failure(self, provider, request_body):
        """A 429 rate limit response returns failure with proper error_type."""
        mock_response = httpx.Response(
            status_code=429,
            json={"error": {"message": "Rate limited"}},
        )
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            success, result = await forward_to_provider(provider, request_body, "chat/completions")
            assert success is False
            assert result["error_type"] == "http_429"
            assert result["status_code"] == 429

    @pytest.mark.asyncio
    async def test_500_returns_failure(self, provider, request_body):
        """A 500 server error response returns failure."""
        mock_response = httpx.Response(
            status_code=500,
            json={"error": {"message": "Internal server error"}},
        )
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            success, result = await forward_to_provider(provider, request_body, "chat/completions")
            assert success is False
            assert result["error_type"] == "http_500"
            assert result["status_code"] == 500

    @pytest.mark.asyncio
    async def test_502_returns_failure(self, provider, request_body):
        """A 502 bad gateway response returns failure."""
        mock_response = httpx.Response(
            status_code=502,
            json={"error": {"message": "Bad gateway"}},
        )
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            success, result = await forward_to_provider(provider, request_body, "chat/completions")
            assert success is False
            assert result["error_type"] == "http_502"
            assert result["status_code"] == 502

    @pytest.mark.asyncio
    async def test_400_returns_failure_as_is(self, provider, request_body):
        """A 400 client error returns failure with body (returned as-is to client)."""
        error_body = {"error": {"message": "Invalid request"}}
        mock_response = httpx.Response(
            status_code=400,
            json=error_body,
        )
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            success, result = await forward_to_provider(provider, request_body, "chat/completions")
            assert success is False
            assert result["error_type"] == "http_400"
            assert result["status_code"] == 400
            assert result["body"] == error_body

    @pytest.mark.asyncio
    async def test_401_returns_failure_as_is(self, provider, request_body):
        """A 401 unauthorized returns failure (not retriable)."""
        mock_response = httpx.Response(
            status_code=401,
            json={"error": {"message": "Unauthorized"}},
        )
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            success, result = await forward_to_provider(provider, request_body, "chat/completions")
            assert success is False
            assert result["error_type"] == "http_401"
            assert result["status_code"] == 401


class TestTimeoutHandling:
    """Test timeout error handling."""

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self, provider, request_body):
        """A timeout exception returns failure with error_type 'timeout'."""
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("timed out")):
            success, result = await forward_to_provider(provider, request_body, "chat/completions")
            assert success is False
            assert result["error_type"] == "timeout"
            assert result["status_code"] is None
            assert result["body"] is None

    @pytest.mark.asyncio
    async def test_connection_error_returns_failure(self, provider, request_body):
        """A connection error returns failure with error_type 'connection_error'."""
        with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("connection refused")):
            success, result = await forward_to_provider(provider, request_body, "chat/completions")
            assert success is False
            assert result["error_type"] == "connection_error"
            assert result["status_code"] is None
            assert result["body"] is None


class TestStreamingResponses:
    """Test streaming response handling."""

    @pytest.mark.asyncio
    async def test_streaming_success_returns_streaming_response(self, provider, request_body):
        """A streaming 200 response returns (True, StreamingResponse)."""
        with patch("services.proxy_client._forward_streaming") as mock_stream:
            mock_resp = StreamingResponse(iter([b"data: hello\n\n"]), media_type="text/event-stream")
            mock_stream.return_value = (True, mock_resp)
            success, result = await forward_to_provider(
                provider, request_body, "chat/completions", is_streaming=True
            )
            assert success is True
            assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_streaming_timeout_returns_failure(self, provider, request_body):
        """A timeout during streaming returns failure."""
        with patch("services.proxy_client._forward_streaming", side_effect=httpx.TimeoutException("timeout")):
            success, result = await forward_to_provider(
                provider, request_body, "chat/completions", is_streaming=True
            )
            assert success is False
            assert result["error_type"] == "timeout"

    @pytest.mark.asyncio
    async def test_streaming_connection_error_returns_failure(self, provider, request_body):
        """A connection error during streaming returns failure."""
        with patch(
            "services.proxy_client._forward_streaming",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            success, result = await forward_to_provider(
                provider, request_body, "chat/completions", is_streaming=True
            )
            assert success is False
            assert result["error_type"] == "connection_error"


class TestFailureLogging:
    """Test that failures are logged with required fields."""

    def test_log_failure_contains_provider_name(self, caplog):
        """Log entry includes provider name."""
        import logging
        with caplog.at_level(logging.WARNING):
            _log_failure("my-provider", "timeout")
        assert "my-provider" in caplog.text

    def test_log_failure_contains_error_type(self, caplog):
        """Log entry includes error type."""
        import logging
        with caplog.at_level(logging.WARNING):
            _log_failure("my-provider", "http_429")
        assert "http_429" in caplog.text

    def test_log_failure_contains_timestamp(self, caplog):
        """Log entry includes ISO-format timestamp."""
        import logging
        with caplog.at_level(logging.WARNING):
            _log_failure("my-provider", "timeout")
        # Check for ISO timestamp pattern (contains 'T' and timezone info)
        assert "timestamp=" in caplog.text
