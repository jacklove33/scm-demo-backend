from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.dependencies.audit import build_audit_context
from app.api.dependencies.identity import get_current_user
from app.api.dependencies.products import get_product_use_cases
from app.modules.audit.domain.enums import AuditSource
from app.modules.products.application.commands import (
    CreateProductCommand,
    ProductImportRowCommand,
    UpdateProductCommand,
)
from app.modules.products.application.use_cases import ProductUseCases
from app.modules.products.domain.repository import ProductSearchCriteria
from app.modules.products.presentation.schemas import (
    CreateProductRequest,
    ProductImportRequest,
    ProductImportResponse,
    ProductListResponse,
    ProductResponse,
    UpdateProductRequest,
    VersionRequest,
)
from app.shared.application.date_ranges import validate_date_range
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
async def search_products(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[ProductUseCases, Depends(get_product_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = Query(None, max_length=240),
    product_code: str | None = Query(None, max_length=100),
    product_name: str | None = Query(None, max_length=240),
    product_type: str | None = Query(None, max_length=30),
    product_status: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    category: str | None = Query(None, max_length=120),
    owner_user_id: UUID | None = None,
    created_date_from: date | None = None,
    created_date_to: date | None = None,
    updated_date_from: date | None = None,
    updated_date_to: date | None = None,
    show_deleted: bool = False,
    sort_field: Literal[
        "product_code", "product_name", "product_type", "status", "updated_at"
    ] = "updated_at",
    sort_direction: Literal["asc", "desc"] = "desc",
) -> ProductListResponse:
    created = validate_date_range(
        created_date_from, created_date_to, max_days=14, field_name="created"
    )
    updated = validate_date_range(
        updated_date_from, updated_date_to, max_days=14, field_name="updated"
    )
    criteria = ProductSearchCriteria(
        page,
        page_size,
        search,
        product_code,
        product_name,
        product_type,
        product_status,
        category,
        owner_user_id,
        created.from_inclusive,
        created.to_exclusive,
        updated.from_inclusive,
        updated.to_exclusive,
        show_deleted,
        sort_field,
        sort_direction,
    )
    items, total = await use_cases.search(criteria, actor)
    return ProductListResponse(
        data=[ProductResponse.model_validate(item) for item in items],
        meta={"page": page, "pageSize": page_size, "total": total},
    )


@router.post("/import", response_model=ProductImportResponse)
async def import_products(
    body: ProductImportRequest,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[ProductUseCases, Depends(get_product_use_cases)],
) -> ProductImportResponse:
    rows = [
        ProductImportRowCommand(
            **row.model_dump(exclude={"row_number"}),
            row_number=row.row_number or index + 2,
        )
        for index, row in enumerate(body.rows)
    ]
    total = await use_cases.import_products(
        rows, actor, build_audit_context(actor, request, source=AuditSource.IMPORT)
    )
    return ProductImportResponse(total=total, imported=total, failed=0)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[ProductUseCases, Depends(get_product_use_cases)],
) -> ProductResponse:
    return ProductResponse.model_validate(await use_cases.get(product_id, actor))


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: CreateProductRequest,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[ProductUseCases, Depends(get_product_use_cases)],
) -> ProductResponse:
    return ProductResponse.model_validate(
        await use_cases.create(
            CreateProductCommand(**body.model_dump()), actor, build_audit_context(actor, request)
        )
    )


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    body: UpdateProductRequest,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[ProductUseCases, Depends(get_product_use_cases)],
) -> ProductResponse:
    values = body.model_dump()
    version = values.pop("expected_version")
    return ProductResponse.model_validate(
        await use_cases.update(
            UpdateProductCommand(product_id=product_id, expected_version=version, **values),
            actor,
            build_audit_context(actor, request),
        )
    )


@router.post("/{product_id}/soft-delete", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_product(
    product_id: UUID,
    body: VersionRequest,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[ProductUseCases, Depends(get_product_use_cases)],
) -> Response:
    await use_cases.soft_delete(
        product_id, body.expected_version, actor, build_audit_context(actor, request)
    )
    return Response(status_code=204)


@router.post("/{product_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_product(
    product_id: UUID,
    body: VersionRequest,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[ProductUseCases, Depends(get_product_use_cases)],
) -> Response:
    await use_cases.restore(
        product_id, body.expected_version, actor, build_audit_context(actor, request)
    )
    return Response(status_code=204)
