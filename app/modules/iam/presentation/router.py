from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.iam import get_iam_management_service
from app.api.dependencies.identity import get_current_user
from app.modules.iam.application.management_service import IamManagementService
from app.modules.iam.domain.repository import UserSearchCriteria
from app.modules.iam.presentation.schemas import (
    EffectivePermissionResponse,
    GroupResponse,
    MeResponse,
    PermissionResponse,
    PermissionSourceResponse,
    PolicyResponse,
    RoleResponse,
    UserListResponse,
    UserSummaryResponse,
)
from app.shared.domain.current_user import CurrentUser

router = APIRouter(prefix="/iam", tags=["iam"])


@router.get("/me/effective-permissions", response_model=MeResponse)
async def get_my_effective_permissions(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
) -> MeResponse:
    permissions = [
        EffectivePermissionResponse(
            permission_code=item.permission_code,
            effect=item.effect.value,
            scope=item.scope.value if item.scope else None,
            sources=[
                PermissionSourceResponse(
                    source_type=source.source_type,
                    source_name=source.source_name,
                    policy_code=source.policy_code,
                    effect=source.effect.value,
                    scope=source.scope.value if source.scope else None,
                )
                for source in item.sources
            ],
        )
        for item in sorted(actor.permissions.values(), key=lambda item: item.permission_code)
    ]

    return MeResponse(
        user_id=str(actor.user_id),
        tenant_id=str(actor.tenant_id),
        email=actor.email,
        display_name=actor.display_name,
        permissions=permissions,
    )


@router.get("/users", response_model=UserListResponse)
async def search_users(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[IamManagementService, Depends(get_iam_management_service)],
    search: str | None = Query(None, max_length=320),
    user_status: Annotated[str | None, Query(alias="status")] = None,
    role_id: UUID | None = None,
    group_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> UserListResponse:
    result = await service.search_users(
        UserSearchCriteria(search, user_status, role_id, group_id, page, page_size), actor
    )
    return UserListResponse(
        data=[UserSummaryResponse.model_validate(item) for item in result.items],
        meta={"page": result.page, "pageSize": result.page_size, "total": result.total},
    )


@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[IamManagementService, Depends(get_iam_management_service)],
) -> list[GroupResponse]:
    return [GroupResponse.model_validate(item) for item in await service.list_groups(actor)]


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[IamManagementService, Depends(get_iam_management_service)],
) -> list[RoleResponse]:
    return [RoleResponse.model_validate(item) for item in await service.list_roles(actor)]


@router.get("/policies", response_model=list[PolicyResponse])
async def list_policies(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[IamManagementService, Depends(get_iam_management_service)],
) -> list[PolicyResponse]:
    return [PolicyResponse.model_validate(item) for item in await service.list_policies(actor)]


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[IamManagementService, Depends(get_iam_management_service)],
) -> list[PermissionResponse]:
    return [
        PermissionResponse.model_validate(item) for item in await service.list_permissions(actor)
    ]
