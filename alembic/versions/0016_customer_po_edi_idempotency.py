"""Add concurrency-safe EDI Customer PO idempotency.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_customer_pos_edi_external_message"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "customer_purchase_orders",
        ["tenant_id", "edi_sender_id", "external_message_id"],
        unique=True,
        postgresql_where=sa.text(
            "source = 'EDI' AND edi_sender_id IS NOT NULL AND external_message_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="customer_purchase_orders")
