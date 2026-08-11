from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.audit.domain.entities import AuditChange, AuditContext, AuditEvent, JsonValue
from app.modules.audit.domain.enums import AuditAction, AuditStatus
from app.modules.audit.domain.repository import AuditRepository


class AuditWriter:
    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    async def write_event(
        self,
        *,
        context: AuditContext,
        action: AuditAction,
        module: str,
        entity_type: str,
        entity_id: UUID | None,
        entity_code: str | None,
        entity_display_name: str | None,
        changes: list[AuditChange],
        status: AuditStatus = AuditStatus.SUCCESS,
        metadata: dict[str, JsonValue] | None = None,
        reason: str | None = None,
        batch_id: UUID | None = None,
    ) -> UUID:
        event_id = uuid4()
        now = datetime.now(UTC)
        event = AuditEvent(
            id=event_id,
            tenant_id=context.tenant_id,
            occurred_at=now,
            actor_user_id=context.actor_user_id,
            actor_email=context.actor_email,
            actor_display_name=context.actor_display_name,
            module=module,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_code=entity_code,
            entity_display_name=entity_display_name,
            source=context.source,
            correlation_id=context.correlation_id,
            request_id=context.request_id,
            request_method=context.request_method,
            request_path=context.request_path,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            status=status,
            actor_type=context.actor_type,
            batch_id=batch_id,
            reason=reason,
            metadata=metadata or {},
            created_at=now,
            changes=tuple(changes),
        )
        await self.repository.add_event(event, changes)
        return event_id
