import io
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_error_handlers
from app.core.logging import (
    ContextFilter,
    JsonFormatter,
    UtcFormatter,
    logging_context,
    sanitize_log_data,
)
from app.core.logging_middleware import LoggingMiddleware


def render_log(
    message: str,
    *,
    created: float = 0.123,
    correlation_id: str | None = None,
) -> str:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(
        UtcFormatter(
            "%(asctime)s UTC %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger = logging.getLogger("app.test.logging")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __file__,
        1,
        message,
        (),
        None,
        extra={"correlation_id": correlation_id} if correlation_id else None,
    )
    record.created = created
    record.msecs = (created - int(created)) * 1000
    logger.handle(record)
    return output.getvalue().strip()


def test_formatter_includes_utc_timestamp_level_logger_and_message() -> None:
    rendered = render_log("Application started")
    assert rendered == ("1970-01-01 00:00:00.123 UTC INFO app.test.logging Application started")


def test_formatter_preserves_optional_correlation_id() -> None:
    rendered = render_log("GET /api/v1/customers 200 42ms", correlation_id="abc-123")
    assert "correlation_id=abc-123 GET /api/v1/customers 200 42ms" in rendered


def test_formatter_does_not_introduce_authentication_secrets() -> None:
    rendered = render_log("Login succeeded")
    assert "Authorization" not in rendered
    assert "access_token" not in rendered
    assert "refresh_token" not in rendered
    assert "password" not in rendered


def test_sanitizer_recursively_redacts_sensitive_values() -> None:
    sanitized = sanitize_log_data(
        {
            "username": "jack",
            "password": "abc123",
            "nested": {
                "access_token": "jwt",
                "Authorization": "Bearer secret",
                "safe": "value",
            },
        }
    )
    assert sanitized == {
        "username": "jack",
        "password": "***REDACTED***",
        "nested": {
            "access_token": "***REDACTED***",
            "Authorization": "***REDACTED***",
            "safe": "value",
        },
    }


def test_json_formatter_includes_context_business_and_edi_metadata() -> None:
    formatter = JsonFormatter()
    record = logging.makeLogRecord(
        {
            "name": "app.modules.edi.service",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "EDI message received",
            "args": (),
            "business_module": "edi",
            "edi_message_id": "edi-123",
        }
    )
    with logging_context(
        request_id="req-1",
        correlation_id="corr-1",
        user_id="user-1",
        tenant_id="tenant-1",
    ):
        ContextFilter().filter(record)
        payload = json.loads(formatter.format(record))

    assert payload["module"] == "edi"
    assert payload["edi_message_id"] == "edi-123"
    assert payload["correlation_id"] == "corr-1"
    assert payload["user_id"] == "user-1"
    assert payload["tenant_id"] == "tenant-1"


def test_logging_middleware_generates_and_preserves_request_ids() -> None:
    test_app = FastAPI()
    test_app.add_middleware(LoggingMiddleware)

    @test_app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    generated = TestClient(test_app).get("/ok")
    preserved = TestClient(test_app).get(
        "/ok", headers={"X-Request-ID": "request-123", "X-Correlation-ID": "flow-456"}
    )
    assert generated.headers["X-Request-ID"]
    assert generated.headers["X-Correlation-ID"] == generated.headers["X-Request-ID"]
    assert preserved.headers["X-Request-ID"] == "request-123"
    assert preserved.headers["X-Correlation-ID"] == "flow-456"


def test_unhandled_error_response_has_request_id_without_stack_trace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    test_app = FastAPI()
    register_error_handlers(test_app)
    test_app.add_middleware(LoggingMiddleware)

    @test_app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("database detail that must not leak")

    response = TestClient(test_app, raise_server_exceptions=False).get(
        "/explode", headers={"X-Request-ID": "error-request"}
    )
    assert response.status_code == 500
    assert response.json()["error"]["requestId"] == "error-request"
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "database detail" not in response.text
    assert "traceback" not in response.text.lower()
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert any(
        record.getMessage() == "Unhandled exception while processing request"
        for record in error_records
    )
    assert any(getattr(record, "request_id", None) == "error-request" for record in error_records)
