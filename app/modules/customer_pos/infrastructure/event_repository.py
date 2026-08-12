from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.domain.entities import JsonValue
from app.modules.customer_pos.domain.events import (
    CustomerPoEvent,
    CustomerPoEventActorType,
    CustomerPoEventCategory,
    CustomerPoEventPage,
    CustomerPoEventSource,
    CustomerPoEventType,
)
from app.modules.customer_pos.infrastructure.models import CustomerPoEventModel


class SqlAlchemyCustomerPoEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, event: CustomerPoEvent) -> None:
        self.session.add(
            CustomerPoEventModel(
                id=event.id,
                tenant_id=event.tenant_id,
                customer_po_id=event.customer_po_id,
                event_type=event.event_type.value,
                event_category=event.event_category.value,
                title=event.title,
                description=event.description,
                actor_type=event.actor_type.value,
                actor_user_id=event.actor_user_id,
                actor_display_name=event.actor_display_name,
                source=event.source.value,
                correlation_id=event.correlation_id,
                request_id=event.request_id,
                metadata_json=event.metadata,
                occurred_at=event.occurred_at,
                created_at=event.created_at,
            )
        )
        await self.session.flush()

    async def list_for_po(
        self,
        tenant_id: UUID,
        customer_po_id: UUID,
        page: int,
        page_size: int,
        event_type: CustomerPoEventType | None = None,
        category: CustomerPoEventCategory | None = None,
    ) -> CustomerPoEventPage:
        conditions = [
            CustomerPoEventModel.tenant_id == tenant_id,
            CustomerPoEventModel.customer_po_id == customer_po_id,
        ]
        if event_type is not None:
            conditions.append(CustomerPoEventModel.event_type == event_type.value)
        if category is not None:
            conditions.append(CustomerPoEventModel.event_category == category.value)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(CustomerPoEventModel).where(*conditions)
            )
            or 0
        )
        rows = (
            await self.session.scalars(
                select(CustomerPoEventModel)
                .where(*conditions)
                .order_by(CustomerPoEventModel.occurred_at.desc(), CustomerPoEventModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return CustomerPoEventPage(
            items=[self._entity(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _entity(row: CustomerPoEventModel) -> CustomerPoEvent:
        return CustomerPoEvent(
            id=row.id,
            tenant_id=row.tenant_id,
            customer_po_id=row.customer_po_id,
            event_type=CustomerPoEventType(row.event_type),
            event_category=CustomerPoEventCategory(row.event_category),
            title=row.title,
            description=row.description,
            actor_type=CustomerPoEventActorType(row.actor_type),
            actor_user_id=row.actor_user_id,
            actor_display_name=row.actor_display_name,
            source=CustomerPoEventSource(row.source),
            correlation_id=row.correlation_id,
            request_id=row.request_id,
            metadata=cast(dict[str, JsonValue], row.metadata_json),
            occurred_at=row.occurred_at,
            created_at=row.created_at,
        )
