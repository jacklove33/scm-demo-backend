from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class PaymentTermModel(Base):
    __tablename__ = "payment_terms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_payment_terms_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_payment_terms_tenant_id_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BusinessPartnerModel(Base):
    __tablename__ = "business_partners"
    __table_args__ = (
        UniqueConstraint("tenant_id", "partner_code", name="uq_business_partners_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_business_partners_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "payment_term_id"],
            ["payment_terms.tenant_id", "payment_terms.id"],
            name="fk_business_partners_tenant_payment_term",
        ),
        Index("ix_business_partners_tenant_owner", "tenant_id", "owner_user_id"),
        Index("ix_business_partners_tenant_status", "tenant_id", "status", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    partner_code: Mapped[str] = mapped_column(String(20), nullable=False)
    partner_name: Mapped[str] = mapped_column(String(240), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(80))
    country_code: Mapped[str | None] = mapped_column(String(2))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    payment_term_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    owner_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id")
    )
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("profiles.id"))
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    addresses: Mapped[list["PartnerAddressModel"]] = relationship(lazy="selectin")


class PartnerRoleModel(Base):
    __tablename__ = "partner_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "partner_id"],
            ["business_partners.tenant_id", "business_partners.id"],
            name="fk_partner_roles_tenant_partner",
        ),
        UniqueConstraint(
            "tenant_id", "partner_id", "role_type", name="uq_partner_roles_partner_type"
        ),
        Index("ix_partner_roles_tenant_type_partner", "tenant_id", "role_type", "partner_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    partner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role_type: Mapped[str] = mapped_column(String(30), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PartnerAddressModel(Base):
    __tablename__ = "partner_addresses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "partner_id"],
            ["business_partners.tenant_id", "business_partners.id"],
            name="fk_partner_addresses_tenant_partner",
        ),
        UniqueConstraint(
            "tenant_id", "partner_id", "address_code", name="uq_partner_addresses_partner_code"
        ),
        Index(
            "ix_partner_addresses_tenant_partner_type", "tenant_id", "partner_id", "address_type"
        ),
        Index(
            "ix_partner_addresses_tenant_partner_default", "tenant_id", "partner_id", "is_default"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    partner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    address_code: Mapped[str] = mapped_column(String(40), nullable=False)
    address_type: Mapped[str] = mapped_column(String(30), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(160))
    address1: Mapped[str | None] = mapped_column(String(240))
    address2: Mapped[str | None] = mapped_column(String(240))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(30))
    country_code: Mapped[str | None] = mapped_column(String(2))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CustomerUserAssignmentModel(Base):
    __tablename__ = "customer_user_assignments"
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_partners.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id"), primary_key=True
    )
    assignment_type: Mapped[str] = mapped_column(String(40), default="MEMBER", nullable=False)


class CustomerGroupAssignmentModel(Base):
    __tablename__ = "customer_group_assignments"
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_partners.id"), primary_key=True
    )
    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
