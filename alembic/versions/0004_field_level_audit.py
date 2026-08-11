"""Add append-only field-level audit trail.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

AUDIT_READ_PERMISSION = "50000000-0000-0000-0000-000000000011"
ADMIN_POLICY = "30000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
        ),
        sa.Column("actor_email", sa.String(255)),
        sa.Column("actor_display_name", sa.String(255)),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("entity_code", sa.String(100)),
        sa.Column("entity_display_name", sa.String(255)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("correlation_id", sa.String(100)),
        sa.Column("request_id", sa.String(100)),
        sa.Column("request_method", sa.String(10)),
        sa.Column("request_path", sa.String(500)),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "source IN ('UI','API','IMPORT','EDI','SYSTEM','JOB','ADMIN')",
            name="ck_audit_events_source",
        ),
        sa.CheckConstraint("status IN ('SUCCESS','FAILURE')", name="ck_audit_events_status"),
    )
    op.create_table(
        "audit_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "audit_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("audit_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("field_path", sa.String(500), nullable=False),
        sa.Column("field_label", sa.String(255)),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("value_type", sa.String(30)),
        sa.Column("old_value", postgresql.JSONB()),
        sa.Column("new_value", postgresql.JSONB()),
        sa.Column("old_display_value", sa.Text()),
        sa.Column("new_display_value", sa.Text()),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "audit_event_id", "sequence_no", name="uq_audit_changes_event_sequence"
        ),
        sa.CheckConstraint(
            "change_type IN ('ADD','UPDATE','REMOVE')", name="ck_audit_changes_type"
        ),
        sa.CheckConstraint(
            "value_type IS NULL OR value_type IN "
            "('STRING','NUMBER','BOOLEAN','DATE','DATETIME','UUID','ENUM','JSON','NULL')",
            name="ck_audit_changes_value_type",
        ),
    )
    indexes = (
        ("ix_audit_events_occurred_at", "audit_events", [sa.text("occurred_at DESC")]),
        (
            "ix_audit_events_actor_occurred",
            "audit_events",
            ["actor_user_id", sa.text("occurred_at DESC")],
        ),
        (
            "ix_audit_events_entity_id_occurred",
            "audit_events",
            ["entity_type", "entity_id", sa.text("occurred_at DESC")],
        ),
        (
            "ix_audit_events_entity_code_occurred",
            "audit_events",
            ["entity_type", "entity_code", sa.text("occurred_at DESC")],
        ),
        (
            "ix_audit_events_module_occurred",
            "audit_events",
            ["module", sa.text("occurred_at DESC")],
        ),
        (
            "ix_audit_events_action_occurred",
            "audit_events",
            ["action", sa.text("occurred_at DESC")],
        ),
        ("ix_audit_events_correlation_id", "audit_events", ["correlation_id"]),
        ("ix_audit_events_batch_id", "audit_events", ["batch_id"]),
        (
            "ix_audit_events_status_occurred",
            "audit_events",
            ["status", sa.text("occurred_at DESC")],
        ),
        (
            "ix_audit_events_tenant_occurred",
            "audit_events",
            ["tenant_id", sa.text("occurred_at DESC")],
        ),
        ("ix_audit_changes_event_sequence", "audit_changes", ["audit_event_id", "sequence_no"]),
        ("ix_audit_changes_field_path", "audit_changes", ["field_path"]),
    )
    for name, table, columns in indexes:
        op.create_index(name, table, columns)

    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_changes ENABLE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY audit_events_tenant_isolation ON audit_events
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)""")
    op.execute("""CREATE POLICY audit_changes_tenant_isolation ON audit_changes
        USING (EXISTS (SELECT 1 FROM audit_events e WHERE e.id = audit_event_id
                       AND e.tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid))
        WITH CHECK (EXISTS (SELECT 1 FROM audit_events e WHERE e.id = audit_event_id
          AND e.tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid))""")
    op.execute(f"""INSERT INTO permissions (id, code, resource, action, description)
        VALUES ('{AUDIT_READ_PERMISSION}', 'audit.read', 'audit', 'read', 'Read audit trail')""")
    op.execute(f"""INSERT INTO policy_permissions (policy_id, permission_id, effect, scope)
        VALUES ('{ADMIN_POLICY}', '{AUDIT_READ_PERMISSION}', 'ALLOW', 'ALL')""")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
          GRANT SELECT, INSERT ON audit_events, audit_changes TO app_runtime;
        END IF;
      END $$""")


def downgrade() -> None:
    op.execute(f"DELETE FROM policy_permissions WHERE permission_id = '{AUDIT_READ_PERMISSION}'")
    op.execute(f"DELETE FROM permissions WHERE id = '{AUDIT_READ_PERMISSION}'")
    op.drop_table("audit_changes")
    op.drop_table("audit_events")
