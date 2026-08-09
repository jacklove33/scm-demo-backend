from collections import defaultdict

from app.modules.iam.domain.repository import PermissionGrant
from app.shared.domain.current_user import (
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
    PermissionSource,
)


_SCOPE_RANK: dict[PermissionScope, int] = {
    PermissionScope.NONE: 0,
    PermissionScope.OWN: 10,
    PermissionScope.ASSIGNED: 20,
    PermissionScope.TEAM: 30,
    PermissionScope.ALL: 40,
}


class EffectivePermissionResolver:
    """Single authorization merge engine shared by every business module."""

    def resolve(self, grants: list[PermissionGrant]) -> dict[str, EffectivePermission]:
        by_permission: dict[str, list[PermissionGrant]] = defaultdict(list)
        for grant in grants:
            by_permission[grant.permission_code].append(grant)

        result: dict[str, EffectivePermission] = {}

        for permission_code, items in by_permission.items():
            sources = tuple(
                PermissionSource(
                    source_type=item.source_type,
                    source_name=item.source_name,
                    policy_code=item.policy_code,
                    effect=item.effect,
                    scope=item.scope,
                )
                for item in items
            )

            # Explicit DENY wins over every ALLOW source.
            if any(item.effect == PermissionEffect.DENY for item in items):
                result[permission_code] = EffectivePermission(
                    permission_code=permission_code,
                    effect=PermissionEffect.DENY,
                    scope=None,
                    sources=sources,
                )
                continue

            allows = [item for item in items if item.effect == PermissionEffect.ALLOW]
            if not allows:
                continue

            scopes = [item.scope or PermissionScope.NONE for item in allows]
            effective_scope = max(scopes, key=lambda scope: _SCOPE_RANK[scope])

            result[permission_code] = EffectivePermission(
                permission_code=permission_code,
                effect=PermissionEffect.ALLOW,
                scope=effective_scope,
                sources=sources,
            )

        return result
