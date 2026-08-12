import os
from uuid import UUID

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.api.dependencies.identity import get_current_user
from app.main import app
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)


async def dashboard_actor(allowed: bool = True) -> CurrentUser:
    permissions = {}
    if allowed:
        permissions["dashboard.customer_pos.read"] = EffectivePermission(
            "dashboard.customer_pos.read",
            PermissionEffect.ALLOW,
            PermissionScope.ALL,
            (),
        )
    return CurrentUser(
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        UUID("11111111-1111-1111-1111-111111111111"),
        "admin@example.test",
        "Admin",
        True,
        permissions,
    )


def test_dashboard_modules_requires_jwt() -> None:
    response = TestClient(app).get("/api/v1/dashboard/modules")
    assert response.status_code == 401


def test_dashboard_modules_requires_permission() -> None:
    async def denied() -> CurrentUser:
        return await dashboard_actor(False)

    app.dependency_overrides[get_current_user] = denied
    try:
        response = TestClient(app).get("/api/v1/dashboard/modules")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


def test_dashboard_modules_advertises_phase_one_and_future_modules() -> None:
    app.dependency_overrides[get_current_user] = dashboard_actor
    try:
        response = TestClient(app).get("/api/v1/dashboard/modules")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    modules = {item["code"]: item["enabled"] for item in response.json()["modules"]}
    assert modules["CUSTOMER_PO"] is True
    assert modules["SALES_ORDER"] is False
    assert modules["EDI"] is False


def test_dashboard_rejects_invalid_query_parameters() -> None:
    app.dependency_overrides[get_current_user] = dashboard_actor
    try:
        invalid_dates = TestClient(app).get(
            "/api/v1/dashboard/customer-pos/summary",
            params={"date_from": "2026-08-02", "date_to": "2026-08-01"},
        )
        invalid_granularity = TestClient(app).get(
            "/api/v1/dashboard/customer-pos/trend", params={"granularity": "YEAR"}
        )
        invalid_limit = TestClient(app).get(
            "/api/v1/dashboard/customer-pos/by-customer", params={"limit": 0}
        )
    finally:
        app.dependency_overrides.clear()

    assert invalid_dates.status_code == 422
    assert invalid_dates.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_granularity.status_code == 422
    assert invalid_limit.status_code == 422
