"""Add generic private attachment metadata.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ENTITY_TYPES = (
    "'CUSTOMER','CUSTOMER_PO','SALES_ORDER','PURCHASE_ORDER','SHIPMENT','SUPPLIER','PRODUCT'"
)


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255)),
        sa.Column("content_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_provider", sa.String(20), nullable=False, server_default="S3"),
        sa.Column("bucket_name", sa.String(255), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
        ),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "deleted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
        ),
        sa.CheckConstraint(f"entity_type IN ({ENTITY_TYPES})", name="ck_attachments_entity_type"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_attachments_size_nonnegative"),
        sa.CheckConstraint("storage_provider = 'S3'", name="ck_attachments_storage_provider"),
        sa.UniqueConstraint("object_key", name="uq_attachments_object_key"),
    )
    op.create_index(
        "ix_attachments_tenant_entity_created",
        "attachments",
        ["tenant_id", "entity_type", "entity_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_attachments_tenant_deleted", "attachments", ["tenant_id", "deleted_at"])
    op.execute("ALTER TABLE attachments ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY attachments_tenant_isolation ON attachments "
        "USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
            GRANT SELECT, INSERT, UPDATE ON attachments TO app_runtime;
            REVOKE DELETE, TRUNCATE ON attachments FROM app_runtime;
          END IF;
        END $$
    """)


def downgrade() -> None:
    op.drop_table("attachments")
