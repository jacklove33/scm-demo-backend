from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from app.core.exceptions import AuthenticationRequired


class JwtService:
    def __init__(
        self,
        *,
        secret: str,
        algorithm: str,
        expire_minutes: int,
        issuer: str = "",
        audience: str = "",
    ) -> None:
        self.secret = secret
        self.algorithm = algorithm
        self.expire_minutes = expire_minutes
        self.issuer = issuer
        self.audience = audience

    @property
    def expires_in(self) -> int:
        return self.expire_minutes * 60

    def create_access_token(self, profile_id: UUID, *, now: datetime | None = None) -> str:
        issued_at = now or datetime.now(UTC)
        payload: dict[str, object] = {
            "sub": str(profile_id),
            "type": "access",
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=self.expire_minutes),
        }
        if self.issuer:
            payload["iss"] = self.issuer
        if self.audience:
            payload["aud"] = self.audience
        return jwt.encode(payload, self._secret(), algorithm=self.algorithm)

    def decode_access_token(self, token: str) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self._secret(),
                algorithms=[self.algorithm],
                audience=self.audience or None,
                issuer=self.issuer or None,
                options={
                    "verify_aud": bool(self.audience),
                    "verify_iss": bool(self.issuer),
                    "require": ["sub", "type", "iat", "exp"],
                },
            )
            if payload.get("type") != "access":
                raise AuthenticationRequired("Invalid access token")
            return UUID(str(payload["sub"]))
        except AuthenticationRequired:
            raise
        except (InvalidTokenError, KeyError, ValueError, TypeError) as exc:
            raise AuthenticationRequired("Invalid access token") from exc

    def _secret(self) -> str:
        if len(self.secret.encode("utf-8")) < 32:
            raise RuntimeError("JWT_SECRET must be configured with at least 32 bytes")
        return self.secret
