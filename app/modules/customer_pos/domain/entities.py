from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.modules.customer_pos.domain.enums import (
    CustomerPoSource,
    CustomerPoStatus,
    CustomerPoStatusEventType,
)


@dataclass(frozen=True, slots=True)
class CustomerPoLine:
    id: UUID
    line_number: int
    customer_line_number: str | None
    customer_item_number: str | None
    product_id: UUID | None
    internal_item_number: str | None
    item_description: str | None
    ordered_quantity: Decimal
    unit_of_measure: str | None
    unit_price: Decimal | None
    line_amount: Decimal | None
    currency_code: str | None
    requested_ship_date: date | None
    requested_delivery_date: date | None
    ship_to_code: str | None
    status: str | None
    customer_notes: str | None
    edi_line_reference: str | None
    row_version: int = 1


@dataclass(frozen=True, slots=True)
class CustomerPurchaseOrder:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_po_number: str
    customer_po_revision: str | None
    customer_po_date: date | None
    received_at: datetime | None
    requested_ship_date: date | None
    requested_delivery_date: date | None
    currency_code: str | None
    payment_term_id: UUID | None
    ship_to_code: str | None
    bill_to_code: str | None
    ship_to_name: str | None
    ship_to_address1: str | None
    ship_to_address2: str | None
    ship_to_city: str | None
    ship_to_state: str | None
    ship_to_postal_code: str | None
    ship_to_country_code: str | None
    customer_contact_name: str | None
    customer_contact_email: str | None
    buyer_name: str | None
    buyer_email: str | None
    customer_notes: str | None
    internal_notes: str | None
    status: CustomerPoStatus
    source: CustomerPoSource
    owner_user_id: UUID | None
    total_amount: Decimal | None
    row_version: int
    deleted_at: datetime | None
    deleted_by: UUID | None
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None
    updated_by: UUID | None
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
    sales_order_id: UUID | None = None
    conversion_status: str | None = None
    converted_at: datetime | None = None
    lines: tuple[CustomerPoLine, ...] = ()
    customer_code: str | None = None
    customer_name: str | None = None
    owner_display_name: str | None = None


@dataclass(frozen=True, slots=True)
class CustomerPoStatusEvent:
    id: UUID
    tenant_id: UUID
    customer_po_id: UUID
    from_status: CustomerPoStatus | None
    to_status: CustomerPoStatus
    event_type: CustomerPoStatusEventType
    reason: str | None
    actor_user_id: UUID | None
    source: CustomerPoSource
    correlation_id: str | None
    edi_log_id: UUID | None
    metadata: dict[str, object]
    occurred_at: datetime
