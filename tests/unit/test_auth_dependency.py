from uuid import UUID

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies.auth import get_jwt_service, get_principal
from app.core.config import settings
from app.core.exceptions import AuthenticationRequired

PROFILE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.mark.asyncio
async def test_dev_header_mode_still_resolves_profile_id() -> None:
    original_mode = settings.auth_mode
    settings.auth_mode = "dev_header"
    try:
        principal = await get_principal(None, str(PROFILE_ID))
    finally:
        settings.auth_mode = original_mode
    assert principal.user_id == PROFILE_ID


@pytest.mark.asyncio
async def test_jwt_mode_accepts_bearer_and_never_falls_back_to_dev_header() -> None:
    original_mode, original_secret = settings.auth_mode, settings.jwt_secret
    settings.auth_mode = "jwt"
    settings.jwt_secret = "dependency-test-secret-that-is-at-least-32-bytes"
    try:
        token = get_jwt_service().create_access_token(PROFILE_ID)
        principal = await get_principal(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), None
        )
        assert principal.user_id == PROFILE_ID
        with pytest.raises(AuthenticationRequired):
            await get_principal(None, str(PROFILE_ID))
    finally:
        settings.auth_mode = original_mode
        settings.jwt_secret = original_secret
