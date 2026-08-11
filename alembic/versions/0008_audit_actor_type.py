"""Add explicit Audit actor type.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("actor_type", sa.String(30), nullable=False, server_default="SYSTEM"),
    )
    op.execute("UPDATE audit_events SET actor_type='USER' WHERE actor_user_id IS NOT NULL")
    op.create_check_constraint(
        "ck_audit_events_actor_type",
        "audit_events",
        "actor_type IN ('USER','SYSTEM','API_CLIENT')",
    )
    op.alter_column("audit_events", "actor_type", server_default="USER")


def downgrade() -> None:
    op.drop_constraint("ck_audit_events_actor_type", "audit_events", type_="check")
    op.drop_column("audit_events", "actor_type")
