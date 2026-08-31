from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status

from app.api.dependencies.audit import build_audit_context
from app.api.dependencies.edi import (
    get_edi_inbound_actor,
    get_edi_message_use_cases,
    get_receive_rest_edi_payload,
)
from app.api.dependencies.identity import get_current_user
from app.modules.audit.domain.enums import AuditSource
from app.modules.edi.application.receive_rest_payload import (
    ReceiveRestEdiPayload,
    ReceiveRestEdiPayloadCommand,
)
from app.modules.edi.application.use_cases import EdiMessageUseCases
from app.modules.edi.domain.enums import (
    EdiMessageDirection,
    EdiMessageStatus,
    EdiRelatedEntityType,
)
from app.modules.edi.domain.repository import EdiMessageSearchCriteria
from app.modules.edi.presentation.schemas import RestEdiPayloadRequest, RestEdiReceiptResponse
from app.modules.edi.presentation.tracking_schemas import (
    EdiMessageEventResponse,
    EdiMessageListResponse,
    EdiMessageResponse,
)
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/edi", tags=["edi"])


@router.post(
    "/rest/receive",
    response_model=RestEdiReceiptResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_rest_edi_payload(
    request: RestEdiPayloadRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_edi_inbound_actor)],
    use_case: Annotated[ReceiveRestEdiPayload, Depends(get_receive_rest_edi_payload)],
    sender_id: Annotated[str, Header(alias="X-Sender-ID", min_length=1)],
    receiver_id: Annotated[str, Header(alias="X-Receiver-ID", min_length=1)],
    document_type: Annotated[str, Header(alias="X-Document-Type", min_length=1)],
    external_message_id: Annotated[
        str | None, Header(alias="X-External-Message-ID", min_length=1)
    ] = None,
) -> RestEdiReceiptResponse:
    receipt = await use_case.execute(
        ReceiveRestEdiPayloadCommand(
            sender_id=sender_id.strip(),
            receiver_id=receiver_id.strip(),
            document_type=document_type.strip(),
            external_message_id=external_message_id.strip() if external_message_id else None,
            document=request.to_document(),
            raw_payload=request.model_dump(by_alias=True, mode="json"),
        ),
        actor,
        build_audit_context(actor, http_request, source=AuditSource.EDI),
    )
    return RestEdiReceiptResponse(
        status="RECEIVED",
        sender_id=receipt.sender_id,
        receiver_id=receipt.receiver_id,
        document_type=receipt.document_type,
        external_message_id=receipt.external_message_id,
        customer_po_id=receipt.customer_po_id,
        edi_message_id=receipt.edi_message_id,
    )


@router.get("/messages", response_model=EdiMessageListResponse)
async def search_edi_messages(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[EdiMessageUseCases, Depends(get_edi_message_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    direction: EdiMessageDirection | None = None,
    message_status: Annotated[EdiMessageStatus | None, Query(alias="status")] = None,
    document_type: str | None = None,
    sender_id: str | None = None,
    receiver_id: str | None = None,
    external_message_id: str | None = None,
    business_document_number: str | None = None,
    related_entity_type: EdiRelatedEntityType | None = None,
    related_entity_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort_field: str = "created_at",
    sort_direction: str = "desc",
) -> EdiMessageListResponse:
    result = await use_cases.search(
        EdiMessageSearchCriteria(
            page,
            page_size,
            direction,
            message_status,
            document_type,
            sender_id,
            receiver_id,
            external_message_id,
            business_document_number,
            related_entity_type,
            related_entity_id,
            created_from,
            created_to,
            sort_field,
            sort_direction,
        ),
        actor,
    )
    return EdiMessageListResponse(
        items=[EdiMessageResponse.from_domain(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/messages/{message_id}", response_model=EdiMessageResponse)
async def get_edi_message(
    message_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[EdiMessageUseCases, Depends(get_edi_message_use_cases)],
) -> EdiMessageResponse:
    return EdiMessageResponse.from_domain(await use_cases.get(message_id, actor))


@router.get("/messages/{message_id}/events", response_model=list[EdiMessageEventResponse])
async def get_edi_message_events(
    message_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[EdiMessageUseCases, Depends(get_edi_message_use_cases)],
) -> list[EdiMessageEventResponse]:
    return [
        EdiMessageEventResponse.from_domain(event)
        for event in await use_cases.events(message_id, actor)
    ]
