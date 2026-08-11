from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoleModel(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GroupModel(Base):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_groups_tenant_code"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProfileModel(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    primary_role_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    locale: Mapped[str] = mapped_column(String(20), default="zh-TW", nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Taipei", nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserGroupModel(Base):
    __tablename__ = "user_groups"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id"), primary_key=True
    )
    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PermissionModel(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class PolicyModel(Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_policies_tenant_code"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"))
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PolicyPermissionModel(Base):
    __tablename__ = "policy_permissions"

    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policies.id"), primary_key=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True
    )
    effect: Mapped[str] = mapped_column(String(10), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(20))


class RolePolicyModel(Base):
    __tablename__ = "role_policies"

    role_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True
    )
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policies.id"), primary_key=True
    )


class GroupPolicyModel(Base):
    __tablename__ = "group_policies"

    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policies.id"), primary_key=True
    )


class UserPolicyModel(Base):
    __tablename__ = "user_policies"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id"), primary_key=True
    )
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policies.id"), primary_key=True
    )


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id")
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    before_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    after_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
