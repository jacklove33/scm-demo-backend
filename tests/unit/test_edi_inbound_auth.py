from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.dependencies.edi as edi_dependencies
import app.api.dependencies.identity as identity_dependencies
from app.core.config import settings
from app.core.exceptions import AuthenticationRequired
from app.shared.domain.current_user import CurrentUser

USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")


def current_user() -> CurrentUser:
    return CurrentUser(USER_ID, TENANT_ID, "kevin@local.test", "Kevin Admin", True, {})


@pytest.mark.asyncio
async def test_local_dev_no_auth_resolves_configured_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[tuple[UUID, Any]] = []
    session = object()

    async def load(user_id: UUID, db_session: Any) -> CurrentUser:
        loaded.append((user_id, db_session))
        return current_user()

    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "edi_inbound_auth_mode", "dev_no_auth")
    monkeypatch.setattr(settings, "edi_dev_user_id", USER_ID)
    monkeypatch.setattr(edi_dependencies, "load_current_user_context", load)

    actor = await edi_dependencies.get_edi_inbound_actor(session)  # type: ignore[arg-type]

    assert actor.user_id == USER_ID
    assert actor.tenant_id == TENANT_ID
    assert loaded == [(USER_ID, session)]


@pytest.mark.asyncio
async def test_dev_no_auth_requires_configured_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "edi_inbound_auth_mode", "dev_no_auth")
    monkeypatch.setattr(settings, "edi_dev_user_id", None)

    with pytest.raises(AuthenticationRequired, match="EDI_DEV_USER_ID"):
        await edi_dependencies.get_edi_inbound_actor(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_nonexistent_configured_user_failure_is_propagated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def missing_user(*_: object) -> CurrentUser:
        raise AuthenticationRequired("Authenticated user profile was not found")

    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "edi_inbound_auth_mode", "dev_no_auth")
    monkeypatch.setattr(settings, "edi_dev_user_id", USER_ID)
    monkeypatch.setattr(edi_dependencies, "load_current_user_context", missing_user)

    with pytest.raises(AuthenticationRequired, match="profile was not found"):
        await edi_dependencies.get_edi_inbound_actor(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_prod_rejects_dev_no_auth_before_loading_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def must_not_load(*_: object) -> CurrentUser:
        raise AssertionError("actor loader must not run")

    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "edi_inbound_auth_mode", "dev_no_auth")
    monkeypatch.setattr(settings, "edi_dev_user_id", USER_ID)
    monkeypatch.setattr(edi_dependencies, "load_current_user_context", must_not_load)

    with pytest.raises(AuthenticationRequired, match="disabled outside"):
        await edi_dependencies.get_edi_inbound_actor(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_api_key_mode_is_fail_closed_until_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "edi_inbound_auth_mode", "api_key")

    with pytest.raises(AuthenticationRequired, match="not implemented"):
        await edi_dependencies.get_edi_inbound_actor(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_shared_loader_sets_tenant_and_user_rls_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = current_user()

    class Service:
        def __init__(self, **_: object) -> None:
            pass

        async def load(self, user_id: UUID) -> CurrentUser:
            assert user_id == USER_ID
            return actor

    class Session:
        def __init__(self) -> None:
            self.parameters: dict[str, str] | None = None

        async def execute(self, statement: object, parameters: dict[str, str]) -> object:
            assert "set_config('app.tenant_id'" in str(statement)
            assert "set_config('app.user_id'" in str(statement)
            self.parameters = parameters
            return SimpleNamespace()

    session = Session()
    monkeypatch.setattr(identity_dependencies, "CurrentUserService", Service)

    result = await identity_dependencies.load_current_user_context(
        USER_ID, cast(AsyncSession, cast(object, session))
    )

    assert result is actor
    assert session.parameters == {"tenant_id": str(TENANT_ID), "user_id": str(USER_ID)}
