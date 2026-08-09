from pydantic import BaseModel


class PermissionSourceResponse(BaseModel):
    source_type: str
    source_name: str
    policy_code: str
    effect: str
    scope: str | None


class EffectivePermissionResponse(BaseModel):
    permission_code: str
    effect: str
    scope: str | None
    sources: list[PermissionSourceResponse]


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    permissions: list[EffectivePermissionResponse]
