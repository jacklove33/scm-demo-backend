"""Add Customer PO dashboard permission.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

ADMIN_POLICY_ID = "30000000-0000-0000-0000-000000000001"
PERMISSION_ID = "50000000-0000-0000-0000-000000000026"


def upgrade() -> None:
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
                "id": PERMISSION_ID,
                "code": "dashboard.customer_pos.read",
                "resource": "dashboard.customer_pos",
                "action": "read",
                "description": "Read Customer PO executive analytics",
            }
        ],
    )
    op.bulk_insert(
        mappings,
        [
            {
                "policy_id": ADMIN_POLICY_ID,
                "permission_id": PERMISSION_ID,
                "effect": "ALLOW",
                "scope": "ALL",
            }
        ],
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM policy_permissions WHERE permission_id=:permission_id"),
        {"permission_id": PERMISSION_ID},
    )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE id=:permission_id"),
        {"permission_id": PERMISSION_ID},
    )
