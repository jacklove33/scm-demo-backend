import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

# Keep local .env values from affecting application construction during tests.
os.environ["DEBUG"] = "false"

from app.api.dependencies.customers import get_customer_use_cases
from app.api.dependencies.identity import get_current_user
from app.core.exceptions import ImportValidationFailure, PermissionDenied
from app.main import app
from app.modules.customers.application.capabilities import CustomerCapabilities
from app.modules.customers.application.dto import CustomerSearchDTO
from app.shared.domain.current_user import CurrentUser


class FakeCustomerUseCases:
    import_error: Exception | None = None

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

    async def import_customers(self, rows: list[Any], actor: CurrentUser) -> int:
        if self.import_error:
            raise self.import_error
        return len(rows)


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


def valid_import_body() -> dict[str, object]:
    return {
        "rows": [
            {
                "row_number": 2,
                "customer_code": "CUST100",
                "customer_name": "ACME",
                "address_type": "SOLD_TO",
                "address_code": "MAIN",
                "address_line1": "No. 1 Road",
                "address_country_code": "TW",
            }
        ]
    }


def test_import_customers_returns_compact_summary() -> None:
    fake = FakeCustomerUseCases()
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_customer_use_cases] = lambda: fake
    try:
        response = TestClient(app).post("/api/v1/customers/import", json=valid_import_body())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"total": 1, "imported": 1, "failed": 0}


def test_import_customers_uses_structured_error_envelope() -> None:
    fake = FakeCustomerUseCases()
    fake.import_error = ImportValidationFailure(
        "Customer import validation failed",
        details={
            "errors": [
                {
                    "row_number": 2,
                    "field": "customer_code",
                    "code": "INVALID_CUSTOMER_CODE",
                    "message": "Invalid code",
                }
            ]
        },
    )
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_customer_use_cases] = lambda: fake
    try:
        response = TestClient(app).post("/api/v1/customers/import", json=valid_import_body())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED"
    assert response.json()["error"]["details"]["errors"][0]["row_number"] == 2


def test_import_customers_permission_failure_is_403() -> None:
    fake = FakeCustomerUseCases()
    fake.import_error = PermissionDenied("Missing permission: customers.create")
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_customer_use_cases] = lambda: fake
    try:
        response = TestClient(app).post("/api/v1/customers/import", json=valid_import_body())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
