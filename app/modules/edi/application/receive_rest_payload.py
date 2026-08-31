import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.core.exceptions import AppError, EntityConflict, ValidationFailure
from app.core.logging import sanitize_log_data
from app.modules.audit.domain.entities import AuditContext
from app.modules.customer_pos.application.commands import (
    CreateCustomerPoCommand,
    CustomerPoLineCommand,
)
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customer_pos.domain.enums import CustomerPoSource
from app.modules.customers.domain.entities import Customer
from app.modules.edi.application.tracker import EdiMessageTracker
from app.modules.edi.domain.enums import EdiMessageDirection, EdiRelatedEntityType
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
    document: InboundCustomerPoDocument
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RestEdiReceipt:
    sender_id: str
    receiver_id: str
    document_type: str
    external_message_id: str | None
    customer_po_id: UUID
    edi_message_id: UUID


class ReceiveRestEdiPayload:
    """Map a canonical REST EDI document through the Customer PO application boundary."""

    def __init__(
        self,
        customer_repository: EdiCustomerResolver,
        customer_po_use_cases: CustomerPoUseCases,
        tracker: EdiMessageTracker,
    ) -> None:
        self.customer_repository = customer_repository
        self.customer_po_use_cases = customer_po_use_cases
        self.tracker = tracker

    async def execute(
        self,
        command: ReceiveRestEdiPayloadCommand,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> RestEdiReceipt:
        self._log_received(command)
        message, duplicate = await self.tracker.create_received(
            tenant_id=actor.tenant_id,
            direction=EdiMessageDirection.INBOUND,
            source_system="DIRECT_API",
            source_protocol="REST",
            document_standard="JSON",
            document_type=command.document_type,
            sender_id=command.sender_id,
            receiver_id=command.receiver_id,
            external_message_id=command.external_message_id,
            correlation_id=audit_context.correlation_id,
        )
        if duplicate:
            if message.related_entity_id is None:
                raise EntityConflict("Duplicate EDI message is not linked to a business document")
            self._log_duplicate(command, message.related_entity_id)
            return self._receipt(command, message.related_entity_id, message.id)
        message = await self.tracker.start_validation(message)
        try:
            document, customer = await self._validate_and_resolve(command, actor)
        except ValidationFailure as error:
            await self.tracker.validation_failed(
                message,
                str(error.details.get("error_code", error.code)),
                error.message,
                error.details,
            )
            raise
        message = await self.tracker.validation_passed(message)
        message = await self.tracker.start_processing(message)
        received_at = datetime.now(UTC)
        po_command = self._to_customer_po_command(
            document, customer, command, received_at, message.id
        )
        try:
            created, _capabilities = await self.customer_po_use_cases.create(
                po_command, actor, audit_context
            )
        except AppError as error:
            await self.tracker.failed(message, error.code, error.message, error.details)
            raise
        except Exception as error:
            await self.tracker.failed(message, "EDI_PROCESSING_FAILED", str(error))
            raise
        message = await self.tracker.link_related_entity(
            message,
            EdiRelatedEntityType.CUSTOMER_PO,
            created.id,
            created.customer_po_number,
        )
        await self.tracker.completed(message)
        return self._receipt(command, created.id, message.id)

    async def _validate_and_resolve(
        self, command: ReceiveRestEdiPayloadCommand, actor: CurrentUser
    ) -> tuple[InboundCustomerPoDocument, Customer]:
        if command.document_type.strip() != "850":
            raise ValidationFailure(
                "Unsupported EDI document type",
                details={
                    "error_code": "EDI_DOCUMENT_TYPE_UNSUPPORTED",
                    "document_type": command.document_type,
                    "supported_document_types": ["850"],
                },
            )
        document = command.document
        self._validate_document(document)
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
        return document, customer

    @staticmethod
    def _receipt(
        command: ReceiveRestEdiPayloadCommand, customer_po_id: UUID, edi_message_id: UUID
    ) -> RestEdiReceipt:
        return RestEdiReceipt(
            command.sender_id,
            command.receiver_id,
            command.document_type,
            command.external_message_id,
            customer_po_id,
            edi_message_id,
        )

    @staticmethod
    def _to_customer_po_command(
        document: InboundCustomerPoDocument,
        customer: Customer,
        envelope: ReceiveRestEdiPayloadCommand,
        received_at: datetime,
        edi_message_id: UUID,
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
            edi_message_id=edi_message_id,
            edi_transaction_type=envelope.document_type,
            edi_sender_id=envelope.sender_id,
            edi_receiver_id=envelope.receiver_id,
            edi_received_at=received_at,
            external_message_id=envelope.external_message_id,
            source_document_hash=ReceiveRestEdiPayload._document_hash(envelope.raw_payload),
        )

    @staticmethod
    def _validate_document(document: InboundCustomerPoDocument) -> None:
        if len({line.line_number for line in document.lines}) != len(document.lines):
            raise ValidationFailure("Duplicate EDI line number", details={"field": "lineNumber"})

    @staticmethod
    def _document_hash(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(serialized.encode()).hexdigest()

    @staticmethod
    def _log_received(command: ReceiveRestEdiPayloadCommand) -> None:
        logger.info(
            "REST EDI inbound payload received sender_id=%s receiver_id=%s document_type=%s "
            "external_message_id=%s source_protocol=REST payload=%s",
            command.sender_id,
            command.receiver_id,
            command.document_type,
            command.external_message_id,
            sanitize_log_data(command.raw_payload),
            extra={
                "business_module": "edi",
                "sender_id": command.sender_id,
                "receiver_id": command.receiver_id,
                "document_type": command.document_type,
                "external_message_id": command.external_message_id,
                "source_protocol": "REST",
                "payload": command.raw_payload,
            },
        )

    @staticmethod
    def _log_duplicate(command: ReceiveRestEdiPayloadCommand, customer_po_id: UUID) -> None:
        logger.info(
            "Duplicate REST EDI delivery detected",
            extra={
                "business_module": "edi",
                "sender_id": command.sender_id,
                "receiver_id": command.receiver_id,
                "document_type": command.document_type,
                "external_message_id": command.external_message_id,
                "customer_po_id": str(customer_po_id),
                "source_protocol": "REST",
            },
        )
