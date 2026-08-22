"""Seed deterministic WPG Customer demo master data in local/test only.

Revision ID: 0017
Revises: 0016
"""

from alembic import op
from app.core.config import settings

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

TENANT_ID = "11111111-1111-1111-1111-111111111111"
ADMIN_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WPG_PARTNER_ID = "40000000-0000-0000-0000-000000000099"
WPG_CUSTOMER_ROLE_ID = "41000000-0000-0000-0000-000000000099"
WPG_SHIP_TO_ADDRESS_ID = "42000000-0000-0000-0000-000000000099"


def upgrade() -> None:
    if settings.app_env not in {"local", "test"}:
        return

    # Do not overwrite an existing shared Business Partner. Subsequent inserts
    # resolve by tenant/code so an existing multi-role WPG partner is supported.
    op.execute(
        f"""
        INSERT INTO business_partners
            (id, tenant_id, partner_code, partner_name, country_code, currency_code,
             owner_user_id, status)
        VALUES
            ('{WPG_PARTNER_ID}', '{TENANT_ID}', 'WPG', 'WPG Demo', 'TW', 'USD',
             '{ADMIN_USER_ID}', 'ACTIVE')
        ON CONFLICT (tenant_id, partner_code) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO partner_roles (id, tenant_id, partner_id, role_type)
        SELECT '{WPG_CUSTOMER_ROLE_ID}', bp.tenant_id, bp.id, 'CUSTOMER'
        FROM business_partners bp
        WHERE bp.tenant_id = '{TENANT_ID}' AND bp.partner_code = 'WPG'
        ON CONFLICT (tenant_id, partner_id, role_type) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO partner_addresses
            (id, tenant_id, partner_id, address_code, address_type, contact_name,
             address1, address2, city, state, postal_code, country_code,
             phone, email, is_default)
        SELECT
            '{WPG_SHIP_TO_ADDRESS_ID}', bp.tenant_id, bp.id, 'WPG_WH', 'SHIP_TO',
            'WPG Warehouse', '1 Demo Road', NULL, 'Taipei', NULL, '110', 'TW',
            NULL, NULL, true
        FROM business_partners bp
        WHERE bp.tenant_id = '{TENANT_ID}' AND bp.partner_code = 'WPG'
        ON CONFLICT (tenant_id, partner_id, address_code) DO NOTHING
        """
    )


def downgrade() -> None:
    if settings.app_env not in {"local", "test"}:
        return

    op.execute(
        f"DELETE FROM partner_addresses WHERE id = '{WPG_SHIP_TO_ADDRESS_ID}' "
        f"AND tenant_id = '{TENANT_ID}'"
    )
    op.execute(
        f"DELETE FROM partner_roles WHERE id = '{WPG_CUSTOMER_ROLE_ID}' "
        f"AND tenant_id = '{TENANT_ID}'"
    )
    op.execute(
        f"DELETE FROM business_partners WHERE id = '{WPG_PARTNER_ID}' "
        f"AND tenant_id = '{TENANT_ID}' AND partner_code = 'WPG'"
    )
