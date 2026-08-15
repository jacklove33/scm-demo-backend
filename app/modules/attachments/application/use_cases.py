import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.core.exceptions import EntityNotFound, ExternalServiceFailure, ValidationFailure
from app.modules.attachments.application.access import (
    AttachmentEntityAccess,
    AttachmentEventPublisher,
)
from app.modules.attachments.application.commands import UploadAttachmentCommand
from app.modules.attachments.domain.entities import Attachment, AttachmentEntityType
from app.modules.attachments.domain.repository import AttachmentRepository, AttachmentStorage
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.domain.entities import AuditContext
from app.modules.audit.domain.enums import AuditAction
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.current_user import CurrentUser

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {
    ".pdf": {"application/pdf"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".xls": {"application/vnd.ms-excel"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".doc": {"application/msword"},
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
    ".txt": {"text/plain"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
}


def safe_filename(filename: str) -> str:
    base = Path(filename.replace("\\", "/")).name.strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return (cleaned or "attachment")[:180]


def object_key(
    tenant_id: UUID,
    entity_type: AttachmentEntityType,
    entity_id: UUID,
    attachment_id: UUID,
    filename: str,
) -> str:
    segment = entity_type.value.lower().replace("_", "-")
    return f"{tenant_id}/{segment}/{entity_id}/{attachment_id}/{safe_filename(filename)}"


class AttachmentUseCases:
    def __init__(
        self,
        repository: AttachmentRepository,
        storage: AttachmentStorage,
        access: AttachmentEntityAccess,
        event_publisher: AttachmentEventPublisher,
        audit_writer: AuditWriter,
        unit_of_work: UnitOfWork,
        *,
        bucket_name: str,
        max_size_bytes: int,
        download_expire_seconds: int,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.access = access
        self.event_publisher = event_publisher
        self.audit_writer = audit_writer
        self.unit_of_work = unit_of_work
        self.bucket_name = bucket_name
        self.max_size_bytes = max_size_bytes
        self.download_expire_seconds = download_expire_seconds

    async def list(
        self, entity_type: AttachmentEntityType, entity_id: UUID, actor: CurrentUser
    ) -> list[Attachment]:
        await self.access.require_read(entity_type, entity_id, actor)
        return await self.repository.list_for_entity(actor.tenant_id, entity_type, entity_id)

    def _validate(self, command: UploadAttachmentCommand) -> str:
        if not self.bucket_name:
            raise ExternalServiceFailure("Attachment storage is not configured")
        if not command.content:
            raise ValidationFailure("Attachment file is empty")
        if len(command.content) > self.max_size_bytes:
            raise ValidationFailure("Attachment exceeds maximum file size")
        if len(command.filename) > 255:
            raise ValidationFailure("Attachment filename is too long")
        if command.content_type and len(command.content_type) > 255:
            raise ValidationFailure("Attachment content type is too long")
        if command.description and len(command.description) > 2000:
            raise ValidationFailure("Attachment description is too long")
        filename = safe_filename(command.filename)
        extension = Path(filename).suffix.lower()
        allowed = ALLOWED_TYPES.get(extension)
        if allowed is None:
            raise ValidationFailure("Attachment file extension is not allowed")
        if command.content_type and command.content_type.lower() not in allowed:
            raise ValidationFailure("Attachment content type does not match file extension")
        return filename

    async def upload(
        self, command: UploadAttachmentCommand, actor: CurrentUser, context: AuditContext
    ) -> Attachment:
        await self.access.require_write(command.entity_type, command.entity_id, actor)
        filename = self._validate(command)
        attachment_id = uuid4()
        key = object_key(
            actor.tenant_id, command.entity_type, command.entity_id, attachment_id, filename
        )
        try:
            await self.storage.upload(
                object_key=key, content=command.content, content_type=command.content_type
            )
        except Exception as error:
            await self.unit_of_work.rollback()
            logger.exception(
                "attachment_upload_failed",
                extra={
                    "attachment_id": str(attachment_id),
                    "entity_type": command.entity_type.value,
                    "entity_id": str(command.entity_id),
                    "size_bytes": len(command.content),
                },
            )
            raise ExternalServiceFailure("Attachment upload failed") from error
        try:
            now = datetime.now(UTC)
            attachment = await self.repository.create(
                Attachment(
                    attachment_id,
                    actor.tenant_id,
                    command.entity_type,
                    command.entity_id,
                    command.filename,
                    filename,
                    command.content_type,
                    len(command.content),
                    "S3",
                    self.bucket_name,
                    key,
                    command.description,
                    actor.user_id,
                    actor.display_name,
                    1,
                    now,
                    None,
                    None,
                )
            )
            await self.event_publisher.uploaded(
                attachment.id,
                attachment.entity_id,
                attachment.original_filename,
                context,
            )
            await self._audit(context, AuditAction.CREATE, attachment)
            await self.unit_of_work.commit()
        except Exception:
            await self.unit_of_work.rollback()
            try:
                await self.storage.delete(object_key=key)
            except Exception:
                logger.exception(
                    "attachment_upload_compensation_failed",
                    extra={
                        "attachment_id": str(attachment_id),
                        "entity_type": command.entity_type,
                    },
                )
            raise
        logger.info(
            "attachment_upload_completed",
            extra={
                "attachment_id": str(attachment.id),
                "entity_type": attachment.entity_type.value,
                "entity_id": str(attachment.entity_id),
                "size_bytes": attachment.size_bytes,
            },
        )
        return attachment

    async def download(self, attachment_id: UUID, actor: CurrentUser) -> tuple[str, int]:
        attachment = await self._get(attachment_id, actor)
        await self.access.require_read(attachment.entity_type, attachment.entity_id, actor)
        try:
            url = await self.storage.create_download_url(
                object_key=attachment.object_key, expires_in=self.download_expire_seconds
            )
        except Exception as error:
            raise ExternalServiceFailure("Could not create attachment download") from error
        logger.info(
            "attachment_download_url_created",
            extra={
                "attachment_id": str(attachment.id),
                "entity_type": attachment.entity_type.value,
            },
        )
        return url, self.download_expire_seconds

    async def delete(
        self,
        attachment_id: UUID,
        expected_version: int,
        actor: CurrentUser,
        context: AuditContext,
    ) -> None:
        attachment = await self._get(attachment_id, actor)
        await self.access.require_write(attachment.entity_type, attachment.entity_id, actor)
        try:
            await self.storage.delete(object_key=attachment.object_key)
        except Exception as error:
            await self.unit_of_work.rollback()
            logger.exception(
                "attachment_delete_failed",
                extra={
                    "attachment_id": str(attachment.id),
                    "entity_type": attachment.entity_type.value,
                },
            )
            raise ExternalServiceFailure("Attachment storage delete failed") from error
        try:
            deleted = await self.repository.soft_delete(
                actor.tenant_id, attachment.id, expected_version, actor.user_id
            )
            if deleted is None:
                raise EntityNotFound("Attachment not found or version changed")
            await self.event_publisher.deleted(
                deleted.id,
                deleted.entity_id,
                deleted.original_filename,
                context,
            )
            await self._audit(context, AuditAction.DELETE, deleted)
            await self.unit_of_work.commit()
        except Exception:
            await self.unit_of_work.rollback()
            raise
        logger.info(
            "attachment_delete_completed",
            extra={
                "attachment_id": str(attachment.id),
                "entity_type": attachment.entity_type.value,
            },
        )

    async def _get(self, attachment_id: UUID, actor: CurrentUser) -> Attachment:
        attachment = await self.repository.get(actor.tenant_id, attachment_id)
        if attachment is None:
            raise EntityNotFound("Attachment not found")
        return attachment

    async def _audit(
        self, context: AuditContext, action: AuditAction, attachment: Attachment
    ) -> None:
        await self.audit_writer.write_event(
            context=context,
            action=action,
            module="ATTACHMENTS",
            entity_type=attachment.entity_type.value,
            entity_id=attachment.entity_id,
            entity_code=attachment.original_filename,
            entity_display_name=attachment.original_filename,
            changes=[],
            metadata={
                "attachment_id": str(attachment.id),
                "filename": attachment.original_filename,
            },
        )
