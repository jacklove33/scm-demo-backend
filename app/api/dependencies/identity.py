from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_principal
from app.core.logging import bind_log_context
from app.infrastructure.database.session import get_session
from app.modules.iam.application.current_user_service import CurrentUserService
from app.modules.iam.application.permission_resolver import EffectivePermissionResolver
from app.modules.iam.infrastructure.repository import SqlAlchemyIamRepository
from app.shared.domain.current_user import AuthenticatedPrincipal, CurrentUser


async def get_current_user(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    # FastAPI caches dependency results inside the same request by default,
    # so IAM is resolved once even when multiple downstream dependencies reuse CurrentUser.
    service = CurrentUserService(
        repository=SqlAlchemyIamRepository(session),
        resolver=EffectivePermissionResolver(),
    )
    current_user = await service.load(principal.user_id)
    bind_log_context(user_id=current_user.user_id, tenant_id=current_user.tenant_id)
    # Transaction-local settings are consumed by tenant RLS policies. Values are
    # parameterized and disappear automatically at transaction end/pool reuse.
    await session.execute(
        text(
            "SELECT set_config('app.tenant_id', :tenant_id, true), "
            "set_config('app.user_id', :user_id, true)"
        ),
        {"tenant_id": str(current_user.tenant_id), "user_id": str(current_user.user_id)},
    )
    return current_user
