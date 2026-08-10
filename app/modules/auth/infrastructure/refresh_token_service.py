import hashlib
import secrets


class RefreshTokenService:
    @staticmethod
    def generate() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
