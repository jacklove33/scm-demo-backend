from dataclasses import dataclass
from uuid import UUID

from app.modules.auth.domain.entities import AuthProfile


@dataclass(frozen=True, slots=True)
class TokenPairDTO:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class AuthProfileDTO:
    id: UUID
    email: str
    display_name: str
    is_active: bool
    locale: str
    timezone: str

    @classmethod
    def from_domain(cls, profile: AuthProfile) -> "AuthProfileDTO":
        return cls(
            id=profile.id,
            email=profile.email,
            display_name=profile.display_name,
            is_active=profile.is_active,
            locale=profile.locale,
            timezone=profile.timezone,
        )
