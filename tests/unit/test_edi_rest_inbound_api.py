from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.edi import get_edi_inbound_actor, get_receive_rest_edi_payload
from app.core.exceptions import EntityConflict, ValidationFailure
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
from app.modules.edi.application.tracker import EdiMessageTracker
from app.modules.edi.domain.entities import EdiMessage
from app.modules.edi.domain.enums import (
    EdiMessageDirection,
    EdiMessageStatus,
    EdiRelatedEntityType,
)
from app.modules.edi.presentation.schemas import RestEdiPayloadRequest
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
EDI_ID = UUID("80000000-0000-0000-0000-000000000099")
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
        return SimpleNamespace(id=PO_ID, customer_po_number=command.customer_po_number), None


class StubTracker:
    def __init__(self, *, duplicate: bool = False) -> None:
        now = datetime.now(UTC)
        self.message = EdiMessage(
            EDI_ID,
            TENANT,
            EdiMessageDirection.INBOUND,
            "DIRECT_API",
            "REST",
            "JSON",
            "850",
            "WPG",
            "SYNA",
            "REST-DEMO-001",
            "corr",
            None,
            EdiMessageStatus.RECEIVED,
            None,
            None,
            EdiRelatedEntityType.CUSTOMER_PO if duplicate else None,
            PO_ID if duplicate else None,
            now,
            now if duplicate else None,
            now,
            now,
        )
        self.duplicate = duplicate
        self.transitions: list[str] = []

    async def create_received(self, **_: object) -> tuple[EdiMessage, bool]:
        self.transitions.append("RECEIVED")
        return self.message, self.duplicate

    async def start_validation(self, message: EdiMessage) -> EdiMessage:
        self.transitions.append("VALIDATION_STARTED")
        return message

    async def validation_passed(self, message: EdiMessage) -> EdiMessage:
        self.transitions.append("VALIDATION_PASSED")
        return message

    async def validation_failed(
        self,
        message: EdiMessage,
        error_code: str,
        error_message: str,
        details: dict[str, object] | None = None,
    ) -> EdiMessage:
        self.transitions.append(f"VALIDATION_FAILED:{error_code}")
        return message

    async def start_processing(self, message: EdiMessage) -> EdiMessage:
        self.transitions.append("PROCESSING_STARTED")
        return message

    async def link_related_entity(
        self,
        message: EdiMessage,
        entity_type: EdiRelatedEntityType,
        entity_id: UUID,
        business_document_number: str,
    ) -> EdiMessage:
        self.transitions.append("RELATED_ENTITY_CREATED")
        return message

    async def completed(self, message: EdiMessage) -> EdiMessage:
        self.transitions.append("COMPLETED")
        return message

    async def failed(
        self,
        message: EdiMessage,
        error_code: str,
        error_message: str,
        details: dict[str, object] | None = None,
    ) -> EdiMessage:
        self.transitions.append(f"FAILED:{error_code}")
        return message


def inbound_service(
    customers: CustomerLookup,
    customer_pos: CapturingCustomerPoUseCases,
    tracker: StubTracker | None = None,
) -> ReceiveRestEdiPayload:
    return ReceiveRestEdiPayload(
        cast(EdiCustomerResolver, cast(Any, customers)),
        cast(CustomerPoUseCases, cast(Any, customer_pos)),
        cast(EdiMessageTracker, cast(Any, tracker or StubTracker())),
    )


class ConflictingCustomerPoUseCases(CapturingCustomerPoUseCases):
    async def create(
        self, command: CreateCustomerPoCommand, actor: CurrentUser, context: AuditContext
    ) -> tuple[Any, Any]:
        self.command = command
        raise EntityConflict("Duplicate Customer PO")


def inbound_command(
    *,
    document_type: str = "850",
    external_message_id: str | None = "REST-DEMO-001",
    payload: dict[str, Any] = PAYLOAD,
) -> ReceiveRestEdiPayloadCommand:
    request = RestEdiPayloadRequest.model_validate(payload)
    return ReceiveRestEdiPayloadCommand(
        "WPG",
        "SYNA",
        document_type,
        external_message_id,
        request.to_document(),
        request.model_dump(by_alias=True, mode="json"),
    )


@pytest.mark.asyncio
async def test_fixture_maps_to_existing_customer_po_creation_contract() -> None:
    customers = CustomerLookup()
    customer_pos = CapturingCustomerPoUseCases()
    tracker = StubTracker()
    service = inbound_service(customers, customer_pos, tracker)

    receipt = await service.execute(inbound_command(), actor(), context())

    command = customer_pos.command
    assert command is not None
    assert customers.requested == ("WPG", TENANT)
    assert receipt.customer_po_id == PO_ID
    assert receipt.edi_message_id == EDI_ID
    assert command.edi_message_id == EDI_ID
    assert tracker.transitions == [
        "RECEIVED",
        "VALIDATION_STARTED",
        "VALIDATION_PASSED",
        "PROCESSING_STARTED",
        "RELATED_ENTITY_CREATED",
        "COMPLETED",
    ]
    assert command.customer_id == CUSTOMER_ID
    assert command.customer_po_number == "PO123456"
    assert command.customer_po_date == date(2026, 8, 18)
    assert command.ship_to_name == "Synaptics Demo Warehouse"
    assert command.source == CustomerPoSource.EDI
    assert command.currency_code == "TWD"
    assert command.source_document_hash is not None
    assert len(command.source_document_hash) == 64
    assert command.edi_sender_id == "WPG"
    assert command.edi_receiver_id == "SYNA"
    assert command.external_message_id == "REST-DEMO-001"
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
    tracker = StubTracker()
    service = inbound_service(CustomerLookup(False), customer_pos, tracker)
    with pytest.raises(ValidationFailure, match="customer was not found") as raised:
        await service.execute(inbound_command(external_message_id=None), actor(), context())
    assert raised.value.details["error_code"] == "EDI_CUSTOMER_NOT_FOUND"
    assert customer_pos.command is None
    assert tracker.transitions[-1] == "VALIDATION_FAILED:EDI_CUSTOMER_NOT_FOUND"


@pytest.mark.asyncio
async def test_duplicate_line_number_stops_before_customer_po_creation() -> None:
    customer_pos = CapturingCustomerPoUseCases()
    service = inbound_service(CustomerLookup(), customer_pos)
    duplicate = RestEdiPayloadRequest.model_validate(
        {**PAYLOAD, "lines": [PAYLOAD["lines"][0], PAYLOAD["lines"][0]]}
    )
    with pytest.raises(ValidationFailure, match="Duplicate EDI line number"):
        await service.execute(
            ReceiveRestEdiPayloadCommand(
                "WPG",
                "SYNA",
                "850",
                None,
                duplicate.to_document(),
                duplicate.model_dump(by_alias=True, mode="json"),
            ),
            actor(),
            context(),
        )
    assert customer_pos.command is None


@pytest.mark.asyncio
async def test_non_850_is_rejected_before_customer_resolution() -> None:
    customers = CustomerLookup()
    customer_pos = CapturingCustomerPoUseCases()
    service = inbound_service(customers, customer_pos)
    with pytest.raises(ValidationFailure) as raised:
        await service.execute(inbound_command(document_type="860"), actor(), context())
    assert raised.value.details["error_code"] == "EDI_DOCUMENT_TYPE_UNSUPPORTED"
    assert customers.requested is None
    assert customer_pos.command is None


@pytest.mark.asyncio
async def test_duplicate_delivery_returns_original_po_without_creating() -> None:
    customers = CustomerLookup()
    customer_pos = CapturingCustomerPoUseCases()
    tracker = StubTracker(duplicate=True)
    service = inbound_service(customers, customer_pos, tracker)
    receipt = await service.execute(inbound_command(), actor(), context())
    assert receipt.customer_po_id == PO_ID
    assert tracker.transitions == ["RECEIVED"]
    assert customers.requested is None
    assert customer_pos.command is None


@pytest.mark.asyncio
async def test_business_conflict_marks_tracking_failed() -> None:
    tracker = StubTracker()
    service = inbound_service(CustomerLookup(), ConflictingCustomerPoUseCases(), tracker)
    with pytest.raises(EntityConflict):
        await service.execute(inbound_command(), actor(), context())
    assert tracker.transitions[-1] == "FAILED:CONFLICT"


class ApiService:
    last_actor: CurrentUser | None = None
    last_context: AuditContext | None = None

    async def execute(
        self, command: ReceiveRestEdiPayloadCommand, actor: CurrentUser, audit_context: AuditContext
    ) -> RestEdiReceipt:
        type(self).last_actor = actor
        type(self).last_context = audit_context
        return RestEdiReceipt(
            command.sender_id,
            command.receiver_id,
            command.document_type,
            command.external_message_id,
            PO_ID,
            EDI_ID,
        )


@pytest.fixture
def api_overrides() -> Iterator[None]:
    app.dependency_overrides[get_edi_inbound_actor] = actor
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
        "edi_message_id": str(EDI_ID),
    }
    assert ApiService.last_actor == actor()
    assert ApiService.last_context is not None
    assert ApiService.last_context.tenant_id == TENANT
    assert ApiService.last_context.source == AuditSource.EDI


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


@pytest.mark.parametrize(
    "payload",
    [
        {**PAYLOAD, "lines": []},
        {
            **PAYLOAD,
            "lines": [
                {
                    "uom": "EA",
                    "item": "ABC123",
                    "quantity": 0,
                    "unitPrice": 12.5,
                    "lineNumber": "1",
                    "itemQualifier": "BP",
                }
            ],
        },
    ],
)
def test_canonical_contract_rejects_empty_lines_and_invalid_quantity(
    payload: dict[str, Any], api_overrides: None
) -> None:
    response = TestClient(app).post(PATH, headers=REQUIRED_HEADERS, json=payload)
    assert response.status_code == 422
