from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attachments.domain.entities import Attachment, AttachmentEntityType
from app.modules.attachments.infrastructure.models import AttachmentModel
from app.modules.iam.infrastructure.models import ProfileModel


class SqlAlchemyAttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_entity(
        self, tenant_id: UUID, entity_type: AttachmentEntityType, entity_id: UUID
    ) -> list[Attachment]:
        rows = (
            await self.session.execute(
                select(AttachmentModel, ProfileModel.display_name)
                .outerjoin(ProfileModel, ProfileModel.id == AttachmentModel.uploaded_by)
                .where(
                    AttachmentModel.tenant_id == tenant_id,
                    AttachmentModel.entity_type == entity_type.value,
                    AttachmentModel.entity_id == entity_id,
                    AttachmentModel.deleted_at.is_(None),
                )
                .order_by(AttachmentModel.created_at.desc(), AttachmentModel.id.desc())
            )
        ).all()
        return [self._entity(row, display_name) for row, display_name in rows]

    async def get(self, tenant_id: UUID, attachment_id: UUID) -> Attachment | None:
        result = await self.session.execute(
            select(AttachmentModel, ProfileModel.display_name)
            .outerjoin(ProfileModel, ProfileModel.id == AttachmentModel.uploaded_by)
            .where(
                AttachmentModel.tenant_id == tenant_id,
                AttachmentModel.id == attachment_id,
                AttachmentModel.deleted_at.is_(None),
            )
        )
        row = result.one_or_none()
        return self._entity(*row) if row else None

    async def create(self, attachment: Attachment) -> Attachment:
        row = AttachmentModel(
            **{
                name: getattr(attachment, name)
                for name in AttachmentModel.__table__.columns.keys()
                if name != "uploaded_by_display_name"
            }
        )
        self.session.add(row)
        await self.session.flush()
        return attachment

    async def soft_delete(
        self, tenant_id: UUID, attachment_id: UUID, expected_version: int, actor_id: UUID
    ) -> Attachment | None:
        result = await self.session.execute(
            update(AttachmentModel)
            .where(
                AttachmentModel.tenant_id == tenant_id,
                AttachmentModel.id == attachment_id,
                AttachmentModel.row_version == expected_version,
                AttachmentModel.deleted_at.is_(None),
            )
            .values(
                deleted_at=datetime.now(UTC),
                deleted_by=actor_id,
                row_version=AttachmentModel.row_version + 1,
            )
            .returning(AttachmentModel)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._entity(row, None)

    @staticmethod
    def _entity(row: AttachmentModel, display_name: str | None) -> Attachment:
        return Attachment(
            id=row.id,
            tenant_id=row.tenant_id,
            entity_type=AttachmentEntityType(row.entity_type),
            entity_id=row.entity_id,
            original_filename=row.original_filename,
            stored_filename=row.stored_filename,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            storage_provider=row.storage_provider,
            bucket_name=row.bucket_name,
            object_key=row.object_key,
            description=row.description,
            uploaded_by=row.uploaded_by,
            uploaded_by_display_name=display_name,
            row_version=row.row_version,
            created_at=row.created_at,
            deleted_at=row.deleted_at,
            deleted_by=row.deleted_by,
        )
