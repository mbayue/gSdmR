"""Structured logging configuration with request correlation via X-Request-ID."""

import logging
import sys
import json
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter with request_id correlation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request_id if available
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)

        # Add exception info
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the application.

    Call this once at startup.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Structured JSON handler to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
