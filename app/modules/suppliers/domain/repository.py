from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.suppliers.domain.entities import Supplier
from app.shared.domain.current_user import PermissionScope


@dataclass(frozen=True, slots=True)
class SupplierSearchCriteria:
    page: int = 1
    page_size: int = 20
    supplier_code: str | None = None
    supplier_name_prefix: str | None = None
    status: str | None = None
    created_at_from: datetime | None = None
    created_at_to_exclusive: datetime | None = None
    updated_at_from: datetime | None = None
    updated_at_to_exclusive: datetime | None = None
    show_deleted: bool = False
    sort_field: str = "created_at"
    sort_direction: str = "desc"


@dataclass(frozen=True, slots=True)
class SupplierAccessFacts:
    is_owner: bool
    is_assigned: bool
    is_team_assigned: bool


@dataclass(frozen=True, slots=True)
class SupplierSearchItem:
    supplier: Supplier
    access: SupplierAccessFacts


@dataclass(frozen=True, slots=True)
class SupplierPage:
    items: list[SupplierSearchItem]
    total: int
    page: int
    page_size: int


class SupplierRepository(Protocol):
    async def list_payment_terms(self, tenant_id: UUID) -> list[tuple[UUID, str, str]]: ...

    async def find_existing_partner_owner(
        self, tenant_id: UUID, supplier_code: str
    ) -> tuple[bool, UUID | None]: ...

    async def find_valid_payment_term_ids(self, tenant_id: UUID, ids: set[UUID]) -> set[UUID]: ...
    async def find_valid_owner_ids(self, tenant_id: UUID, ids: set[UUID]) -> set[UUID]: ...
    async def search(
        self,
        criteria: SupplierSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> SupplierPage: ...
    async def get_by_id(
        self,
        supplier_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> Supplier | None: ...
    async def get_access_facts(
        self, supplier_id: UUID, *, actor_id: UUID, tenant_id: UUID
    ) -> SupplierAccessFacts: ...
    async def create(self, supplier: Supplier) -> Supplier: ...
    async def update(
        self,
        supplier_id: UUID,
        expected_version: int,
        data: dict[str, object],
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Supplier | None: ...
    async def soft_delete(
        self,
        supplier_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Supplier | None: ...
    async def restore(
        self,
        supplier_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Supplier | None: ...
