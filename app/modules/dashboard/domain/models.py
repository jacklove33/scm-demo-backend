from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.modules.customer_pos.domain.enums import CustomerPoStatus
from app.shared.domain.current_user import PermissionScope


class TrendGranularity(StrEnum):
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"


OPEN_CUSTOMER_PO_STATUSES = (
    CustomerPoStatus.DRAFT,
    CustomerPoStatus.RECEIVED,
    CustomerPoStatus.VALIDATING,
    CustomerPoStatus.VALIDATED,
    CustomerPoStatus.PROCESSING,
    CustomerPoStatus.ON_HOLD,
)

# Only signals that are directly and reliably derivable from the current PO lifecycle.
ATTENTION_RULES = {
    CustomerPoStatus.ON_HOLD: ("ON_HOLD", "WARNING", "POs on hold"),
    CustomerPoStatus.VALIDATING: (
        "VALIDATION_PENDING",
        "INFO",
        "POs waiting for validation",
    ),
}


@dataclass(frozen=True, slots=True)
class CustomerPoDashboardFilter:
    date_from: date | None = None
    date_to: date | None = None
    customer_id: UUID | None = None
    owner_user_id: UUID | None = None
    status: CustomerPoStatus | None = None


@dataclass(frozen=True, slots=True)
class DashboardQueryContext:
    tenant_id: UUID
    actor_id: UUID
    scope: PermissionScope


@dataclass(frozen=True, slots=True)
class AmountByCurrency:
    currency: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class SummaryResult:
    total_po_count: int
    open_po_count: int
    on_hold_count: int
    converted_count: int
    cancelled_count: int
    amount_by_currency: tuple[AmountByCurrency, ...]
    open_amount_by_currency: tuple[AmountByCurrency, ...]
    on_hold_amount_by_currency: tuple[AmountByCurrency, ...]
    converted_amount_by_currency: tuple[AmountByCurrency, ...]
    average_po_value_by_currency: tuple[AmountByCurrency, ...]


@dataclass(frozen=True, slots=True)
class TrendPoint:
    period: str
    po_count: int
    amount_by_currency: tuple[AmountByCurrency, ...]


@dataclass(frozen=True, slots=True)
class DimensionItem:
    key: str
    count: int
    percentage: Decimal
    amount_by_currency: tuple[AmountByCurrency, ...]
    entity_id: UUID | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class ProductItem:
    product_id: UUID | None
    product_code: str
    product_name: str
    po_count: int
    ordered_quantity: Decimal
    percentage: Decimal
    amount_by_currency: tuple[AmountByCurrency, ...]


class DashboardRepository(Protocol):
    async def summary(
        self, filters: CustomerPoDashboardFilter, context: DashboardQueryContext
    ) -> SummaryResult: ...

    async def trend(
        self,
        filters: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        granularity: TrendGranularity,
    ) -> tuple[TrendPoint, ...]: ...

    async def dimension(
        self,
        dimension: str,
        filters: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        limit: int | None = None,
    ) -> tuple[DimensionItem, ...]: ...

    async def products(
        self,
        filters: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        limit: int | None = 10,
    ) -> tuple[ProductItem, ...]: ...
