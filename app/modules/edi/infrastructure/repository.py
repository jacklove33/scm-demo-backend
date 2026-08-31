from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.edi.domain.entities import EdiMessage, EdiMessageEvent
from app.modules.edi.domain.enums import (
    EdiMessageDirection,
    EdiMessageEventType,
    EdiMessageStatus,
    EdiRelatedEntityType,
)
from app.modules.edi.domain.repository import (
    EdiMessagePage,
    EdiMessageSearchCriteria,
)
from app.modules.edi.infrastructure.models import EdiMessageEventModel, EdiMessageModel


class SqlAlchemyEdiMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_message(self, message: EdiMessage, event: EdiMessageEvent) -> None:
        self.session.add(self._message_model(message))
        await self.session.flush()
        self.session.add(self._event_model(event))
        await self.session.flush()

    async def get_message(self, tenant_id: UUID, message_id: UUID) -> EdiMessage | None:
        row = await self.session.scalar(
            select(EdiMessageModel).where(
                EdiMessageModel.tenant_id == tenant_id, EdiMessageModel.id == message_id
            )
        )
        return self._message(row) if row else None

    async def update_message(self, message: EdiMessage, event: EdiMessageEvent) -> None:
        row = await self.session.scalar(
            select(EdiMessageModel).where(
                EdiMessageModel.tenant_id == message.tenant_id,
                EdiMessageModel.id == message.id,
            )
        )
        if row is None:
            return
        for name in (
            "status",
            "error_code",
            "error_message",
            "business_document_number",
            "related_entity_type",
            "related_entity_id",
            "processed_at",
            "updated_at",
        ):
            value = getattr(message, name)
            setattr(row, name, value.value if hasattr(value, "value") else value)
        self.session.add(self._event_model(event))
        await self.session.flush()

    async def append_event(self, event: EdiMessageEvent) -> None:
        self.session.add(self._event_model(event))
        await self.session.flush()

    async def list_events(self, tenant_id: UUID, message_id: UUID) -> list[EdiMessageEvent]:
        rows = (
            await self.session.scalars(
                select(EdiMessageEventModel)
                .where(
                    EdiMessageEventModel.tenant_id == tenant_id,
                    EdiMessageEventModel.edi_message_id == message_id,
                )
                .order_by(EdiMessageEventModel.created_at, EdiMessageEventModel.id)
            )
        ).all()
        return [self._event(row) for row in rows]

    async def search(self, tenant_id: UUID, criteria: EdiMessageSearchCriteria) -> EdiMessagePage:
        statement = select(EdiMessageModel).where(EdiMessageModel.tenant_id == tenant_id)
        filters: tuple[tuple[object | None, Any], ...] = (
            (
                criteria.direction,
                EdiMessageModel.direction == criteria.direction.value
                if criteria.direction
                else None,
            ),
            (
                criteria.status,
                EdiMessageModel.status == criteria.status.value if criteria.status else None,
            ),
            (criteria.document_type, EdiMessageModel.document_type == criteria.document_type),
            (criteria.sender_id, EdiMessageModel.sender_id == criteria.sender_id),
            (criteria.receiver_id, EdiMessageModel.receiver_id == criteria.receiver_id),
            (
                criteria.external_message_id,
                EdiMessageModel.external_message_id == criteria.external_message_id,
            ),
            (
                criteria.business_document_number,
                EdiMessageModel.business_document_number == criteria.business_document_number,
            ),
            (
                criteria.related_entity_type,
                EdiMessageModel.related_entity_type == criteria.related_entity_type.value
                if criteria.related_entity_type
                else None,
            ),
            (
                criteria.related_entity_id,
                EdiMessageModel.related_entity_id == criteria.related_entity_id,
            ),
            (
                criteria.created_from,
                EdiMessageModel.created_at >= criteria.created_from
                if criteria.created_from
                else None,
            ),
            (
                criteria.created_to,
                EdiMessageModel.created_at <= criteria.created_to if criteria.created_to else None,
            ),
        )
        for value, condition in filters:
            if value is not None and condition is not None:
                statement = statement.where(condition)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(statement.order_by(None).subquery())
            )
            or 0
        )
        sort_columns = {
            "created_at": EdiMessageModel.created_at,
            "received_at": EdiMessageModel.received_at,
            "status": EdiMessageModel.status,
            "document_type": EdiMessageModel.document_type,
        }
        column = sort_columns.get(criteria.sort_field, EdiMessageModel.created_at)
        statement = (
            statement.order_by(
                column.asc() if criteria.sort_direction == "asc" else column.desc(),
                EdiMessageModel.id.desc(),
            )
            .offset((criteria.page - 1) * criteria.page_size)
            .limit(criteria.page_size)
        )
        rows = (await self.session.scalars(statement)).all()
        return EdiMessagePage(
            [self._message(row) for row in rows], total, criteria.page, criteria.page_size
        )

    async def find_by_external_message_id(
        self, tenant_id: UUID, direction: EdiMessageDirection, external_message_id: str
    ) -> EdiMessage | None:
        row = await self.session.scalar(
            select(EdiMessageModel).where(
                EdiMessageModel.tenant_id == tenant_id,
                EdiMessageModel.direction == direction.value,
                EdiMessageModel.external_message_id == external_message_id,
            )
        )
        return self._message(row) if row else None

    async def list_for_related_entity(
        self, tenant_id: UUID, entity_type: EdiRelatedEntityType, entity_id: UUID
    ) -> list[EdiMessage]:
        rows = (
            await self.session.scalars(
                select(EdiMessageModel)
                .where(
                    EdiMessageModel.tenant_id == tenant_id,
                    EdiMessageModel.related_entity_type == entity_type.value,
                    EdiMessageModel.related_entity_id == entity_id,
                )
                .order_by(EdiMessageModel.created_at, EdiMessageModel.id)
            )
        ).all()
        return [self._message(row) for row in rows]

    @staticmethod
    def _message_model(value: EdiMessage) -> EdiMessageModel:
        return EdiMessageModel(
            **{
                name: (field.value if hasattr(field, "value") else field)
                for name in value.__dataclass_fields__
                if (field := getattr(value, name)) is not None
            }
        )

    @staticmethod
    def _event_model(value: EdiMessageEvent) -> EdiMessageEventModel:
        return EdiMessageEventModel(
            id=value.id,
            tenant_id=value.tenant_id,
            edi_message_id=value.edi_message_id,
            event_type=value.event_type.value,
            status_from=value.status_from.value if value.status_from else None,
            status_to=value.status_to.value if value.status_to else None,
            message=value.message,
            error_code=value.error_code,
            error_details=value.error_details,
            metadata_json=value.metadata,
            created_at=value.created_at,
        )

    @staticmethod
    def _message(row: EdiMessageModel) -> EdiMessage:
        return EdiMessage(
            row.id,
            row.tenant_id,
            EdiMessageDirection(row.direction),
            row.source_system,
            row.source_protocol,
            row.document_standard,
            row.document_type,
            row.sender_id,
            row.receiver_id,
            row.external_message_id,
            row.correlation_id,
            row.business_document_number,
            EdiMessageStatus(row.status),
            row.error_code,
            row.error_message,
            EdiRelatedEntityType(row.related_entity_type) if row.related_entity_type else None,
            row.related_entity_id,
            row.received_at,
            row.processed_at,
            row.created_at,
            row.updated_at,
        )

    @staticmethod
    def _event(row: EdiMessageEventModel) -> EdiMessageEvent:
        return EdiMessageEvent(
            row.id,
            row.tenant_id,
            row.edi_message_id,
            EdiMessageEventType(row.event_type),
            EdiMessageStatus(row.status_from) if row.status_from else None,
            EdiMessageStatus(row.status_to) if row.status_to else None,
            row.message,
            row.error_code,
            row.error_details,
            row.metadata_json,
            row.created_at,
        )
