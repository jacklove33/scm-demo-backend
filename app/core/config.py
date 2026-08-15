from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SCM DEMO 1"
    app_env: Literal["local", "test", "prod"] = "local"
    debug: bool = True
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str
    migration_database_url: str | None = None

    auth_mode: Literal["dev_header", "jwt"] = "dev_header"
    jwt_secret: str = ""
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = ""
    jwt_audience: str = "authenticated"
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=14, ge=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "console"
    slow_request_threshold_ms: int = Field(default=1000, ge=1)
    sqlalchemy_echo: bool = False
    aws_region: str = "ap-northeast-1"
    s3_attachments_bucket: str = ""
    attachment_max_file_size_bytes: int = Field(default=10_485_760, ge=1)
    attachment_download_url_expire_seconds: int = Field(default=300, ge=1, le=3600)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
