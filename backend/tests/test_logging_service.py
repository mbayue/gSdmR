"""Tests for the structured logging service."""

import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.logging import StructuredFormatter, setup_logging, get_logger


class TestStructuredFormatter:
    """Tests for StructuredFormatter — JSON log output."""

    def setup_method(self):
        """Create a fresh formatter for each test."""
        self.formatter = StructuredFormatter()

    def test_format_produces_valid_json(self):
        """format() produces a valid JSON string."""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_log_entry_contains_timestamp(self):
        """Log entry contains timestamp field in ISO format."""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed
        # ISO format contains 'T' separator
        assert "T" in parsed["timestamp"]

    def test_log_entry_contains_level(self):
        """Log entry contains level field."""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning message",
            args=None,
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "WARNING"

    def test_log_entry_contains_logger_name(self):
        """Log entry contains logger name."""
        record = logging.LogRecord(
            name="gsdm_r.health",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Check complete",
            args=None,
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["logger"] == "gsdm_r.health"

    def test_log_entry_contains_message(self):
        """Log entry contains the formatted message."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "Hello world"

    def test_log_entry_includes_request_id_when_available(self):
        """Log entry includes request_id when set on the record."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Request handled",
            args=None,
            exc_info=None,
        )
        record.request_id = "req-abc-123"
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["request_id"] == "req-abc-123"

    def test_log_entry_excludes_request_id_when_not_available(self):
        """Log entry does NOT include request_id when not set."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="No request context",
            args=None,
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert "request_id" not in parsed

    def test_log_entry_includes_extra_data_when_available(self):
        """Log entry includes extra_data fields merged in."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="With extras",
            args=None,
            exc_info=None,
        )
        record.extra_data = {"provider": "openai", "latency_ms": 150}
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["provider"] == "openai"
        assert parsed["latency_ms"] == 150

    def test_log_entry_includes_exception_info(self):
        """Log entry includes exception traceback when exc_info is set."""
        try:
            raise ValueError("test error")
        except ValueError:
            import sys as _sys
            exc_info = _sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Something failed",
            args=None,
            exc_info=exc_info,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "test error" in parsed["exception"]


class TestSetupLogging:
    """Tests for setup_logging — configures the root logger."""

    def test_configures_root_logger(self):
        """setup_logging configures the root logger with a handler."""
        setup_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) > 0

    def test_handler_uses_structured_formatter(self):
        """The handler uses StructuredFormatter."""
        setup_logging("INFO")
        root = logging.getLogger()
        # Find the StreamHandler we added
        stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1
        assert isinstance(stream_handlers[0].formatter, StructuredFormatter)

    def test_suppresses_noisy_loggers(self):
        """setup_logging suppresses uvicorn.access and httpx loggers."""
        setup_logging()
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


class TestGetLogger:
    """Tests for get_logger utility."""

    def test_returns_logger_with_name(self):
        """get_logger returns a logger with the specified name."""
        logger = get_logger("gsdm_r.test")
        assert logger.name == "gsdm_r.test"
        assert isinstance(logger, logging.Logger)
