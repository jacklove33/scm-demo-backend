from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LoginCommand:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class RefreshCommand:
    refresh_token: str


@dataclass(frozen=True, slots=True)
class LogoutCommand:
    refresh_token: str
