from uuid import UUID

from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)


def test_current_user_can_and_scope() -> None:
    permission = EffectivePermission(
        permission_code="customers.read",
        effect=PermissionEffect.ALLOW,
        scope=PermissionScope.OWN,
        sources=(),
    )
    user = CurrentUser(
        user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        email="jack@local.test",
        display_name="Jack",
        is_active=True,
        permissions={"customers.read": permission},
    )

    assert user.can("customers.read")
    assert user.scope_for("customers.read") == PermissionScope.OWN
    assert not user.can("customers.delete")
    assert user.scope_for("customers.delete") == PermissionScope.NONE
