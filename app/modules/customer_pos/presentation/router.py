from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.dependencies.audit import build_audit_context
from app.api.dependencies.customer_pos import get_customer_po_use_cases
from app.api.dependencies.identity import get_current_user
from app.modules.customer_pos.application.capabilities import capabilities
from app.modules.customer_pos.application.commands import (
    ChangeCustomerPoStatusCommand,
    CreateCustomerPoCommand,
    CustomerPoLineCommand,
    UpdateCustomerPoCommand,
)
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customer_pos.domain.enums import CustomerPoSource, CustomerPoStatus
from app.modules.customer_pos.domain.events import CustomerPoEventCategory, CustomerPoEventType
from app.modules.customer_pos.domain.repository import CustomerPoSearchCriteria
from app.modules.customer_pos.presentation.schemas import (
    ChangeStatusRequest,
    CreateCustomerPoRequest,
    CustomerPoEventPageResponse,
    CustomerPoEventResponse,
    CustomerPoLineRequest,
    CustomerPoListResponse,
    CustomerPoResponse,
    StatusEventResponse,
    UpdateCustomerPoRequest,
    VersionRequest,
)
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/customer-pos", tags=["customer-pos"])


def lines(values: list[CustomerPoLineRequest]) -> tuple[CustomerPoLineCommand, ...]:
    return tuple(CustomerPoLineCommand(**value.model_dump()) for value in values)


@router.get("", response_model=CustomerPoListResponse)
async def search_customer_pos(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    customer_po_number: str | None = None,
    customer_id: UUID | None = None,
    po_status: Annotated[CustomerPoStatus | None, Query(alias="status")] = None,
    source: CustomerPoSource | None = None,
    customer_po_date_from: date | None = None,
    customer_po_date_to: date | None = None,
    requested_delivery_date_from: date | None = None,
    requested_delivery_date_to: date | None = None,
    owner_user_id: UUID | None = None,
    edi_log_id: UUID | None = None,
    sales_order_id: UUID | None = None,
    show_deleted: bool = False,
    sort_field: str = "created_at",
    sort_direction: str = "desc",
) -> CustomerPoListResponse:
    result = await use_cases.search(
        CustomerPoSearchCriteria(
            page,
            page_size,
            customer_po_number,
            customer_id,
            po_status,
            source,
            customer_po_date_from,
            customer_po_date_to,
            requested_delivery_date_from,
            requested_delivery_date_to,
            owner_user_id,
            edi_log_id,
            sales_order_id,
            show_deleted,
            sort_field,
            sort_direction,
        ),
        actor,
    )
    return CustomerPoListResponse(
        data=[CustomerPoResponse.from_domain(po, capabilities(po, actor)) for po in result.items],
        meta={"page": result.page, "pageSize": result.page_size, "total": result.total},
    )


@router.post("", response_model=CustomerPoResponse, status_code=status.HTTP_201_CREATED)
async def create_customer_po(
    request: CreateCustomerPoRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> CustomerPoResponse:
    payload = request.model_dump(exclude={"lines"})
    po, caps = await use_cases.create(
        CreateCustomerPoCommand(**payload, lines=lines(request.lines)),
        actor,
        build_audit_context(actor, http_request),
    )
    return CustomerPoResponse.from_domain(po, caps)


@router.get("/{customer_po_id}", response_model=CustomerPoResponse)
async def get_customer_po(
    customer_po_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> CustomerPoResponse:
    po, caps = await use_cases.get(customer_po_id, actor)
    return CustomerPoResponse.from_domain(po, caps)


@router.put("/{customer_po_id}", response_model=CustomerPoResponse)
async def update_customer_po(
    customer_po_id: UUID,
    request: UpdateCustomerPoRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> CustomerPoResponse:
    payload = request.model_dump(exclude={"lines", "expected_version"})
    po, caps = await use_cases.update(
        UpdateCustomerPoCommand(
            **payload,
            customer_po_id=customer_po_id,
            expected_version=request.expected_version,
            lines=lines(request.lines),
        ),
        actor,
        build_audit_context(actor, http_request),
    )
    return CustomerPoResponse.from_domain(po, caps)


@router.post("/{customer_po_id}/status", response_model=CustomerPoResponse)
async def change_customer_po_status(
    customer_po_id: UUID,
    request: ChangeStatusRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> CustomerPoResponse:
    po, caps = await use_cases.change_status(
        ChangeCustomerPoStatusCommand(
            customer_po_id, request.expected_version, request.status, request.reason
        ),
        actor,
        build_audit_context(actor, http_request),
    )
    return CustomerPoResponse.from_domain(po, caps)


@router.get("/{customer_po_id}/status-history", response_model=list[StatusEventResponse])
async def customer_po_status_history(
    customer_po_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> list[StatusEventResponse]:
    return [
        StatusEventResponse.from_domain(event)
        for event in await use_cases.status_history(customer_po_id, actor)
    ]


@router.get("/{customer_po_id}/events", response_model=CustomerPoEventPageResponse)
async def customer_po_event_timeline(
    customer_po_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    event_type: CustomerPoEventType | None = None,
    category: CustomerPoEventCategory | None = None,
) -> CustomerPoEventPageResponse:
    result = await use_cases.event_timeline(
        customer_po_id,
        actor,
        page=page,
        page_size=page_size,
        event_type=event_type,
        category=category,
    )
    return CustomerPoEventPageResponse(
        items=[CustomerPoEventResponse.from_domain(event) for event in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post("/{customer_po_id}/soft-delete", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_customer_po(
    customer_po_id: UUID,
    request: VersionRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> Response:
    await use_cases.soft_delete(
        customer_po_id, request.expected_version, actor, build_audit_context(actor, http_request)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{customer_po_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_customer_po(
    customer_po_id: UUID,
    request: VersionRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> Response:
    await use_cases.restore(
        customer_po_id, request.expected_version, actor, build_audit_context(actor, http_request)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
