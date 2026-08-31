from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class EdiMessageModel(Base):
    __tablename__ = "edi_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_edi_messages_tenant_id_id"),
        Index("ix_edi_messages_tenant_direction", "tenant_id", "direction"),
        Index("ix_edi_messages_tenant_status", "tenant_id", "status"),
        Index("ix_edi_messages_tenant_document_type", "tenant_id", "document_type"),
        Index("ix_edi_messages_tenant_sender", "tenant_id", "sender_id"),
        Index("ix_edi_messages_tenant_receiver", "tenant_id", "receiver_id"),
        Index("ix_edi_messages_tenant_business_number", "tenant_id", "business_document_number"),
        Index(
            "ix_edi_messages_tenant_related",
            "tenant_id",
            "related_entity_type",
            "related_entity_id",
        ),
        Index("ix_edi_messages_tenant_created", "tenant_id", "created_at"),
        Index(
            "uq_edi_messages_external_identity",
            "tenant_id",
            "direction",
            "external_message_id",
            unique=True,
            postgresql_where=text("external_message_id IS NOT NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_protocol: Mapped[str] = mapped_column(String(30), nullable=False)
    document_standard: Mapped[str] = mapped_column(String(30), nullable=False)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(100), nullable=False)
    receiver_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(160))
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    business_document_number: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    related_entity_type: Mapped[str | None] = mapped_column(String(40))
    related_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EdiMessageEventModel(Base):
    __tablename__ = "edi_message_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "edi_message_id"],
            ["edi_messages.tenant_id", "edi_messages.id"],
            name="fk_edi_message_events_tenant_message",
            ondelete="CASCADE",
        ),
        Index(
            "ix_edi_message_events_tenant_message_time", "tenant_id", "edi_message_id", "created_at"
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    edi_message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status_from: Mapped[str | None] = mapped_column(String(30))
    status_to: Mapped[str | None] = mapped_column(String(30))
    message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_details: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
