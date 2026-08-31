"""Make Customer PO to EDI message linkage tenant-safe.

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_customer_pos_edi_message", "customer_purchase_orders", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_customer_pos_tenant_edi_message",
        "customer_purchase_orders",
        "edi_messages",
        ["tenant_id", "edi_message_id"],
        ["tenant_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_customer_pos_tenant_edi_message",
        "customer_purchase_orders",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_customer_pos_edi_message",
        "customer_purchase_orders",
        "edi_messages",
        ["edi_message_id"],
        ["id"],
    )
