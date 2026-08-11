from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_at", desc("occurred_at")),
        Index("ix_audit_events_actor_occurred", "actor_user_id", desc("occurred_at")),
        Index(
            "ix_audit_events_entity_id_occurred", "entity_type", "entity_id", desc("occurred_at")
        ),
        Index(
            "ix_audit_events_entity_code_occurred",
            "entity_type",
            "entity_code",
            desc("occurred_at"),
        ),
        Index("ix_audit_events_module_occurred", "module", desc("occurred_at")),
        Index("ix_audit_events_action_occurred", "action", desc("occurred_at")),
        Index("ix_audit_events_correlation_id", "correlation_id"),
        Index("ix_audit_events_batch_id", "batch_id"),
        Index("ix_audit_events_status_occurred", "status", desc("occurred_at")),
        Index("ix_audit_events_tenant_occurred", "tenant_id", desc("occurred_at")),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    actor_email: Mapped[str | None] = mapped_column(String(255))
    actor_display_name: Mapped[str | None] = mapped_column(String(255))
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False, default="USER")
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    entity_code: Mapped[str | None] = mapped_column(String(100))
    entity_display_name: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    request_id: Mapped[str | None] = mapped_column(String(100))
    request_method: Mapped[str | None] = mapped_column(String(10))
    request_path: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    batch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    changes: Mapped[list["AuditChangeModel"]] = relationship(
        lazy="selectin", order_by="AuditChangeModel.sequence_no"
    )


class AuditChangeModel(Base):
    __tablename__ = "audit_changes"
    __table_args__ = (
        UniqueConstraint("audit_event_id", "sequence_no", name="uq_audit_changes_event_sequence"),
        Index("ix_audit_changes_event_sequence", "audit_event_id", "sequence_no"),
        Index("ix_audit_changes_field_path", "field_path"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    audit_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("audit_events.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    field_path: Mapped[str] = mapped_column(String(500), nullable=False)
    field_label: Mapped[str | None] = mapped_column(String(255))
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value_type: Mapped[str | None] = mapped_column(String(30))
    old_value: Mapped[object | None] = mapped_column(JSONB)
    new_value: Mapped[object | None] = mapped_column(JSONB)
    old_display_value: Mapped[str | None] = mapped_column(Text)
    new_display_value: Mapped[str | None] = mapped_column(Text)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
