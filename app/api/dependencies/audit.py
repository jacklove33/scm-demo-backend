from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.application.use_cases import AuditUseCases
from app.modules.audit.domain.entities import AuditContext
from app.modules.audit.domain.enums import AuditActorType, AuditSource
from app.modules.audit.infrastructure.repository import SqlAlchemyAuditRepository
from app.shared.domain.current_user import CurrentUser


async def get_audit_writer(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditWriter:
    return AuditWriter(SqlAlchemyAuditRepository(session))


async def get_audit_use_cases(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditUseCases:
    return AuditUseCases(SqlAlchemyAuditRepository(session))


def build_audit_context(
    actor: CurrentUser, request: Request, *, source: AuditSource = AuditSource.API
) -> AuditContext:
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
    client_host = request.client.host if request.client else None
    return AuditContext(
        tenant_id=actor.tenant_id,
        actor_user_id=actor.user_id,
        actor_email=actor.email,
        actor_display_name=actor.display_name,
        source=source,
        actor_type=AuditActorType.USER,
        correlation_id=correlation_id[:100],
        request_id=(request.headers.get("X-Request-ID") or "")[:100] or None,
        request_method=request.method[:10],
        request_path=request.url.path[:500],
        ip_address=client_host,
        user_agent=(request.headers.get("User-Agent") or "")[:2000] or None,
    )
