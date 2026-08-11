from uuid import UUID

from app.core.exceptions import EntityNotFound, PermissionDenied
from app.modules.audit.domain.entities import AuditEvent, AuditPage
from app.modules.audit.domain.repository import AuditRepository, AuditSearchCriteria
from app.shared.domain.current_user import CurrentUser


class AuditUseCases:
    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    async def search(self, criteria: AuditSearchCriteria, actor: CurrentUser) -> AuditPage:
        self._require(actor)
        return await self.repository.search(actor.tenant_id, criteria)

    async def get(self, event_id: UUID, actor: CurrentUser) -> AuditEvent:
        self._require(actor)
        event = await self.repository.get_by_id(actor.tenant_id, event_id)
        if event is None:
            raise EntityNotFound("Audit event not found")
        return event

    @staticmethod
    def _require(actor: CurrentUser) -> None:
        if not actor.can("audit.read"):
            raise PermissionDenied("Missing permission: audit.read")
