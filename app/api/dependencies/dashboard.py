from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.dashboard.application.service import CustomerPoDashboardService
from app.modules.dashboard.infrastructure.repository import SqlAlchemyDashboardRepository


async def get_customer_po_dashboard_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CustomerPoDashboardService:
    return CustomerPoDashboardService(SqlAlchemyDashboardRepository(session))
