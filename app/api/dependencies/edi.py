from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.customer_pos import get_customer_po_use_cases
from app.infrastructure.database.session import get_session
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customers.infrastructure.repository import SqlAlchemyCustomerRepository
from app.modules.edi.application.receive_rest_payload import ReceiveRestEdiPayload


async def get_receive_rest_edi_payload(
    session: Annotated[AsyncSession, Depends(get_session)],
    customer_po_use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> ReceiveRestEdiPayload:
    return ReceiveRestEdiPayload(SqlAlchemyCustomerRepository(session), customer_po_use_cases)
