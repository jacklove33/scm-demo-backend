import inspect
from types import ModuleType
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.modules.iam.application.permission_resolver import EffectivePermissionResolver
from app.modules.iam.domain.repository import PermissionGrant
from app.shared.domain.current_user import PermissionEffect, PermissionScope

SUPPLIER_PERMISSION_CODES = {
    "suppliers.read",
    "suppliers.detail.read",
    "suppliers.create",
    "suppliers.update",
    "suppliers.delete",
    "suppliers.restore",
    "suppliers.assign_owner",
}


def supplier_migration() -> ModuleType:
    module = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("0013").module
    assert module is not None
    return module


def test_supplier_permissions_use_stable_unique_ids_and_canonical_codes() -> None:
    migration = supplier_migration()

    assert migration.ADMIN_POLICY_ID == "30000000-0000-0000-0000-000000000001"
    assert {code for _, code, _, _ in migration.PERMISSIONS} == SUPPLIER_PERMISSION_CODES
    assert len({UUID(permission_id) for permission_id, _, _, _ in migration.PERMISSIONS}) == 7
    assert all(code.startswith("suppliers.") for _, code, _, _ in migration.PERMISSIONS)


def test_supplier_permission_seed_and_admin_mapping_are_conflict_safe() -> None:
    source = inspect.getsource(supplier_migration().upgrade)

    assert "ON CONFLICT (code) DO UPDATE" in source
    assert "WHERE code = :code" in source
    assert "ON CONFLICT (policy_id, permission_id) DO UPDATE" in source
    assert "'ALLOW', 'ALL'" in source


def test_supplier_export_permission_has_stable_admin_policy_mapping() -> None:
    migration = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("0014").module
    assert migration is not None
    assert migration.PERMISSION_CODE == "suppliers.export"
    assert migration.PERMISSION_ID == "50000000-0000-0000-0000-000000000034"
    assert migration.ADMIN_POLICY_ID == "30000000-0000-0000-0000-000000000001"


def test_admin_supplier_grants_resolve_allow_all_without_granting_other_users() -> None:
    admin_grants = [
        PermissionGrant(
            permission_code=code,
            source_type="ROLE",
            source_name="ADMIN",
            policy_code="ADMIN_BASE_POLICY",
            effect=PermissionEffect.ALLOW,
            scope=PermissionScope.ALL,
        )
        for code in SUPPLIER_PERMISSION_CODES
    ]

    admin_permissions = EffectivePermissionResolver().resolve(admin_grants)
    ordinary_permissions = EffectivePermissionResolver().resolve([])

    assert SUPPLIER_PERMISSION_CODES == admin_permissions.keys()
    assert all(
        permission.effect == PermissionEffect.ALLOW
        and permission.scope == PermissionScope.ALL
        and permission.sources[0].source_type == "ROLE"
        and permission.sources[0].source_name == "ADMIN"
        and permission.sources[0].policy_code == "ADMIN_BASE_POLICY"
        for permission in admin_permissions.values()
    )
    assert SUPPLIER_PERMISSION_CODES.isdisjoint(ordinary_permissions)
