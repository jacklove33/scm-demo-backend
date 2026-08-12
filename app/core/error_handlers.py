import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        correlation_id = getattr(request.state, "correlation_id", None) or request_id
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "correlationId": correlation_id,
                    "requestId": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        correlation_id = getattr(request.state, "correlation_id", None) or request_id
        logger.exception(
            "Unhandled exception while processing request",
            extra={
                "request_id": request_id,
                "correlation_id": correlation_id,
                "path": request.url.path,
                "method": request.method,
                "exception_type": type(exc).__name__,
                "business_module": "http",
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred.",
                    "details": {},
                    "correlationId": correlation_id,
                    "requestId": request_id,
                }
            },
        )
