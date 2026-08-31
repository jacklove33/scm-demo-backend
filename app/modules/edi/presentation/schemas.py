from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.edi.application.receive_rest_payload import (
    InboundCustomerPoDocument,
    InboundCustomerPoLine,
)


class CanonicalCustomerPoLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    line_number: int = Field(alias="lineNumber", ge=1)
    item: str = Field(min_length=1, max_length=100)
    item_qualifier: str | None = Field(None, alias="itemQualifier", max_length=30)
    quantity: Decimal = Field(gt=0)
    uom: str | None = Field(None, max_length=20)
    unit_price: Decimal | None = Field(None, alias="unitPrice", ge=0)

    def to_document_line(self) -> InboundCustomerPoLine:
        return InboundCustomerPoLine(
            line_number=self.line_number,
            item=self.item.strip(),
            item_qualifier=self.item_qualifier.strip() if self.item_qualifier else None,
            quantity=self.quantity,
            uom=self.uom.strip().upper() if self.uom else None,
            unit_price=self.unit_price,
        )


class RestEdiPayloadRequest(BaseModel):
    """Canonical Customer PO contract produced by the upstream B2B platform."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    customer: str = Field(min_length=1, max_length=20)
    po_number: str = Field(alias="poNumber", min_length=1, max_length=100)
    po_date: date = Field(alias="poDate")
    purpose_code: str | None = Field(None, alias="purposeCode", max_length=30)
    ship_to: str | None = Field(None, alias="shipTo", max_length=240)
    lines: list[CanonicalCustomerPoLineRequest] = Field(min_length=1, max_length=1000)

    def to_document(self) -> InboundCustomerPoDocument:
        return InboundCustomerPoDocument(
            customer_code=self.customer.strip().upper(),
            po_number=self.po_number.strip(),
            po_date=self.po_date,
            ship_to_name=self.ship_to.strip() if self.ship_to else None,
            purpose_code=self.purpose_code.strip() if self.purpose_code else None,
            lines=tuple(line.to_document_line() for line in self.lines),
        )


class RestEdiReceiptResponse(BaseModel):
    status: str
    sender_id: str
    receiver_id: str
    document_type: str
    external_message_id: str | None
    customer_po_id: UUID
    edi_message_id: UUID
