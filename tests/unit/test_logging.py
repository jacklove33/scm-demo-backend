import io
import logging

from app.core.logging import UtcFormatter


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
