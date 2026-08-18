from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.products.domain.entities import Product
from app.shared.domain.current_user import PermissionScope


@dataclass(frozen=True, slots=True)
class ProductSearchCriteria:
    page: int = 1
    page_size: int = 20
    search: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    product_type: str | None = None
    status: str | None = None
    category: str | None = None
    owner_user_id: UUID | None = None
    created_at_from: datetime | None = None
    created_at_to_exclusive: datetime | None = None
    updated_at_from: datetime | None = None
    updated_at_to_exclusive: datetime | None = None
    show_deleted: bool = False
    sort_field: str = "updated_at"
    sort_direction: str = "desc"


@dataclass(frozen=True, slots=True)
class ProductAccessFacts:
    is_owner: bool
    is_assigned: bool
    is_team_assigned: bool


@dataclass(frozen=True, slots=True)
class ProductSearchItem:
    product: Product
    access: ProductAccessFacts


@dataclass(frozen=True, slots=True)
class ProductPage:
    items: list[ProductSearchItem]
    total: int
    page: int
    page_size: int


class ProductRepository(Protocol):
    async def find_valid_owner_ids(self, tenant_id: UUID, ids: set[UUID]) -> set[UUID]: ...
    async def search(
        self,
        criteria: ProductSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> ProductPage: ...
    async def get_by_id(
        self,
        product_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> Product | None: ...
    async def get_access_facts(
        self, product_id: UUID, *, actor_id: UUID, tenant_id: UUID
    ) -> ProductAccessFacts: ...
    async def create(self, product: Product) -> Product: ...
    async def update(
        self,
        product_id: UUID,
        expected_version: int,
        data: dict[str, object],
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Product | None: ...
    async def soft_delete(
        self,
        product_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Product | None: ...
    async def restore(
        self,
        product_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Product | None: ...
