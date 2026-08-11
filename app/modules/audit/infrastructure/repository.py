from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.audit.domain.entities import (
    AuditChange,
    AuditEvent,
    AuditEventSummary,
    AuditPage,
    JsonValue,
)
from app.modules.audit.domain.enums import (
    AuditAction,
    AuditActorType,
    AuditChangeType,
    AuditSource,
    AuditStatus,
    AuditValueType,
)
from app.modules.audit.domain.repository import AuditSearchCriteria
from app.modules.audit.infrastructure.models import AuditChangeModel, AuditEventModel


class SqlAlchemyAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_event(self, event: AuditEvent, changes: list[AuditChange]) -> None:
        row = AuditEventModel(
            id=event.id,
            tenant_id=event.tenant_id,
            occurred_at=event.occurred_at,
            actor_user_id=event.actor_user_id,
            actor_email=event.actor_email,
            actor_display_name=event.actor_display_name,
            actor_type=event.actor_type.value,
            module=event.module,
            action=event.action.value,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            entity_code=event.entity_code,
            entity_display_name=event.entity_display_name,
            source=event.source.value,
            correlation_id=event.correlation_id,
            request_id=event.request_id,
            request_method=event.request_method,
            request_path=event.request_path,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            status=event.status.value,
            error_code=event.error_code,
            error_message=event.error_message,
            batch_id=event.batch_id,
            reason=event.reason,
            metadata_json=cast(dict[str, object], event.metadata),
            created_at=event.created_at,
        )
        row.changes = [
            AuditChangeModel(
                id=uuid4(),
                audit_event_id=event.id,
                sequence_no=change.sequence_no,
                field_path=change.field_path,
                field_label=change.field_label,
                change_type=change.change_type.value,
                value_type=change.value_type.value if change.value_type else None,
                old_value=change.old_value,
                new_value=change.new_value,
                old_display_value=change.old_display_value,
                new_display_value=change.new_display_value,
                is_sensitive=change.is_sensitive,
            )
            for change in changes
        ]
        self.session.add(row)
        await self.session.flush()

    async def search(self, tenant_id: UUID, criteria: AuditSearchCriteria) -> AuditPage:
        change_count = (
            select(func.count(AuditChangeModel.id))
            .where(AuditChangeModel.audit_event_id == AuditEventModel.id)
            .correlate(AuditEventModel)
            .scalar_subquery()
        )
        statement = select(AuditEventModel, change_count.label("change_count")).where(
            AuditEventModel.tenant_id == tenant_id
        )
        statement = self._filters(statement, criteria)
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int((await self.session.scalar(count_statement)) or 0)
        statement = (
            statement.order_by(AuditEventModel.occurred_at.desc(), AuditEventModel.id.desc())
            .offset((criteria.page - 1) * criteria.page_size)
            .limit(criteria.page_size)
        )
        rows = (await self.session.execute(statement)).all()
        return AuditPage(
            items=[AuditEventSummary(self._event(row), int(count)) for row, count in rows],
            total=total,
            page=criteria.page,
            page_size=criteria.page_size,
        )

    async def get_by_id(self, tenant_id: UUID, event_id: UUID) -> AuditEvent | None:
        row = await self.session.scalar(
            select(AuditEventModel)
            .where(AuditEventModel.tenant_id == tenant_id, AuditEventModel.id == event_id)
            .options(selectinload(AuditEventModel.changes))
        )
        return self._event(row, with_changes=True) if row else None

    @staticmethod
    def _filters(statement: Any, criteria: AuditSearchCriteria) -> Any:
        pairs = (
            (
                criteria.from_at,
                AuditEventModel.occurred_at >= criteria.from_at if criteria.from_at else None,
            ),
            (
                criteria.to_at,
                AuditEventModel.occurred_at <= criteria.to_at if criteria.to_at else None,
            ),
            (criteria.actor_user_id, AuditEventModel.actor_user_id == criteria.actor_user_id),
            (criteria.module, AuditEventModel.module == criteria.module),
            (criteria.action, AuditEventModel.action == criteria.action),
            (criteria.entity_type, AuditEventModel.entity_type == criteria.entity_type),
            (criteria.entity_id, AuditEventModel.entity_id == criteria.entity_id),
            (criteria.entity_code, AuditEventModel.entity_code == criteria.entity_code),
            (criteria.source, AuditEventModel.source == criteria.source),
            (criteria.status, AuditEventModel.status == criteria.status),
            (criteria.correlation_id, AuditEventModel.correlation_id == criteria.correlation_id),
            (criteria.batch_id, AuditEventModel.batch_id == criteria.batch_id),
        )
        for value, condition in pairs:
            if value is not None and condition is not None:
                statement = statement.where(condition)
        if criteria.search:
            pattern = f"%{criteria.search.strip()}%"
            statement = statement.where(
                or_(
                    AuditEventModel.entity_code.ilike(pattern),
                    AuditEventModel.entity_display_name.ilike(pattern),
                    AuditEventModel.actor_email.ilike(pattern),
                    AuditEventModel.actor_display_name.ilike(pattern),
                )
            )
        return statement

    @staticmethod
    def _change(row: AuditChangeModel) -> AuditChange:
        return AuditChange(
            sequence_no=row.sequence_no,
            field_path=row.field_path,
            field_label=row.field_label,
            change_type=AuditChangeType(row.change_type),
            value_type=AuditValueType(row.value_type) if row.value_type else None,
            old_value=cast(JsonValue, row.old_value),
            new_value=cast(JsonValue, row.new_value),
            old_display_value=row.old_display_value,
            new_display_value=row.new_display_value,
            is_sensitive=row.is_sensitive,
        )

    @classmethod
    def _event(cls, row: AuditEventModel, *, with_changes: bool = False) -> AuditEvent:
        return AuditEvent(
            id=row.id,
            tenant_id=row.tenant_id,
            occurred_at=row.occurred_at,
            actor_user_id=row.actor_user_id,
            actor_email=row.actor_email,
            actor_display_name=row.actor_display_name,
            module=row.module,
            action=AuditAction(row.action),
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            entity_code=row.entity_code,
            entity_display_name=row.entity_display_name,
            source=AuditSource(row.source),
            correlation_id=row.correlation_id,
            request_id=row.request_id,
            request_method=row.request_method,
            request_path=row.request_path,
            ip_address=str(row.ip_address) if row.ip_address is not None else None,
            user_agent=row.user_agent,
            status=AuditStatus(row.status),
            actor_type=AuditActorType(row.actor_type),
            error_code=row.error_code,
            error_message=row.error_message,
            batch_id=row.batch_id,
            reason=row.reason,
            metadata=cast(dict[str, JsonValue], row.metadata_json),
            created_at=row.created_at,
            changes=tuple(cls._change(change) for change in row.changes) if with_changes else (),
        )
