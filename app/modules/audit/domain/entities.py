from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.modules.audit.domain.enums import (
    AuditAction,
    AuditActorType,
    AuditChangeType,
    AuditSource,
    AuditStatus,
    AuditValueType,
)

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AuditContext:
    tenant_id: UUID
    actor_user_id: UUID | None
    actor_email: str | None
    actor_display_name: str | None
    source: AuditSource
    actor_type: AuditActorType = AuditActorType.USER
    correlation_id: str | None = None
    request_id: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None

    @classmethod
    def for_system(
        cls,
        *,
        tenant_id: UUID,
        display_name: str = "SYSTEM",
        source: AuditSource = AuditSource.SYSTEM,
        correlation_id: str | None = None,
    ) -> "AuditContext":
        return cls(
            tenant_id=tenant_id,
            actor_user_id=None,
            actor_email=None,
            actor_display_name=display_name,
            source=source,
            actor_type=AuditActorType.SYSTEM,
            correlation_id=correlation_id,
        )


@dataclass(frozen=True, slots=True)
class AuditChange:
    sequence_no: int
    field_path: str
    field_label: str | None
    change_type: AuditChangeType
    value_type: AuditValueType | None
    old_value: JsonValue
    new_value: JsonValue
    old_display_value: str | None
    new_display_value: str | None
    is_sensitive: bool = False


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: UUID
    tenant_id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None
    actor_email: str | None
    actor_display_name: str | None
    module: str
    action: AuditAction
    entity_type: str
    entity_id: UUID | None
    entity_code: str | None
    entity_display_name: str | None
    source: AuditSource
    correlation_id: str | None
    request_id: str | None
    request_method: str | None
    request_path: str | None
    ip_address: str | None
    user_agent: str | None
    status: AuditStatus
    actor_type: AuditActorType = AuditActorType.USER
    error_code: str | None = None
    error_message: str | None = None
    batch_id: UUID | None = None
    reason: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    created_at: datetime | None = None
    changes: tuple[AuditChange, ...] = ()


@dataclass(frozen=True, slots=True)
class AuditEventSummary:
    event: AuditEvent
    change_count: int


@dataclass(frozen=True, slots=True)
class AuditPage:
    items: list[AuditEventSummary]
    total: int
    page: int
    page_size: int
