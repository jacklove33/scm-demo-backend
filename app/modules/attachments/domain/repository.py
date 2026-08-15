from typing import Protocol
from uuid import UUID

from app.modules.attachments.domain.entities import Attachment, AttachmentEntityType


class AttachmentRepository(Protocol):
    async def list_for_entity(
        self, tenant_id: UUID, entity_type: AttachmentEntityType, entity_id: UUID
    ) -> list[Attachment]: ...

    async def get(self, tenant_id: UUID, attachment_id: UUID) -> Attachment | None: ...

    async def create(self, attachment: Attachment) -> Attachment: ...

    async def soft_delete(
        self, tenant_id: UUID, attachment_id: UUID, expected_version: int, actor_id: UUID
    ) -> Attachment | None: ...


class AttachmentStorage(Protocol):
    async def upload(
        self, *, object_key: str, content: bytes, content_type: str | None
    ) -> None: ...

    async def delete(self, *, object_key: str) -> None: ...

    async def create_download_url(self, *, object_key: str, expires_in: int) -> str: ...
