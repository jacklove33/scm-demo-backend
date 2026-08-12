"""Add Customer date-search indexes.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_business_partners_tenant_created_at",
        "business_partners",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_business_partners_tenant_updated_at",
        "business_partners",
        ["tenant_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_business_partners_tenant_updated_at", table_name="business_partners")
    op.drop_index("ix_business_partners_tenant_created_at", table_name="business_partners")
