from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies.customers import get_customer_use_cases
from app.api.dependencies.identity import get_current_user
from app.modules.customers.application.commands import CreateCustomerCommand, UpdateCustomerCommand
from app.modules.customers.application.use_cases import CustomerUseCases
from app.modules.customers.domain.repository import CustomerSearchCriteria
from app.modules.customers.presentation.schemas import (
    CreateCustomerRequest,
    CustomerListResponse,
    CustomerResponse,
    UpdateCustomerRequest,
    VersionRequest,
)
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=CustomerListResponse)
async def search_customers(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerUseCases, Depends(get_customer_use_cases)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    customer_code: str | None = Query(None, max_length=80),
    customer_name_prefix: str | None = Query(None, max_length=240),
    customer_status: str | None = Query(None, alias="status", max_length=30),
    show_deleted: bool = False,
    sort_field: Literal[
        "customer_code",
        "customer_name",
        "created_at",
        "updated_at",
        "status",
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
) -> CustomerListResponse:
    items, total = await use_cases.search(
        CustomerSearchCriteria(
            page=page,
            page_size=page_size,
            customer_code=customer_code,
            customer_name_prefix=customer_name_prefix,
            status=customer_status,
            show_deleted=show_deleted,
            sort_field=sort_field,
            sort_direction=sort_direction,
        ),
        actor,
    )
    return CustomerListResponse(
        data=[CustomerResponse.model_validate(item) for item in items],
        meta={"page": page, "pageSize": page_size, "total": total},
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerUseCases, Depends(get_customer_use_cases)],
) -> CustomerResponse:
    return CustomerResponse.model_validate(await use_cases.get(customer_id, actor))


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: CreateCustomerRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerUseCases, Depends(get_customer_use_cases)],
) -> CustomerResponse:
    return CustomerResponse.model_validate(
        await use_cases.create(CreateCustomerCommand(**request.model_dump()), actor)
    )


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    request: UpdateCustomerRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerUseCases, Depends(get_customer_use_cases)],
) -> CustomerResponse:
    payload = request.model_dump()
    expected_version = payload.pop("expected_version")
    return CustomerResponse.model_validate(
        await use_cases.update(
            UpdateCustomerCommand(
                customer_id=customer_id,
                expected_version=expected_version,
                **payload,
            ),
            actor,
        )
    )


@router.post("/{customer_id}/soft-delete", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_customer(
    customer_id: UUID,
    request: VersionRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerUseCases, Depends(get_customer_use_cases)],
) -> Response:
    await use_cases.soft_delete(customer_id, request.expected_version, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{customer_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_customer(
    customer_id: UUID,
    request: VersionRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    use_cases: Annotated[CustomerUseCases, Depends(get_customer_use_cases)],
) -> Response:
    await use_cases.restore(customer_id, request.expected_version, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
