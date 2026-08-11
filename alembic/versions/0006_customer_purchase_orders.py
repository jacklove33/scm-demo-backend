"""Add Customer Purchase Orders.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ADMIN_POLICY_ID = "30000000-0000-0000-0000-000000000001"
PERMISSIONS = tuple(
    (f"50000000-0000-0000-0000-0000000000{number}", code, action)
    for number, code, action in (
        (17, "customer_pos.read", "read"),
        (18, "customer_pos.detail.read", "detail.read"),
        (19, "customer_pos.create", "create"),
        (20, "customer_pos.update", "update"),
        (21, "customer_pos.delete", "delete"),
        (22, "customer_pos.restore", "restore"),
        (23, "customer_pos.change_status", "change_status"),
        (24, "customer_pos.assign_owner", "assign_owner"),
        (25, "customer_pos.export", "export"),
    )
)


def timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "customer_purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_po_number", sa.String(100), nullable=False),
        sa.Column("customer_po_revision", sa.String(50)),
        sa.Column("customer_po_date", sa.Date()),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("requested_ship_date", sa.Date()),
        sa.Column("requested_delivery_date", sa.Date()),
        sa.Column("currency_code", sa.String(3)),
        sa.Column("payment_term_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ship_to_code", sa.String(40)),
        sa.Column("bill_to_code", sa.String(40)),
        sa.Column("ship_to_name", sa.String(240)),
        sa.Column("ship_to_address1", sa.String(240)),
        sa.Column("ship_to_address2", sa.String(240)),
        sa.Column("ship_to_city", sa.String(120)),
        sa.Column("ship_to_state", sa.String(120)),
        sa.Column("ship_to_postal_code", sa.String(30)),
        sa.Column("ship_to_country_code", sa.String(2)),
        sa.Column("customer_contact_name", sa.String(160)),
        sa.Column("customer_contact_email", sa.String(320)),
        sa.Column("buyer_name", sa.String(160)),
        sa.Column("buyer_email", sa.String(320)),
        sa.Column("customer_notes", sa.Text()),
        sa.Column("internal_notes", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column("total_amount", sa.Numeric(20, 6)),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        *timestamps(),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column(
            "edi_log_id",
            postgresql.UUID(as_uuid=True),
            comment="Reserved for future linkage to EDI transmission/log event",
        ),
        sa.Column("edi_transaction_type", sa.String(30)),
        sa.Column("edi_standard", sa.String(30)),
        sa.Column("edi_version", sa.String(30)),
        sa.Column("edi_sender_id", sa.String(100)),
        sa.Column("edi_receiver_id", sa.String(100)),
        sa.Column("edi_interchange_control_number", sa.String(100)),
        sa.Column("edi_group_control_number", sa.String(100)),
        sa.Column("edi_transaction_control_number", sa.String(100)),
        sa.Column("edi_document_id", sa.String(160)),
        sa.Column("edi_received_at", sa.DateTime(timezone=True)),
        sa.Column("external_message_id", sa.String(160)),
        sa.Column("source_document_hash", sa.String(128)),
        sa.Column("sales_order_id", postgresql.UUID(as_uuid=True)),
        sa.Column("conversion_status", sa.String(30)),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["business_partners.tenant_id", "business_partners.id"],
            name="fk_customer_pos_tenant_customer",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payment_term_id"],
            ["payment_terms.tenant_id", "payment_terms.id"],
            name="fk_customer_pos_tenant_payment_term",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_customer_pos_tenant_id_id"),
        sa.CheckConstraint(
            "source IN ('MANUAL','IMPORT','API','EDI')", name="ck_customer_pos_source"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','RECEIVED','VALIDATING','VALIDATED','PROCESSING',"
            "'ON_HOLD','CONVERTED','REJECTED','CANCELLED')",
            name="ck_customer_pos_status",
        ),
    )
    op.create_index(
        "uq_customer_pos_business_key",
        "customer_purchase_orders",
        [
            "tenant_id",
            "customer_id",
            "customer_po_number",
            sa.text("COALESCE(customer_po_revision, '')"),
        ],
        unique=True,
    )
    for name, columns in (
        ("ix_customer_pos_tenant_customer", ["tenant_id", "customer_id"]),
        ("ix_customer_pos_tenant_number", ["tenant_id", "customer_po_number"]),
        ("ix_customer_pos_tenant_status", ["tenant_id", "status", "deleted_at"]),
        ("ix_customer_pos_tenant_owner", ["tenant_id", "owner_user_id"]),
        ("ix_customer_pos_tenant_source", ["tenant_id", "source"]),
        ("ix_customer_pos_tenant_po_date", ["tenant_id", "customer_po_date"]),
        ("ix_customer_pos_tenant_delivery", ["tenant_id", "requested_delivery_date"]),
        ("ix_customer_pos_edi_log_id", ["edi_log_id"]),
        ("ix_customer_pos_sales_order_id", ["sales_order_id"]),
    ):
        op.create_index(name, "customer_purchase_orders", columns)
    op.create_table(
        "customer_purchase_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_po_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("customer_line_number", sa.String(50)),
        sa.Column("customer_item_number", sa.String(100)),
        sa.Column("product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("internal_item_number", sa.String(100)),
        sa.Column("item_description", sa.String(500)),
        sa.Column("ordered_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit_of_measure", sa.String(20)),
        sa.Column("unit_price", sa.Numeric(20, 6)),
        sa.Column("line_amount", sa.Numeric(20, 6)),
        sa.Column("currency_code", sa.String(3)),
        sa.Column("requested_ship_date", sa.Date()),
        sa.Column("requested_delivery_date", sa.Date()),
        sa.Column("ship_to_code", sa.String(40)),
        sa.Column("status", sa.String(30)),
        sa.Column("customer_notes", sa.Text()),
        sa.Column("edi_line_reference", sa.String(100)),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_po_id"],
            ["customer_purchase_orders.tenant_id", "customer_purchase_orders.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "customer_po_id", "line_number", name="uq_customer_po_lines_number"
        ),
        sa.CheckConstraint("line_number > 0", name="ck_customer_po_lines_number_positive"),
        sa.CheckConstraint("ordered_quantity > 0", name="ck_customer_po_lines_quantity_positive"),
        sa.CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0", name="ck_customer_po_lines_price_nonnegative"
        ),
    )
    op.create_index(
        "ix_customer_po_lines_po_number",
        "customer_purchase_order_lines",
        ["customer_po_id", "line_number"],
    )
    op.create_table(
        "customer_po_status_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_po_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
        ),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("correlation_id", sa.String(100)),
        sa.Column("edi_log_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_po_id"],
            ["customer_purchase_orders.tenant_id", "customer_purchase_orders.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_customer_po_status_events_po_time",
        "customer_po_status_events",
        ["customer_po_id", sa.text("occurred_at DESC")],
    )
    for table in (
        "customer_purchase_orders",
        "customer_purchase_order_lines",
        "customer_po_status_events",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    tenant_policy = (
        "USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        f"CREATE POLICY customer_pos_tenant_isolation ON customer_purchase_orders {tenant_policy}"
    )
    for table in ("customer_purchase_order_lines", "customer_po_status_events"):
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} {tenant_policy}")
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
                "resource": "customer_pos",
                "action": action,
                "description": f"Customer PO {action}",
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
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE ON customer_purchase_orders, "
        "customer_purchase_order_lines, customer_po_status_events TO app_runtime; "
        "GRANT DELETE ON customer_purchase_order_lines TO app_runtime; "
        "END IF; END $$"
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
    op.drop_table("customer_po_status_events")
    op.drop_table("customer_purchase_order_lines")
    op.drop_table("customer_purchase_orders")
