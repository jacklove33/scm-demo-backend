from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.database.session import get_session
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.attachments.application.access import CustomerPoAttachmentAccess
from app.modules.attachments.application.customer_po_events import (
    CustomerPoAttachmentEventPublisher,
)
from app.modules.attachments.application.use_cases import AttachmentUseCases
from app.modules.attachments.infrastructure.repository import SqlAlchemyAttachmentRepository
from app.modules.attachments.infrastructure.s3_storage import S3AttachmentStorage
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.infrastructure.repository import SqlAlchemyAuditRepository
from app.modules.customer_pos.application.event_writer import CustomerPoEventWriter
from app.modules.customer_pos.infrastructure.event_repository import (
    SqlAlchemyCustomerPoEventRepository,
)
from app.modules.customer_pos.infrastructure.repository import SqlAlchemyCustomerPoRepository


async def get_attachment_use_cases(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AttachmentUseCases:
    return AttachmentUseCases(
        SqlAlchemyAttachmentRepository(session),
        S3AttachmentStorage(
            bucket_name=settings.s3_attachments_bucket,
            region=settings.aws_region,
        ),
        CustomerPoAttachmentAccess(SqlAlchemyCustomerPoRepository(session)),
        CustomerPoAttachmentEventPublisher(
            CustomerPoEventWriter(SqlAlchemyCustomerPoEventRepository(session))
        ),
        AuditWriter(SqlAlchemyAuditRepository(session)),
        SqlAlchemyUnitOfWork(session),
        bucket_name=settings.s3_attachments_bucket,
        max_size_bytes=settings.attachment_max_file_size_bytes,
        download_expire_seconds=settings.attachment_download_url_expire_seconds,
    )
