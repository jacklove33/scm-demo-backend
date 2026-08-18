"""Add Supplier permissions and role-specific assignments.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

ADMIN_POLICY_ID = "30000000-0000-0000-0000-000000000001"
PERMISSIONS = (
    ("50000000-0000-0000-0000-000000000027", "suppliers.read", "suppliers", "read"),
    ("50000000-0000-0000-0000-000000000028", "suppliers.detail.read", "suppliers.detail", "read"),
    ("50000000-0000-0000-0000-000000000029", "suppliers.create", "suppliers", "create"),
    ("50000000-0000-0000-0000-000000000030", "suppliers.update", "suppliers", "update"),
    ("50000000-0000-0000-0000-000000000031", "suppliers.delete", "suppliers", "delete"),
    ("50000000-0000-0000-0000-000000000032", "suppliers.restore", "suppliers", "restore"),
    ("50000000-0000-0000-0000-000000000033", "suppliers.assign_owner", "suppliers", "assign_owner"),
)


def upgrade() -> None:
    op.create_table(
        "supplier_user_assignments",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False
        ),
        sa.Column("assignment_type", sa.String(40), nullable=False, server_default="MEMBER"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["business_partners.tenant_id", "business_partners.id"],
            name="fk_supplier_user_assignments_tenant_partner",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "supplier_id", "user_id"),
    )
    op.create_table(
        "supplier_group_assignments",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["business_partners.tenant_id", "business_partners.id"],
            name="fk_supplier_group_assignments_tenant_partner",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "supplier_id", "group_id"),
    )
    for table in ("supplier_user_assignments", "supplier_group_assignments"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)""")
    op.execute(
        """DO $$ BEGIN IF EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime'
        ) THEN
            GRANT SELECT, INSERT, UPDATE, DELETE
            ON supplier_user_assignments, supplier_group_assignments TO app_runtime;
        END IF; END $$"""
    )

    connection = op.get_bind()
    # Permission codes are the public IAM contract. A database may already contain a
    # code created during development, so resolve policy mappings by code instead of
    # assuming that its row has our deterministic seed ID.
    for permission_id, code, resource, action in PERMISSIONS:
        connection.execute(
            sa.text(
                """
                INSERT INTO permissions (id, code, resource, action, description)
                VALUES (:id, :code, :resource, :action, :description)
                ON CONFLICT (code) DO UPDATE SET
                    resource = EXCLUDED.resource,
                    action = EXCLUDED.action,
                    description = EXCLUDED.description
                """
            ),
            {
                "id": permission_id,
                "code": code,
                "resource": resource,
                "action": action,
                "description": f"Supplier {action}",
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO policy_permissions (policy_id, permission_id, effect, scope)
                SELECT :policy_id, id, 'ALLOW', 'ALL'
                FROM permissions
                WHERE code = :code
                ON CONFLICT (policy_id, permission_id) DO UPDATE SET
                    effect = EXCLUDED.effect,
                    scope = EXCLUDED.scope
                """
            ),
            {"policy_id": ADMIN_POLICY_ID, "code": code},
        )


def downgrade() -> None:
    connection = op.get_bind()
    for _permission_id, code, _resource, _action in PERMISSIONS:
        connection.execute(
            sa.text(
                """
                DELETE FROM policy_permissions
                WHERE policy_id = :policy_id
                  AND permission_id = (SELECT id FROM permissions WHERE code = :code)
                """
            ),
            {"policy_id": ADMIN_POLICY_ID, "code": code},
        )
        connection.execute(sa.text("DELETE FROM permissions WHERE code=:code"), {"code": code})
    op.drop_table("supplier_group_assignments")
    op.drop_table("supplier_user_assignments")
