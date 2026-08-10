from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.auth.domain.entities import AuthProfile, LoginIdentity, RefreshToken


class AuthRepository(Protocol):
    async def get_login_identity(self, email: str) -> LoginIdentity | None: ...

    async def get_profile(self, profile_id: UUID) -> AuthProfile | None: ...

    async def create_refresh_token(self, token: RefreshToken) -> None: ...

    async def rotate_refresh_token(
        self, old_token_hash: str, new_token: RefreshToken, now: datetime
    ) -> AuthProfile | None: ...

    async def revoke_refresh_token(self, token_hash: str, now: datetime) -> None: ...
