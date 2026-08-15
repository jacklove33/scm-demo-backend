from typing import Protocol
from uuid import UUID

from app.core.exceptions import EntityNotFound, PermissionDenied, ValidationFailure
from app.modules.attachments.domain.entities import AttachmentEntityType
from app.modules.audit.domain.entities import AuditContext
from app.modules.customer_pos.application.capabilities import capabilities
from app.modules.customer_pos.domain.entities import CustomerPurchaseOrder
from app.modules.customer_pos.domain.repository import CustomerPoRepository
from app.shared.domain.current_user import CurrentUser


class AttachmentEntityAccess(Protocol):
    async def require_read(
        self, entity_type: AttachmentEntityType, entity_id: UUID, actor: CurrentUser
    ) -> None: ...

    async def require_write(
        self, entity_type: AttachmentEntityType, entity_id: UUID, actor: CurrentUser
    ) -> None: ...


class AttachmentEventPublisher(Protocol):
    async def uploaded(
        self, attachment_id: UUID, entity_id: UUID, filename: str, context: AuditContext
    ) -> None: ...

    async def deleted(
        self, attachment_id: UUID, entity_id: UUID, filename: str, context: AuditContext
    ) -> None: ...


class CustomerPoAttachmentAccess:
    def __init__(self, repository: CustomerPoRepository) -> None:
        self.repository = repository

    @staticmethod
    def _supported(entity_type: AttachmentEntityType) -> None:
        if entity_type != AttachmentEntityType.CUSTOMER_PO:
            raise ValidationFailure(f"Attachment entity type is not supported: {entity_type}")

    async def _load(self, entity_id: UUID, actor: CurrentUser) -> CustomerPurchaseOrder:
        po = await self.repository.get(
            entity_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("customer_pos.detail.read"),
        )
        if po is None:
            raise EntityNotFound("Customer PO not found")
        return po

    async def require_read(
        self, entity_type: AttachmentEntityType, entity_id: UUID, actor: CurrentUser
    ) -> None:
        self._supported(entity_type)
        if not actor.can("customer_pos.detail.read"):
            raise PermissionDenied("Missing permission: customer_pos.detail.read")
        await self._load(entity_id, actor)

    async def require_write(
        self, entity_type: AttachmentEntityType, entity_id: UUID, actor: CurrentUser
    ) -> None:
        self._supported(entity_type)
        if not actor.can("customer_pos.detail.read"):
            raise PermissionDenied("Missing permission: customer_pos.detail.read")
        po = await self._load(entity_id, actor)
        if not capabilities(po, actor).update:
            raise PermissionDenied("Customer PO is not writable")
