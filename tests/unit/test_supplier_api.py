import os
from uuid import UUID

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.api.dependencies.identity import get_current_user
from app.api.dependencies.suppliers import get_supplier_use_cases
from app.main import app
from app.shared.domain.current_user import CurrentUser

ACTOR = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT = UUID("11111111-1111-1111-1111-111111111111")


def current_user() -> CurrentUser:
    return CurrentUser(ACTOR, TENANT, "kevin@local.test", "Kevin Admin", True, {})


class FakeSupplierUseCases:
    async def list_payment_terms(self, actor: CurrentUser) -> list[tuple[UUID, str, str]]:
        return [(UUID("90000000-0000-0000-0000-000000000001"), "NET30", "Net 30")]


def test_supplier_routes_are_registered_and_require_authentication() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/suppliers" in paths
    assert "/api/v1/suppliers/{supplier_id}" in paths
    assert "/api/v1/suppliers/import" in paths
    assert TestClient(app).get("/api/v1/suppliers").status_code == 401


def test_payment_term_lookup_is_tenant_scoped_through_current_actor() -> None:
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_supplier_use_cases] = FakeSupplierUseCases
    try:
        response = TestClient(app).get("/api/v1/suppliers/payment-terms")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == [
        {"id": "90000000-0000-0000-0000-000000000001", "code": "NET30", "name": "Net 30"}
    ]


def test_create_rejects_read_only_owner_display_name_before_use_case() -> None:
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_supplier_use_cases] = FakeSupplierUseCases
    try:
        response = TestClient(app).post(
            "/api/v1/suppliers",
            json={
                "supplier_code": "SUP-1",
                "supplier_name": "ACME",
                "owner_user_id": str(ACTOR),
                "owner_display_name": "Kevin Admin",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
