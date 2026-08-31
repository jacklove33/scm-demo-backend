"""Add protocol-neutral ERP EDI message tracking.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

ADMIN_POLICY_ID = "30000000-0000-0000-0000-000000000001"
PERMISSIONS = (
    ("50000000-0000-0000-0000-000000000043", "edi_messages.read", "read"),
    ("50000000-0000-0000-0000-000000000044", "edi_messages.detail.read", "detail.read"),
)


def upgrade() -> None:
    op.create_table(
        "edi_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_protocol", sa.String(30), nullable=False),
        sa.Column("document_standard", sa.String(30), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("sender_id", sa.String(100), nullable=False),
        sa.Column("receiver_id", sa.String(100), nullable=False),
        sa.Column("external_message_id", sa.String(160)),
        sa.Column("correlation_id", sa.String(100)),
        sa.Column("business_document_number", sa.String(160)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("related_entity_type", sa.String(40)),
        sa.Column("related_entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_edi_messages_tenant_id_id"),
        sa.CheckConstraint("direction IN ('INBOUND','OUTBOUND')", name="ck_edi_messages_direction"),
        sa.CheckConstraint(
            "status IN ('RECEIVED','VALIDATING','VALIDATED','PROCESSING','COMPLETED',"
            "'VALIDATION_FAILED','FAILED','DUPLICATE','CANCELLED')",
            name="ck_edi_messages_status",
        ),
    )
    for name, columns in (
        ("ix_edi_messages_tenant_direction", ["tenant_id", "direction"]),
        ("ix_edi_messages_tenant_status", ["tenant_id", "status"]),
        ("ix_edi_messages_tenant_document_type", ["tenant_id", "document_type"]),
        ("ix_edi_messages_tenant_sender", ["tenant_id", "sender_id"]),
        ("ix_edi_messages_tenant_receiver", ["tenant_id", "receiver_id"]),
        ("ix_edi_messages_tenant_business_number", ["tenant_id", "business_document_number"]),
        (
            "ix_edi_messages_tenant_related",
            ["tenant_id", "related_entity_type", "related_entity_id"],
        ),
        ("ix_edi_messages_tenant_created", ["tenant_id", "created_at"]),
    ):
        op.create_index(name, "edi_messages", columns)
    op.create_index(
        "uq_edi_messages_external_identity",
        "edi_messages",
        ["tenant_id", "direction", "external_message_id"],
        unique=True,
        postgresql_where=sa.text("external_message_id IS NOT NULL"),
    )
    op.create_table(
        "edi_message_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("edi_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("status_from", sa.String(30)),
        sa.Column("status_to", sa.String(30)),
        sa.Column("message", sa.Text()),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_details", postgresql.JSONB()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "edi_message_id"],
            ["edi_messages.tenant_id", "edi_messages.id"],
            name="fk_edi_message_events_tenant_message",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_edi_message_events_tenant_message_time",
        "edi_message_events",
        ["tenant_id", "edi_message_id", "created_at"],
    )
    op.execute("""
        INSERT INTO edi_messages
            (id, tenant_id, direction, source_system, source_protocol,
             document_standard, document_type, sender_id, receiver_id,
             external_message_id, business_document_number, status,
             related_entity_type, related_entity_id, received_at, processed_at,
             created_at, updated_at)
        SELECT DISTINCT ON (po.edi_log_id)
             po.edi_log_id, po.tenant_id, 'INBOUND', 'LEGACY', 'INTERNAL',
             COALESCE(po.edi_standard, 'OTHER'),
             COALESCE(po.edi_transaction_type, 'UNKNOWN'),
             COALESCE(po.edi_sender_id, 'UNKNOWN'),
             COALESCE(po.edi_receiver_id, 'UNKNOWN'), po.external_message_id,
             po.customer_po_number, 'COMPLETED', 'CUSTOMER_PO', po.id,
             po.edi_received_at, po.created_at, po.created_at, po.updated_at
        FROM customer_purchase_orders po WHERE po.edi_log_id IS NOT NULL
        ORDER BY po.edi_log_id, po.created_at ON CONFLICT (id) DO NOTHING
    """)
    op.drop_index("ix_customer_pos_edi_log_id", table_name="customer_purchase_orders")
    op.alter_column("customer_purchase_orders", "edi_log_id", new_column_name="edi_message_id")
    op.alter_column("customer_po_status_events", "edi_log_id", new_column_name="edi_message_id")
    op.create_index(
        "ix_customer_pos_edi_message_id", "customer_purchase_orders", ["edi_message_id"]
    )
    op.create_foreign_key(
        "fk_customer_pos_edi_message",
        "customer_purchase_orders",
        "edi_messages",
        ["edi_message_id"],
        ["id"],
    )
    tenant_policy = (
        "USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    for table in ("edi_messages", "edi_message_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} {tenant_policy}")
    op.execute("""
        DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_runtime') THEN
          GRANT SELECT, INSERT, UPDATE ON edi_messages TO app_runtime;
          GRANT SELECT, INSERT ON edi_message_events TO app_runtime;
        END IF; END $$
    """)
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("description", sa.Text()),
    )
    mappings = sa.table(
        "policy_permissions",
        sa.column("policy_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
        sa.column("effect", sa.String()),
        sa.column("scope", sa.String()),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "id": id_,
                "code": code,
                "resource": "edi_messages",
                "action": action,
                "description": f"EDI messages {action}",
            }
            for id_, code, action in PERMISSIONS
        ],
    )
    op.bulk_insert(
        mappings,
        [
            {"policy_id": ADMIN_POLICY_ID, "permission_id": id_, "effect": "ALLOW", "scope": "ALL"}
            for id_, _code, _action in PERMISSIONS
        ],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for permission_id, _code, _action in PERMISSIONS:
        connection.execute(
            sa.text(
                "DELETE FROM policy_permissions "
                "WHERE policy_id=:policy AND permission_id=:permission"
            ),
            {"policy": ADMIN_POLICY_ID, "permission": permission_id},
        )
        connection.execute(
            sa.text("DELETE FROM permissions WHERE id=:permission"), {"permission": permission_id}
        )
    op.drop_constraint(
        "fk_customer_pos_edi_message", "customer_purchase_orders", type_="foreignkey"
    )
    op.drop_index("ix_customer_pos_edi_message_id", table_name="customer_purchase_orders")
    op.alter_column("customer_po_status_events", "edi_message_id", new_column_name="edi_log_id")
    op.alter_column("customer_purchase_orders", "edi_message_id", new_column_name="edi_log_id")
    op.create_index("ix_customer_pos_edi_log_id", "customer_purchase_orders", ["edi_log_id"])
    op.drop_table("edi_message_events")
    op.drop_table("edi_messages")
