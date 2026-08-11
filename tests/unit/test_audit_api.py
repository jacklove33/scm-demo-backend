import os
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.api.dependencies.audit import get_audit_use_cases
from app.api.dependencies.identity import get_current_user
from app.main import app
from app.modules.audit.application.use_cases import AuditUseCases
from app.modules.audit.domain.entities import AuditChange, AuditEvent, AuditEventSummary, AuditPage
from app.modules.audit.domain.enums import (
    AuditAction,
    AuditChangeType,
    AuditSource,
    AuditStatus,
    AuditValueType,
)
from app.modules.audit.domain.repository import AuditSearchCriteria
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EVENT = UUID("70000000-0000-0000-0000-000000000001")
CUSTOMER = UUID("40000000-0000-0000-0000-000000000001")


def event() -> AuditEvent:
    now = datetime.now(UTC)
    return AuditEvent(
        id=EVENT,
        tenant_id=TENANT,
        occurred_at=now,
        actor_user_id=USER,
        actor_email="admin@local.test",
        actor_display_name="Admin",
        module="CUSTOMER",
        action=AuditAction.UPDATE,
        entity_type="CUSTOMER",
        entity_id=CUSTOMER,
        entity_code="CUST001",
        entity_display_name="Apple",
        source=AuditSource.API,
        correlation_id="corr-1",
        request_id=None,
        request_method="PUT",
        request_path=f"/api/v1/customers/{CUSTOMER}",
        ip_address="127.0.0.1",
        user_agent="test",
        status=AuditStatus.SUCCESS,
        created_at=now,
        changes=(
            AuditChange(
                sequence_no=1,
                field_path="customer.customer_name",
                field_label="Customer Name",
                change_type=AuditChangeType.UPDATE,
                value_type=AuditValueType.STRING,
                old_value="Apple",
                new_value="Apple Taiwan",
                old_display_value="Apple",
                new_display_value="Apple Taiwan",
            ),
        ),
    )


class AuditRepositoryFake:
    def __init__(self) -> None:
        self.last_criteria: AuditSearchCriteria | None = None

    async def add_event(self, event: AuditEvent, changes: list[AuditChange]) -> None:
        return None

    async def search(self, tenant_id: UUID, criteria: AuditSearchCriteria) -> AuditPage:
        self.last_criteria = criteria
        return AuditPage([AuditEventSummary(event(), 1)], 1, criteria.page, criteria.page_size)

    async def get_by_id(self, tenant_id: UUID, event_id: UUID) -> AuditEvent | None:
        return event() if event_id == EVENT else None


def user(*, allowed: bool) -> CurrentUser:
    permissions = {}
    if allowed:
        permissions["audit.read"] = EffectivePermission(
            "audit.read", PermissionEffect.ALLOW, PermissionScope.ALL, ()
        )
    return CurrentUser(USER, TENANT, "admin@local.test", "Admin", True, permissions)


def test_audit_search_and_detail_require_audit_read() -> None:
    repository = AuditRepositoryFake()
    audit = AuditUseCases(repository)
    current = user(allowed=True)
    app.dependency_overrides[get_audit_use_cases] = lambda: audit
    app.dependency_overrides[get_current_user] = lambda: current
    try:
        listing = TestClient(app).get(
            "/api/v1/audit-events",
            params={
                "page": 2,
                "page_size": 25,
                "from": "2026-08-10T00:00:00Z",
                "to": "2026-08-12T00:00:00Z",
                "actor_user_id": str(USER),
                "module": "CUSTOMER",
                "action": "UPDATE",
                "entity_type": "CUSTOMER",
                "entity_id": str(CUSTOMER),
                "entity_code": "CUST001",
                "source": "API",
                "status": "SUCCESS",
                "correlation_id": "corr-1",
                "batch_id": "80000000-0000-0000-0000-000000000001",
            },
        )
        detail = TestClient(app).get(f"/api/v1/audit-events/{EVENT}")
    finally:
        app.dependency_overrides.clear()

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["data"][0]["change_count"] == 1
    assert listing.json()["data"][0]["actor_type"] == "USER"
    assert listing.json()["data"][0]["actor_user_id"] == str(USER)
    assert listing.json()["data"][0]["actor_display_name"] == "Admin"
    assert listing.json()["data"][0]["actor_email"] == "admin@local.test"
    assert listing.json()["data"][0]["module"] == "CUSTOMER"
    assert listing.json()["data"][0]["entity_code"] == "CUST001"
    assert detail.status_code == 200
    assert detail.json()["changes"][0]["field_path"] == "customer.customer_name"
    assert detail.json()["actor_type"] == "USER"
    assert detail.json()["actor_display_name"] == "Admin"
    assert repository.last_criteria is not None
    assert repository.last_criteria.page == 2
    assert repository.last_criteria.page_size == 25
    assert repository.last_criteria.actor_user_id == USER
    assert repository.last_criteria.module == "CUSTOMER"
    assert repository.last_criteria.action == "UPDATE"
    assert repository.last_criteria.entity_id == CUSTOMER
    assert repository.last_criteria.correlation_id == "corr-1"

    app.dependency_overrides[get_audit_use_cases] = lambda: audit
    app.dependency_overrides[get_current_user] = lambda: user(allowed=False)
    try:
        denied = TestClient(app).get("/api/v1/audit-events")
    finally:
        app.dependency_overrides.clear()
    assert denied.status_code == 403
