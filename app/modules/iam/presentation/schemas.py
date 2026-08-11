from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PermissionSourceResponse(BaseModel):
    source_type: str
    source_name: str
    policy_code: str
    effect: str
    scope: str | None


class EffectivePermissionResponse(BaseModel):
    permission_code: str
    effect: str
    scope: str | None
    sources: list[PermissionSourceResponse]


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    permissions: list[EffectivePermissionResponse]


class UserSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    display_name: str
    status: Literal["ACTIVE", "INACTIVE"]
    primary_role_id: UUID | None
    primary_role_name: str | None
    group_ids: list[UUID]
    group_names: list[str]
    direct_policy_ids: list[UUID]
    direct_policy_names: list[str]
    row_version: int
    updated_at: datetime


class UserListResponse(BaseModel):
    data: list[UserSummaryResponse]
    meta: dict[str, int]


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    member_count: int
    policy_ids: list[UUID]
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    is_system: bool
    policy_ids: list[UUID]
    user_count: int
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PolicyRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    permission_code: str
    effect: Literal["ALLOW", "DENY"]
    scope: Literal["NONE", "OWN", "ASSIGNED", "TEAM", "ALL"]


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    is_system: bool
    rules: list[PolicyRuleResponse]
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    resource: str
    action: str
    description: str
