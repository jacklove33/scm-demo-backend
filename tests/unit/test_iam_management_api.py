import os
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.api.dependencies.iam import get_iam_management_service
from app.api.dependencies.identity import get_current_user
from app.main import app
from app.modules.iam.application.management_service import IamManagementService
from app.modules.iam.domain.repository import (
    GroupSummary,
    IamRepository,
    PermissionSummary,
    PolicyRule,
    PolicySummary,
    RoleSummary,
    UserPage,
    UserSearchCriteria,
    UserSummary,
)
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ROLE = UUID("10000000-0000-0000-0000-000000000001")
GROUP = UUID("20000000-0000-0000-0000-000000000001")
POLICY = UUID("30000000-0000-0000-0000-000000000001")
NOW = datetime.now(UTC)
PERMISSIONS = ("users.read", "groups.read", "roles.read", "policies.read", "permissions.read")


class ManagementRepositoryFake:
    def __init__(self) -> None:
        self.tenant_ids: list[UUID] = []

    def tenant(self, tenant_id: UUID) -> None:
        self.tenant_ids.append(tenant_id)
        assert tenant_id == TENANT

    async def search_users(self, tenant_id: UUID, criteria: UserSearchCriteria) -> UserPage:
        self.tenant(tenant_id)
        item = UserSummary(
            USER,
            "kevin@local.test",
            "Kevin Admin",
            "ACTIVE",
            ROLE,
            "Administrator",
            [GROUP],
            ["Taiwan Sales"],
            [POLICY],
            ["Admin Base"],
            1,
            NOW,
        )
        return UserPage([item], 1, criteria.page, criteria.page_size)

    async def list_groups(self, tenant_id: UUID) -> list[GroupSummary]:
        self.tenant(tenant_id)
        return [GroupSummary(GROUP, "Taiwan Sales", "Sales", 1, [POLICY], None, NOW, NOW)]

    async def list_roles(self, tenant_id: UUID) -> list[RoleSummary]:
        self.tenant(tenant_id)
        return [RoleSummary(ROLE, "Administrator", "Admin", True, [POLICY], 1, None, NOW, NOW)]

    async def list_policies(self, tenant_id: UUID) -> list[PolicySummary]:
        self.tenant(tenant_id)
        return [
            PolicySummary(
                POLICY,
                "Admin Base",
                "Admin",
                True,
                [PolicyRule("users.read", "ALLOW", "ALL")],
                None,
                NOW,
                NOW,
            )
        ]

    async def list_permissions(self) -> list[PermissionSummary]:
        return [PermissionSummary("users.read", "users", "read", "Read users")]


def actor(*, allowed: bool) -> CurrentUser:
    permissions = {
        code: EffectivePermission(code, PermissionEffect.ALLOW, PermissionScope.ALL, ())
        for code in PERMISSIONS
        if allowed
    }
    return CurrentUser(USER, TENANT, "kevin@local.test", "Kevin Admin", True, permissions)


def service(repository: ManagementRepositoryFake) -> IamManagementService:
    return IamManagementService(cast(IamRepository, cast(Any, repository)))


def test_management_routes_match_frontend_contract_and_forward_tenant() -> None:
    repository = ManagementRepositoryFake()
    app.dependency_overrides[get_current_user] = lambda: actor(allowed=True)
    app.dependency_overrides[get_iam_management_service] = lambda: service(repository)
    client = TestClient(app)
    try:
        users = client.get("/api/v1/iam/users?page=2&page_size=10&status=ACTIVE")
        groups = client.get("/api/v1/iam/groups")
        roles = client.get("/api/v1/iam/roles")
        policies = client.get("/api/v1/iam/policies")
        permissions = client.get("/api/v1/iam/permissions")
    finally:
        app.dependency_overrides.clear()

    assert users.status_code == 200
    assert users.json()["meta"] == {"page": 2, "pageSize": 10, "total": 1}
    assert users.json()["data"][0]["primary_role_name"] == "Administrator"
    assert groups.json()[0]["member_count"] == 1
    assert roles.json()[0]["user_count"] == 1
    assert policies.json()[0]["rules"][0] == {
        "permission_code": "users.read",
        "effect": "ALLOW",
        "scope": "ALL",
    }
    assert permissions.json()[0]["code"] == "users.read"
    assert repository.tenant_ids == [TENANT, TENANT, TENANT, TENANT]


def test_management_routes_return_403_without_required_permissions() -> None:
    repository = ManagementRepositoryFake()
    app.dependency_overrides[get_current_user] = lambda: actor(allowed=False)
    app.dependency_overrides[get_iam_management_service] = lambda: service(repository)
    try:
        statuses = [
            TestClient(app).get(f"/api/v1/iam/{route}").status_code
            for route in ("users", "groups", "roles", "policies", "permissions")
        ]
    finally:
        app.dependency_overrides.clear()

    assert statuses == [403, 403, 403, 403, 403]
    assert repository.tenant_ids == []


def test_management_route_returns_401_without_jwt() -> None:
    app.dependency_overrides[get_iam_management_service] = lambda: service(
        ManagementRepositoryFake()
    )
    try:
        response = TestClient(app).get("/api/v1/iam/users")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401
