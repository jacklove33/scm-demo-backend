from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.modules.customer_pos.domain.enums import CustomerPoSource, CustomerPoStatus


@dataclass(frozen=True, slots=True)
class CustomerPoLineCommand:
    line_number: int
    ordered_quantity: Decimal
    id: UUID | None = None
    customer_line_number: str | None = None
    customer_item_number: str | None = None
    product_id: UUID | None = None
    internal_item_number: str | None = None
    item_description: str | None = None
    unit_of_measure: str | None = None
    unit_price: Decimal | None = None
    currency_code: str | None = None
    requested_ship_date: date | None = None
    requested_delivery_date: date | None = None
    ship_to_code: str | None = None
    status: str | None = None
    customer_notes: str | None = None
    edi_line_reference: str | None = None


@dataclass(frozen=True, slots=True)
class CustomerPoFields:
    requested_ship_date: date | None = None
    requested_delivery_date: date | None = None
    currency_code: str | None = None
    payment_term_id: UUID | None = None
    ship_to_code: str | None = None
    bill_to_code: str | None = None
    ship_to_name: str | None = None
    ship_to_address1: str | None = None
    ship_to_address2: str | None = None
    ship_to_city: str | None = None
    ship_to_state: str | None = None
    ship_to_postal_code: str | None = None
    ship_to_country_code: str | None = None
    customer_contact_name: str | None = None
    customer_contact_email: str | None = None
    buyer_name: str | None = None
    buyer_email: str | None = None
    customer_notes: str | None = None
    internal_notes: str | None = None
    owner_user_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CreateCustomerPoCommand(CustomerPoFields):
    customer_id: UUID = UUID(int=0)
    customer_po_number: str = ""
    customer_po_revision: str | None = None
    customer_po_date: date | None = None
    received_at: datetime | None = None
    source: CustomerPoSource = CustomerPoSource.MANUAL
    lines: tuple[CustomerPoLineCommand, ...] = ()
    edi_log_id: UUID | None = None
    edi_transaction_type: str | None = None
    edi_standard: str | None = None
    edi_version: str | None = None
    edi_sender_id: str | None = None
    edi_receiver_id: str | None = None
    edi_interchange_control_number: str | None = None
    edi_group_control_number: str | None = None
    edi_transaction_control_number: str | None = None
    edi_document_id: str | None = None
    edi_received_at: datetime | None = None
    external_message_id: str | None = None
    source_document_hash: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateCustomerPoCommand(CustomerPoFields):
    customer_po_id: UUID = UUID(int=0)
    expected_version: int = 1
    lines: tuple[CustomerPoLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class ChangeCustomerPoStatusCommand:
    customer_po_id: UUID
    expected_version: int
    status: CustomerPoStatus
    reason: str | None = None
