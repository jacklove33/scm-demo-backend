from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Header
from jwt import InvalidTokenError

from app.core.config import settings
from app.core.exceptions import AuthenticationRequired
from app.shared.domain.current_user import AuthenticatedPrincipal


async def get_principal(
    x_dev_user_id: Annotated[str | None, Header(alias="X-Dev-User-Id")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal:
    if settings.auth_mode == "dev_header":
        if not x_dev_user_id:
            raise AuthenticationRequired("X-Dev-User-Id header is required in local dev mode")
        try:
            return AuthenticatedPrincipal(user_id=UUID(x_dev_user_id))
        except ValueError as exc:
            raise AuthenticationRequired("Invalid X-Dev-User-Id") from exc

    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationRequired("Bearer token is required")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience or None,
            issuer=settings.jwt_issuer or None,
            options={
                "verify_aud": bool(settings.jwt_audience),
                "verify_iss": bool(settings.jwt_issuer),
            },
        )
        return AuthenticatedPrincipal(user_id=UUID(payload["sub"]))
    except (InvalidTokenError, KeyError, ValueError) as exc:
        raise AuthenticationRequired("Invalid access token") from exc
