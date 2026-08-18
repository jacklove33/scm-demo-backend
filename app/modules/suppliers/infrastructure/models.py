from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class SupplierUserAssignmentModel(Base):
    __tablename__ = "supplier_user_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"], ["business_partners.tenant_id", "business_partners.id"]
        ),
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    supplier_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id"), primary_key=True
    )
    assignment_type: Mapped[str] = mapped_column(String(40), default="MEMBER", nullable=False)


class SupplierGroupAssignmentModel(Base):
    __tablename__ = "supplier_group_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"], ["business_partners.tenant_id", "business_partners.id"]
        ),
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    supplier_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
