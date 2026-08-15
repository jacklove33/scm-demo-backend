from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from app.core.exceptions import PermissionDenied, ValidationFailure
from app.modules.dashboard.domain.models import (
    CustomerPoDashboardFilter,
    DashboardQueryContext,
    DashboardRepository,
    DimensionItem,
    ProductItem,
    SummaryResult,
    TrendGranularity,
    TrendPoint,
)
from app.shared.domain.current_user import CurrentUser

PERMISSION = "dashboard.customer_pos.read"


def percentage_change(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        return None
    return ((current - previous) / previous * 100).quantize(Decimal("0.01"))


class CustomerPoDashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self.repository = repository

    @staticmethod
    def validate(filters: CustomerPoDashboardFilter) -> None:
        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise ValidationFailure("date_from must be on or before date_to")

    @staticmethod
    def _context(actor: CurrentUser) -> DashboardQueryContext:
        if not actor.can(PERMISSION):
            raise PermissionDenied(f"Missing permission: {PERMISSION}")
        return DashboardQueryContext(actor.tenant_id, actor.user_id, actor.scope_for(PERMISSION))

    async def summary(
        self, filters: CustomerPoDashboardFilter, actor: CurrentUser
    ) -> tuple[SummaryResult, SummaryResult | None]:
        self.validate(filters)
        context = self._context(actor)
        current = await self.repository.summary(filters, context)
        previous = None
        if filters.date_from and filters.date_to:
            days = (filters.date_to - filters.date_from).days + 1
            previous_to = filters.date_from - timedelta(days=1)
            previous = await self.repository.summary(
                replace(
                    filters, date_from=previous_to - timedelta(days=days - 1), date_to=previous_to
                ),
                context,
            )
        return current, previous

    async def trend(
        self,
        filters: CustomerPoDashboardFilter,
        actor: CurrentUser,
        granularity: TrendGranularity | None,
    ) -> tuple[TrendGranularity, tuple[TrendPoint, ...]]:
        self.validate(filters)
        selected = granularity or self.default_granularity(filters.date_from, filters.date_to)
        return selected, await self.repository.trend(filters, self._context(actor), selected)

    async def dimension(
        self,
        dimension: str,
        filters: CustomerPoDashboardFilter,
        actor: CurrentUser,
        limit: int | None = None,
    ) -> tuple[DimensionItem, ...]:
        self.validate(filters)
        return await self.repository.dimension(dimension, filters, self._context(actor), limit)

    async def products(
        self,
        filters: CustomerPoDashboardFilter,
        actor: CurrentUser,
        limit: int | None = 10,
    ) -> tuple[ProductItem, ...]:
        self.validate(filters)
        return await self.repository.products(filters, self._context(actor), limit)

    @staticmethod
    def default_granularity(date_from: date | None, date_to: date | None) -> TrendGranularity:
        if not date_from or not date_to:
            return TrendGranularity.MONTH
        days = (date_to - date_from).days + 1
        if days <= 31:
            return TrendGranularity.DAY
        if days <= 120:
            return TrendGranularity.WEEK
        return TrendGranularity.MONTH
