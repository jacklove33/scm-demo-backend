"""Add Product Master.

Revision ID: 0015
Revises: 0014
"""
# ruff: noqa: E501

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

ADMIN_POLICY_ID = "30000000-0000-0000-0000-000000000001"
PERMISSIONS = (
    ("50000000-0000-0000-0000-000000000035", "products.read", "products", "read"),
    ("50000000-0000-0000-0000-000000000036", "products.detail.read", "products.detail", "read"),
    ("50000000-0000-0000-0000-000000000037", "products.create", "products", "create"),
    ("50000000-0000-0000-0000-000000000038", "products.update", "products", "update"),
    ("50000000-0000-0000-0000-000000000039", "products.delete", "products", "delete"),
    ("50000000-0000-0000-0000-000000000040", "products.restore", "products", "restore"),
    ("50000000-0000-0000-0000-000000000041", "products.assign_owner", "products", "assign_owner"),
    ("50000000-0000-0000-0000-000000000042", "products.export", "products", "export"),
)


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("product_code", sa.String(100), nullable=False),
        sa.Column("product_name", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("product_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("base_uom", sa.String(20), nullable=False),
        sa.Column("category", sa.String(120)),
        sa.Column("brand", sa.String(120)),
        sa.Column("model", sa.String(120)),
        sa.Column("barcode", sa.String(100)),
        sa.Column("country_of_origin", sa.String(2)),
        sa.Column("weight", sa.Numeric(18, 6)),
        sa.Column("weight_uom", sa.String(20)),
        sa.Column("length", sa.Numeric(18, 6)),
        sa.Column("width", sa.Numeric(18, 6)),
        sa.Column("height", sa.Numeric(18, 6)),
        sa.Column("dimension_uom", sa.String(20)),
        sa.Column("default_currency_code", sa.String(3)),
        sa.Column("standard_cost", sa.Numeric(18, 4)),
        sa.Column("list_price", sa.Numeric(18, 4)),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("row_version", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint("tenant_id", "product_code", name="uq_products_tenant_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id_id"),
        sa.CheckConstraint(
            "product_type IN ('FINISHED_GOOD','RAW_MATERIAL','SEMI_FINISHED','PACKAGING','SERVICE','OTHER')",
            name="ck_products_type",
        ),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_products_status"),
        sa.CheckConstraint(
            "standard_cost IS NULL OR standard_cost >= 0", name="ck_products_standard_cost"
        ),
        sa.CheckConstraint("list_price IS NULL OR list_price >= 0", name="ck_products_list_price"),
        sa.CheckConstraint("weight IS NULL OR weight >= 0", name="ck_products_weight"),
        sa.CheckConstraint("length IS NULL OR length >= 0", name="ck_products_length"),
        sa.CheckConstraint("width IS NULL OR width >= 0", name="ck_products_width"),
        sa.CheckConstraint("height IS NULL OR height >= 0", name="ck_products_height"),
    )
    op.create_index("ix_products_tenant_name", "products", ["tenant_id", "product_name"])
    op.create_index(
        "ix_products_tenant_type_status", "products", ["tenant_id", "product_type", "status"]
    )
    op.create_index("ix_products_tenant_category", "products", ["tenant_id", "category"])
    op.create_index("ix_products_tenant_owner", "products", ["tenant_id", "owner_user_id"])
    for table, target in (
        ("product_user_assignments", "profiles.id"),
        ("product_group_assignments", "groups.id"),
    ):
        key = "user_id" if table.startswith("product_user") else "group_id"
        op.create_table(
            table,
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(key, postgresql.UUID(as_uuid=True), sa.ForeignKey(target), nullable=False),
            sa.ForeignKeyConstraint(
                ["tenant_id", "product_id"], ["products.tenant_id", "products.id"]
            ),
            sa.PrimaryKeyConstraint("tenant_id", "product_id", key),
        )
    for table in ("products", "product_user_assignments", "product_group_assignments"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
        )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_runtime') THEN GRANT SELECT, INSERT, UPDATE, DELETE ON products, product_user_assignments, product_group_assignments TO app_runtime; END IF; END $$"
    )
    connection = op.get_bind()
    for permission_id, code, resource, action in PERMISSIONS:
        connection.execute(
            sa.text(
                "INSERT INTO permissions (id, code, resource, action, description) VALUES (:id,:code,:resource,:action,:description) ON CONFLICT (code) DO UPDATE SET resource=EXCLUDED.resource, action=EXCLUDED.action, description=EXCLUDED.description"
            ),
            {
                "id": permission_id,
                "code": code,
                "resource": resource,
                "action": action,
                "description": f"Product {action}",
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO policy_permissions (policy_id, permission_id, effect, scope) SELECT :policy,id,'ALLOW','ALL' FROM permissions WHERE code=:code ON CONFLICT (policy_id, permission_id) DO UPDATE SET effect='ALLOW', scope='ALL'"
            ),
            {"policy": ADMIN_POLICY_ID, "code": code},
        )


def downgrade() -> None:
    connection = op.get_bind()
    for _id, code, _resource, _action in PERMISSIONS:
        connection.execute(
            sa.text(
                "DELETE FROM policy_permissions WHERE policy_id=:policy AND permission_id=(SELECT id FROM permissions WHERE code=:code)"
            ),
            {"policy": ADMIN_POLICY_ID, "code": code},
        )
        connection.execute(sa.text("DELETE FROM permissions WHERE code=:code"), {"code": code})
    op.drop_table("product_group_assignments")
    op.drop_table("product_user_assignments")
    op.drop_table("products")
