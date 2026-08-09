from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_principal
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
    return await service.load(principal.user_id)
