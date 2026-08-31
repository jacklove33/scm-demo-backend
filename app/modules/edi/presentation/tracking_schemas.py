from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.edi.domain.entities import EdiMessage, EdiMessageEvent
from app.modules.edi.domain.enums import (
    EdiMessageDirection,
    EdiMessageEventType,
    EdiMessageStatus,
    EdiRelatedEntityType,
)


class EdiMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
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

    @classmethod
    def from_domain(cls, value: EdiMessage) -> "EdiMessageResponse":
        return cls.model_validate(value)


class EdiMessageListResponse(BaseModel):
    items: list[EdiMessageResponse]
    total: int
    page: int
    page_size: int


class EdiMessageEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    edi_message_id: UUID
    event_type: EdiMessageEventType
    status_from: EdiMessageStatus | None
    status_to: EdiMessageStatus | None
    message: str | None
    error_code: str | None
    error_details: dict[str, object] | None
    metadata: dict[str, object] | None
    created_at: datetime

    @classmethod
    def from_domain(cls, value: EdiMessageEvent) -> "EdiMessageEventResponse":
        return cls.model_validate(value)


class CustomerPoEdiHistoryResponse(BaseModel):
    items: list[EdiMessageResponse]
