from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.edi import get_receive_rest_edi_payload
from app.api.dependencies.identity import get_current_user
from app.core.exceptions import ValidationFailure
from app.main import app
from app.modules.audit.domain.entities import AuditContext
from app.modules.audit.domain.enums import AuditActorType, AuditSource
from app.modules.customer_pos.application.commands import CreateCustomerPoCommand
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customer_pos.domain.enums import CustomerPoSource
from app.modules.customers.domain.entities import Customer
from app.modules.edi.application.receive_rest_payload import (
    EdiCustomerResolver,
    ReceiveRestEdiPayload,
    ReceiveRestEdiPayloadCommand,
    RestEdiReceipt,
)
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)

PATH = "/api/v1/edi/rest/receive"
TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CUSTOMER_ID = UUID("40000000-0000-0000-0000-000000000099")
PO_ID = UUID("70000000-0000-0000-0000-000000000099")
PAYLOAD = {
    "lines": [
        {
            "uom": "EA",
            "item": "ABC123",
            "quantity": 100,
            "unitPrice": 12.5,
            "lineNumber": "1",
            "itemQualifier": "BP",
        },
        {
            "uom": "EA",
            "item": "XYZ789",
            "quantity": 50,
            "unitPrice": 8.75,
            "lineNumber": "2",
            "itemQualifier": "BP",
        },
    ],
    "poDate": "2026-08-18",
    "shipTo": "Synaptics Demo Warehouse",
    "customer": "WPG",
    "poNumber": "PO123456",
    "purposeCode": "00",
}
REQUIRED_HEADERS = {"X-Sender-ID": "WPG", "X-Receiver-ID": "SYNA", "X-Document-Type": "850"}


def actor() -> CurrentUser:
    permission = EffectivePermission(
        "customer_pos.create", PermissionEffect.ALLOW, PermissionScope.ALL, ()
    )
    return CurrentUser(
        ACTOR,
        TENANT,
        "kevin@local.test",
        "Kevin Admin",
        True,
        {permission.permission_code: permission},
    )


def context() -> AuditContext:
    return AuditContext(
        TENANT,
        ACTOR,
        "kevin@local.test",
        "Kevin Admin",
        AuditSource.EDI,
        AuditActorType.USER,
        "corr",
        "req",
    )


class CustomerLookup:
    def __init__(self, found: bool = True) -> None:
        now = datetime.now(UTC)
        self.customer = (
            Customer(
                CUSTOMER_ID,
                TENANT,
                "WPG",
                "WPG",
                ACTOR,
                "ACTIVE",
                None,
                None,
                1,
                now,
                now,
                currency_code="TWD",
            )
            if found
            else None
        )
        self.requested: tuple[str, UUID] | None = None

    async def get_by_code(self, customer_code: str, *, tenant_id: UUID) -> Customer | None:
        self.requested = (customer_code, tenant_id)
        return self.customer


class CapturingCustomerPoUseCases:
    def __init__(self) -> None:
        self.command: CreateCustomerPoCommand | None = None

    async def create(
        self, command: CreateCustomerPoCommand, actor: CurrentUser, context: AuditContext
    ) -> tuple[Any, Any]:
        self.command = command
        return SimpleNamespace(id=PO_ID), None


@pytest.mark.asyncio
async def test_fixture_maps_to_existing_customer_po_creation_contract() -> None:
    customers = CustomerLookup()
    customer_pos = CapturingCustomerPoUseCases()
    service = ReceiveRestEdiPayload(
        cast(EdiCustomerResolver, cast(Any, customers)),
        cast(CustomerPoUseCases, cast(Any, customer_pos)),
    )

    receipt = await service.execute(
        ReceiveRestEdiPayloadCommand("WPG", "SYNA", "850", "REST-DEMO-001", PAYLOAD),
        actor(),
        context(),
    )

    command = customer_pos.command
    assert command is not None
    assert customers.requested == ("WPG", TENANT)
    assert receipt.customer_po_id == PO_ID
    assert command.customer_id == CUSTOMER_ID
    assert command.customer_po_number == "PO123456"
    assert command.customer_po_date == date(2026, 8, 18)
    assert command.ship_to_name == "Synaptics Demo Warehouse"
    assert command.source == CustomerPoSource.EDI
    assert command.currency_code == "TWD"
    assert len(command.lines) == 2
    assert [
        (
            line.line_number,
            line.customer_item_number,
            line.ordered_quantity,
            line.unit_of_measure,
            line.unit_price,
        )
        for line in command.lines
    ] == [
        (1, "ABC123", Decimal("100"), "EA", Decimal("12.5")),
        (2, "XYZ789", Decimal("50"), "EA", Decimal("8.75")),
    ]
    assert sum(
        line.ordered_quantity * (line.unit_price or Decimal()) for line in command.lines
    ) == Decimal("1687.50")
    assert command.customer_notes is None
    assert all(line.edi_line_reference is None for line in command.lines)


@pytest.mark.asyncio
async def test_missing_customer_stops_before_customer_po_creation() -> None:
    customer_pos = CapturingCustomerPoUseCases()
    service = ReceiveRestEdiPayload(
        cast(EdiCustomerResolver, cast(Any, CustomerLookup(False))),
        cast(CustomerPoUseCases, cast(Any, customer_pos)),
    )
    with pytest.raises(ValidationFailure, match="customer was not found") as raised:
        await service.execute(
            ReceiveRestEdiPayloadCommand("WPG", "SYNA", "850", None, PAYLOAD), actor(), context()
        )
    assert raised.value.details["error_code"] == "EDI_CUSTOMER_NOT_FOUND"
    assert customer_pos.command is None


@pytest.mark.asyncio
async def test_duplicate_line_number_stops_before_customer_po_creation() -> None:
    customer_pos = CapturingCustomerPoUseCases()
    service = ReceiveRestEdiPayload(
        cast(EdiCustomerResolver, cast(Any, CustomerLookup())),
        cast(CustomerPoUseCases, cast(Any, customer_pos)),
    )
    duplicate = {**PAYLOAD, "lines": [PAYLOAD["lines"][0], PAYLOAD["lines"][0]]}
    with pytest.raises(ValidationFailure, match="Duplicate EDI line number"):
        await service.execute(
            ReceiveRestEdiPayloadCommand("WPG", "SYNA", "850", None, duplicate), actor(), context()
        )
    assert customer_pos.command is None


class ApiService:
    async def execute(
        self, command: ReceiveRestEdiPayloadCommand, actor: CurrentUser, audit_context: AuditContext
    ) -> RestEdiReceipt:
        return RestEdiReceipt(
            command.sender_id,
            command.receiver_id,
            command.document_type,
            command.external_message_id,
            PO_ID,
        )


@pytest.fixture
def api_overrides() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = actor
    app.dependency_overrides[get_receive_rest_edi_payload] = ApiService
    yield
    app.dependency_overrides.clear()


def test_receive_rest_edi_payload_returns_accepted(api_overrides: None) -> None:
    response = TestClient(app).post(
        PATH, headers={**REQUIRED_HEADERS, "X-External-Message-ID": "REST-DEMO-001"}, json=PAYLOAD
    )
    assert response.status_code == 202
    assert response.json() == {
        "status": "RECEIVED",
        "sender_id": "WPG",
        "receiver_id": "SYNA",
        "document_type": "850",
        "external_message_id": "REST-DEMO-001",
        "customer_po_id": str(PO_ID),
    }


@pytest.mark.parametrize("missing_header", REQUIRED_HEADERS)
def test_receive_rest_edi_payload_requires_routing_headers(
    missing_header: str, api_overrides: None
) -> None:
    response = TestClient(app).post(
        PATH,
        headers={key: value for key, value in REQUIRED_HEADERS.items() if key != missing_header},
        json=PAYLOAD,
    )
    assert response.status_code == 422


def test_receive_rest_edi_payload_rejects_invalid_json(api_overrides: None) -> None:
    response = TestClient(app).post(
        PATH,
        headers={**REQUIRED_HEADERS, "Content-Type": "application/json"},
        content='{"poNumber":',
    )
    assert response.status_code == 422
