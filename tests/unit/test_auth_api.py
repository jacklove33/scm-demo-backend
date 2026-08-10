import os
from uuid import UUID

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.api.dependencies.auth import get_auth_use_cases, get_principal
from app.main import app
from app.modules.auth.application.dto import AuthProfileDTO, TokenPairDTO
from app.shared.domain.current_user import AuthenticatedPrincipal

PROFILE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class FakeAuthUseCases:
    async def login(self, command: object) -> TokenPairDTO:
        return TokenPairDTO("access", "refresh", "bearer", 900)

    async def refresh(self, command: object) -> TokenPairDTO:
        return TokenPairDTO("new-access", "new-refresh", "bearer", 900)

    async def logout(self, command: object) -> None:
        return None

    async def me(self, profile_id: UUID) -> AuthProfileDTO:
        return AuthProfileDTO(
            id=profile_id,
            email="jack@local.test",
            display_name="Jack",
            is_active=True,
            locale="zh-TW",
            timezone="Asia/Taipei",
        )


async def auth_use_cases() -> FakeAuthUseCases:
    return FakeAuthUseCases()


async def principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=PROFILE_ID)


def test_auth_routes_contracts() -> None:
    app.dependency_overrides[get_auth_use_cases] = auth_use_cases
    app.dependency_overrides[get_principal] = principal
    client = TestClient(app)
    try:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "jack@local.test", "password": "password123"},
        )
        refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": "refresh"})
        logout = client.post("/api/v1/auth/logout", json={"refresh_token": "refresh"})
        me = client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert login.status_code == 200
    assert login.json() == {
        "access_token": "access",
        "refresh_token": "refresh",
        "token_type": "bearer",
        "expires_in": 900,
    }
    assert refresh.json()["refresh_token"] == "new-refresh"
    assert logout.status_code == 204
    assert me.status_code == 200
    assert me.json()["id"] == str(PROFILE_ID)
    assert "permissions" not in me.json()
