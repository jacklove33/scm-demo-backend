from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from app.modules.customer_pos.domain.entities import CustomerPoStatusEvent, CustomerPurchaseOrder
from app.modules.customer_pos.domain.enums import CustomerPoSource, CustomerPoStatus
from app.shared.domain.current_user import PermissionScope


@dataclass(frozen=True, slots=True)
class CustomerPoSearchCriteria:
    page: int = 1
    page_size: int = 20
    customer_po_number: str | None = None
    customer_id: UUID | None = None
    status: CustomerPoStatus | None = None
    source: CustomerPoSource | None = None
    customer_po_date_from: date | None = None
    customer_po_date_to: date | None = None
    requested_delivery_date_from: date | None = None
    requested_delivery_date_to: date | None = None
    owner_user_id: UUID | None = None
    edi_log_id: UUID | None = None
    sales_order_id: UUID | None = None
    show_deleted: bool = False
    sort_field: str = "created_at"
    sort_direction: str = "desc"


@dataclass(frozen=True, slots=True)
class CustomerPoPage:
    items: list[CustomerPurchaseOrder]
    total: int
    page: int
    page_size: int


class CustomerPoRepository(Protocol):
    async def customer_exists(self, tenant_id: UUID, customer_id: UUID) -> bool: ...
    async def owner_exists(self, tenant_id: UUID, owner_id: UUID) -> bool: ...
    async def search(
        self,
        criteria: CustomerPoSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> CustomerPoPage: ...
    async def get(
        self,
        customer_po_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> CustomerPurchaseOrder | None: ...
    async def create(
        self, po: CustomerPurchaseOrder, event: CustomerPoStatusEvent
    ) -> CustomerPurchaseOrder: ...
    async def update(
        self, po: CustomerPurchaseOrder, expected_version: int
    ) -> CustomerPurchaseOrder | None: ...
    async def change_status(
        self,
        customer_po_id: UUID,
        expected_version: int,
        status: CustomerPoStatus,
        actor_id: UUID,
        event: CustomerPoStatusEvent,
    ) -> CustomerPurchaseOrder | None: ...
    async def soft_delete(
        self, customer_po_id: UUID, expected_version: int, actor_id: UUID
    ) -> CustomerPurchaseOrder | None: ...
    async def restore(
        self, customer_po_id: UUID, expected_version: int, actor_id: UUID
    ) -> CustomerPurchaseOrder | None: ...
    async def status_history(
        self, customer_po_id: UUID, tenant_id: UUID
    ) -> list[CustomerPoStatusEvent]: ...
