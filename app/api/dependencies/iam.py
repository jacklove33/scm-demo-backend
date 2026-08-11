from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.iam.application.management_service import IamManagementService
from app.modules.iam.infrastructure.repository import SqlAlchemyIamRepository


async def get_iam_management_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IamManagementService:
    return IamManagementService(SqlAlchemyIamRepository(session))
