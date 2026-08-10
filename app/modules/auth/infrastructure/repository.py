from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain.entities import AuthProfile, LoginIdentity, RefreshToken
from app.modules.auth.infrastructure.models import RefreshTokenModel, UserCredentialModel
from app.modules.iam.infrastructure.models import ProfileModel


class SqlAlchemyAuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _profile(row: ProfileModel) -> AuthProfile:
        return AuthProfile(
            id=row.id,
            email=row.email,
            display_name=row.display_name,
            is_active=row.is_active,
            locale=row.locale,
            timezone=row.timezone,
        )

    async def get_login_identity(self, email: str) -> LoginIdentity | None:
        result = (
            await self.session.execute(
                select(ProfileModel, UserCredentialModel)
                .join(UserCredentialModel, UserCredentialModel.profile_id == ProfileModel.id)
                .where(ProfileModel.email == email)
            )
        ).first()
        if result is None:
            return None
        profile, credential = result
        return LoginIdentity(
            profile=self._profile(profile),
            password_hash=credential.password_hash,
            failed_attempts=credential.failed_attempts,
            locked_until=credential.locked_until,
        )

    async def get_profile(self, profile_id: UUID) -> AuthProfile | None:
        row = await self.session.scalar(select(ProfileModel).where(ProfileModel.id == profile_id))
        return self._profile(row) if row else None

    async def create_refresh_token(self, token: RefreshToken) -> None:
        self.session.add(self._refresh_model(token))
        await self.session.commit()

    async def rotate_refresh_token(
        self, old_token_hash: str, new_token: RefreshToken, now: datetime
    ) -> AuthProfile | None:
        result = (
            await self.session.execute(
                select(RefreshTokenModel, ProfileModel)
                .join(ProfileModel, ProfileModel.id == RefreshTokenModel.profile_id)
                .where(RefreshTokenModel.token_hash == old_token_hash)
                .with_for_update(of=RefreshTokenModel)
            )
        ).first()
        if result is None:
            return None
        old_token, profile = result
        if old_token.revoked_at is not None or old_token.expires_at <= now or not profile.is_active:
            return None
        self.session.add(self._refresh_model(new_token, profile_id=old_token.profile_id))
        # Insert the replacement before pointing the old row at its self-FK.
        # Both statements remain in the same transaction and commit atomically.
        await self.session.flush()
        old_token.revoked_at = now
        old_token.replaced_by_token_id = new_token.id
        await self.session.commit()
        return self._profile(profile)

    async def revoke_refresh_token(self, token_hash: str, now: datetime) -> None:
        await self.session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.token_hash == token_hash,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self.session.commit()

    @staticmethod
    def _refresh_model(token: RefreshToken, *, profile_id: UUID | None = None) -> RefreshTokenModel:
        resolved_profile_id = profile_id or token.profile_id
        if resolved_profile_id is None:
            raise ValueError("Refresh token profile_id is required")
        return RefreshTokenModel(
            id=token.id,
            profile_id=resolved_profile_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            revoked_at=token.revoked_at,
            replaced_by_token_id=token.replaced_by_token_id,
        )
