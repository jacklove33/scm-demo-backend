from app.core.exceptions import PermissionDenied, ValidationFailure
from app.modules.iam.domain.repository import (
    GroupSummary,
    IamRepository,
    PermissionSummary,
    PolicySummary,
    RoleSummary,
    UserPage,
    UserSearchCriteria,
)
from app.shared.domain.current_user import CurrentUser


class IamManagementService:
    def __init__(self, repository: IamRepository) -> None:
        self.repository = repository

    @staticmethod
    def _require(actor: CurrentUser, permission: str) -> None:
        if not actor.can(permission):
            raise PermissionDenied(f"Missing permission: {permission}")

    async def search_users(self, criteria: UserSearchCriteria, actor: CurrentUser) -> UserPage:
        self._require(actor, "users.read")
        if criteria.status not in (None, "ACTIVE", "INACTIVE"):
            raise ValidationFailure("Invalid user status")
        return await self.repository.search_users(actor.tenant_id, criteria)

    async def list_groups(self, actor: CurrentUser) -> list[GroupSummary]:
        self._require(actor, "groups.read")
        return await self.repository.list_groups(actor.tenant_id)

    async def list_roles(self, actor: CurrentUser) -> list[RoleSummary]:
        self._require(actor, "roles.read")
        return await self.repository.list_roles(actor.tenant_id)

    async def list_policies(self, actor: CurrentUser) -> list[PolicySummary]:
        self._require(actor, "policies.read")
        return await self.repository.list_policies(actor.tenant_id)

    async def list_permissions(self, actor: CurrentUser) -> list[PermissionSummary]:
        self._require(actor, "permissions.read")
        return await self.repository.list_permissions()
