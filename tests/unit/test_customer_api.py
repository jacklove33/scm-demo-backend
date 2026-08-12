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

    def __init__(self) -> None:
        self.criteria: Any = None

    async def search(
        self, criteria: Any, actor: CurrentUser
    ) -> tuple[list[CustomerSearchDTO], int]:
        self.criteria = criteria
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

    async def import_customers(
        self, rows: list[Any], actor: CurrentUser, audit_context: object | None = None
    ) -> int:
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


def fake_override(fake: FakeCustomerUseCases) -> Any:
    async def override() -> FakeCustomerUseCases:
        return fake

    return override


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


def test_customer_date_filters_use_utc_half_open_boundaries_and_can_be_combined() -> None:
    fake = FakeCustomerUseCases()
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_customer_use_cases] = lambda: fake
    try:
        response = TestClient(app).get(
            "/api/v1/customers",
            params={
                "created_date_from": "2026-09-01",
                "created_date_to": "2026-09-10",
                "updated_date_from": "2026-09-05",
                "updated_date_to": "2026-09-12",
                "customer_code": "ABC",
                "status": "ACTIVE",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake.criteria.created_at_from == datetime(2026, 9, 1, tzinfo=UTC)
    assert fake.criteria.created_at_to_exclusive == datetime(2026, 9, 11, tzinfo=UTC)
    assert fake.criteria.updated_at_from == datetime(2026, 9, 5, tzinfo=UTC)
    assert fake.criteria.updated_at_to_exclusive == datetime(2026, 9, 13, tzinfo=UTC)
    assert fake.criteria.customer_code == "ABC"
    assert fake.criteria.status == "ACTIVE"


def test_customer_date_filters_support_each_one_sided_boundary() -> None:
    expected = {
        "created_date_from": ("created_at_from", datetime(2026, 9, 1, tzinfo=UTC)),
        "created_date_to": ("created_at_to_exclusive", datetime(2026, 9, 2, tzinfo=UTC)),
        "updated_date_from": ("updated_at_from", datetime(2026, 9, 1, tzinfo=UTC)),
        "updated_date_to": ("updated_at_to_exclusive", datetime(2026, 9, 2, tzinfo=UTC)),
    }
    for parameter, (field, boundary) in expected.items():
        fake = FakeCustomerUseCases()

        app.dependency_overrides[get_current_user] = override_current_user
        app.dependency_overrides[get_customer_use_cases] = fake_override(fake)
        try:
            response = TestClient(app).get("/api/v1/customers", params={parameter: "2026-09-01"})
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 200
        assert getattr(fake.criteria, field) == boundary


def test_customer_date_range_validation_errors_have_specific_codes() -> None:
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_customer_use_cases] = override_customer_use_cases
    try:
        invalid = TestClient(app).get(
            "/api/v1/customers?created_date_from=2026-09-10&created_date_to=2026-09-01"
        )
        too_large = TestClient(app).get(
            "/api/v1/customers?updated_date_from=2026-09-01&updated_date_to=2026-09-15"
        )
        fourteen_days = TestClient(app).get(
            "/api/v1/customers?created_date_from=2026-09-01&created_date_to=2026-09-14"
        )
    finally:
        app.dependency_overrides.clear()

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_DATE_RANGE"
    assert too_large.status_code == 422
    assert too_large.json()["error"]["code"] == "DATE_RANGE_TOO_LARGE"
    assert fourteen_days.status_code == 200


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
