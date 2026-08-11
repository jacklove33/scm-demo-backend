from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.audit.domain.entities import AuditChange, AuditEvent, AuditPage


@dataclass(frozen=True, slots=True)
class AuditSearchCriteria:
    page: int = 1
    page_size: int = 50
    from_at: datetime | None = None
    to_at: datetime | None = None
    actor_user_id: UUID | None = None
    module: str | None = None
    action: str | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None
    entity_code: str | None = None
    source: str | None = None
    status: str | None = None
    correlation_id: str | None = None
    batch_id: UUID | None = None
    search: str | None = None


class AuditRepository(Protocol):
    async def add_event(self, event: AuditEvent, changes: list[AuditChange]) -> None: ...
    async def search(self, tenant_id: UUID, criteria: AuditSearchCriteria) -> AuditPage: ...
    async def get_by_id(self, tenant_id: UUID, event_id: UUID) -> AuditEvent | None: ...
