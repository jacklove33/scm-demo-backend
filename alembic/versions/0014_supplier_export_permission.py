"""Add Supplier export permission.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

PERMISSION_ID = "50000000-0000-0000-0000-000000000034"
PERMISSION_CODE = "suppliers.export"
ADMIN_POLICY_ID = "30000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("""INSERT INTO permissions (id, code, resource, action, description)
        VALUES (:id, :code, 'suppliers', 'export', 'Supplier export')
        ON CONFLICT (code) DO UPDATE SET
            resource='suppliers', action='export', description='Supplier export'"""),
        {"id": PERMISSION_ID, "code": PERMISSION_CODE},
    )
    connection.execute(
        sa.text("""INSERT INTO policy_permissions (policy_id, permission_id, effect, scope)
        SELECT :policy, id, 'ALLOW', 'ALL' FROM permissions WHERE code=:code
        ON CONFLICT (policy_id, permission_id) DO UPDATE SET effect='ALLOW', scope='ALL'"""),
        {"policy": ADMIN_POLICY_ID, "code": PERMISSION_CODE},
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """DELETE FROM policy_permissions
            WHERE policy_id=:policy
              AND permission_id=(SELECT id FROM permissions WHERE code=:code)"""
        ),
        {"policy": ADMIN_POLICY_ID, "code": PERMISSION_CODE},
    )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE code=:code"), {"code": PERMISSION_CODE}
    )
