from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.exceptions import AuthenticationRequired
from app.modules.auth.infrastructure.jwt_service import JwtService
from app.modules.auth.infrastructure.password_hasher import PasswordHasher
from app.modules.auth.infrastructure.refresh_token_service import RefreshTokenService

TEST_SECRET = "test-secret-that-is-at-least-32-bytes-long"


def jwt_service(secret: str = TEST_SECRET) -> JwtService:
    return JwtService(
        secret=secret,
        algorithm="HS256",
        expire_minutes=15,
        audience="authenticated",
    )


def test_argon2_password_hash_and_verify() -> None:
    hasher = PasswordHasher()
    encoded = hasher.hash_password("correct horse battery staple")

    assert encoded != "correct horse battery staple"
    assert encoded.startswith("$argon2id$")
    assert hasher.verify_password("correct horse battery staple", encoded)
    assert not hasher.verify_password("wrong", encoded)


def test_access_token_is_minimal_and_decodes_profile_sub() -> None:
    profile_id = uuid4()
    service = jwt_service()
    token = service.create_access_token(profile_id)
    payload = jwt.decode(
        token,
        TEST_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
    )

    assert service.decode_access_token(token) == profile_id
    assert payload["sub"] == str(profile_id)
    assert payload["type"] == "access"
    assert "tenant_id" not in payload
    assert "permissions" not in payload
    assert "roles" not in payload


def test_expired_and_invalid_signature_tokens_are_rejected() -> None:
    profile_id = uuid4()
    expired = jwt_service().create_access_token(
        profile_id, now=datetime.now(UTC) - timedelta(hours=1)
    )

    with pytest.raises(AuthenticationRequired):
        jwt_service().decode_access_token(expired)
    with pytest.raises(AuthenticationRequired):
        jwt_service("different-secret-that-is-at-least-32-bytes").decode_access_token(
            jwt_service().create_access_token(profile_id)
        )


def test_wrong_token_type_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "aud": "authenticated",
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationRequired):
        jwt_service().decode_access_token(token)


def test_refresh_tokens_are_random_and_only_hashes_match() -> None:
    first = RefreshTokenService.generate()
    second = RefreshTokenService.generate()
    assert first != second
    assert RefreshTokenService.hash_token(first) != first
    assert len(RefreshTokenService.hash_token(first)) == 64
