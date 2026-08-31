from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customer_pos.infrastructure.models import CustomerPoLineModel, CustomerPoModel
from app.modules.customers.infrastructure.models import (
    BusinessPartnerModel,
    CustomerGroupAssignmentModel,
    CustomerUserAssignmentModel,
)
from app.modules.dashboard.domain.models import (
    OPEN_CUSTOMER_PO_STATUSES,
    AmountByCurrency,
    CustomerPoDashboardFilter,
    DashboardQueryContext,
    DimensionItem,
    ProductItem,
    SummaryResult,
    TrendGranularity,
    TrendPoint,
)
from app.modules.iam.infrastructure.models import UserGroupModel
from app.shared.domain.current_user import PermissionScope


class SqlAlchemyDashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self, filters: CustomerPoDashboardFilter, context: DashboardQueryContext) -> Any:
        statement = select().where(
            CustomerPoModel.tenant_id == context.tenant_id,
            CustomerPoModel.deleted_at.is_(None),
            CustomerPoModel.customer_po_date.is_not(None),
        )
        if context.scope == PermissionScope.OWN:
            statement = statement.where(CustomerPoModel.owner_user_id == context.actor_id)
        elif context.scope == PermissionScope.ASSIGNED:
            assigned = select(CustomerUserAssignmentModel.customer_id).where(
                CustomerUserAssignmentModel.user_id == context.actor_id
            )
            statement = statement.where(CustomerPoModel.customer_id.in_(assigned))
        elif context.scope == PermissionScope.TEAM:
            groups = select(UserGroupModel.group_id).where(
                UserGroupModel.user_id == context.actor_id
            )
            team = select(CustomerGroupAssignmentModel.customer_id).where(
                CustomerGroupAssignmentModel.group_id.in_(groups)
            )
            statement = statement.where(
                or_(
                    CustomerPoModel.owner_user_id == context.actor_id,
                    CustomerPoModel.customer_id.in_(team),
                )
            )
        elif context.scope != PermissionScope.ALL:
            statement = statement.where(false())
        if filters.date_from:
            statement = statement.where(CustomerPoModel.customer_po_date >= filters.date_from)
        if filters.date_to:
            statement = statement.where(CustomerPoModel.customer_po_date <= filters.date_to)
        if filters.customer_id:
            statement = statement.where(CustomerPoModel.customer_id == filters.customer_id)
        if filters.owner_user_id:
            statement = statement.where(CustomerPoModel.owner_user_id == filters.owner_user_id)
        if filters.status:
            statement = statement.where(CustomerPoModel.status == filters.status.value)
        return statement

    async def summary(
        self, filters: CustomerPoDashboardFilter, context: DashboardQueryContext
    ) -> SummaryResult:
        currency = func.coalesce(CustomerPoModel.currency_code, "UNSPECIFIED")
        amount = func.coalesce(CustomerPoModel.total_amount, 0)
        open_values = tuple(status.value for status in OPEN_CUSTOMER_PO_STATUSES)
        statement = (
            self._base(filters, context)
            .add_columns(
                currency.label("currency"),
                func.count().label("total_count"),
                func.sum(amount).label("total_amount"),
                func.sum(case((CustomerPoModel.status.in_(open_values), 1), else_=0)).label(
                    "open_count"
                ),
                func.sum(case((CustomerPoModel.status.in_(open_values), amount), else_=0)).label(
                    "open_amount"
                ),
                func.sum(case((CustomerPoModel.status == "ON_HOLD", 1), else_=0)).label(
                    "hold_count"
                ),
                func.sum(case((CustomerPoModel.status == "ON_HOLD", amount), else_=0)).label(
                    "hold_amount"
                ),
                func.sum(case((CustomerPoModel.status == "CONVERTED", 1), else_=0)).label(
                    "converted_count"
                ),
                func.sum(case((CustomerPoModel.status == "CONVERTED", amount), else_=0)).label(
                    "converted_amount"
                ),
                func.sum(case((CustomerPoModel.status == "CANCELLED", 1), else_=0)).label(
                    "cancelled_count"
                ),
                func.avg(amount).label("average_amount"),
            )
            .group_by(currency)
            .order_by(currency)
        )
        rows = (await self.session.execute(statement)).all()

        def amounts(field: str) -> tuple[AmountByCurrency, ...]:
            return tuple(
                AmountByCurrency(str(row.currency), Decimal(str(getattr(row, field) or 0)))
                for row in rows
            )

        return SummaryResult(
            total_po_count=sum(int(row.total_count) for row in rows),
            open_po_count=sum(int(row.open_count or 0) for row in rows),
            on_hold_count=sum(int(row.hold_count or 0) for row in rows),
            converted_count=sum(int(row.converted_count or 0) for row in rows),
            cancelled_count=sum(int(row.cancelled_count or 0) for row in rows),
            amount_by_currency=amounts("total_amount"),
            open_amount_by_currency=amounts("open_amount"),
            on_hold_amount_by_currency=amounts("hold_amount"),
            converted_amount_by_currency=amounts("converted_amount"),
            average_po_value_by_currency=amounts("average_amount"),
        )

    async def trend(
        self,
        filters: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        granularity: TrendGranularity,
    ) -> tuple[TrendPoint, ...]:
        bucket = func.date_trunc(granularity.value.lower(), CustomerPoModel.customer_po_date)
        currency = func.coalesce(CustomerPoModel.currency_code, "UNSPECIFIED")
        statement = (
            self._base(filters, context)
            .add_columns(
                bucket.label("bucket"),
                currency.label("currency"),
                func.count().label("count"),
                func.coalesce(func.sum(CustomerPoModel.total_amount), 0).label("amount"),
            )
            .where(CustomerPoModel.customer_po_date.is_not(None))
            .group_by(bucket, currency)
            .order_by(bucket, currency)
        )
        rows = (await self.session.execute(statement)).all()
        grouped: dict[Any, list[Any]] = defaultdict(list)
        for row in rows:
            grouped[row.bucket].append(row)
        formats = {
            TrendGranularity.DAY: "%Y-%m-%d",
            TrendGranularity.WEEK: "%Y-%m-%d",
            TrendGranularity.MONTH: "%Y-%m",
        }
        return tuple(
            TrendPoint(
                bucket_value.strftime(formats[granularity]),
                sum(int(row.count) for row in bucket_rows),
                tuple(
                    AmountByCurrency(str(row.currency), Decimal(str(row.amount)))
                    for row in bucket_rows
                ),
            )
            for bucket_value, bucket_rows in grouped.items()
        )

    async def dimension(
        self,
        dimension: str,
        filters: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        limit: int | None = None,
    ) -> tuple[DimensionItem, ...]:
        columns: dict[str, tuple[Any, Any | None, Any | None]] = {
            "status": (CustomerPoModel.status, None, None),
            "source": (CustomerPoModel.source, None, None),
            "country": (CustomerPoModel.ship_to_country_code, None, None),
            "customer": (
                BusinessPartnerModel.partner_code,
                BusinessPartnerModel.id,
                BusinessPartnerModel.partner_name,
            ),
        }
        key, entity_id, label = columns[dimension]
        currency = func.coalesce(CustomerPoModel.currency_code, "UNSPECIFIED")
        selected = [key.label("key")]
        groups = [key, currency]
        if entity_id is not None:
            assert label is not None
            selected.extend([entity_id.label("entity_id"), label.label("label")])
            groups.extend([entity_id, label])
        statement = self._base(filters, context).add_columns(
            *selected,
            currency.label("currency"),
            func.count().label("count"),
            func.coalesce(func.sum(CustomerPoModel.total_amount), 0).label("amount"),
        )
        if dimension == "customer":
            statement = statement.join(
                BusinessPartnerModel,
                (BusinessPartnerModel.id == CustomerPoModel.customer_id)
                & (BusinessPartnerModel.tenant_id == CustomerPoModel.tenant_id),
            )
        if dimension == "country":
            statement = statement.where(CustomerPoModel.ship_to_country_code.is_not(None))
        rows = (
            await self.session.execute(statement.group_by(*groups).order_by(key, currency))
        ).all()
        merged: dict[str, list[Any]] = defaultdict(list)
        for row in rows:
            merged[str(row.key)].append(row)
        total = sum(int(row._mapping["count"]) for row in rows)
        items = [
            DimensionItem(
                key_value,
                sum(int(row._mapping["count"]) for row in item_rows),
                Decimal("0")
                if total == 0
                else Decimal(sum(int(row._mapping["count"]) for row in item_rows) * 100)
                / Decimal(total),
                tuple(
                    AmountByCurrency(str(row.currency), Decimal(str(row.amount)))
                    for row in item_rows
                ),
                getattr(item_rows[0], "entity_id", None),
                getattr(item_rows[0], "label", None),
            )
            for key_value, item_rows in merged.items()
        ]
        items.sort(key=lambda item: (-item.count, item.key))
        return tuple(items[:limit] if limit else items)

    async def products(
        self,
        filters: CustomerPoDashboardFilter,
        context: DashboardQueryContext,
        limit: int | None = 10,
    ) -> tuple[ProductItem, ...]:
        product_code = func.coalesce(
            CustomerPoLineModel.internal_item_number,
            CustomerPoLineModel.customer_item_number,
            CustomerPoLineModel.item_description,
            "UNSPECIFIED",
        )
        product_name = func.coalesce(
            CustomerPoLineModel.item_description,
            CustomerPoLineModel.internal_item_number,
            CustomerPoLineModel.customer_item_number,
            "Unspecified Product",
        )
        currency = func.coalesce(
            CustomerPoLineModel.currency_code, CustomerPoModel.currency_code, "UNSPECIFIED"
        )
        line_amount = func.coalesce(
            CustomerPoLineModel.line_amount,
            CustomerPoLineModel.ordered_quantity * func.coalesce(CustomerPoLineModel.unit_price, 0),
            0,
        )
        statement = (
            self._base(filters, context)
            .join(
                CustomerPoLineModel,
                (CustomerPoLineModel.customer_po_id == CustomerPoModel.id)
                & (CustomerPoLineModel.tenant_id == CustomerPoModel.tenant_id),
            )
            .add_columns(
                CustomerPoLineModel.product_id.label("product_id"),
                product_code.label("product_code"),
                product_name.label("product_name"),
                currency.label("currency"),
                func.count(func.distinct(CustomerPoModel.id)).label("po_count"),
                func.sum(CustomerPoLineModel.ordered_quantity).label("ordered_quantity"),
                func.sum(line_amount).label("amount"),
            )
            .group_by(CustomerPoLineModel.product_id, product_code, product_name, currency)
        )
        rows = (await self.session.execute(statement)).all()
        grouped: dict[tuple[Any, str, str], list[Any]] = defaultdict(list)
        for row in rows:
            grouped[(row.product_id, str(row.product_code), str(row.product_name))].append(row)
        total_associations = sum(
            sum(int(row.po_count) for row in product_rows) for product_rows in grouped.values()
        )
        items = [
            ProductItem(
                product_id=product_id,
                product_code=code,
                product_name=name,
                po_count=sum(int(row.po_count) for row in product_rows),
                ordered_quantity=sum(
                    (Decimal(str(row.ordered_quantity or 0)) for row in product_rows), Decimal(0)
                ),
                percentage=Decimal(0)
                if total_associations == 0
                else Decimal(sum(int(row.po_count) for row in product_rows) * 100)
                / Decimal(total_associations),
                amount_by_currency=tuple(
                    AmountByCurrency(str(row.currency), Decimal(str(row.amount or 0)))
                    for row in product_rows
                ),
            )
            for (product_id, code, name), product_rows in grouped.items()
        ]
        items.sort(key=lambda item: (-item.po_count, item.product_code))
        return tuple(items[:limit] if limit else items)
