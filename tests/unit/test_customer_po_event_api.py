import os
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.api.dependencies.customer_pos import get_customer_po_use_cases
from app.api.dependencies.identity import get_current_user
from app.main import app
from app.modules.customer_pos.domain.events import (
    CustomerPoEvent,
    CustomerPoEventActorType,
    CustomerPoEventCategory,
    CustomerPoEventPage,
    CustomerPoEventSource,
    CustomerPoEventType,
)
from app.shared.domain.current_user import CurrentUser

PO_ID = UUID("60000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("61000000-0000-0000-0000-000000000001")
TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class FakeTimelineUseCases:
    def __init__(self) -> None:
        self.call: tuple[object, ...] | None = None

    async def event_timeline(
        self,
        po_id: UUID,
        actor: CurrentUser,
        *,
        page: int,
        page_size: int,
        event_type: CustomerPoEventType | None,
        category: CustomerPoEventCategory | None,
    ) -> CustomerPoEventPage:
        self.call = (po_id, actor.tenant_id, page, page_size, event_type, category)
        event = CustomerPoEvent(
            EVENT_ID,
            TENANT,
            PO_ID,
            CustomerPoEventType.STATUS_CHANGE,
            CustomerPoEventCategory.WORKFLOW,
            "Status changed",
            "RECEIVED → VALIDATING",
            CustomerPoEventActorType.USER,
            ACTOR,
            "Kevin Admin",
            CustomerPoEventSource.API,
            "correlation-1",
            "request-1",
            {"from_status": "RECEIVED", "to_status": "VALIDATING"},
            datetime(2026, 8, 12, tzinfo=UTC),
            datetime(2026, 8, 12, tzinfo=UTC),
        )
        return CustomerPoEventPage([event], 1, page, page_size)


def current_user() -> CurrentUser:
    return CurrentUser(ACTOR, TENANT, "kevin@local.test", "Kevin Admin", True, {})


def test_timeline_requires_jwt() -> None:
    response = TestClient(app).get(f"/api/v1/customer-pos/{PO_ID}/events")
    assert response.status_code == 401


def test_timeline_returns_business_events_and_forwards_filters() -> None:
    fake = FakeTimelineUseCases()
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_customer_po_use_cases] = lambda: fake
    try:
        response = TestClient(app).get(
            f"/api/v1/customer-pos/{PO_ID}/events",
            params={
                "page": 2,
                "page_size": 10,
                "event_type": "STATUS_CHANGE",
                "category": "WORKFLOW",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 2
    assert payload["items"][0]["event_type"] == "STATUS_CHANGE"
    assert payload["items"][0]["actor_display_name"] == "Kevin Admin"
    assert "actor_user_id" not in payload["items"][0]["metadata"]
    assert fake.call == (
        PO_ID,
        TENANT,
        2,
        10,
        CustomerPoEventType.STATUS_CHANGE,
        CustomerPoEventCategory.WORKFLOW,
    )


def test_timeline_rejects_invalid_filters_and_pagination() -> None:
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_customer_po_use_cases] = FakeTimelineUseCases
    try:
        event_type = TestClient(app).get(
            f"/api/v1/customer-pos/{PO_ID}/events", params={"event_type": "FABRICATED"}
        )
        page_size = TestClient(app).get(
            f"/api/v1/customer-pos/{PO_ID}/events", params={"page_size": 0}
        )
    finally:
        app.dependency_overrides.clear()
    assert event_type.status_code == 422
    assert page_size.status_code == 422
