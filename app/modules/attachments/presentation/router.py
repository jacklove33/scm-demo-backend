from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status

from app.api.dependencies.attachments import get_attachment_use_cases
from app.api.dependencies.audit import build_audit_context
from app.api.dependencies.identity import get_current_user
from app.core.config import settings
from app.modules.attachments.application.commands import UploadAttachmentCommand
from app.modules.attachments.application.use_cases import AttachmentUseCases
from app.modules.attachments.domain.entities import AttachmentEntityType
from app.modules.attachments.presentation.schemas import (
    AttachmentDownloadResponse,
    AttachmentListResponse,
    AttachmentResponse,
)
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.get("", response_model=AttachmentListResponse)
async def list_attachments(
    entity_type: AttachmentEntityType,
    entity_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[AttachmentUseCases, Depends(get_attachment_use_cases)],
) -> AttachmentListResponse:
    items = await use_cases.list(entity_type, entity_id, actor)
    return AttachmentListResponse(items=[AttachmentResponse.from_domain(item) for item in items])


@router.post("", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[AttachmentUseCases, Depends(get_attachment_use_cases)],
    entity_type: Annotated[AttachmentEntityType, Form()],
    entity_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form(max_length=2000)] = None,
) -> AttachmentResponse:
    content = await file.read(settings.attachment_max_file_size_bytes + 1)
    attachment = await use_cases.upload(
        UploadAttachmentCommand(
            entity_type=entity_type,
            entity_id=entity_id,
            filename=file.filename or "attachment",
            content_type=file.content_type,
            content=content,
            description=description,
        ),
        actor,
        build_audit_context(actor, request),
    )
    return AttachmentResponse.from_domain(attachment)


@router.get("/{attachment_id}/download", response_model=AttachmentDownloadResponse)
async def download_attachment(
    attachment_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[AttachmentUseCases, Depends(get_attachment_use_cases)],
) -> AttachmentDownloadResponse:
    url, expires_in = await use_cases.download(attachment_id, actor)
    return AttachmentDownloadResponse(url=url, expires_in=expires_in)


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: UUID,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[AttachmentUseCases, Depends(get_attachment_use_cases)],
    expected_version: int = Query(ge=1),
) -> Response:
    await use_cases.delete(
        attachment_id,
        expected_version,
        actor,
        build_audit_context(actor, request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
