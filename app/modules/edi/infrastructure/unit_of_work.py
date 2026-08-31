from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyEdiTrackingUnitOfWork:
    """Keep transaction-local RLS identity valid across tracking commits."""

    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID) -> None:
        self.session = session
        self.parameters = {"tenant_id": str(tenant_id), "user_id": str(user_id)}

    async def bind(self) -> None:
        await self.session.execute(
            text(
                "SELECT set_config('app.tenant_id', :tenant_id, true), "
                "set_config('app.user_id', :user_id, true)"
            ),
            self.parameters,
        )

    async def commit(self) -> None:
        await self.session.commit()
        await self.bind()

    async def rollback(self) -> None:
        await self.session.rollback()
