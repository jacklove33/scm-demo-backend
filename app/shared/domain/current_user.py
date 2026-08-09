from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class PermissionEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class PermissionScope(StrEnum):
    NONE = "NONE"
    OWN = "OWN"
    ASSIGNED = "ASSIGNED"
    TEAM = "TEAM"
    ALL = "ALL"


@dataclass(frozen=True, slots=True)
class PermissionSource:
    source_type: str
    source_name: str
    policy_code: str
    effect: PermissionEffect
    scope: PermissionScope | None


@dataclass(frozen=True, slots=True)
class EffectivePermission:
    permission_code: str
    effect: PermissionEffect
    scope: PermissionScope | None
    sources: tuple[PermissionSource, ...]

    @property
    def allowed(self) -> bool:
        return self.effect == PermissionEffect.ALLOW


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Authentication only proves who the caller is."""

    user_id: UUID


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """Backend-neutral application identity + resolved authorization context."""

    user_id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    is_active: bool
    permissions: dict[str, EffectivePermission]

    def can(self, permission_code: str) -> bool:
        permission = self.permissions.get(permission_code)
        return bool(self.is_active and permission and permission.allowed)

    def scope_for(self, permission_code: str) -> PermissionScope:
        permission = self.permissions.get(permission_code)
        if not self.is_active or permission is None or not permission.allowed:
            return PermissionScope.NONE
        return permission.scope or PermissionScope.NONE
