import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

CUSTOMER_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class CustomerAddress:
    id: UUID
    address_code: str
    address_type: str
    contact_name: str | None = None
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    phone: str | None = None
    email: str | None = None
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class Customer:
    id: UUID
    tenant_id: UUID
    customer_code: str
    customer_name: str
    owner_user_id: UUID | None
    status: str
    deleted_at: datetime | None
    deleted_by: UUID | None
    row_version: int
    created_at: datetime
    updated_at: datetime
    tax_id: str | None = None
    country_code: str | None = None
    currency_code: str | None = None
    payment_term_id: UUID | None = None
    addresses: tuple[CustomerAddress, ...] = ()

    @staticmethod
    def normalize_code(value: str) -> str:
        return value.strip().upper()

    @staticmethod
    def is_valid_code(value: str) -> bool:
        code = Customer.normalize_code(value)
        return len(code) <= 20 and bool(CUSTOMER_CODE_PATTERN.fullmatch(code))

    @staticmethod
    def normalize_name(value: str) -> str:
        return " ".join(value.strip().split())
