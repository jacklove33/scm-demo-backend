from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.modules.edi.domain.entities import EdiMessage, EdiMessageEvent
from app.modules.edi.domain.enums import (
    EdiMessageDirection,
    EdiMessageEventType,
    EdiMessageStatus,
    EdiRelatedEntityType,
)
from app.modules.edi.domain.repository import EdiMessageRepository


class EdiTrackingUnitOfWork(Protocol):
    async def bind(self) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class EdiMessageTracker:
    """Persist protocol-neutral message state and append-only operational events."""

    def __init__(
        self, repository: EdiMessageRepository, unit_of_work: EdiTrackingUnitOfWork
    ) -> None:
        self.repository = repository
        self.unit_of_work = unit_of_work

    async def create_received(
        self,
        *,
        tenant_id: UUID,
        direction: EdiMessageDirection,
        source_system: str,
        source_protocol: str,
        document_standard: str,
        document_type: str,
        sender_id: str,
        receiver_id: str,
        external_message_id: str | None,
        correlation_id: str | None,
    ) -> tuple[EdiMessage, bool]:
        await self.unit_of_work.bind()
        if external_message_id:
            existing = await self.repository.find_by_external_message_id(
                tenant_id, direction, external_message_id
            )
            if existing:
                await self._duplicate_event(existing)
                return existing, True
        now = datetime.now(UTC)
        message = EdiMessage(
            uuid4(),
            tenant_id,
            direction,
            source_system,
            source_protocol,
            document_standard,
            document_type,
            sender_id,
            receiver_id,
            external_message_id,
            correlation_id,
            None,
            EdiMessageStatus.RECEIVED,
            None,
            None,
            None,
            None,
            now if direction == EdiMessageDirection.INBOUND else None,
            None,
            now,
            now,
        )
        event = self._event(message, EdiMessageEventType.RECEIVED, None, message.status)
        try:
            await self.repository.create_message(message, event)
            await self.unit_of_work.commit()
            return message, False
        except IntegrityError:
            await self.unit_of_work.rollback()
            if external_message_id:
                existing = await self.repository.find_by_external_message_id(
                    tenant_id, direction, external_message_id
                )
                if existing:
                    await self._duplicate_event(existing)
                    return existing, True
            raise

    async def start_validation(self, message: EdiMessage) -> EdiMessage:
        await self.unit_of_work.bind()
        return await self._transition(
            message, EdiMessageStatus.VALIDATING, EdiMessageEventType.VALIDATION_STARTED
        )

    async def validation_passed(self, message: EdiMessage) -> EdiMessage:
        await self.unit_of_work.bind()
        return await self._transition(
            message, EdiMessageStatus.VALIDATED, EdiMessageEventType.VALIDATION_PASSED
        )

    async def validation_failed(
        self,
        message: EdiMessage,
        error_code: str,
        error_message: str,
        details: dict[str, object] | None = None,
    ) -> EdiMessage:
        await self.unit_of_work.bind()
        return await self._transition(
            message,
            EdiMessageStatus.VALIDATION_FAILED,
            EdiMessageEventType.VALIDATION_FAILED,
            error_code,
            error_message,
            details,
        )

    async def start_processing(self, message: EdiMessage) -> EdiMessage:
        await self.unit_of_work.bind()
        return await self._transition(
            message, EdiMessageStatus.PROCESSING, EdiMessageEventType.PROCESSING_STARTED
        )

    async def link_related_entity(
        self,
        message: EdiMessage,
        entity_type: EdiRelatedEntityType,
        entity_id: UUID,
        business_document_number: str,
    ) -> EdiMessage:
        await self.unit_of_work.bind()
        now = datetime.now(UTC)
        linked = replace(
            message,
            related_entity_type=entity_type,
            related_entity_id=entity_id,
            business_document_number=business_document_number,
            updated_at=now,
        )
        event = self._event(
            linked,
            EdiMessageEventType.RELATED_ENTITY_CREATED,
            message.status,
            message.status,
            metadata={"entity_type": entity_type.value, "entity_id": str(entity_id)},
        )
        await self.repository.update_message(linked, event)
        await self.unit_of_work.commit()
        return linked

    async def completed(self, message: EdiMessage) -> EdiMessage:
        await self.unit_of_work.bind()
        return await self._transition(
            message,
            EdiMessageStatus.COMPLETED,
            EdiMessageEventType.COMPLETED,
            processed_at=datetime.now(UTC),
        )

    async def failed(
        self,
        message: EdiMessage,
        error_code: str,
        error_message: str,
        details: dict[str, object] | None = None,
    ) -> EdiMessage:
        await self.unit_of_work.rollback()
        await self.unit_of_work.bind()
        current = await self.repository.get_message(message.tenant_id, message.id) or message
        return await self._transition(
            current,
            EdiMessageStatus.FAILED,
            EdiMessageEventType.FAILED,
            error_code,
            error_message,
            details,
            processed_at=datetime.now(UTC),
        )

    async def _transition(
        self,
        message: EdiMessage,
        status: EdiMessageStatus,
        event_type: EdiMessageEventType,
        error_code: str | None = None,
        error_message: str | None = None,
        details: dict[str, object] | None = None,
        *,
        processed_at: datetime | None = None,
    ) -> EdiMessage:
        updated = replace(
            message,
            status=status,
            error_code=error_code,
            error_message=error_message,
            processed_at=processed_at,
            updated_at=datetime.now(UTC),
        )
        event = self._event(
            updated,
            event_type,
            message.status,
            status,
            text=error_message,
            error_code=error_code,
            error_details=details,
        )
        await self.repository.update_message(updated, event)
        await self.unit_of_work.commit()
        return updated

    async def _duplicate_event(self, existing: EdiMessage) -> None:
        await self.repository.append_event(
            self._event(
                existing,
                EdiMessageEventType.DUPLICATE_DETECTED,
                existing.status,
                existing.status,
                text="Duplicate external message identity received",
            )
        )
        await self.unit_of_work.commit()

    @staticmethod
    def _event(
        edi_message: EdiMessage,
        event_type: EdiMessageEventType,
        status_from: EdiMessageStatus | None,
        status_to: EdiMessageStatus | None,
        *,
        text: str | None = None,
        error_code: str | None = None,
        error_details: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> EdiMessageEvent:
        return EdiMessageEvent(
            uuid4(),
            edi_message.tenant_id,
            edi_message.id,
            event_type,
            status_from,
            status_to,
            text,
            error_code,
            error_details,
            metadata,
            datetime.now(UTC),
        )
