from app.modules.iam.application.permission_resolver import EffectivePermissionResolver
from app.modules.iam.domain.repository import PermissionGrant
from app.shared.domain.current_user import PermissionEffect, PermissionScope


def grant(
    permission: str,
    effect: PermissionEffect,
    scope: PermissionScope | None,
    source: str,
) -> PermissionGrant:
    return PermissionGrant(
        permission_code=permission,
        source_type="TEST",
        source_name=source,
        policy_code=source,
        effect=effect,
        scope=scope,
    )


def test_explicit_deny_wins() -> None:
    resolver = EffectivePermissionResolver()

    result = resolver.resolve(
        [
            grant("customers.export", PermissionEffect.ALLOW, PermissionScope.OWN, "sales"),
            grant("customers.export", PermissionEffect.ALLOW, PermissionScope.ALL, "key-account"),
            grant("customers.export", PermissionEffect.DENY, None, "direct-deny"),
        ]
    )

    permission = result["customers.export"]
    assert permission.effect == PermissionEffect.DENY
    assert permission.scope is None


def test_allow_scopes_merge_to_broader_scope() -> None:
    resolver = EffectivePermissionResolver()

    result = resolver.resolve(
        [
            grant("customers.read", PermissionEffect.ALLOW, PermissionScope.OWN, "role"),
            grant("customers.read", PermissionEffect.ALLOW, PermissionScope.TEAM, "group"),
        ]
    )

    assert result["customers.read"].scope == PermissionScope.TEAM


def test_missing_permission_is_default_deny_by_absence() -> None:
    resolver = EffectivePermissionResolver()
    result = resolver.resolve([])
    assert "customers.delete" not in result
