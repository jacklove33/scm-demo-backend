"""Set a local profile password without storing plaintext credentials in source."""

import argparse
import asyncio
from getpass import getpass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.modules.auth.infrastructure.password_hasher import PasswordHasher


async def set_password(email: str, password: str) -> None:
    if settings.app_env != "local":
        raise RuntimeError("This helper is restricted to APP_ENV=local")
    database_url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    INSERT INTO user_credentials (profile_id, password_hash, password_changed_at)
                    SELECT id, :password_hash, now()
                    FROM profiles
                    WHERE lower(email) = lower(:email)
                    ON CONFLICT (profile_id) DO UPDATE
                    SET password_hash = EXCLUDED.password_hash,
                        password_changed_at = now(),
                        failed_attempts = 0,
                        locked_until = NULL,
                        updated_at = now()
                    """
                ),
                {"email": email.strip(), "password_hash": PasswordHasher().hash_password(password)},
            )
            if result.rowcount != 1:
                raise RuntimeError("Profile was not found")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a password for a local seeded profile")
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass("New local password: ")
    confirmation = getpass("Confirm password: ")
    if not password or password != confirmation:
        raise SystemExit("Passwords are empty or do not match")
    asyncio.run(set_password(args.email, password))


if __name__ == "__main__":
    main()
