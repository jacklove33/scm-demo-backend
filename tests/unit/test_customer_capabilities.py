from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.customers.application.capabilities import CustomerCapabilityPolicy
from app.modules.customers.domain.entities import Customer
from app.modules.customers.domain.repository import CustomerAccessFacts
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)


def make_actor(scope: PermissionScope) -> CurrentUser:
    permission = EffectivePermission(
        permission_code="customers.update",
        effect=PermissionEffect.ALLOW,
        scope=scope,
        sources=(),
    )
    return CurrentUser(
        user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        email="jack@local.test",
        display_name="Jack",
        is_active=True,
        permissions={"customers.update": permission},
    )


def make_customer() -> Customer:
    now = datetime.now(UTC)
    return Customer(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        customer_code="CUST001",
        customer_name="Customer",
        owner_user_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        status="ACTIVE",
        deleted_at=None,
        deleted_by=None,
        row_version=1,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    ("scope", "access", "expected"),
    [
        (PermissionScope.NONE, CustomerAccessFacts(True, True, True), False),
        (PermissionScope.OWN, CustomerAccessFacts(True, False, False), True),
        (PermissionScope.OWN, CustomerAccessFacts(False, True, True), False),
        (PermissionScope.ASSIGNED, CustomerAccessFacts(False, True, False), True),
        (PermissionScope.ASSIGNED, CustomerAccessFacts(True, False, True), False),
        (PermissionScope.TEAM, CustomerAccessFacts(True, False, False), True),
        (PermissionScope.TEAM, CustomerAccessFacts(False, False, True), True),
        (PermissionScope.TEAM, CustomerAccessFacts(False, True, False), False),
        (PermissionScope.ALL, CustomerAccessFacts(False, False, False), True),
    ],
)
def test_update_capability_preserves_existing_scope_semantics(
    scope: PermissionScope,
    access: CustomerAccessFacts,
    expected: bool,
) -> None:
    capabilities = CustomerCapabilityPolicy().evaluate(make_customer(), access, make_actor(scope))

    assert capabilities.update is expected
