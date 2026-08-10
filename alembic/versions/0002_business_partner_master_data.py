"""Replace standalone customers with ERP business partner master data.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_payment_terms_tenant_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_payment_terms_tenant_id_id"),
    )
    op.create_table(
        "business_partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("partner_code", sa.String(20), nullable=False),
        sa.Column("partner_name", sa.String(240), nullable=False),
        sa.Column("tax_id", sa.String(80)),
        sa.Column("country_code", sa.String(2)),
        sa.Column("currency_code", sa.String(3)),
        sa.Column("payment_term_id", postgresql.UUID(as_uuid=True)),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "partner_code", name="uq_business_partners_tenant_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_business_partners_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payment_term_id"],
            ["payment_terms.tenant_id", "payment_terms.id"],
            name="fk_business_partners_tenant_payment_term",
        ),
    )
    op.create_index(
        "ix_business_partners_tenant_owner", "business_partners", ["tenant_id", "owner_user_id"]
    )
    op.create_index(
        "ix_business_partners_tenant_status",
        "business_partners",
        ["tenant_id", "status", "deleted_at"],
    )
    op.create_table(
        "partner_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_type", sa.String(30), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "partner_id"],
            ["business_partners.tenant_id", "business_partners.id"],
            name="fk_partner_roles_tenant_partner",
        ),
        sa.UniqueConstraint(
            "tenant_id", "partner_id", "role_type", name="uq_partner_roles_partner_type"
        ),
        sa.CheckConstraint("role_type IN ('CUSTOMER', 'SUPPLIER')", name="ck_partner_roles_type"),
    )
    op.create_index(
        "ix_partner_roles_tenant_type_partner",
        "partner_roles",
        ["tenant_id", "role_type", "partner_id"],
    )
    op.create_table(
        "partner_addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("address_code", sa.String(40), nullable=False),
        sa.Column("address_type", sa.String(30), nullable=False),
        sa.Column("contact_name", sa.String(160)),
        sa.Column("address1", sa.String(240)),
        sa.Column("address2", sa.String(240)),
        sa.Column("city", sa.String(120)),
        sa.Column("state", sa.String(120)),
        sa.Column("postal_code", sa.String(30)),
        sa.Column("country_code", sa.String(2)),
        sa.Column("phone", sa.String(50)),
        sa.Column("email", sa.String(320)),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "partner_id"],
            ["business_partners.tenant_id", "business_partners.id"],
            name="fk_partner_addresses_tenant_partner",
        ),
        sa.UniqueConstraint(
            "tenant_id", "partner_id", "address_code", name="uq_partner_addresses_partner_code"
        ),
        sa.CheckConstraint(
            "address_type IN ('SOLD_TO','SHIP_TO','BILL_TO','REMIT_TO',"
            "'SUPPLIER_SITE','WAREHOUSE','OFFICE')",
            name="ck_partner_addresses_type",
        ),
    )
    op.create_index(
        "ix_partner_addresses_tenant_partner_type",
        "partner_addresses",
        ["tenant_id", "partner_id", "address_type"],
    )
    op.create_index(
        "ix_partner_addresses_tenant_partner_default",
        "partner_addresses",
        ["tenant_id", "partner_id", "is_default"],
    )

    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM customers
            WHERE upper(trim(customer_code)) !~ '^[A-Z][A-Z0-9_-]*$'
               OR length(upper(trim(customer_code))) > 20
          ) THEN
            RAISE EXCEPTION 'Legacy customer_code cannot be migrated to partner_code';
          END IF;
        END $$
    """)
    op.execute("""
        INSERT INTO business_partners
            (id, tenant_id, partner_code, partner_name, owner_user_id, status,
             deleted_at, deleted_by, row_version, created_at, updated_at)
        SELECT id, tenant_id, upper(trim(customer_code)), customer_name, owner_user_id,
               status, NULL, NULL, row_version, created_at, updated_at
        FROM customers
    """)
    op.execute("""
        INSERT INTO partner_roles (id, tenant_id, partner_id, role_type, deleted_at, deleted_by)
        SELECT id, tenant_id, id, 'CUSTOMER', deleted_at, deleted_by FROM customers
    """)
    op.execute("""
        DO $$ BEGIN
          IF (SELECT count(*) FROM customers) <> (
            SELECT count(*) FROM partner_roles WHERE role_type = 'CUSTOMER'
          ) THEN RAISE EXCEPTION 'Customer migration row-count mismatch'; END IF;
        END $$
    """)

    for table in ("customer_user_assignments", "customer_group_assignments"):
        op.drop_constraint(f"{table}_customer_id_fkey", table, type_="foreignkey")
        op.create_foreign_key(
            f"{table}_customer_id_fkey", table, "business_partners", ["customer_id"], ["id"]
        )
    op.drop_index("ix_customers_tenant_status", table_name="customers")
    op.drop_index("ix_customers_tenant_owner", table_name="customers")
    op.drop_table("customers")

    for table in ("business_partners", "partner_roles", "partner_addresses", "payment_terms"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)""")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
            GRANT SELECT, INSERT, UPDATE
              ON business_partners, partner_roles, partner_addresses TO app_runtime;
            GRANT SELECT ON payment_terms TO app_runtime;
          END IF;
        END $$
    """)


def downgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("customer_code", sa.String(80), nullable=False),
        sa.Column("customer_name", sa.String(240), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id")),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "customer_code", name="uq_customers_tenant_code"),
    )
    op.execute("""
        INSERT INTO customers
        SELECT bp.id, bp.tenant_id, bp.partner_code, bp.partner_name,
               bp.owner_user_id, bp.status, pr.deleted_at, pr.deleted_by,
               bp.row_version, bp.created_at, bp.updated_at
        FROM business_partners bp
        JOIN partner_roles pr
          ON pr.partner_id = bp.id AND pr.tenant_id = bp.tenant_id
        WHERE pr.role_type = 'CUSTOMER'
    """)
    op.create_index("ix_customers_tenant_owner", "customers", ["tenant_id", "owner_user_id"])
    op.create_index("ix_customers_tenant_status", "customers", ["tenant_id", "status"])
    for table in ("customer_user_assignments", "customer_group_assignments"):
        op.drop_constraint(f"{table}_customer_id_fkey", table, type_="foreignkey")
        op.create_foreign_key(
            f"{table}_customer_id_fkey", table, "customers", ["customer_id"], ["id"]
        )
    op.drop_table("partner_addresses")
    op.drop_table("partner_roles")
    op.drop_index("ix_business_partners_tenant_status", table_name="business_partners")
    op.drop_index("ix_business_partners_tenant_owner", table_name="business_partners")
    op.drop_table("business_partners")
    op.drop_table("payment_terms")
