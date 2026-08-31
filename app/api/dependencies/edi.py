from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.customer_pos import get_customer_po_use_cases
from app.api.dependencies.identity import load_current_user_context
from app.core.config import settings
from app.core.exceptions import AuthenticationRequired
from app.infrastructure.database.session import get_session
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customers.infrastructure.repository import SqlAlchemyCustomerRepository
from app.modules.edi.application.receive_rest_payload import ReceiveRestEdiPayload
from app.modules.edi.application.tracker import EdiMessageTracker
from app.modules.edi.application.use_cases import EdiMessageUseCases
from app.modules.edi.infrastructure.repository import SqlAlchemyEdiMessageRepository
from app.modules.edi.infrastructure.unit_of_work import SqlAlchemyEdiTrackingUnitOfWork
from app.shared.domain.current_user import CurrentUser


async def get_edi_inbound_actor(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    """Authenticate an inbound EDI request without coupling it to ERP JWT auth."""
    if settings.edi_inbound_auth_mode == "dev_no_auth":
        if settings.app_env not in {"local", "test"}:
            raise AuthenticationRequired(
                "Unauthenticated EDI inbound is disabled outside local/test environments"
            )
        if settings.edi_dev_user_id is None:
            raise AuthenticationRequired("EDI_DEV_USER_ID must be configured for EDI dev mode")
        return await load_current_user_context(settings.edi_dev_user_id, session)

    # This mode is deliberately fail-closed until partner API-key authentication exists.
    raise AuthenticationRequired("EDI API-key authentication is not implemented")


async def get_receive_rest_edi_payload(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[CurrentUser, Depends(get_edi_inbound_actor)],
    customer_po_use_cases: Annotated[CustomerPoUseCases, Depends(get_customer_po_use_cases)],
) -> ReceiveRestEdiPayload:
    return ReceiveRestEdiPayload(
        SqlAlchemyCustomerRepository(session),
        customer_po_use_cases,
        EdiMessageTracker(
            SqlAlchemyEdiMessageRepository(session),
            SqlAlchemyEdiTrackingUnitOfWork(session, actor.tenant_id, actor.user_id),
        ),
    )


async def get_edi_message_use_cases(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EdiMessageUseCases:
    return EdiMessageUseCases(SqlAlchemyEdiMessageRepository(session))
