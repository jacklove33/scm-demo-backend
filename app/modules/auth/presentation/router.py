from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies.auth import get_auth_use_cases, get_principal
from app.modules.auth.application.commands import LoginCommand, LogoutCommand, RefreshCommand
from app.modules.auth.application.use_cases import AuthUseCases
from app.modules.auth.presentation.schemas import (
    AuthMeResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from app.shared.domain.current_user import AuthenticatedPrincipal

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    use_cases: Annotated[AuthUseCases, Depends(get_auth_use_cases)],
) -> TokenResponse:
    result = await use_cases.login(LoginCommand(email=request.email, password=request.password))
    return TokenResponse.model_validate(result)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    use_cases: Annotated[AuthUseCases, Depends(get_auth_use_cases)],
) -> TokenResponse:
    result = await use_cases.refresh(RefreshCommand(refresh_token=request.refresh_token))
    return TokenResponse.model_validate(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest,
    use_cases: Annotated[AuthUseCases, Depends(get_auth_use_cases)],
) -> Response:
    await use_cases.logout(LogoutCommand(refresh_token=request.refresh_token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AuthMeResponse)
async def me(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_principal)],
    use_cases: Annotated[AuthUseCases, Depends(get_auth_use_cases)],
) -> AuthMeResponse:
    return AuthMeResponse.model_validate(await use_cases.me(principal.user_id))
