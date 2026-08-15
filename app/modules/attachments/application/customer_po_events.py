from uuid import UUID

from app.modules.audit.domain.entities import AuditContext
from app.modules.customer_pos.application.event_writer import CustomerPoEventWriter
from app.modules.customer_pos.domain.events import CustomerPoEventType


class CustomerPoAttachmentEventPublisher:
    def __init__(self, writer: CustomerPoEventWriter) -> None:
        self.writer = writer

    async def uploaded(
        self, attachment_id: UUID, entity_id: UUID, filename: str, context: AuditContext
    ) -> None:
        await self.writer.write(
            tenant_id=context.tenant_id,
            customer_po_id=entity_id,
            event_type=CustomerPoEventType.ATTACHMENT_UPLOADED,
            context=context,
            title="Attachment uploaded",
            description=filename,
            metadata={"attachment_id": str(attachment_id), "file_name": filename},
        )

    async def deleted(
        self, attachment_id: UUID, entity_id: UUID, filename: str, context: AuditContext
    ) -> None:
        await self.writer.write(
            tenant_id=context.tenant_id,
            customer_po_id=entity_id,
            event_type=CustomerPoEventType.ATTACHMENT_DELETED,
            context=context,
            title="Attachment deleted",
            description=filename,
            metadata={"attachment_id": str(attachment_id), "file_name": filename},
        )
