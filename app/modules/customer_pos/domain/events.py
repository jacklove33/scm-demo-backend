from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.modules.audit.domain.entities import JsonValue


class CustomerPoEventType(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    STATUS_CHANGE = "STATUS_CHANGE"
    SOFT_DELETE = "SOFT_DELETE"
    RESTORE = "RESTORE"
    EMAIL_SENT = "EMAIL_SENT"
    PO_SENT = "PO_SENT"
    ATTACHMENT_UPLOADED = "ATTACHMENT_UPLOADED"
    ATTACHMENT_DELETED = "ATTACHMENT_DELETED"
    NOTE_ADDED = "NOTE_ADDED"
    EDI_RECEIVED = "EDI_RECEIVED"
    EDI_PROCESSED = "EDI_PROCESSED"
    CONVERTED = "CONVERTED"


class CustomerPoEventCategory(StrEnum):
    GENERAL = "GENERAL"
    WORKFLOW = "WORKFLOW"
    COMMUNICATION = "COMMUNICATION"
    DOCUMENT = "DOCUMENT"
    EDI = "EDI"
    CONVERSION = "CONVERSION"


class CustomerPoEventActorType(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    API_CLIENT = "API_CLIENT"


class CustomerPoEventSource(StrEnum):
    API = "API"
    EDI = "EDI"
    SYSTEM = "SYSTEM"
    IMPORT = "IMPORT"
    JOB = "JOB"
    UI = "UI"
    ADMIN = "ADMIN"


EVENT_CATEGORIES = {
    CustomerPoEventType.CREATE: CustomerPoEventCategory.GENERAL,
    CustomerPoEventType.UPDATE: CustomerPoEventCategory.GENERAL,
    CustomerPoEventType.STATUS_CHANGE: CustomerPoEventCategory.WORKFLOW,
    CustomerPoEventType.SOFT_DELETE: CustomerPoEventCategory.GENERAL,
    CustomerPoEventType.RESTORE: CustomerPoEventCategory.GENERAL,
    CustomerPoEventType.EMAIL_SENT: CustomerPoEventCategory.COMMUNICATION,
    CustomerPoEventType.PO_SENT: CustomerPoEventCategory.COMMUNICATION,
    CustomerPoEventType.ATTACHMENT_UPLOADED: CustomerPoEventCategory.DOCUMENT,
    CustomerPoEventType.ATTACHMENT_DELETED: CustomerPoEventCategory.DOCUMENT,
    CustomerPoEventType.NOTE_ADDED: CustomerPoEventCategory.GENERAL,
    CustomerPoEventType.EDI_RECEIVED: CustomerPoEventCategory.EDI,
    CustomerPoEventType.EDI_PROCESSED: CustomerPoEventCategory.EDI,
    CustomerPoEventType.CONVERTED: CustomerPoEventCategory.CONVERSION,
}


@dataclass(frozen=True, slots=True)
class CustomerPoEvent:
    id: UUID
    tenant_id: UUID
    customer_po_id: UUID
    event_type: CustomerPoEventType
    event_category: CustomerPoEventCategory
    title: str
    description: str | None
    actor_type: CustomerPoEventActorType
    actor_user_id: UUID | None
    actor_display_name: str | None
    source: CustomerPoEventSource
    correlation_id: str | None
    request_id: str | None
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    occurred_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CustomerPoEventPage:
    items: list[CustomerPoEvent]
    total: int
    page: int
    page_size: int


class CustomerPoEventRepository(Protocol):
    async def add(self, event: CustomerPoEvent) -> None: ...

    async def list_for_po(
        self,
        tenant_id: UUID,
        customer_po_id: UUID,
        page: int,
        page_size: int,
        event_type: CustomerPoEventType | None = None,
        category: CustomerPoEventCategory | None = None,
    ) -> CustomerPoEventPage: ...
