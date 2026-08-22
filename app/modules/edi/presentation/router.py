from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.dependencies.audit import build_audit_context
from app.api.dependencies.edi import get_edi_inbound_actor, get_receive_rest_edi_payload
from app.modules.audit.domain.enums import AuditSource
from app.modules.edi.application.receive_rest_payload import (
    ReceiveRestEdiPayload,
    ReceiveRestEdiPayloadCommand,
)
from app.modules.edi.presentation.schemas import RestEdiPayloadRequest, RestEdiReceiptResponse
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/edi/rest", tags=["edi-rest"])


@router.post(
    "/receive",
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
    )
