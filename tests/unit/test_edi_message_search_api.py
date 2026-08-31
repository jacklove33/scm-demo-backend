import os
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.api.dependencies.edi import get_edi_message_use_cases
from app.api.dependencies.identity import get_current_user
from app.main import app
from app.modules.edi.application.use_cases import EdiMessageUseCases
from app.modules.edi.domain.enums import EdiMessageDirection, EdiMessageStatus
from app.modules.edi.domain.repository import EdiMessagePage, EdiMessageSearchCriteria
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)

PATH = "/api/v1/edi/messages"
TENANT = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def actor(*, allowed: bool) -> CurrentUser:
    permissions = {}
    if allowed:
        permission = EffectivePermission(
            "edi_messages.read", PermissionEffect.ALLOW, PermissionScope.ALL, ()
        )
        permissions[permission.permission_code] = permission
    return CurrentUser(USER, TENANT, "admin@example.test", "Admin", True, permissions)


class CapturingRepository:
    def __init__(self) -> None:
        self.tenant_id: UUID | None = None
        self.criteria: EdiMessageSearchCriteria | None = None

    async def search(
        self, tenant_id: UUID, criteria: EdiMessageSearchCriteria
    ) -> EdiMessagePage:
        self.tenant_id = tenant_id
        self.criteria = criteria
        return EdiMessagePage([], 0, criteria.page, criteria.page_size)


def test_search_requires_edi_messages_read() -> None:
    repository = CapturingRepository()
    app.dependency_overrides[get_current_user] = lambda: actor(allowed=False)
    app.dependency_overrides[get_edi_message_use_cases] = lambda: EdiMessageUseCases(repository)
    try:
        response = TestClient(app).get(PATH)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    assert repository.tenant_id is None


def test_search_maps_filters_pagination_and_authenticated_tenant() -> None:
    repository = CapturingRepository()
    app.dependency_overrides[get_current_user] = lambda: actor(allowed=True)
    app.dependency_overrides[get_edi_message_use_cases] = lambda: EdiMessageUseCases(repository)
    params = {
        "page": 2,
        "page_size": 10,
        "direction": "INBOUND",
        "status": "FAILED",
        "document_type": "850",
        "sender_id": "WPG",
        "receiver_id": "SYNA",
        "external_message_id": "MSG-1",
        "business_document_number": "PO123",
        "created_from": "2026-08-01T00:00:00Z",
        "created_to": "2026-08-31T23:59:59Z",
    }
    try:
        response = TestClient(app).get(PATH, params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 2, "page_size": 10}
    assert repository.tenant_id == TENANT
    assert repository.criteria == EdiMessageSearchCriteria(
        page=2,
        page_size=10,
        direction=EdiMessageDirection.INBOUND,
        status=EdiMessageStatus.FAILED,
        document_type="850",
        sender_id="WPG",
        receiver_id="SYNA",
        external_message_id="MSG-1",
        business_document_number="PO123",
        created_from=datetime(2026, 8, 1, tzinfo=UTC),
        created_to=datetime(2026, 8, 31, 23, 59, 59, tzinfo=UTC),
        sort_field="created_at",
        sort_direction="desc",
    )
