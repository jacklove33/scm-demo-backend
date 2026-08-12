from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class CustomerPoModel(Base):
    __tablename__ = "customer_purchase_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["business_partners.tenant_id", "business_partners.id"],
            name="fk_customer_pos_tenant_customer",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "payment_term_id"],
            ["payment_terms.tenant_id", "payment_terms.id"],
            name="fk_customer_pos_tenant_payment_term",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_customer_pos_tenant_id_id"),
        Index("ix_customer_pos_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_customer_pos_tenant_number", "tenant_id", "customer_po_number"),
        Index("ix_customer_pos_tenant_status", "tenant_id", "status", "deleted_at"),
        Index("ix_customer_pos_tenant_owner", "tenant_id", "owner_user_id"),
        Index("ix_customer_pos_tenant_source", "tenant_id", "source"),
        Index("ix_customer_pos_tenant_po_date", "tenant_id", "customer_po_date"),
        Index("ix_customer_pos_tenant_delivery", "tenant_id", "requested_delivery_date"),
        Index("ix_customer_pos_edi_log_id", "edi_log_id"),
        Index("ix_customer_pos_sales_order_id", "sales_order_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_po_number: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_po_revision: Mapped[str | None] = mapped_column(String(50))
    customer_po_date: Mapped[date | None] = mapped_column(Date)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ship_date: Mapped[date | None] = mapped_column(Date)
    requested_delivery_date: Mapped[date | None] = mapped_column(Date)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    payment_term_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    ship_to_code: Mapped[str | None] = mapped_column(String(40))
    bill_to_code: Mapped[str | None] = mapped_column(String(40))
    ship_to_name: Mapped[str | None] = mapped_column(String(240))
    ship_to_address1: Mapped[str | None] = mapped_column(String(240))
    ship_to_address2: Mapped[str | None] = mapped_column(String(240))
    ship_to_city: Mapped[str | None] = mapped_column(String(120))
    ship_to_state: Mapped[str | None] = mapped_column(String(120))
    ship_to_postal_code: Mapped[str | None] = mapped_column(String(30))
    ship_to_country_code: Mapped[str | None] = mapped_column(String(2))
    customer_contact_name: Mapped[str | None] = mapped_column(String(160))
    customer_contact_email: Mapped[str | None] = mapped_column(String(320))
    buyer_name: Mapped[str | None] = mapped_column(String(160))
    buyer_email: Mapped[str | None] = mapped_column(String(320))
    customer_notes: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id")
    )
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("profiles.id"))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("profiles.id"))
    edi_log_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), comment="Reserved for future linkage to EDI transmission/log event"
    )
    edi_transaction_type: Mapped[str | None] = mapped_column(String(30))
    edi_standard: Mapped[str | None] = mapped_column(String(30))
    edi_version: Mapped[str | None] = mapped_column(String(30))
    edi_sender_id: Mapped[str | None] = mapped_column(String(100))
    edi_receiver_id: Mapped[str | None] = mapped_column(String(100))
    edi_interchange_control_number: Mapped[str | None] = mapped_column(String(100))
    edi_group_control_number: Mapped[str | None] = mapped_column(String(100))
    edi_transaction_control_number: Mapped[str | None] = mapped_column(String(100))
    edi_document_id: Mapped[str | None] = mapped_column(String(160))
    edi_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_message_id: Mapped[str | None] = mapped_column(String(160))
    source_document_hash: Mapped[str | None] = mapped_column(String(128))
    sales_order_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    conversion_status: Mapped[str | None] = mapped_column(String(30))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lines: Mapped[list["CustomerPoLineModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CustomerPoLineModel.line_number"
    )


class CustomerPoLineModel(Base):
    __tablename__ = "customer_purchase_order_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_po_id"],
            ["customer_purchase_orders.tenant_id", "customer_purchase_orders.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id", "customer_po_id", "line_number", name="uq_customer_po_lines_number"
        ),
        Index("ix_customer_po_lines_po_number", "customer_po_id", "line_number"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_po_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_line_number: Mapped[str | None] = mapped_column(String(50))
    customer_item_number: Mapped[str | None] = mapped_column(String(100))
    product_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    internal_item_number: Mapped[str | None] = mapped_column(String(100))
    item_description: Mapped[str | None] = mapped_column(String(500))
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_of_measure: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    line_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    requested_ship_date: Mapped[date | None] = mapped_column(Date)
    requested_delivery_date: Mapped[date | None] = mapped_column(Date)
    ship_to_code: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str | None] = mapped_column(String(30))
    customer_notes: Mapped[str | None] = mapped_column(Text)
    edi_line_reference: Mapped[str | None] = mapped_column(String(100))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CustomerPoStatusEventModel(Base):
    __tablename__ = "customer_po_status_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_po_id"],
            ["customer_purchase_orders.tenant_id", "customer_purchase_orders.id"],
            ondelete="CASCADE",
        ),
        Index("ix_customer_po_status_events_po_time", "customer_po_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_po_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    edi_log_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CustomerPoEventModel(Base):
    __tablename__ = "customer_po_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_po_id"],
            ["customer_purchase_orders.tenant_id", "customer_purchase_orders.id"],
            name="fk_customer_po_events_tenant_po",
        ),
        Index(
            "ix_customer_po_events_tenant_po_time",
            "tenant_id",
            "customer_po_id",
            "occurred_at",
        ),
        Index("ix_customer_po_events_tenant_type", "tenant_id", "event_type"),
        Index("ix_customer_po_events_tenant_category", "tenant_id", "event_category"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_po_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    event_category: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    actor_display_name: Mapped[str | None] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    request_id: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
