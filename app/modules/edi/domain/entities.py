from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.edi.domain.enums import (
    EdiMessageDirection,
    EdiMessageEventType,
    EdiMessageStatus,
    EdiRelatedEntityType,
)


@dataclass(frozen=True, slots=True)
class EdiMessage:
    id: UUID
    tenant_id: UUID
    direction: EdiMessageDirection
    source_system: str
    source_protocol: str
    document_standard: str
    document_type: str
    sender_id: str
    receiver_id: str
    external_message_id: str | None
    correlation_id: str | None
    business_document_number: str | None
    status: EdiMessageStatus
    error_code: str | None
    error_message: str | None
    related_entity_type: EdiRelatedEntityType | None
    related_entity_id: UUID | None
    received_at: datetime | None
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EdiMessageEvent:
    id: UUID
    tenant_id: UUID
    edi_message_id: UUID
    event_type: EdiMessageEventType
    status_from: EdiMessageStatus | None
    status_to: EdiMessageStatus | None
    message: str | None
    error_code: str | None
    error_details: dict[str, object] | None
    metadata: dict[str, object] | None
    created_at: datetime
