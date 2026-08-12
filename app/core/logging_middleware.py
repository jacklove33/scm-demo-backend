import logging
import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.logging import reset_log_context, set_log_context

logger = logging.getLogger(__name__)


def _trace_header(value: bytes) -> str:
    return value.decode(errors="replace").replace("\r", "").replace("\n", "")[:100]


class LoggingMiddleware:
    """Request tracing middleware that does not inspect headers or bodies containing secrets."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        request_id = _trace_header(headers.get(b"x-request-id", b"")) or str(uuid4())
        correlation_id = _trace_header(headers.get(b"x-correlation-id", b"")) or request_id
        scope.setdefault("state", {})["request_id"] = request_id
        scope["state"]["correlation_id"] = correlation_id
        token = set_log_context(request_id=request_id, correlation_id=correlation_id)
        started = time.perf_counter()
        path = scope.get("path", "")
        method = scope.get("method", "")
        client = scope.get("client")
        metadata = {
            "method": method,
            "path": path,
            "client_ip": client[0] if client else None,
            "user_agent": headers.get(b"user-agent", b"").decode()[:500] or None,
            "business_module": "http",
        }
        if path == "/health":
            logger.debug("HTTP request started", extra=metadata)
        else:
            logger.info("HTTP request started", extra=metadata)
        status_code = 500

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode()))
                response_headers.append((b"x-correlation-id", correlation_id.encode()))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            completed = {**metadata, "status_code": status_code, "duration_ms": duration_ms}
            if duration_ms >= settings.slow_request_threshold_ms:
                logger.warning("Slow API request", extra=completed)
            elif path == "/health":
                logger.debug("HTTP request completed", extra=completed)
            else:
                logger.info("HTTP request completed", extra=completed)
            reset_log_context(token)
