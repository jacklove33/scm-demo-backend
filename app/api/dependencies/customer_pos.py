from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.infrastructure.repository import SqlAlchemyAuditRepository
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customer_pos.infrastructure.event_repository import (
    SqlAlchemyCustomerPoEventRepository,
)
from app.modules.customer_pos.infrastructure.repository import SqlAlchemyCustomerPoRepository


async def get_customer_po_use_cases(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CustomerPoUseCases:
    return CustomerPoUseCases(
        SqlAlchemyCustomerPoRepository(session),
        AuditWriter(SqlAlchemyAuditRepository(session)),
        SqlAlchemyCustomerPoEventRepository(session),
        SqlAlchemyUnitOfWork(session),
    )
