import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import UUID

from app.core.exceptions import ValidationFailure
from app.core.logging import sanitize_log_data
from app.modules.audit.domain.entities import AuditContext
from app.modules.customer_pos.application.commands import (
    CreateCustomerPoCommand,
    CustomerPoLineCommand,
)
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customer_pos.domain.enums import CustomerPoSource
from app.modules.customers.domain.entities import Customer
from app.shared.domain.current_user import CurrentUser

logger = logging.getLogger("app.modules.edi")


class EdiCustomerResolver(Protocol):
    async def get_by_code(self, customer_code: str, *, tenant_id: UUID) -> Customer | None: ...


@dataclass(frozen=True, slots=True)
class InboundCustomerPoLine:
    line_number: int
    item: str
    item_qualifier: str | None
    quantity: Decimal
    uom: str | None
    unit_price: Decimal | None


@dataclass(frozen=True, slots=True)
class InboundCustomerPoDocument:
    customer_code: str
    po_number: str
    po_date: date
    ship_to_name: str | None
    purpose_code: str | None
    lines: tuple[InboundCustomerPoLine, ...]


@dataclass(frozen=True, slots=True)
class ReceiveRestEdiPayloadCommand:
    sender_id: str
    receiver_id: str
    document_type: str
    external_message_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RestEdiReceipt:
    sender_id: str
    receiver_id: str
    document_type: str
    external_message_id: str | None
    customer_po_id: UUID


class ReceiveRestEdiPayload:
    """Map a canonical REST EDI document through the Customer PO application boundary."""

    def __init__(
        self, customer_repository: EdiCustomerResolver, customer_po_use_cases: CustomerPoUseCases
    ) -> None:
        self.customer_repository = customer_repository
        self.customer_po_use_cases = customer_po_use_cases

    async def execute(
        self,
        command: ReceiveRestEdiPayloadCommand,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> RestEdiReceipt:
        self._log_received(command)
        document = self._parse(command.payload)
        customer = await self.customer_repository.get_by_code(
            document.customer_code, tenant_id=actor.tenant_id
        )
        if customer is None:
            raise ValidationFailure(
                "EDI customer was not found",
                details={
                    "error_code": "EDI_CUSTOMER_NOT_FOUND",
                    "customer_code": document.customer_code,
                },
            )
        if not customer.currency_code:
            raise ValidationFailure(
                "EDI Customer PO currency is unavailable",
                details={"error_code": "EDI_CURRENCY_UNAVAILABLE"},
            )
        received_at = datetime.now(UTC)
        po_command = self._to_customer_po_command(document, customer, command, received_at)
        created, _capabilities = await self.customer_po_use_cases.create(
            po_command, actor, audit_context
        )
        return RestEdiReceipt(
            command.sender_id,
            command.receiver_id,
            command.document_type,
            command.external_message_id,
            created.id,
        )

    @staticmethod
    def _to_customer_po_command(
        document: InboundCustomerPoDocument,
        customer: Customer,
        envelope: ReceiveRestEdiPayloadCommand,
        received_at: datetime,
    ) -> CreateCustomerPoCommand:
        return CreateCustomerPoCommand(
            customer_id=customer.id,
            customer_po_number=document.po_number,
            customer_po_date=document.po_date,
            received_at=received_at,
            currency_code=customer.currency_code,
            payment_term_id=customer.payment_term_id,
            ship_to_name=document.ship_to_name,
            source=CustomerPoSource.EDI,
            lines=tuple(
                CustomerPoLineCommand(
                    line_number=line.line_number,
                    customer_item_number=line.item,
                    ordered_quantity=line.quantity,
                    unit_of_measure=line.uom,
                    unit_price=line.unit_price,
                    currency_code=customer.currency_code,
                )
                for line in document.lines
            ),
            edi_transaction_type=envelope.document_type,
            edi_sender_id=envelope.sender_id,
            edi_receiver_id=envelope.receiver_id,
            edi_received_at=received_at,
            external_message_id=envelope.external_message_id,
        )

    @classmethod
    def _parse(cls, payload: dict[str, Any]) -> InboundCustomerPoDocument:
        customer = cls._required_text(payload, "customer")
        po_number = cls._required_text(payload, "poNumber")
        try:
            po_date = date.fromisoformat(cls._required_text(payload, "poDate"))
        except ValueError as exc:
            raise ValidationFailure("Invalid EDI poDate", details={"field": "poDate"}) from exc
        raw_lines = payload.get("lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            raise ValidationFailure(
                "EDI document requires at least one line", details={"field": "lines"}
            )
        lines = tuple(cls._parse_line(value, index + 1) for index, value in enumerate(raw_lines))
        if len({line.line_number for line in lines}) != len(lines):
            raise ValidationFailure("Duplicate EDI line number", details={"field": "lineNumber"})
        return InboundCustomerPoDocument(
            customer.upper(),
            po_number,
            po_date,
            cls._optional_text(payload.get("shipTo")),
            cls._optional_text(payload.get("purposeCode")),
            lines,
        )

    @classmethod
    def _parse_line(cls, value: Any, row: int) -> InboundCustomerPoLine:
        if not isinstance(value, dict):
            raise ValidationFailure("Invalid EDI line", details={"row": row})
        try:
            line_number = int(cls._required_text(value, "lineNumber"))
            quantity = cls._decimal(value.get("quantity"), "quantity", row)
            unit_price = (
                cls._decimal(value["unitPrice"], "unitPrice", row)
                if value.get("unitPrice") is not None
                else None
            )
        except (TypeError, ValueError) as exc:
            raise ValidationFailure("Invalid EDI line value", details={"row": row}) from exc
        if line_number < 1 or quantity <= 0 or (unit_price is not None and unit_price < 0):
            raise ValidationFailure("Invalid EDI line value", details={"row": row})
        return InboundCustomerPoLine(
            line_number,
            cls._required_text(value, "item"),
            cls._optional_text(value.get("itemQualifier")),
            quantity,
            cls._optional_text(value.get("uom"), upper=True),
            unit_price,
        )

    @staticmethod
    def _decimal(value: Any, field: str, row: int) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationFailure(
                "Invalid EDI decimal", details={"field": field, "row": row}
            ) from exc

    @staticmethod
    def _required_text(value: dict[str, Any], field: str) -> str:
        result = ReceiveRestEdiPayload._optional_text(value.get(field))
        if not result:
            raise ValidationFailure("Missing EDI field", details={"field": field})
        return result

    @staticmethod
    def _optional_text(value: Any, *, upper: bool = False) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result.upper() if result and upper else result or None

    @staticmethod
    def _log_received(command: ReceiveRestEdiPayloadCommand) -> None:
        logger.info(
            "REST EDI inbound payload received sender_id=%s receiver_id=%s document_type=%s "
            "external_message_id=%s source_protocol=REST payload=%s",
            command.sender_id,
            command.receiver_id,
            command.document_type,
            command.external_message_id,
            sanitize_log_data(command.payload),
            extra={
                "business_module": "edi",
                "sender_id": command.sender_id,
                "receiver_id": command.receiver_id,
                "document_type": command.document_type,
                "external_message_id": command.external_message_id,
                "source_protocol": "REST",
                "payload": command.payload,
            },
        )
