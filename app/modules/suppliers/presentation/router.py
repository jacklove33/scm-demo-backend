from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.dependencies.audit import build_audit_context
from app.api.dependencies.identity import get_current_user
from app.api.dependencies.suppliers import get_supplier_use_cases
from app.modules.audit.domain.enums import AuditSource
from app.modules.suppliers.application.commands import (
    CreateSupplierCommand,
    SupplierAddressCommand,
    SupplierImportRowCommand,
    UpdateSupplierCommand,
)
from app.modules.suppliers.application.use_cases import SupplierUseCases
from app.modules.suppliers.domain.repository import SupplierSearchCriteria
from app.modules.suppliers.presentation.schemas import (
    CreateSupplierRequest,
    PaymentTermOptionResponse,
    SupplierImportRequest,
    SupplierImportResponse,
    SupplierListResponse,
    SupplierResponse,
    UpdateSupplierRequest,
    VersionRequest,
)
from app.shared.application.date_ranges import validate_date_range
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post("/import", response_model=SupplierImportResponse)
async def import_suppliers(
    request: SupplierImportRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[SupplierUseCases, Depends(get_supplier_use_cases)],
) -> SupplierImportResponse:
    rows = [
        SupplierImportRowCommand(
            **row.model_dump(exclude={"row_number"}),
            row_number=row.row_number if row.row_number is not None else index + 2,
        )
        for index, row in enumerate(request.rows)
    ]
    total = await use_cases.import_suppliers(
        rows,
        actor,
        build_audit_context(actor, http_request, source=AuditSource.IMPORT),
    )
    return SupplierImportResponse(total=total, imported=total, failed=0)


@router.get("", response_model=SupplierListResponse)
async def search_suppliers(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[SupplierUseCases, Depends(get_supplier_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    supplier_code: str | None = Query(None, max_length=20),
    supplier_name_prefix: str | None = Query(None, max_length=240),
    supplier_status: Annotated[str | None, Query(alias="status", max_length=30)] = None,
    created_date_from: date | None = None,
    created_date_to: date | None = None,
    updated_date_from: date | None = None,
    updated_date_to: date | None = None,
    show_deleted: bool = False,
    sort_field: Literal[
        "supplier_code", "supplier_name", "created_at", "updated_at", "status"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
) -> SupplierListResponse:
    created = validate_date_range(
        created_date_from, created_date_to, max_days=14, field_name="created"
    )
    updated = validate_date_range(
        updated_date_from, updated_date_to, max_days=14, field_name="updated"
    )
    items, total = await use_cases.search(
        SupplierSearchCriteria(
            page,
            page_size,
            supplier_code,
            supplier_name_prefix,
            supplier_status,
            created.from_inclusive,
            created.to_exclusive,
            updated.from_inclusive,
            updated.to_exclusive,
            show_deleted,
            sort_field,
            sort_direction,
        ),
        actor,
    )
    return SupplierListResponse(
        data=[SupplierResponse.model_validate(item) for item in items],
        meta={"page": page, "pageSize": page_size, "total": total},
    )


@router.get("/payment-terms", response_model=list[PaymentTermOptionResponse])
async def list_supplier_payment_terms(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[SupplierUseCases, Depends(get_supplier_use_cases)],
) -> list[PaymentTermOptionResponse]:
    return [
        PaymentTermOptionResponse(id=id_, code=code, name=name)
        for id_, code, name in await use_cases.list_payment_terms(actor)
    ]


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[SupplierUseCases, Depends(get_supplier_use_cases)],
) -> SupplierResponse:
    return SupplierResponse.model_validate(await use_cases.get(supplier_id, actor))


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    request: CreateSupplierRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[SupplierUseCases, Depends(get_supplier_use_cases)],
) -> SupplierResponse:
    return SupplierResponse.model_validate(
        await use_cases.create(
            CreateSupplierCommand(
                **request.model_dump(exclude={"default_address"}),
                default_address=SupplierAddressCommand(**request.default_address.model_dump())
                if request.default_address
                else None,
            ),
            actor,
            build_audit_context(actor, http_request),
        )
    )


@router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: UUID,
    request: UpdateSupplierRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[SupplierUseCases, Depends(get_supplier_use_cases)],
) -> SupplierResponse:
    payload = request.model_dump()
    expected_version = payload.pop("expected_version")
    return SupplierResponse.model_validate(
        await use_cases.update(
            UpdateSupplierCommand(
                supplier_id=supplier_id, expected_version=expected_version, **payload
            ),
            actor,
            build_audit_context(actor, http_request),
        )
    )


@router.post("/{supplier_id}/soft-delete", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_supplier(
    supplier_id: UUID,
    request: VersionRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[SupplierUseCases, Depends(get_supplier_use_cases)],
) -> Response:
    await use_cases.soft_delete(
        supplier_id, request.expected_version, actor, build_audit_context(actor, http_request)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{supplier_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_supplier(
    supplier_id: UUID,
    request: VersionRequest,
    http_request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[SupplierUseCases, Depends(get_supplier_use_cases)],
) -> Response:
    await use_cases.restore(
        supplier_id, request.expected_version, actor, build_audit_context(actor, http_request)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
