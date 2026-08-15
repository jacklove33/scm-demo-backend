from dataclasses import dataclass
from uuid import UUID

from app.modules.attachments.domain.entities import AttachmentEntityType


@dataclass(frozen=True, slots=True)
class UploadAttachmentCommand:
    entity_type: AttachmentEntityType
    entity_id: UUID
    filename: str
    content_type: str | None
    content: bytes
    description: str | None = None
