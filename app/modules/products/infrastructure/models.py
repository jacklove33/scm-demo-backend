from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "product_code", name="uq_products_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id_id"),
        Index("ix_products_tenant_name", "tenant_id", "product_name"),
        Index("ix_products_tenant_type_status", "tenant_id", "product_type", "status"),
        Index("ix_products_tenant_category", "tenant_id", "category"),
        Index("ix_products_tenant_owner", "tenant_id", "owner_user_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    product_code: Mapped[str] = mapped_column(String(100), nullable=False)
    product_name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    base_uom: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    barcode: Mapped[str | None] = mapped_column(String(100))
    country_of_origin: Mapped[str | None] = mapped_column(String(2))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    weight_uom: Mapped[str | None] = mapped_column(String(20))
    length: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    width: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    height: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    dimension_uom: Mapped[str | None] = mapped_column(String(20))
    default_currency_code: Mapped[str | None] = mapped_column(String(3))
    standard_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    list_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    owner_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id")
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False
    )
    updated_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(default=1, nullable=False)


class ProductUserAssignmentModel(Base):
    __tablename__ = "product_user_assignments"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id"), primary_key=True
    )


class ProductGroupAssignmentModel(Base):
    __tablename__ = "product_group_assignments"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
