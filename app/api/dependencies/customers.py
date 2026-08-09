from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.customers.application.use_cases import CustomerUseCases
from app.modules.customers.infrastructure.repository import SqlAlchemyCustomerRepository


async def get_customer_use_cases(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CustomerUseCases:
    return CustomerUseCases(SqlAlchemyCustomerRepository(session))
