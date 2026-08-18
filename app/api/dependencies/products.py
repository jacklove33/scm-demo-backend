from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.infrastructure.repository import SqlAlchemyAuditRepository
from app.modules.products.application.use_cases import ProductUseCases
from app.modules.products.infrastructure.repository import SqlAlchemyProductRepository


async def get_product_use_cases(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProductUseCases:
    return ProductUseCases(
        SqlAlchemyProductRepository(session),
        audit_writer=AuditWriter(SqlAlchemyAuditRepository(session)),
        unit_of_work=SqlAlchemyUnitOfWork(session),
    )
