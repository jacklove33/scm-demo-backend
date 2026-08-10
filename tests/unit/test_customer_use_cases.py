from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.core.exceptions import PermissionDenied
from app.modules.customers.application.commands import CreateCustomerCommand
from app.modules.customers.application.use_cases import CustomerUseCases
from app.modules.customers.domain.entities import Customer
from app.modules.customers.domain.repository import (
    CustomerAccessFacts,
    CustomerPage,
    CustomerSearchCriteria,
    CustomerSearchItem,
)
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)


class FakeCustomerRepository:
    def __init__(self, items: list[CustomerSearchItem] | None = None) -> None:
        self.items = items or []
        self.search_scope: PermissionScope | None = None

    async def search(
        self,
        criteria: CustomerSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> CustomerPage:
        self.search_scope = scope
        return CustomerPage(
            items=self.items,
            total=len(self.items),
            page=criteria.page,
            page_size=criteria.page_size,
        )

    async def get_by_id(
        self,
        customer_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> Customer | None:
        return None

    async def create(self, customer: Customer) -> Customer:
        return customer

    async def update(self, *args: Any, **kwargs: Any) -> Customer | None:
        return None

    async def soft_delete(self, *args: Any, **kwargs: Any) -> bool:
        return False

    async def restore(self, *args: Any, **kwargs: Any) -> bool:
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


def make_user_with_permissions(
    permissions: dict[str, PermissionScope],
) -> CurrentUser:
    actor = make_user("placeholder", PermissionScope.NONE)
    return CurrentUser(
        user_id=actor.user_id,
        tenant_id=actor.tenant_id,
        email=actor.email,
        display_name=actor.display_name,
        is_active=True,
        permissions={
            code: EffectivePermission(
                permission_code=code,
                effect=PermissionEffect.ALLOW,
                scope=scope,
                sources=(),
            )
            for code, scope in permissions.items()
        },
    )


def make_customer(owner_user_id: UUID, *, deleted: bool = False) -> Customer:
    now = datetime.now(UTC)
    return Customer(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        customer_code="CUST001",
        customer_name="Customer",
        owner_user_id=owner_user_id,
        status="ACTIVE",
        deleted_at=now if deleted else None,
        deleted_by=None,
        row_version=1,
        created_at=now,
        updated_at=now,
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


@pytest.mark.asyncio
async def test_search_capabilities_use_action_scope_not_read_scope() -> None:
    actor = make_user_with_permissions(
        {
            "customers.read": PermissionScope.TEAM,
            "customers.update": PermissionScope.OWN,
        }
    )
    jack_customer = make_customer(actor.user_id)
    mary_customer = make_customer(UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"))
    repository = FakeCustomerRepository(
        [
            CustomerSearchItem(
                customer=jack_customer,
                access=CustomerAccessFacts(
                    is_owner=True,
                    is_assigned=False,
                    is_team_assigned=True,
                ),
            ),
            CustomerSearchItem(
                customer=mary_customer,
                access=CustomerAccessFacts(
                    is_owner=False,
                    is_assigned=False,
                    is_team_assigned=True,
                ),
            ),
        ]
    )

    items, _ = await CustomerUseCases(repository).search(CustomerSearchCriteria(), actor)

    assert repository.search_scope == PermissionScope.TEAM
    assert items[0].capabilities.update is True
    assert items[1].capabilities.update is False


@pytest.mark.asyncio
async def test_search_capabilities_follow_lifecycle_and_current_assign_owner_gate() -> None:
    actor = make_user_with_permissions(
        {
            "customers.read": PermissionScope.ALL,
            "customers.update": PermissionScope.ALL,
            "customers.delete": PermissionScope.ALL,
            "customers.restore": PermissionScope.ALL,
            "customers.assign_owner": PermissionScope.NONE,
        }
    )
    access = CustomerAccessFacts(
        is_owner=False,
        is_assigned=False,
        is_team_assigned=False,
    )
    repository = FakeCustomerRepository(
        [
            CustomerSearchItem(customer=make_customer(actor.user_id), access=access),
            CustomerSearchItem(customer=make_customer(actor.user_id, deleted=True), access=access),
        ]
    )

    items, _ = await CustomerUseCases(repository).search(
        CustomerSearchCriteria(show_deleted=True), actor
    )

    assert items[0].capabilities.update is True
    assert items[0].capabilities.delete is True
    assert items[0].capabilities.restore is False
    # The endpoint checks can(), not the assign_owner scope value.
    assert items[0].capabilities.assign_owner is True
    assert items[1].capabilities.update is False
    assert items[1].capabilities.delete is False
    assert items[1].capabilities.restore is True
    assert items[1].capabilities.assign_owner is False
