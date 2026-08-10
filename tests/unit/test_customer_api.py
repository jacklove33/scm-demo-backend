import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

# Keep local .env values from affecting application construction during tests.
os.environ["DEBUG"] = "false"

from app.api.dependencies.customers import get_customer_use_cases
from app.api.dependencies.identity import get_current_user
from app.main import app
from app.modules.customers.application.capabilities import CustomerCapabilities
from app.modules.customers.application.dto import CustomerSearchDTO
from app.shared.domain.current_user import CurrentUser


class FakeCustomerUseCases:
    async def search(
        self, criteria: Any, actor: CurrentUser
    ) -> tuple[list[CustomerSearchDTO], int]:
        now = datetime.now(UTC)
        return (
            [
                CustomerSearchDTO(
                    id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                    customer_code="CUST001",
                    customer_name="Apple Demo",
                    owner_user_id=actor.user_id,
                    status="ACTIVE",
                    deleted_at=None,
                    row_version=1,
                    created_at=now,
                    updated_at=now,
                    capabilities=CustomerCapabilities(
                        update=True,
                        delete=False,
                        restore=False,
                        assign_owner=False,
                    ),
                )
            ],
            1,
        )


async def override_current_user() -> CurrentUser:
    return CurrentUser(
        user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        email="jack@local.test",
        display_name="Jack",
        is_active=True,
        permissions={},
    )


async def override_customer_use_cases() -> FakeCustomerUseCases:
    return FakeCustomerUseCases()


def test_search_customers_serializes_row_capabilities() -> None:
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_customer_use_cases] = override_customer_use_cases
    try:
        response = TestClient(app).get("/api/v1/customers")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"][0]["capabilities"] == {
        "update": True,
        "delete": False,
        "restore": False,
        "assign_owner": False,
    }
