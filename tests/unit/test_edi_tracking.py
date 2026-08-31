from dataclasses import replace
from uuid import UUID

import pytest

from app.modules.edi.application.tracker import EdiMessageTracker
from app.modules.edi.domain.entities import EdiMessage, EdiMessageEvent
from app.modules.edi.domain.enums import (
    EdiMessageDirection,
    EdiMessageEventType,
    EdiMessageStatus,
    EdiRelatedEntityType,
)
from app.modules.edi.domain.repository import EdiMessagePage, EdiMessageSearchCriteria

TENANT = UUID("11111111-1111-1111-1111-111111111111")
PO_ID = UUID("70000000-0000-0000-0000-000000000099")


class MemoryRepository:
    def __init__(self) -> None:
        self.messages: dict[UUID, EdiMessage] = {}
        self.events: list[EdiMessageEvent] = []

    async def create_message(self, message: EdiMessage, event: EdiMessageEvent) -> None:
        self.messages[message.id] = message
        self.events.append(event)

    async def get_message(self, tenant_id: UUID, message_id: UUID) -> EdiMessage | None:
        message = self.messages.get(message_id)
        return message if message and message.tenant_id == tenant_id else None

    async def update_message(self, message: EdiMessage, event: EdiMessageEvent) -> None:
        self.messages[message.id] = message
        self.events.append(event)

    async def append_event(self, event: EdiMessageEvent) -> None:
        self.events.append(event)

    async def list_events(self, tenant_id: UUID, message_id: UUID) -> list[EdiMessageEvent]:
        return [
            e for e in self.events if e.tenant_id == tenant_id and e.edi_message_id == message_id
        ]

    async def search(self, tenant_id: UUID, criteria: EdiMessageSearchCriteria) -> EdiMessagePage:
        items = [message for message in self.messages.values() if message.tenant_id == tenant_id]
        return EdiMessagePage(items, len(items), criteria.page, criteria.page_size)

    async def find_by_external_message_id(
        self, tenant_id: UUID, direction: EdiMessageDirection, external_message_id: str
    ) -> EdiMessage | None:
        return next(
            (
                message
                for message in self.messages.values()
                if message.tenant_id == tenant_id
                and message.direction == direction
                and message.external_message_id == external_message_id
            ),
            None,
        )

    async def list_for_related_entity(
        self, tenant_id: UUID, entity_type: EdiRelatedEntityType, entity_id: UUID
    ) -> list[EdiMessage]:
        return [
            message
            for message in self.messages.values()
            if message.tenant_id == tenant_id
            and message.related_entity_type == entity_type
            and message.related_entity_id == entity_id
        ]


class UnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.binds = 0

    async def bind(self) -> None:
        self.binds += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


async def received(
    tracker: EdiMessageTracker,
    *,
    direction: EdiMessageDirection = EdiMessageDirection.INBOUND,
    external_id: str | None = "MSG-1",
) -> tuple[EdiMessage, bool]:
    return await tracker.create_received(
        tenant_id=TENANT,
        direction=direction,
        source_system="DIRECT_API",
        source_protocol="REST" if direction == EdiMessageDirection.INBOUND else "INTERNAL",
        document_standard="JSON",
        document_type="850" if direction == EdiMessageDirection.INBOUND else "855",
        sender_id="WPG" if direction == EdiMessageDirection.INBOUND else "SYNA",
        receiver_id="SYNA" if direction == EdiMessageDirection.INBOUND else "WPG",
        external_message_id=external_id,
        correlation_id="corr-1",
    )


@pytest.mark.asyncio
async def test_inbound_message_completion_and_append_only_timeline() -> None:
    repository, uow = MemoryRepository(), UnitOfWork()
    tracker = EdiMessageTracker(repository, uow)
    message, duplicate = await received(tracker)
    assert not duplicate
    message = await tracker.start_validation(message)
    message = await tracker.validation_passed(message)
    message = await tracker.start_processing(message)
    message = await tracker.link_related_entity(
        message, EdiRelatedEntityType.CUSTOMER_PO, PO_ID, "PO123456"
    )
    message = await tracker.completed(message)

    assert message.status == EdiMessageStatus.COMPLETED
    assert message.related_entity_id == PO_ID
    assert message.processed_at is not None
    assert [event.event_type for event in repository.events] == [
        EdiMessageEventType.RECEIVED,
        EdiMessageEventType.VALIDATION_STARTED,
        EdiMessageEventType.VALIDATION_PASSED,
        EdiMessageEventType.PROCESSING_STARTED,
        EdiMessageEventType.RELATED_ENTITY_CREATED,
        EdiMessageEventType.COMPLETED,
    ]
    assert uow.commits == 6


@pytest.mark.asyncio
async def test_validation_failure_is_committed_with_details() -> None:
    repository, uow = MemoryRepository(), UnitOfWork()
    tracker = EdiMessageTracker(repository, uow)
    message, _ = await received(tracker, external_id=None)
    message = await tracker.start_validation(message)
    message = await tracker.validation_failed(
        message,
        "EDI_CUSTOMER_NOT_FOUND",
        "EDI customer was not found",
        {"customer_code": "DOES_NOT_EXIST"},
    )
    assert message.status == EdiMessageStatus.VALIDATION_FAILED
    assert message.error_code == "EDI_CUSTOMER_NOT_FOUND"
    assert repository.events[-1].error_details == {"customer_code": "DOES_NOT_EXIST"}
    assert uow.commits == 3


@pytest.mark.asyncio
async def test_duplicate_external_identity_reuses_message_and_appends_event() -> None:
    repository, uow = MemoryRepository(), UnitOfWork()
    tracker = EdiMessageTracker(repository, uow)
    original, _ = await received(tracker)
    repository.messages[original.id] = replace(
        original,
        status=EdiMessageStatus.COMPLETED,
        related_entity_type=EdiRelatedEntityType.CUSTOMER_PO,
        related_entity_id=PO_ID,
    )
    duplicate, detected = await received(tracker)
    assert detected
    assert duplicate.id == original.id
    assert len(repository.messages) == 1
    assert repository.events[-1].event_type == EdiMessageEventType.DUPLICATE_DETECTED


@pytest.mark.asyncio
async def test_outbound_direction_is_supported_without_inbound_table_assumptions() -> None:
    repository, uow = MemoryRepository(), UnitOfWork()
    message, duplicate = await received(
        EdiMessageTracker(repository, uow), direction=EdiMessageDirection.OUTBOUND
    )
    assert not duplicate
    assert message.direction == EdiMessageDirection.OUTBOUND
    assert message.document_type == "855"
    assert message.received_at is None


def test_event_entity_supports_operational_metadata_without_raw_payload() -> None:
    fields = EdiMessageEvent.__dataclass_fields__
    assert {"error_details", "metadata"} <= fields.keys()
    assert not {"payload", "raw_content", "s3_key", "as2_mic"} & fields.keys()
