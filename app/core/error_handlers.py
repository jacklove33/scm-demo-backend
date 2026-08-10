import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        correlation_id = str(uuid4())
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "correlationId": correlation_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        correlation_id = str(uuid4())
        logger.exception(
            "Unexpected request error",
            exc_info=exc,
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "UNEXPECTED_ERROR",
                    "message": "Unexpected server error",
                    "details": {},
                    "correlationId": correlation_id,
                }
            },
        )
