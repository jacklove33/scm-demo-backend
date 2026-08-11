from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True, slots=True)
class UserSearchCriteria:
    search: str | None = None
    status: str | None = None
    role_id: UUID | None = None
    group_id: UUID | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class UserSummary:
    id: UUID
    email: str
    display_name: str
    status: str
    primary_role_id: UUID | None
    primary_role_name: str | None
    group_ids: list[UUID]
    group_names: list[str]
    direct_policy_ids: list[UUID]
    direct_policy_names: list[str]
    row_version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UserPage:
    items: list[UserSummary]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class GroupSummary:
    id: UUID
    name: str
    description: str
    member_count: int
    policy_ids: list[UUID]
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RoleSummary:
    id: UUID
    name: str
    description: str
    is_system: bool
    policy_ids: list[UUID]
    user_count: int
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PolicyRule:
    permission_code: str
    effect: str
    scope: str


@dataclass(frozen=True, slots=True)
class PolicySummary:
    id: UUID
    name: str
    description: str
    is_system: bool
    rules: list[PolicyRule]
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PermissionSummary:
    code: str
    resource: str
    action: str
    description: str


class IamRepository(Protocol):
    async def get_profile(self, user_id: UUID) -> UserProfile | None: ...

    async def get_permission_grants(self, user_id: UUID) -> list[PermissionGrant]: ...

    async def search_users(self, tenant_id: UUID, criteria: UserSearchCriteria) -> UserPage: ...

    async def list_groups(self, tenant_id: UUID) -> list[GroupSummary]: ...

    async def list_roles(self, tenant_id: UUID) -> list[RoleSummary]: ...

    async def list_policies(self, tenant_id: UUID) -> list[PolicySummary]: ...

    async def list_permissions(self) -> list[PermissionSummary]: ...
