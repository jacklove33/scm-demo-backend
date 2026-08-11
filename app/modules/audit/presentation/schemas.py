from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.audit.domain.entities import AuditChange, AuditEvent, AuditEventSummary


class AuditActorResponse(BaseModel):
    type: str
    id: UUID | None
    email: str | None
    display_name: str | None


class AuditChangeResponse(BaseModel):
    sequence_no: int
    field_path: str
    field_label: str | None
    change_type: str
    value_type: str | None
    old_value: object | None
    new_value: object | None
    old_display_value: str | None
    new_display_value: str | None
    is_sensitive: bool

    @classmethod
    def from_domain(cls, change: AuditChange) -> "AuditChangeResponse":
        return cls(
            sequence_no=change.sequence_no,
            field_path=change.field_path,
            field_label=change.field_label,
            change_type=change.change_type.value,
            value_type=change.value_type.value if change.value_type else None,
            old_value=change.old_value,
            new_value=change.new_value,
            old_display_value=change.old_display_value,
            new_display_value=change.new_display_value,
            is_sensitive=change.is_sensitive,
        )


class AuditEventSummaryResponse(BaseModel):
    id: UUID
    occurred_at: datetime
    actor: AuditActorResponse
    actor_type: str
    actor_user_id: UUID | None
    actor_email: str | None
    actor_display_name: str | None
    module: str
    action: str
    entity_type: str
    entity_id: UUID | None
    entity_code: str | None
    entity_display_name: str | None
    source: str
    status: str
    change_count: int
    correlation_id: str | None
    batch_id: UUID | None

    @classmethod
    def from_domain(cls, item: AuditEventSummary) -> "AuditEventSummaryResponse":
        event = item.event
        return cls(
            id=event.id,
            occurred_at=event.occurred_at,
            actor=AuditActorResponse(
                type=event.actor_type.value,
                id=event.actor_user_id,
                email=event.actor_email,
                display_name=event.actor_display_name,
            ),
            actor_type=event.actor_type.value,
            actor_user_id=event.actor_user_id,
            actor_email=event.actor_email,
            actor_display_name=event.actor_display_name,
            module=event.module,
            action=event.action.value,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            entity_code=event.entity_code,
            entity_display_name=event.entity_display_name,
            source=event.source.value,
            status=event.status.value,
            change_count=item.change_count,
            correlation_id=event.correlation_id,
            batch_id=event.batch_id,
        )


class AuditEventListResponse(BaseModel):
    data: list[AuditEventSummaryResponse]
    total: int
    page: int
    page_size: int


class AuditEventDetailResponse(BaseModel):
    id: UUID
    occurred_at: datetime
    actor: AuditActorResponse
    actor_type: str
    actor_user_id: UUID | None
    actor_email: str | None
    actor_display_name: str | None
    module: str
    action: str
    entity_type: str
    entity_id: UUID | None
    entity_code: str | None
    entity_display_name: str | None
    source: str
    correlation_id: str | None
    request_id: str | None
    request_method: str | None
    request_path: str | None
    ip_address: str | None
    user_agent: str | None
    status: str
    error_code: str | None
    error_message: str | None
    batch_id: UUID | None
    reason: str | None
    metadata: dict[str, object]
    changes: list[AuditChangeResponse]

    @classmethod
    def from_domain(cls, event: AuditEvent) -> "AuditEventDetailResponse":
        return cls(
            id=event.id,
            occurred_at=event.occurred_at,
            actor=AuditActorResponse(
                type=event.actor_type.value,
                id=event.actor_user_id,
                email=event.actor_email,
                display_name=event.actor_display_name,
            ),
            actor_type=event.actor_type.value,
            actor_user_id=event.actor_user_id,
            actor_email=event.actor_email,
            actor_display_name=event.actor_display_name,
            module=event.module,
            action=event.action.value,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            entity_code=event.entity_code,
            entity_display_name=event.entity_display_name,
            source=event.source.value,
            correlation_id=event.correlation_id,
            request_id=event.request_id,
            request_method=event.request_method,
            request_path=event.request_path,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            status=event.status.value,
            error_code=event.error_code,
            error_message=event.error_message,
            batch_id=event.batch_id,
            reason=event.reason,
            metadata=dict(event.metadata),
            changes=[AuditChangeResponse.from_domain(change) for change in event.changes],
        )
