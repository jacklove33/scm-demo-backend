import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging
from app.core.logging_middleware import LoggingMiddleware

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Application starting environment=%s auth_mode=%s",
        settings.app_env,
        settings.auth_mode,
    )
    logger.info(
        "Attachment storage configured attachments_storage=S3 aws_region=%s s3_bucket=%s",
        settings.aws_region,
        settings.s3_attachments_bucket or "NOT_CONFIGURED",
    )
    logger.info("Application started")
    yield
    logger.info("Application shutting down")
    logger.info("Application stopped")


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

register_error_handlers(app)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_prefix)
