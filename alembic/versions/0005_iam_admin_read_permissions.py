"""Add IAM administration read permissions.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ADMIN_POLICY_ID = "30000000-0000-0000-0000-000000000001"

PERMISSIONS = (
    ("50000000-0000-0000-0000-000000000012", "users.read", "users", "Read users"),
    ("50000000-0000-0000-0000-000000000013", "groups.read", "groups", "Read groups"),
    ("50000000-0000-0000-0000-000000000014", "roles.read", "roles", "Read roles"),
    ("50000000-0000-0000-0000-000000000015", "policies.read", "policies", "Read policies"),
    (
        "50000000-0000-0000-0000-000000000016",
        "permissions.read",
        "permissions",
        "Read permissions",
    ),
)


def upgrade() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("description", sa.Text()),
    )
    policy_permissions = sa.table(
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
                "id": permission_id,
                "code": code,
                "resource": resource,
                "action": "read",
                "description": description,
            }
            for permission_id, code, resource, description in PERMISSIONS
        ],
    )
    op.bulk_insert(
        policy_permissions,
        [
            {
                "policy_id": ADMIN_POLICY_ID,
                "permission_id": permission_id,
                "effect": "ALLOW",
                "scope": "ALL",
            }
            for permission_id, _code, _resource, _description in PERMISSIONS
        ],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for permission_id, _code, _resource, _description in PERMISSIONS:
        connection.execute(
            sa.text(
                "DELETE FROM policy_permissions "
                "WHERE policy_id = :policy_id AND permission_id = :permission_id"
            ),
            {"policy_id": ADMIN_POLICY_ID, "permission_id": permission_id},
        )
        connection.execute(
            sa.text("DELETE FROM permissions WHERE id = :permission_id"),
            {"permission_id": permission_id},
        )
