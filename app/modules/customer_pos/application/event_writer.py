from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.audit.domain.entities import AuditContext, JsonValue
from app.modules.customer_pos.domain.events import (
    EVENT_CATEGORIES,
    CustomerPoEvent,
    CustomerPoEventActorType,
    CustomerPoEventRepository,
    CustomerPoEventSource,
    CustomerPoEventType,
)


class CustomerPoEventWriter:
    def __init__(self, repository: CustomerPoEventRepository) -> None:
        self.repository = repository

    async def write(
        self,
        *,
        tenant_id: UUID,
        customer_po_id: UUID,
        event_type: CustomerPoEventType,
        context: AuditContext,
        title: str,
        description: str | None = None,
        metadata: dict[str, JsonValue] | None = None,
    ) -> CustomerPoEvent:
        now = datetime.now(UTC)
        event = CustomerPoEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            customer_po_id=customer_po_id,
            event_type=event_type,
            event_category=EVENT_CATEGORIES[event_type],
            title=title,
            description=description,
            actor_type=CustomerPoEventActorType(context.actor_type.value),
            actor_user_id=context.actor_user_id,
            actor_display_name=context.actor_display_name,
            source=CustomerPoEventSource(context.source.value),
            correlation_id=context.correlation_id,
            request_id=context.request_id,
            metadata=metadata or {},
            occurred_at=now,
            created_at=now,
        )
        await self.repository.add(event)
        return event
