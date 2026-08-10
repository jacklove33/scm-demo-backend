from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.exceptions import AuthenticationRequired
from app.modules.auth.application.commands import LoginCommand, LogoutCommand, RefreshCommand
from app.modules.auth.application.dto import AuthProfileDTO, TokenPairDTO
from app.modules.auth.domain.entities import AuthProfile, RefreshToken
from app.modules.auth.domain.repository import AuthRepository
from app.modules.auth.infrastructure.jwt_service import JwtService
from app.modules.auth.infrastructure.password_hasher import PasswordHasher
from app.modules.auth.infrastructure.refresh_token_service import RefreshTokenService


class AuthUseCases:
    def __init__(
        self,
        repository: AuthRepository,
        password_hasher: PasswordHasher,
        jwt_service: JwtService,
        refresh_token_service: RefreshTokenService,
        refresh_expire_days: int,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.jwt_service = jwt_service
        self.refresh_token_service = refresh_token_service
        self.refresh_expire_days = refresh_expire_days

    async def login(self, command: LoginCommand) -> TokenPairDTO:
        now = datetime.now(UTC)
        identity = await self.repository.get_login_identity(command.email.strip().lower())
        valid = bool(
            identity
            and identity.profile.is_active
            and (identity.locked_until is None or identity.locked_until <= now)
            and self.password_hasher.verify_password(command.password, identity.password_hash)
        )
        if not valid or identity is None:
            raise AuthenticationRequired("Invalid email or password")

        raw_refresh, refresh = self._new_refresh_token(identity.profile.id, now)
        await self.repository.create_refresh_token(refresh)
        return self._token_pair(identity.profile, raw_refresh, now)

    async def refresh(self, command: RefreshCommand) -> TokenPairDTO:
        now = datetime.now(UTC)
        raw_refresh = self.refresh_token_service.generate()
        old_hash = self.refresh_token_service.hash_token(command.refresh_token)
        new_token = RefreshToken(
            id=uuid4(),
            profile_id=None,
            token_hash=self.refresh_token_service.hash_token(raw_refresh),
            expires_at=now + timedelta(days=self.refresh_expire_days),
        )
        profile = await self.repository.rotate_refresh_token(old_hash, new_token, now)
        if profile is None:
            raise AuthenticationRequired("Invalid refresh token")
        return self._token_pair(profile, raw_refresh, now)

    async def logout(self, command: LogoutCommand) -> None:
        await self.repository.revoke_refresh_token(
            self.refresh_token_service.hash_token(command.refresh_token), datetime.now(UTC)
        )

    async def me(self, profile_id: UUID) -> AuthProfileDTO:
        profile = await self.repository.get_profile(profile_id)
        if profile is None or not profile.is_active:
            raise AuthenticationRequired("Authenticated user profile was not found")
        return AuthProfileDTO.from_domain(profile)

    def _new_refresh_token(self, profile_id: UUID, now: datetime) -> tuple[str, RefreshToken]:
        raw = self.refresh_token_service.generate()
        return raw, RefreshToken(
            id=uuid4(),
            profile_id=profile_id,
            token_hash=self.refresh_token_service.hash_token(raw),
            expires_at=now + timedelta(days=self.refresh_expire_days),
        )

    def _token_pair(self, profile: AuthProfile, raw_refresh: str, now: datetime) -> TokenPairDTO:
        return TokenPairDTO(
            access_token=self.jwt_service.create_access_token(profile.id, now=now),
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=self.jwt_service.expires_in,
        )
