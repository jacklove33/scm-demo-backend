from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import literal_column
from sqlalchemy.dialects import postgresql

from app.core.exceptions import PermissionDenied, ValidationFailure
from app.modules.dashboard.application.service import CustomerPoDashboardService
from app.modules.dashboard.domain.models import (
    AmountByCurrency,
    CustomerPoDashboardFilter,
    DashboardQueryContext,
    DashboardRepository,
    DimensionItem,
    ProductItem,
    SummaryResult,
    TrendGranularity,
    TrendPoint,
)
from app.modules.dashboard.infrastructure.repository import SqlAlchemyDashboardRepository
from app.modules.dashboard.presentation.router import (
    attention_response,
    product_response,
    summary_response,
)
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def empty_summary() -> SummaryResult:
    return SummaryResult(0, 0, 0, 0, 0, (), (), (), (), ())


class FakeRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, DashboardQueryContext]] = []

    async def summary(
        self, values: CustomerPoDashboardFilter, context: DashboardQueryContext
    ) -> SummaryResult:
        self.calls.append(("summary", values, context))
        return SummaryResult(
            3,
            1,
            1,
            1,
            0,
            (AmountByCurrency("USD", Decimal("60")), AmountByCurrency("TWD", Decimal("900"))),
            (AmountByCurrency("USD", Decimal("10")),),
            (AmountByCurrency("USD", Decimal("10")),),
            (AmountByCurrency("TWD", Decimal("900")),),
            (AmountByCurrency("USD", Decimal("30")), AmountByCurrency("TWD", Decimal("900"))),
        )

    async def trend(
        self,
        values: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        granularity: TrendGranularity,
    ) -> tuple[TrendPoint, ...]:
        self.calls.append(("trend", values, context))
        return (TrendPoint("2026-08", 3, (AmountByCurrency("USD", Decimal("60")),)),)

    async def dimension(
        self,
        dimension: str,
        values: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        limit: int | None = None,
    ) -> tuple[DimensionItem, ...]:
        self.calls.append((dimension, values, context))
        return (
            DimensionItem("EDI", 2, Decimal("66.67"), (AmountByCurrency("USD", Decimal("50")),)),
        )

    async def products(
        self,
        values: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        limit: int | None = 10,
    ) -> tuple[ProductItem, ...]:
        self.calls.append(("product", values, context))
        return (
            ProductItem(
                None,
                "P1001",
                "USB Controller",
                2,
                Decimal("12"),
                Decimal("66.67"),
                (AmountByCurrency("USD", Decimal("50")),),
            ),
        )


def actor(*, allowed: bool = True, scope: PermissionScope = PermissionScope.ALL) -> CurrentUser:
    permissions = {}
    if allowed:
        permissions["dashboard.customer_pos.read"] = EffectivePermission(
            "dashboard.customer_pos.read", PermissionEffect.ALLOW, scope, ()
        )
    return CurrentUser(ACTOR, TENANT, "admin@example.test", "Admin", True, permissions)


def service(repository: FakeRepository) -> CustomerPoDashboardService:
    return CustomerPoDashboardService(cast(DashboardRepository, cast(Any, repository)))


@pytest.mark.asyncio
async def test_dashboard_requires_permission_and_uses_authenticated_tenant_and_scope() -> None:
    repository = FakeRepository()
    with pytest.raises(PermissionDenied):
        await service(repository).summary(CustomerPoDashboardFilter(), actor(allowed=False))

    result, previous = await service(repository).summary(
        CustomerPoDashboardFilter(customer_id=UUID("40000000-0000-0000-0000-000000000001")),
        actor(scope=PermissionScope.TEAM),
    )
    assert result.total_po_count == 3
    assert previous is None
    context = repository.calls[0][2]
    assert context.tenant_id == TENANT
    assert context.actor_id == ACTOR
    assert context.scope == PermissionScope.TEAM


@pytest.mark.asyncio
async def test_summary_uses_equal_previous_period_and_preserves_currency_groups() -> None:
    repository = FakeRepository()
    result, previous = await service(repository).summary(
        CustomerPoDashboardFilter(date(2026, 8, 1), date(2026, 8, 10)), actor()
    )
    assert previous is not None
    previous_filter = cast(CustomerPoDashboardFilter, repository.calls[1][1])
    assert previous_filter.date_from == date(2026, 7, 22)
    assert previous_filter.date_to == date(2026, 7, 31)
    assert {item.currency for item in result.amount_by_currency} == {"USD", "TWD"}


@pytest.mark.asyncio
async def test_filters_trend_dimensions_and_empty_results_are_valid() -> None:
    repository = FakeRepository()
    values = CustomerPoDashboardFilter(date(2026, 1, 1), date(2026, 8, 1))
    granularity, points = await service(repository).trend(values, actor(), None)
    assert granularity == TrendGranularity.MONTH
    assert points[0].po_count == 3
    items = await service(repository).dimension("source", values, actor(), 10)
    assert items[0].key == "EDI"


def test_invalid_date_range_is_rejected() -> None:
    with pytest.raises(ValidationFailure):
        CustomerPoDashboardService.validate(
            CustomerPoDashboardFilter(date(2026, 8, 2), date(2026, 8, 1))
        )


def test_summary_response_never_combines_currency_amounts() -> None:
    response = summary_response(
        SummaryResult(
            2,
            1,
            0,
            1,
            0,
            (AmountByCurrency("TWD", Decimal("1000")), AmountByCurrency("USD", Decimal("50"))),
            (AmountByCurrency("USD", Decimal("50")),),
            (),
            (AmountByCurrency("TWD", Decimal("1000")),),
            (AmountByCurrency("TWD", Decimal("1000")), AmountByCurrency("USD", Decimal("50"))),
        ),
        None,
    )
    assert [(item.currency, item.amount) for item in response.amount_by_currency] == [
        ("TWD", Decimal("1000")),
        ("USD", Decimal("50")),
    ]


def test_attention_uses_actionable_codes_and_only_reliable_statuses() -> None:
    items = (
        DimensionItem("VALIDATING", 2, Decimal("50"), (AmountByCurrency("USD", Decimal("20")),)),
        DimensionItem("ON_HOLD", 1, Decimal("25"), (AmountByCurrency("USD", Decimal("10")),)),
        DimensionItem("DRAFT", 1, Decimal("25"), (AmountByCurrency("USD", Decimal("5")),)),
    )
    response = attention_response(items)
    assert [(item.code, item.severity, item.count) for item in response.items] == [
        ("VALIDATION_PENDING", "INFO", 2),
        ("ON_HOLD", "WARNING", 1),
    ]


def test_product_response_preserves_decimal_quantity_and_currency_groups() -> None:
    response = product_response(
        (
            ProductItem(
                None,
                "P1001",
                "USB Controller",
                15,
                Decimal("1200.5"),
                Decimal("28.5"),
                (
                    AmountByCurrency("EUR", Decimal("520000")),
                    AmountByCurrency("USD", Decimal("310000")),
                ),
            ),
        )
    )
    item = response.items[0]
    assert item.product_code == "P1001"
    assert item.ordered_quantity == Decimal("1200.5")
    assert [(amount.currency, amount.amount) for amount in item.amount_by_currency] == [
        ("EUR", Decimal("520000")),
        ("USD", Decimal("310000")),
    ]


def test_repository_base_query_enforces_tenant_scope_dates_and_soft_delete() -> None:
    repository = SqlAlchemyDashboardRepository(cast(Any, object()))
    customer_id = UUID("40000000-0000-0000-0000-000000000001")
    values = CustomerPoDashboardFilter(
        date(2026, 1, 1),
        date(2026, 1, 31),
        customer_id,
        ACTOR,
    )
    statement = repository._base(values, DashboardQueryContext(TENANT, ACTOR, PermissionScope.OWN))
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    compiled = statement.add_columns(literal_column("1")).compile(dialect=dialect)
    sql = str(compiled)

    assert "customer_purchase_orders.tenant_id =" in sql
    assert "customer_purchase_orders.deleted_at IS NULL" in sql
    assert "customer_purchase_orders.customer_po_date IS NOT NULL" in sql
    assert "customer_purchase_orders.owner_user_id =" in sql
    assert "customer_purchase_orders.customer_id =" in sql
    assert TENANT in compiled.params.values()
    assert customer_id in compiled.params.values()


@pytest.mark.asyncio
async def test_product_repository_aggregates_lines_without_combining_currencies() -> None:
    rows = [
        SimpleNamespace(
            product_id=None,
            product_code="P1001",
            product_name="Controller",
            currency="EUR",
            po_count=2,
            ordered_quantity=Decimal("12"),
            amount=Decimal("500"),
        ),
        SimpleNamespace(
            product_id=None,
            product_code="P1001",
            product_name="Controller",
            currency="USD",
            po_count=1,
            ordered_quantity=Decimal("3"),
            amount=Decimal("200"),
        ),
    ]
    result = SimpleNamespace(all=lambda: rows)
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    repository = SqlAlchemyDashboardRepository(cast(Any, session))
    items = await repository.products(
        CustomerPoDashboardFilter(), DashboardQueryContext(TENANT, ACTOR, PermissionScope.ALL)
    )
    assert items[0].po_count == 3
    assert items[0].ordered_quantity == Decimal("15")
    assert [(amount.currency, amount.amount) for amount in items[0].amount_by_currency] == [
        ("EUR", Decimal("500")),
        ("USD", Decimal("200")),
    ]
