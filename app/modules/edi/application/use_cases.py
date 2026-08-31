from uuid import UUID

from app.core.exceptions import EntityNotFound, PermissionDenied
from app.modules.edi.domain.entities import EdiMessage, EdiMessageEvent
from app.modules.edi.domain.enums import EdiRelatedEntityType
from app.modules.edi.domain.repository import (
    EdiMessagePage,
    EdiMessageRepository,
    EdiMessageSearchCriteria,
)
from app.shared.domain.current_user import CurrentUser


class EdiMessageUseCases:
    def __init__(self, repository: EdiMessageRepository) -> None:
        self.repository = repository

    @staticmethod
    def _require(actor: CurrentUser, permission: str) -> None:
        if not actor.can(permission):
            raise PermissionDenied(f"Missing permission: {permission}")

    async def search(
        self, criteria: EdiMessageSearchCriteria, actor: CurrentUser
    ) -> EdiMessagePage:
        self._require(actor, "edi_messages.read")
        return await self.repository.search(actor.tenant_id, criteria)

    async def get(self, message_id: UUID, actor: CurrentUser) -> EdiMessage:
        self._require(actor, "edi_messages.detail.read")
        message = await self.repository.get_message(actor.tenant_id, message_id)
        if message is None:
            raise EntityNotFound("EDI message not found")
        return message

    async def events(self, message_id: UUID, actor: CurrentUser) -> list[EdiMessageEvent]:
        await self.get(message_id, actor)
        return await self.repository.list_events(actor.tenant_id, message_id)

    async def customer_po_history(
        self, customer_po_id: UUID, actor: CurrentUser
    ) -> list[EdiMessage]:
        self._require(actor, "edi_messages.detail.read")
        return await self.repository.list_for_related_entity(
            actor.tenant_id, EdiRelatedEntityType.CUSTOMER_PO, customer_po_id
        )
