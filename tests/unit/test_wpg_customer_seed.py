from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2] / "alembic/versions/0017_local_test_wpg_customer_seed.py"
)


def migration_source() -> str:
    return MIGRATION.read_text()


def test_wpg_seed_uses_business_partner_golden_reference() -> None:
    source = migration_source()
    assert 'down_revision = "0016"' in source
    assert "INSERT INTO business_partners" in source
    assert "INSERT INTO partner_roles" in source
    assert "INSERT INTO partner_addresses" in source
    assert "INSERT INTO customers" not in source


def test_wpg_seed_is_deterministic_tenant_scoped_and_local_test_only() -> None:
    source = migration_source()
    assert 'TENANT_ID = "11111111-1111-1111-1111-111111111111"' in source
    assert 'WPG_PARTNER_ID = "40000000-0000-0000-0000-000000000099"' in source
    assert 'ADMIN_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"' in source
    assert 'settings.app_env not in {"local", "test"}' in source


def test_wpg_seed_has_expected_customer_role_and_master_data() -> None:
    source = migration_source()
    for value in ("'WPG'", "'WPG Demo'", "'CUSTOMER'", "'ACTIVE'", "'TW'", "'USD'"):
        assert value in source
    assert "payment_term" not in source


def test_wpg_seed_has_default_ship_to_address() -> None:
    source = migration_source()
    for value in (
        "'WPG_WH'",
        "'SHIP_TO'",
        "'WPG Warehouse'",
        "'1 Demo Road'",
        "'Taipei'",
        "'110'",
    ):
        assert value in source
    assert "NULL, NULL, true" in source


def test_wpg_seed_is_idempotent_and_preserves_existing_partner_data() -> None:
    source = migration_source()
    assert source.count("ON CONFLICT") == 3
    assert source.count("DO NOTHING") == 3
    assert "DO UPDATE" not in source
    assert "WHERE bp.tenant_id = '{TENANT_ID}' AND bp.partner_code = 'WPG'" in source


def test_existing_customer_seed_migration_is_not_modified() -> None:
    baseline = MIGRATION.with_name("0001_iam_customer_baseline.py").read_text()
    assert "'CUST001', 'Apple Demo'" in baseline
