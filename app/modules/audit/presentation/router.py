from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.audit import get_audit_use_cases
from app.api.dependencies.customer_pos import get_customer_po_use_cases
from app.api.dependencies.customers import get_customer_use_cases
from app.api.dependencies.identity import get_current_user
from app.core.exceptions import ValidationFailure
from app.modules.audit.application.use_cases import AuditUseCases
from app.modules.audit.domain.entities import AuditPage
from app.modules.audit.domain.enums import AuditAction, AuditSource, AuditStatus
from app.modules.audit.domain.repository import AuditSearchCriteria
from app.modules.audit.presentation.schemas import (
    AuditEventDetailResponse,
    AuditEventListResponse,
    AuditEventSummaryResponse,
)
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customers.application.use_cases import CustomerUseCases
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/audit-events", tags=["audit"])


def list_response(audit_page: AuditPage) -> AuditEventListResponse:
    return AuditEventListResponse(
        data=[AuditEventSummaryResponse.from_domain(item) for item in audit_page.items],
        total=audit_page.total,
        page=audit_page.page,
        page_size=audit_page.page_size,
    )


@router.get("/entity/{entity_type}/{entity_id}", response_model=AuditEventListResponse)
async def entity_history(
    entity_type: str,
    entity_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    audit: Annotated[AuditUseCases, Depends(get_audit_use_cases)],
    customers: Annotated[CustomerUseCases, Depends(get_customer_use_cases)],
    customer_pos: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: AuditAction | None = None,
) -> AuditEventListResponse:
    normalized_type = entity_type.upper()
    if normalized_type == "CUSTOMER":
        await customers.get(entity_id, actor)
    elif normalized_type == "CUSTOMER_PO":
        await customer_pos.get(entity_id, actor, include_deleted=True)
    else:
        raise ValidationFailure("Unsupported audit entity type")
    result = await audit.search(
        AuditSearchCriteria(
            page=page,
            page_size=page_size,
            entity_type=normalized_type,
            entity_id=entity_id,
            action=action.value if action else None,
        ),
        actor,
    )
    return list_response(result)


@router.get("/correlation/{correlation_id}", response_model=AuditEventListResponse)
async def correlation_history(
    correlation_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    audit: Annotated[AuditUseCases, Depends(get_audit_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> AuditEventListResponse:
    result = await audit.search(
        AuditSearchCriteria(page=page, page_size=page_size, correlation_id=correlation_id), actor
    )
    return list_response(result)


@router.get("", response_model=AuditEventListResponse)
async def search_audit_events(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    audit: Annotated[AuditUseCases, Depends(get_audit_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    actor_user_id: UUID | None = None,
    module: str | None = None,
    action: AuditAction | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    entity_code: str | None = None,
    source: AuditSource | None = None,
    audit_status: Annotated[AuditStatus | None, Query(alias="status")] = None,
    correlation_id: str | None = None,
    batch_id: UUID | None = None,
    search: str | None = Query(None, max_length=255),
) -> AuditEventListResponse:
    result = await audit.search(
        AuditSearchCriteria(
            page=page,
            page_size=page_size,
            from_at=from_at,
            to_at=to_at,
            actor_user_id=actor_user_id,
            module=module,
            action=action.value if action else None,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_code=entity_code,
            source=source.value if source else None,
            status=audit_status.value if audit_status else None,
            correlation_id=correlation_id,
            batch_id=batch_id,
            search=search,
        ),
        actor,
    )
    return list_response(result)


@router.get("/{event_id}", response_model=AuditEventDetailResponse)
async def get_audit_event(
    event_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    audit: Annotated[AuditUseCases, Depends(get_audit_use_cases)],
) -> AuditEventDetailResponse:
    return AuditEventDetailResponse.from_domain(await audit.get(event_id, actor))
