from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.audit.domain.entities import JsonValue
from app.modules.customer_pos.application.capabilities import CustomerPoCapabilities
from app.modules.customer_pos.domain.entities import CustomerPoStatusEvent, CustomerPurchaseOrder
from app.modules.customer_pos.domain.enums import CustomerPoSource, CustomerPoStatus
from app.modules.customer_pos.domain.events import (
    CustomerPoEvent,
    CustomerPoEventActorType,
    CustomerPoEventCategory,
    CustomerPoEventSource,
    CustomerPoEventType,
)


class CustomerPoLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID | None = None
    line_number: int = Field(gt=0)
    customer_line_number: str | None = Field(None, max_length=50)
    customer_item_number: str | None = Field(None, max_length=100)
    product_id: UUID | None = None
    internal_item_number: str | None = Field(None, max_length=100)
    item_description: str | None = Field(None, max_length=500)
    ordered_quantity: Decimal = Field(gt=0)
    unit_of_measure: str | None = Field(None, max_length=20)
    unit_price: Decimal | None = Field(None, ge=0)
    currency_code: str | None = Field(None, min_length=3, max_length=3)
    requested_ship_date: date | None = None
    requested_delivery_date: date | None = None
    ship_to_code: str | None = Field(None, max_length=40)
    status: str | None = Field(None, max_length=30)
    customer_notes: str | None = None
    edi_line_reference: str | None = Field(None, max_length=100)


class CustomerPoMutableFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_ship_date: date | None = None
    requested_delivery_date: date | None = None
    currency_code: str | None = Field(None, min_length=3, max_length=3)
    payment_term_id: UUID | None = None
    ship_to_code: str | None = Field(None, max_length=40)
    bill_to_code: str | None = Field(None, max_length=40)
    ship_to_name: str | None = Field(None, max_length=240)
    ship_to_address1: str | None = Field(None, max_length=240)
    ship_to_address2: str | None = Field(None, max_length=240)
    ship_to_city: str | None = Field(None, max_length=120)
    ship_to_state: str | None = Field(None, max_length=120)
    ship_to_postal_code: str | None = Field(None, max_length=30)
    ship_to_country_code: str | None = Field(None, min_length=2, max_length=2)
    customer_contact_name: str | None = Field(None, max_length=160)
    customer_contact_email: str | None = Field(None, max_length=320)
    buyer_name: str | None = Field(None, max_length=160)
    buyer_email: str | None = Field(None, max_length=320)
    customer_notes: str | None = None
    internal_notes: str | None = None
    owner_user_id: UUID | None = None
    lines: list[CustomerPoLineRequest] = Field(min_length=1)

    @field_validator("currency_code", "ship_to_country_code", mode="before")
    @classmethod
    def uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class CreateCustomerPoRequest(CustomerPoMutableFields):
    customer_id: UUID
    customer_po_number: str = Field(min_length=1, max_length=100)
    customer_po_revision: str | None = Field(None, max_length=50)
    customer_po_date: date | None = None
    received_at: datetime | None = None
    source: CustomerPoSource = CustomerPoSource.MANUAL


class UpdateCustomerPoRequest(CustomerPoMutableFields):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class ChangeStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    status: CustomerPoStatus
    reason: str | None = None


class VersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class CustomerPoLineResponse(CustomerPoLineRequest):
    line_amount: Decimal | None
    row_version: int


class CustomerPoResponse(BaseModel):
    id: UUID
    customer_id: UUID
    customer_code: str | None
    customer_name: str | None
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
    owner_display_name: str | None
    total_amount: Decimal | None
    row_version: int
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    edi_log_id: UUID | None
    sales_order_id: UUID | None
    lines: list[CustomerPoLineResponse]
    capabilities: CustomerPoCapabilities

    @classmethod
    def from_domain(
        cls, po: CustomerPurchaseOrder, caps: CustomerPoCapabilities
    ) -> "CustomerPoResponse":
        return cls(
            **{
                name: getattr(po, name)
                for name in cls.model_fields
                if name not in {"lines", "capabilities"}
            },
            lines=[
                CustomerPoLineResponse.model_validate(line, from_attributes=True)
                for line in po.lines
            ],
            capabilities=caps,
        )


class CustomerPoListResponse(BaseModel):
    data: list[CustomerPoResponse]
    meta: dict[str, int]


class StatusEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    from_status: CustomerPoStatus | None
    to_status: CustomerPoStatus
    event_type: str
    reason: str | None
    actor_user_id: UUID | None
    source: CustomerPoSource
    correlation_id: str | None
    occurred_at: datetime

    @classmethod
    def from_domain(cls, event: CustomerPoStatusEvent) -> "StatusEventResponse":
        return cls.model_validate(event, from_attributes=True)


class CustomerPoEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_type: CustomerPoEventType
    event_category: CustomerPoEventCategory
    title: str
    description: str | None
    actor_type: CustomerPoEventActorType
    actor_user_id: UUID | None
    actor_display_name: str | None
    source: CustomerPoEventSource
    correlation_id: str | None
    request_id: str | None
    metadata: dict[str, JsonValue]
    occurred_at: datetime

    @classmethod
    def from_domain(cls, event: CustomerPoEvent) -> "CustomerPoEventResponse":
        return cls.model_validate(event, from_attributes=True)


class CustomerPoEventPageResponse(BaseModel):
    items: list[CustomerPoEventResponse]
    total: int
    page: int
    page_size: int
