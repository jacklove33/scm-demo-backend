from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.dashboard import get_customer_po_dashboard_service
from app.api.dependencies.identity import get_current_user
from app.core.exceptions import PermissionDenied
from app.modules.customer_pos.domain.enums import CustomerPoStatus
from app.modules.dashboard.application.service import (
    PERMISSION,
    CustomerPoDashboardService,
    percentage_change,
)
from app.modules.dashboard.domain.models import (
    ATTENTION_RULES,
    CustomerPoDashboardFilter,
    DimensionItem,
    SummaryResult,
    TrendGranularity,
)
from app.modules.dashboard.presentation.schemas import (
    AttentionItemResponse,
    AttentionResponse,
    CountryItemResponse,
    CountryResponse,
    CurrencyPercentResponse,
    CustomerItemResponse,
    CustomerResponse,
    DimensionItemResponse,
    DimensionResponse,
    ModulesResponse,
    OverviewResponse,
    SourceItemResponse,
    SourceResponse,
    StatusItemResponse,
    StatusResponse,
    SummaryChangeResponse,
    SummaryMetricsResponse,
    SummaryResponse,
    TrendPointResponse,
    TrendResponse,
)
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def filters(
    date_from: date | None,
    date_to: date | None,
    customer_id: UUID | None,
    owner_user_id: UUID | None,
    status: CustomerPoStatus | None,
) -> CustomerPoDashboardFilter:
    return CustomerPoDashboardFilter(date_from, date_to, customer_id, owner_user_id, status)


def metrics(value: SummaryResult) -> SummaryMetricsResponse:
    return SummaryMetricsResponse(
        **{field: getattr(value, field) for field in SummaryMetricsResponse.model_fields}
    )


def summary_response(current: SummaryResult, previous: SummaryResult | None) -> SummaryResponse:
    change = None
    if previous:
        previous_amounts = {item.currency: item.amount for item in previous.amount_by_currency}
        amount_changes = [
            CurrencyPercentResponse(currency=item.currency, percent=change_value)
            for item in current.amount_by_currency
            if (
                change_value := percentage_change(
                    item.amount, previous_amounts.get(item.currency, Decimal(0))
                )
            )
            is not None
        ]
        change = SummaryChangeResponse(
            po_count_percent=percentage_change(
                Decimal(current.total_po_count), Decimal(previous.total_po_count)
            ),
            po_amount_percent_by_currency=amount_changes,
        )
    return SummaryResponse(
        **metrics(current).model_dump(),
        previous_period=metrics(previous) if previous else None,
        change=change,
    )


def dimension_response(items: tuple[DimensionItem, ...]) -> DimensionResponse:
    return DimensionResponse(
        items=[DimensionItemResponse.model_validate(item, from_attributes=True) for item in items]
    )


def status_response(items: tuple[DimensionItem, ...]) -> StatusResponse:
    return StatusResponse(
        items=[
            StatusItemResponse(
                status=item.key,
                count=item.count,
                percentage=item.percentage,
                amount_by_currency=item.amount_by_currency,
            )
            for item in items
        ]
    )


def source_response(items: tuple[DimensionItem, ...]) -> SourceResponse:
    return SourceResponse(
        items=[
            SourceItemResponse(
                source=item.key,
                count=item.count,
                percentage=item.percentage,
                amount_by_currency=item.amount_by_currency,
            )
            for item in items
        ]
    )


def customer_response(items: tuple[DimensionItem, ...]) -> CustomerResponse:
    return CustomerResponse(
        items=[
            CustomerItemResponse(
                customer_id=item.entity_id,
                customer_code=item.key,
                customer_name=item.label or item.key,
                po_count=item.count,
                percentage=item.percentage,
                amount_by_currency=item.amount_by_currency,
            )
            for item in items
            if item.entity_id is not None
        ]
    )


COUNTRY_NAMES = {
    "CN": "China",
    "DE": "Germany",
    "GB": "United Kingdom",
    "JP": "Japan",
    "KR": "South Korea",
    "SG": "Singapore",
    "TW": "Taiwan",
    "US": "United States",
}


def country_response(items: tuple[DimensionItem, ...]) -> CountryResponse:
    return CountryResponse(
        items=[
            CountryItemResponse(
                country_code=item.key,
                country_name=COUNTRY_NAMES.get(item.key, item.key),
                po_count=item.count,
                percentage=item.percentage,
                amount_by_currency=item.amount_by_currency,
            )
            for item in items
        ]
    )


def attention_response(items: tuple[DimensionItem, ...]) -> AttentionResponse:
    return AttentionResponse(
        items=[
            AttentionItemResponse(
                code=rule[0],
                severity=rule[1],
                title=rule[2],
                count=item.count,
                amount_by_currency=item.amount_by_currency,
            )
            for item in items
            if (rule := ATTENTION_RULES.get(CustomerPoStatus(item.key))) is not None
        ]
    )


async def get_summary(
    service: CustomerPoDashboardService, actor: CurrentUser, values: CustomerPoDashboardFilter
) -> SummaryResponse:
    current, previous = await service.summary(values, actor)
    return summary_response(current, previous)


@router.get("/modules", response_model=ModulesResponse)
async def dashboard_modules(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
) -> ModulesResponse:
    if not actor.can(PERMISSION):
        raise PermissionDenied(f"Missing permission: {PERMISSION}")
    return ModulesResponse(
        modules=[
            {"code": "CUSTOMER_PO", "label": "Customer PO", "enabled": True},
            {"code": "SALES_ORDER", "label": "Sales Order", "enabled": False},
            {"code": "PURCHASE_ORDER", "label": "Purchase Order", "enabled": False},
            {"code": "SHIPMENT", "label": "Shipment", "enabled": False},
            {"code": "INVENTORY", "label": "Inventory", "enabled": False},
            {"code": "EDI", "label": "EDI", "enabled": False},
        ]
    )


@router.get("/customer-pos/summary", response_model=SummaryResponse)
async def customer_po_summary(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[CustomerPoDashboardService, Depends(get_customer_po_dashboard_service)],
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: UUID | None = None,
    owner_user_id: UUID | None = None,
    po_status: Annotated[CustomerPoStatus | None, Query(alias="status")] = None,
) -> SummaryResponse:
    return await get_summary(
        service, actor, filters(date_from, date_to, customer_id, owner_user_id, po_status)
    )


@router.get("/customer-pos/trend", response_model=TrendResponse)
async def customer_po_trend(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[CustomerPoDashboardService, Depends(get_customer_po_dashboard_service)],
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: TrendGranularity | None = None,
) -> TrendResponse:
    selected, points = await service.trend(
        CustomerPoDashboardFilter(date_from, date_to), actor, granularity
    )
    return TrendResponse(
        granularity=selected.value,
        series=[TrendPointResponse.model_validate(point, from_attributes=True) for point in points],
    )


async def get_dimension(
    dimension: str,
    service: CustomerPoDashboardService,
    actor: CurrentUser,
    date_from: date | None,
    date_to: date | None,
    customer_id: UUID | None,
    owner_user_id: UUID | None,
    status: CustomerPoStatus | None,
    limit: int | None = None,
) -> DimensionResponse:
    result = await service.dimension(
        dimension, filters(date_from, date_to, customer_id, owner_user_id, status), actor, limit
    )
    return dimension_response(result)


@router.get("/customer-pos/by-status", response_model=StatusResponse)
async def by_status(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[CustomerPoDashboardService, Depends(get_customer_po_dashboard_service)],
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: UUID | None = None,
    owner_user_id: UUID | None = None,
    po_status: Annotated[CustomerPoStatus | None, Query(alias="status")] = None,
) -> StatusResponse:
    result = await service.dimension(
        "status", filters(date_from, date_to, customer_id, owner_user_id, po_status), actor
    )
    return status_response(result)


@router.get("/customer-pos/by-customer", response_model=CustomerResponse)
async def by_customer(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[CustomerPoDashboardService, Depends(get_customer_po_dashboard_service)],
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: UUID | None = None,
    owner_user_id: UUID | None = None,
    po_status: Annotated[CustomerPoStatus | None, Query(alias="status")] = None,
    limit: int = Query(10, ge=1, le=100),
) -> CustomerResponse:
    result = await service.dimension(
        "customer",
        filters(date_from, date_to, customer_id, owner_user_id, po_status),
        actor,
        limit,
    )
    return customer_response(result)


@router.get("/customer-pos/by-source", response_model=SourceResponse)
async def by_source(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[CustomerPoDashboardService, Depends(get_customer_po_dashboard_service)],
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: UUID | None = None,
    owner_user_id: UUID | None = None,
    po_status: Annotated[CustomerPoStatus | None, Query(alias="status")] = None,
) -> SourceResponse:
    result = await service.dimension(
        "source", filters(date_from, date_to, customer_id, owner_user_id, po_status), actor
    )
    return source_response(result)


@router.get("/customer-pos/by-country", response_model=CountryResponse)
async def by_country(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[CustomerPoDashboardService, Depends(get_customer_po_dashboard_service)],
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: UUID | None = None,
    owner_user_id: UUID | None = None,
    po_status: Annotated[CustomerPoStatus | None, Query(alias="status")] = None,
) -> CountryResponse:
    result = await service.dimension(
        "country", filters(date_from, date_to, customer_id, owner_user_id, po_status), actor
    )
    return country_response(result)


@router.get("/customer-pos/attention", response_model=AttentionResponse)
async def attention(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[CustomerPoDashboardService, Depends(get_customer_po_dashboard_service)],
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: UUID | None = None,
    owner_user_id: UUID | None = None,
) -> AttentionResponse:
    result = await service.dimension(
        "status", filters(date_from, date_to, customer_id, owner_user_id, None), actor
    )
    return attention_response(result)


@router.get("/customer-pos/overview", response_model=OverviewResponse)
async def overview(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[CustomerPoDashboardService, Depends(get_customer_po_dashboard_service)],
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: UUID | None = None,
    owner_user_id: UUID | None = None,
    po_status: Annotated[CustomerPoStatus | None, Query(alias="status")] = None,
    granularity: TrendGranularity | None = None,
    customer_limit: int = Query(10, ge=1, le=100),
) -> OverviewResponse:
    values = filters(date_from, date_to, customer_id, owner_user_id, po_status)
    summary = await get_summary(service, actor, values)
    selected, points = await service.trend(values, actor, granularity)
    status_items = await service.dimension("status", values, actor)
    source_items = await service.dimension("source", values, actor)
    customer_items = await service.dimension("customer", values, actor, customer_limit)
    return OverviewResponse(
        summary=summary,
        trend=TrendResponse(
            granularity=selected.value,
            series=[
                TrendPointResponse.model_validate(point, from_attributes=True) for point in points
            ],
        ),
        by_status=status_response(status_items),
        by_customer=customer_response(customer_items),
        by_source=source_response(source_items),
        attention=attention_response(status_items),
    )
