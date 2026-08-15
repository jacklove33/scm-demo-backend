from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.attachments.domain.entities import Attachment, AttachmentEntityType


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    entity_type: AttachmentEntityType
    entity_id: UUID
    original_filename: str
    content_type: str | None
    size_bytes: int
    description: str | None
    uploaded_by: UUID | None
    uploaded_by_display_name: str | None
    created_at: datetime
    row_version: int

    @classmethod
    def from_domain(cls, attachment: Attachment) -> "AttachmentResponse":
        return cls.model_validate(attachment, from_attributes=True)


class AttachmentListResponse(BaseModel):
    items: list[AttachmentResponse]


class AttachmentDownloadResponse(BaseModel):
    url: str
    expires_in: int
