from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.edi.domain.entities import EdiMessage, EdiMessageEvent
from app.modules.edi.domain.enums import (
    EdiMessageDirection,
    EdiMessageStatus,
    EdiRelatedEntityType,
)


@dataclass(frozen=True, slots=True)
class EdiMessageSearchCriteria:
    page: int = 1
    page_size: int = 20
    direction: EdiMessageDirection | None = None
    status: EdiMessageStatus | None = None
    document_type: str | None = None
    sender_id: str | None = None
    receiver_id: str | None = None
    external_message_id: str | None = None
    business_document_number: str | None = None
    related_entity_type: EdiRelatedEntityType | None = None
    related_entity_id: UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    sort_field: str = "created_at"
    sort_direction: str = "desc"


@dataclass(frozen=True, slots=True)
class EdiMessagePage:
    items: list[EdiMessage]
    total: int
    page: int
    page_size: int


class EdiMessageRepository(Protocol):
    async def create_message(self, message: EdiMessage, event: EdiMessageEvent) -> None: ...
    async def get_message(self, tenant_id: UUID, message_id: UUID) -> EdiMessage | None: ...
    async def update_message(self, message: EdiMessage, event: EdiMessageEvent) -> None: ...
    async def append_event(self, event: EdiMessageEvent) -> None: ...
    async def list_events(self, tenant_id: UUID, message_id: UUID) -> list[EdiMessageEvent]: ...
    async def search(
        self, tenant_id: UUID, criteria: EdiMessageSearchCriteria
    ) -> EdiMessagePage: ...
    async def find_by_external_message_id(
        self, tenant_id: UUID, direction: EdiMessageDirection, external_message_id: str
    ) -> EdiMessage | None: ...
    async def list_for_related_entity(
        self, tenant_id: UUID, entity_type: EdiRelatedEntityType, entity_id: UUID
    ) -> list[EdiMessage]: ...
