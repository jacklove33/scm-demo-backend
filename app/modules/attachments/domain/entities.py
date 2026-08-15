from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AttachmentEntityType(StrEnum):
    CUSTOMER = "CUSTOMER"
    CUSTOMER_PO = "CUSTOMER_PO"
    SALES_ORDER = "SALES_ORDER"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    SHIPMENT = "SHIPMENT"
    SUPPLIER = "SUPPLIER"
    PRODUCT = "PRODUCT"


@dataclass(frozen=True, slots=True)
class Attachment:
    id: UUID
    tenant_id: UUID
    entity_type: AttachmentEntityType
    entity_id: UUID
    original_filename: str
    stored_filename: str | None
    content_type: str | None
    size_bytes: int
    storage_provider: str
    bucket_name: str
    object_key: str
    description: str | None
    uploaded_by: UUID | None
    uploaded_by_display_name: str | None
    row_version: int
    created_at: datetime
    deleted_at: datetime | None
    deleted_by: UUID | None
