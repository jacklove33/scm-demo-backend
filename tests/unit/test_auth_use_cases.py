from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import AuthenticationRequired
from app.modules.auth.application.commands import LoginCommand, LogoutCommand, RefreshCommand
from app.modules.auth.application.use_cases import AuthUseCases
from app.modules.auth.domain.entities import AuthProfile, LoginIdentity, RefreshToken
from app.modules.auth.infrastructure.jwt_service import JwtService
from app.modules.auth.infrastructure.password_hasher import PasswordHasher
from app.modules.auth.infrastructure.refresh_token_service import RefreshTokenService


class FakeAuthRepository:
    def __init__(self, profile: AuthProfile, password_hash: str) -> None:
        self.profile = profile
        self.identity = LoginIdentity(profile, password_hash, 0, None)
        self.tokens: dict[str, RefreshToken] = {}

    async def get_login_identity(self, email: str) -> LoginIdentity | None:
        return self.identity if email == self.profile.email else None

    async def get_profile(self, profile_id: UUID) -> AuthProfile | None:
        return self.profile if profile_id == self.profile.id else None

    async def create_refresh_token(self, token: RefreshToken) -> None:
        self.tokens[token.token_hash] = token

    async def rotate_refresh_token(
        self, old_token_hash: str, new_token: RefreshToken, now: datetime
    ) -> AuthProfile | None:
        old = self.tokens.get(old_token_hash)
        if (
            old is None
            or old.revoked_at is not None
            or old.expires_at <= now
            or not self.profile.is_active
        ):
            return None
        self.tokens[old_token_hash] = RefreshToken(
            id=old.id,
            profile_id=old.profile_id,
            token_hash=old.token_hash,
            expires_at=old.expires_at,
            revoked_at=now,
            replaced_by_token_id=new_token.id,
        )
        self.tokens[new_token.token_hash] = RefreshToken(
            id=new_token.id,
            profile_id=self.profile.id,
            token_hash=new_token.token_hash,
            expires_at=new_token.expires_at,
        )
        return self.profile

    async def revoke_refresh_token(self, token_hash: str, now: datetime) -> None:
        old = self.tokens.get(token_hash)
        if old and old.revoked_at is None:
            self.tokens[token_hash] = RefreshToken(
                id=old.id,
                profile_id=old.profile_id,
                token_hash=old.token_hash,
                expires_at=old.expires_at,
                revoked_at=now,
                replaced_by_token_id=old.replaced_by_token_id,
            )


def setup(active: bool = True) -> tuple[AuthUseCases, FakeAuthRepository]:
    profile = AuthProfile(
        id=uuid4(),
        email="jack@local.test",
        display_name="Jack",
        is_active=active,
        locale="zh-TW",
        timezone="Asia/Taipei",
    )
    hasher = PasswordHasher()
    repository = FakeAuthRepository(profile, hasher.hash_password("password123"))
    return (
        AuthUseCases(
            repository,
            hasher,
            JwtService(
                secret="test-secret-that-is-at-least-32-bytes-long",
                algorithm="HS256",
                expire_minutes=15,
                audience="authenticated",
            ),
            RefreshTokenService(),
            14,
        ),
        repository,
    )


@pytest.mark.asyncio
async def test_login_refresh_rotation_reuse_and_logout() -> None:
    use_cases, repository = setup()
    pair = await use_cases.login(LoginCommand("jack@local.test", "password123"))
    assert pair.expires_in == 900
    assert RefreshTokenService.hash_token(pair.refresh_token) in repository.tokens

    rotated = await use_cases.refresh(RefreshCommand(pair.refresh_token))
    assert rotated.refresh_token != pair.refresh_token
    with pytest.raises(AuthenticationRequired):
        await use_cases.refresh(RefreshCommand(pair.refresh_token))

    await use_cases.logout(LogoutCommand(rotated.refresh_token))
    with pytest.raises(AuthenticationRequired):
        await use_cases.refresh(RefreshCommand(rotated.refresh_token))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "password", "active"),
    [
        ("unknown@local.test", "password123", True),
        ("jack@local.test", "wrong", True),
        ("jack@local.test", "password123", False),
    ],
)
async def test_login_failures_are_generic(email: str, password: str, active: bool) -> None:
    use_cases, _ = setup(active)
    with pytest.raises(AuthenticationRequired, match="Invalid email or password"):
        await use_cases.login(LoginCommand(email, password))


@pytest.mark.asyncio
async def test_expired_refresh_and_inactive_me_are_rejected() -> None:
    use_cases, repository = setup()
    raw = RefreshTokenService.generate()
    repository.tokens[RefreshTokenService.hash_token(raw)] = RefreshToken(
        id=uuid4(),
        profile_id=repository.profile.id,
        token_hash=RefreshTokenService.hash_token(raw),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(AuthenticationRequired):
        await use_cases.refresh(RefreshCommand(raw))

    repository.profile = AuthProfile(
        id=repository.profile.id,
        email=repository.profile.email,
        display_name=repository.profile.display_name,
        is_active=False,
        locale=repository.profile.locale,
        timezone=repository.profile.timezone,
    )
    with pytest.raises(AuthenticationRequired):
        await use_cases.me(repository.profile.id)
