from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityConflict
from app.modules.customers.domain.entities import Customer, CustomerAddress
from app.modules.customers.infrastructure.repository import SqlAlchemyCustomerRepository


class FailingSession:
    def __init__(self) -> None:
        self.add_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def add_all(self, instances: list[object]) -> None:
        self.add_calls += 1

    async def commit(self) -> None:
        self.commit_calls += 1
        raise IntegrityError("forced", {}, Exception("forced row 3 failure"))

    async def rollback(self) -> None:
        self.rollback_calls += 1


def customer(code: str) -> Customer:
    now = datetime.now(UTC)
    customer_id = uuid4()
    return Customer(
        id=customer_id,
        tenant_id=uuid4(),
        customer_code=code,
        customer_name=code,
        owner_user_id=None,
        status="ACTIVE",
        deleted_at=None,
        deleted_by=None,
        row_version=1,
        created_at=now,
        updated_at=now,
        addresses=(
            CustomerAddress(
                id=uuid4(),
                address_code="MAIN",
                address_type="SOLD_TO",
                address1="Address",
                country_code="TW",
                is_default=True,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_create_many_rolls_back_whole_batch_on_persistence_failure() -> None:
    session = FailingSession()
    repository = SqlAlchemyCustomerRepository(cast(AsyncSession, cast(Any, session)))

    with pytest.raises(EntityConflict):
        await repository.create_many([customer("A100"), customer("A101"), customer("A102")])

    assert session.add_calls == 3
    assert session.commit_calls == 1
    assert session.rollback_calls == 1
