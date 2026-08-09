from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies.identity import get_current_user
from app.modules.iam.presentation.schemas import (
    EffectivePermissionResponse,
    MeResponse,
    PermissionSourceResponse,
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
