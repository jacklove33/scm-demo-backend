"""Add append-only Customer PO event timeline.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_po_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_po_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("event_category", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
        ),
        sa.Column("actor_display_name", sa.String(160)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("correlation_id", sa.String(100)),
        sa.Column("request_id", sa.String(100)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_po_id"],
            ["customer_purchase_orders.tenant_id", "customer_purchase_orders.id"],
            name="fk_customer_po_events_tenant_po",
        ),
        sa.CheckConstraint(
            "event_type IN ('CREATE','UPDATE','STATUS_CHANGE','SOFT_DELETE','RESTORE',"
            "'EMAIL_SENT','PO_SENT','ATTACHMENT_UPLOADED','ATTACHMENT_DELETED','NOTE_ADDED',"
            "'EDI_RECEIVED','EDI_PROCESSED','CONVERTED')",
            name="ck_customer_po_events_type",
        ),
        sa.CheckConstraint(
            "event_category IN "
            "('GENERAL','WORKFLOW','COMMUNICATION','DOCUMENT','EDI','CONVERSION')",
            name="ck_customer_po_events_category",
        ),
        sa.CheckConstraint(
            "actor_type IN ('USER','SYSTEM','API_CLIENT')",
            name="ck_customer_po_events_actor_type",
        ),
        sa.CheckConstraint(
            "source IN ('API','EDI','SYSTEM','IMPORT','JOB','UI','ADMIN')",
            name="ck_customer_po_events_source",
        ),
    )
    op.create_index(
        "ix_customer_po_events_tenant_po_time",
        "customer_po_events",
        ["tenant_id", "customer_po_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_customer_po_events_tenant_type",
        "customer_po_events",
        ["tenant_id", "event_type"],
    )
    op.create_index(
        "ix_customer_po_events_tenant_category",
        "customer_po_events",
        ["tenant_id", "event_category"],
    )
    op.execute("ALTER TABLE customer_po_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY customer_po_events_tenant_isolation ON customer_po_events "
        "USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON customer_po_events FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
            GRANT SELECT, INSERT ON customer_po_events TO app_runtime;
            REVOKE UPDATE, DELETE, TRUNCATE ON customer_po_events FROM app_runtime;
          END IF;
        END $$
    """)


def downgrade() -> None:
    op.drop_table("customer_po_events")
