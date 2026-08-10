from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.core.exceptions import (
    EntityConflict,
    ImportValidationFailure,
    PermissionDenied,
    ValidationFailure,
)
from app.modules.customers.application.commands import (
    CreateCustomerCommand,
    CustomerImportRowCommand,
)
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
        self.created_many: list[Customer] = []
        self.existing_codes: set[str] = set()

    async def find_existing_codes(self, tenant_id: UUID, codes: set[str]) -> set[str]:
        return codes & self.existing_codes

    async def find_valid_payment_term_ids(
        self, tenant_id: UUID, payment_term_ids: set[UUID]
    ) -> set[UUID]:
        return payment_term_ids

    async def find_valid_owner_ids(self, tenant_id: UUID, owner_ids: set[UUID]) -> set[UUID]:
        return owner_ids

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

    async def get_access_facts(
        self, customer_id: UUID, *, actor_id: UUID, tenant_id: UUID
    ) -> CustomerAccessFacts:
        return CustomerAccessFacts(False, False, False)

    async def create(self, customer: Customer) -> Customer:
        return customer

    async def create_many(self, customers: list[Customer]) -> None:
        self.created_many.extend(customers)

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
@pytest.mark.parametrize("code", ["123", "001ABC", "ABC@123", "A" * 21])
async def test_create_rejects_invalid_customer_code(code: str) -> None:
    use_cases = CustomerUseCases(FakeCustomerRepository())
    actor = make_user("customers.create", PermissionScope.ALL)

    with pytest.raises(ValidationFailure):
        await use_cases.create(
            CreateCustomerCommand(customer_code=code, customer_name="Invalid", owner_user_id=None),
            actor,
        )


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


def import_row(row_number: int, code: str = " CUST100 ") -> CustomerImportRowCommand:
    return CustomerImportRowCommand(
        row_number=row_number,
        customer_code=code,
        customer_name=" ACME ",
        tax_id=None,
        country_code=" tw ",
        currency_code=" twd ",
        payment_term_id=None,
        owner_user_id=None,
        status=" active ",
        address_type=" sold_to ",
        address_code=" main ",
        contact_name=" Jack ",
        address_line1=" No. 1 Road ",
        address_line2=None,
        city=" Taipei ",
        state=None,
        postal_code=" 110 ",
        address_country_code=" tw ",
        phone=None,
        email=" jack@example.com ",
        is_default=False,
    )


@pytest.mark.asyncio
async def test_import_normalizes_and_creates_one_aggregate_per_row() -> None:
    repository = FakeCustomerRepository()
    actor = make_user("customers.create", PermissionScope.ALL)

    total = await CustomerUseCases(repository).import_customers(
        [import_row(2), import_row(3, " cust101 ")], actor
    )

    assert total == 2
    assert [customer.customer_code for customer in repository.created_many] == [
        "CUST100",
        "CUST101",
    ]
    assert repository.created_many[0].country_code == "TW"
    assert repository.created_many[0].addresses[0].address_type == "SOLD_TO"
    assert repository.created_many[0].addresses[0].address1 == "No. 1 Road"
    assert repository.created_many[0].addresses[0].is_default is True


@pytest.mark.asyncio
async def test_import_collects_multiple_errors_and_preserves_row_number() -> None:
    repository = FakeCustomerRepository()
    actor = make_user("customers.create", PermissionScope.ALL)
    row = import_row(12, "123")
    row = CustomerImportRowCommand(
        **{**asdict(row), "customer_name": " ", "address_line1": " ", "email": "bad"}
    )

    with pytest.raises(ImportValidationFailure) as captured:
        await CustomerUseCases(repository).import_customers([row], actor)

    errors = captured.value.details["errors"]
    assert isinstance(errors, list)
    assert {error["field"] for error in errors} >= {
        "customer_code",
        "customer_name",
        "address_line1",
        "email",
    }
    assert all(error["row_number"] == 12 for error in errors)
    assert repository.created_many == []


@pytest.mark.asyncio
async def test_import_rejects_both_normalized_duplicate_rows_without_writes() -> None:
    repository = FakeCustomerRepository()
    actor = make_user("customers.create", PermissionScope.ALL)

    with pytest.raises(ImportValidationFailure) as captured:
        await CustomerUseCases(repository).import_customers(
            [import_row(2, "cust100"), import_row(8, " CUST100 ")], actor
        )

    errors = captured.value.details["errors"]
    assert isinstance(errors, list)
    assert {error["row_number"] for error in errors} == {2, 8}
    assert repository.created_many == []


@pytest.mark.asyncio
async def test_import_existing_partner_code_is_conflict_without_writes() -> None:
    repository = FakeCustomerRepository()
    repository.existing_codes = {"CUST100"}
    actor = make_user("customers.create", PermissionScope.ALL)

    with pytest.raises(EntityConflict):
        await CustomerUseCases(repository).import_customers([import_row(2)], actor)

    assert repository.created_many == []


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [[], [import_row(2)] * 501])
async def test_import_rejects_empty_or_oversized_batch(
    rows: list[CustomerImportRowCommand],
) -> None:
    repository = FakeCustomerRepository()
    actor = make_user("customers.create", PermissionScope.ALL)

    with pytest.raises(ImportValidationFailure):
        await CustomerUseCases(repository).import_customers(rows, actor)

    assert repository.created_many == []
