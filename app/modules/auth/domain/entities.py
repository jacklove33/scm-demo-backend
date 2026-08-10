from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthProfile:
    id: UUID
    email: str
    display_name: str
    is_active: bool
    locale: str
    timezone: str


@dataclass(frozen=True, slots=True)
class LoginIdentity:
    profile: AuthProfile
    password_hash: str
    failed_attempts: int
    locked_until: datetime | None


@dataclass(frozen=True, slots=True)
class RefreshToken:
    id: UUID
    profile_id: UUID | None
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by_token_id: UUID | None = None
