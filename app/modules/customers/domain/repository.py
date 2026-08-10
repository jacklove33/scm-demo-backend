from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.customers.domain.entities import Customer
from app.shared.domain.current_user import PermissionScope


@dataclass(frozen=True, slots=True)
class CustomerSearchCriteria:
    page: int = 1
    page_size: int = 20
    customer_code: str | None = None
    customer_name_prefix: str | None = None
    status: str | None = None
    show_deleted: bool = False
    sort_field: str = "created_at"
    sort_direction: str = "desc"


@dataclass(frozen=True, slots=True)
class CustomerAccessFacts:
    is_owner: bool
    is_assigned: bool
    is_team_assigned: bool


@dataclass(frozen=True, slots=True)
class CustomerSearchItem:
    customer: Customer
    access: CustomerAccessFacts


@dataclass(frozen=True, slots=True)
class CustomerPage:
    items: list[CustomerSearchItem]
    total: int
    page: int
    page_size: int


class CustomerRepository(Protocol):
    async def find_existing_codes(self, tenant_id: UUID, codes: set[str]) -> set[str]: ...

    async def find_valid_payment_term_ids(
        self, tenant_id: UUID, payment_term_ids: set[UUID]
    ) -> set[UUID]: ...

    async def find_valid_owner_ids(self, tenant_id: UUID, owner_ids: set[UUID]) -> set[UUID]: ...

    async def search(
        self,
        criteria: CustomerSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> CustomerPage: ...

    async def get_by_id(
        self,
        customer_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> Customer | None: ...

    async def get_access_facts(
        self, customer_id: UUID, *, actor_id: UUID, tenant_id: UUID
    ) -> CustomerAccessFacts: ...

    async def create(self, customer: Customer) -> Customer: ...

    async def create_many(self, customers: list[Customer]) -> None: ...

    async def update(
        self,
        customer_id: UUID,
        expected_version: int,
        data: dict[str, object],
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Customer | None: ...

    async def soft_delete(
        self,
        customer_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> bool: ...

    async def restore(
        self,
        customer_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> bool: ...
