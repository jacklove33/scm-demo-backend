from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.shared.domain.current_user import PermissionEffect, PermissionScope


@dataclass(frozen=True, slots=True)
class UserProfile:
    id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    permission_code: str
    source_type: str
    source_name: str
    policy_code: str
    effect: PermissionEffect
    scope: PermissionScope | None


class IamRepository(Protocol):
    async def get_profile(self, user_id: UUID) -> UserProfile | None: ...

    async def get_permission_grants(self, user_id: UUID) -> list[PermissionGrant]: ...
