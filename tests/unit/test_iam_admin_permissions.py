import os
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.api.dependencies.identity import get_current_user
from app.main import app
from app.modules.iam.application.permission_resolver import EffectivePermissionResolver
from app.modules.iam.domain.repository import PermissionGrant
from app.shared.domain.current_user import CurrentUser, PermissionEffect, PermissionScope

ADMIN_PERMISSION_CODES = {
    "users.read",
    "groups.read",
    "roles.read",
    "policies.read",
    "permissions.read",
}


def current_user(*, admin: bool) -> CurrentUser:
    grants = [
        PermissionGrant(
            permission_code=code,
            source_type="ROLE",
            source_name="ADMIN",
            policy_code="ADMIN_BASE_POLICY",
            effect=PermissionEffect.ALLOW,
            scope=PermissionScope.ALL,
        )
        for code in ADMIN_PERMISSION_CODES
        if admin
    ]
    return CurrentUser(
        user_id=UUID(
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            if admin
            else "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        ),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        email="kevin@local.test" if admin else "jack@local.test",
        display_name="Kevin Admin" if admin else "Jack Sales",
        is_active=True,
        permissions=EffectivePermissionResolver().resolve(grants),
    )


def test_migration_defines_only_the_five_admin_read_permissions() -> None:
    migration = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("0005").module

    assert migration.ADMIN_POLICY_ID == "30000000-0000-0000-0000-000000000001"
    assert {
        (code, resource, description) for _, code, resource, description in migration.PERMISSIONS
    } == {
        ("users.read", "users", "Read users"),
        ("groups.read", "groups", "Read groups"),
        ("roles.read", "roles", "Read roles"),
        ("policies.read", "policies", "Read policies"),
        ("permissions.read", "permissions", "Read permissions"),
    }


def test_kevin_effective_permissions_include_admin_reads_but_jacks_do_not() -> None:
    kevin = current_user(admin=True)
    jack = current_user(admin=False)

    assert ADMIN_PERMISSION_CODES <= kevin.permissions.keys()
    assert all(
        permission.effect == PermissionEffect.ALLOW
        and permission.scope == PermissionScope.ALL
        and permission.sources[0].source_name == "ADMIN"
        and permission.sources[0].policy_code == "ADMIN_BASE_POLICY"
        for code, permission in kevin.permissions.items()
        if code in ADMIN_PERMISSION_CODES
    )
    assert ADMIN_PERMISSION_CODES.isdisjoint(jack.permissions)


def test_effective_permissions_api_returns_admin_reads_only_for_kevin() -> None:
    app.dependency_overrides[get_current_user] = lambda: current_user(admin=True)
    try:
        kevin_response = TestClient(app).get("/api/v1/iam/me/effective-permissions")
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_current_user] = lambda: current_user(admin=False)
    try:
        jack_response = TestClient(app).get("/api/v1/iam/me/effective-permissions")
    finally:
        app.dependency_overrides.clear()

    assert kevin_response.status_code == 200
    kevin_permissions = {
        item["permission_code"]: item for item in kevin_response.json()["permissions"]
    }
    assert ADMIN_PERMISSION_CODES == kevin_permissions.keys()
    assert all(
        item["effect"] == "ALLOW"
        and item["scope"] == "ALL"
        and item["sources"][0]["source_name"] == "ADMIN"
        and item["sources"][0]["policy_code"] == "ADMIN_BASE_POLICY"
        for item in kevin_permissions.values()
    )
    assert jack_response.status_code == 200
    assert ADMIN_PERMISSION_CODES.isdisjoint(
        item["permission_code"] for item in jack_response.json()["permissions"]
    )
