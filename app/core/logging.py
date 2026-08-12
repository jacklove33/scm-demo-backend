import json
import logging
import logging.config
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

_context: ContextVar[dict[str, str | None] | None] = ContextVar("logging_context", default=None)
_sensitive_fragments = (
    "password",
    "token",
    "authorization",
    "secret",
    "api_key",
    "apikey",
    "credential",
    "cookie",
    "private_key",
)
_standard_attributes = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def sanitize_log_data(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact secrets and return JSON-safe logging metadata."""
    if key and any(fragment in key.lower() for fragment in _sensitive_fragments):
        return "***REDACTED***"
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_log_data(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_log_data(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def get_log_context() -> dict[str, str | None]:
    return dict(_context.get() or {})


def bind_log_context(**values: object | None) -> None:
    current = get_log_context()
    current.update(
        {key: str(value) if value is not None else None for key, value in values.items()}
    )
    _context.set(current)


def set_log_context(**values: object | None) -> Token[dict[str, str | None] | None]:
    return _context.set(
        {key: str(value) if value is not None else None for key, value in values.items()}
    )


def reset_log_context(token: Token[dict[str, str | None] | None]) -> None:
    _context.reset(token)


@contextmanager
def logging_context(**values: object | None) -> Iterator[None]:
    token = set_log_context(**values)
    try:
        yield
    finally:
        reset_log_context(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_log_context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        if not hasattr(record, "environment"):
            record.environment = settings.app_env
        return True


class UtcFormatter(logging.Formatter):
    """Human-readable formatter with deterministic UTC timestamps and context."""

    default_msec_format = "%s.%03d"

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        timestamp = time.strftime(datefmt or "%Y-%m-%d %H:%M:%S", time.gmtime(record.created))
        return f"{timestamp}.{int(record.msecs):03d}"

    def format(self, record: logging.LogRecord) -> str:
        context = {
            key: value
            for key in ("request_id", "correlation_id", "user_id", "tenant_id")
            if (value := getattr(record, key, None))
        }
        prefix = " ".join(f"{key}={value}" for key, value in context.items())
        if not prefix:
            return super().format(record)
        original_message, original_args = record.msg, record.args
        try:
            record.msg = f"{prefix} {record.getMessage()}"
            record.args = ()
            return super().format(record)
        finally:
            record.msg, record.args = original_message, original_args


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": getattr(record, "environment", settings.app_env),
        }
        for key in ("request_id", "correlation_id", "user_id", "tenant_id", "job_id"):
            payload[key] = getattr(record, key, None)
        for key, value in record.__dict__.items():
            if key not in _standard_attributes and key not in payload and not key.startswith("_"):
                payload[key] = sanitize_log_data(value, key=key)
        if "business_module" in payload:
            payload["module"] = payload.pop("business_module")
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(sanitize_log_data(payload), ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    formatter = "json" if settings.log_format == "json" else "console"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"context": {"()": "app.core.logging.ContextFilter"}},
            "formatters": {
                "console": {
                    "()": "app.core.logging.UtcFormatter",
                    "format": "%(asctime)s UTC %(levelname)s %(name)s %(message)s",
                },
                "json": {"()": "app.core.logging.JsonFormatter"},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter,
                    "filters": ["context"],
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"handlers": ["console"], "level": settings.log_level},
            "loggers": {
                name: {"handlers": ["console"], "level": settings.log_level, "propagate": False}
                for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
            },
        }
    )
