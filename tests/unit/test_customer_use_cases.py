from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.exceptions import PermissionDenied
from app.modules.customers.application.commands import CreateCustomerCommand
from app.modules.customers.application.use_cases import CustomerUseCases
from app.modules.customers.domain.entities import Customer
from app.modules.customers.domain.repository import CustomerPage, CustomerSearchCriteria
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)


class FakeCustomerRepository:
    async def search(self, criteria, *, actor_id, tenant_id, scope):
        return CustomerPage(items=[], total=0, page=criteria.page, page_size=criteria.page_size)

    async def get_by_id(self, customer_id, *, actor_id, tenant_id, scope, include_deleted=False):
        return None

    async def create(self, customer):
        return customer

    async def update(self, *args, **kwargs):
        return None

    async def soft_delete(self, *args, **kwargs):
        return False

    async def restore(self, *args, **kwargs):
        return False


def make_user(permission_code: str, scope: PermissionScope) -> CurrentUser:
    return CurrentUser(
        user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        email="jack@local.test",
        display_name="Jack",
        is_active=True,
        permissions={
            permission_code: EffectivePermission(
                permission_code=permission_code,
                effect=PermissionEffect.ALLOW,
                scope=scope,
                sources=(),
            )
        },
    )


@pytest.mark.asyncio
async def test_search_requires_customers_read() -> None:
    use_cases = CustomerUseCases(FakeCustomerRepository())
    actor = make_user("customers.create", PermissionScope.ALL)

    with pytest.raises(PermissionDenied):
        await use_cases.search(CustomerSearchCriteria(), actor)


@pytest.mark.asyncio
async def test_create_without_assign_owner_defaults_to_self() -> None:
    use_cases = CustomerUseCases(FakeCustomerRepository())
    actor = make_user("customers.create", PermissionScope.ALL)

    dto = await use_cases.create(
        CreateCustomerCommand(
            customer_code="cust001",
            customer_name="Apple Demo",
            owner_user_id=None,
        ),
        actor,
    )

    assert dto.customer_code == "CUST001"
    assert dto.owner_user_id == actor.user_id
