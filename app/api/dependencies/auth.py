from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationRequired
from app.infrastructure.database.session import get_session
from app.modules.auth.application.use_cases import AuthUseCases
from app.modules.auth.infrastructure.jwt_service import JwtService
from app.modules.auth.infrastructure.password_hasher import PasswordHasher
from app.modules.auth.infrastructure.refresh_token_service import RefreshTokenService
from app.modules.auth.infrastructure.repository import SqlAlchemyAuthRepository
from app.shared.domain.current_user import AuthenticatedPrincipal

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


def get_jwt_service() -> JwtService:
    return JwtService(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.access_token_expire_minutes,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_dev_user_id: Annotated[str | None, Header(alias="X-Dev-User-Id")] = None,
) -> AuthenticatedPrincipal:
    if settings.auth_mode == "dev_header":
        if not x_dev_user_id:
            raise AuthenticationRequired("X-Dev-User-Id header is required in local dev mode")
        try:
            return AuthenticatedPrincipal(user_id=UUID(x_dev_user_id))
        except ValueError as exc:
            raise AuthenticationRequired("Invalid X-Dev-User-Id") from exc

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationRequired("Bearer token is required")
    return AuthenticatedPrincipal(
        user_id=get_jwt_service().decode_access_token(credentials.credentials)
    )


async def get_auth_use_cases(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthUseCases:
    return AuthUseCases(
        repository=SqlAlchemyAuthRepository(session),
        password_hasher=PasswordHasher(),
        jwt_service=get_jwt_service(),
        refresh_token_service=RefreshTokenService(),
        refresh_expire_days=settings.refresh_token_expire_days,
    )
