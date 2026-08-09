from uuid import UUID

from app.core.exceptions import AuthenticationRequired, PermissionDenied
from app.modules.iam.application.permission_resolver import EffectivePermissionResolver
from app.modules.iam.domain.repository import IamRepository
from app.shared.domain.current_user import CurrentUser


class CurrentUserService:
    def __init__(
        self,
        repository: IamRepository,
        resolver: EffectivePermissionResolver,
    ) -> None:
        self.repository = repository
        self.resolver = resolver

    async def load(self, user_id: UUID) -> CurrentUser:
        profile = await self.repository.get_profile(user_id)
        if profile is None:
            raise AuthenticationRequired("Authenticated user profile was not found")
        if not profile.is_active:
            raise PermissionDenied("User is inactive")

        grants = await self.repository.get_permission_grants(user_id)
        permissions = self.resolver.resolve(grants)

        return CurrentUser(
            user_id=profile.id,
            tenant_id=profile.tenant_id,
            email=profile.email,
            display_name=profile.display_name,
            is_active=profile.is_active,
            permissions=permissions,
        )
