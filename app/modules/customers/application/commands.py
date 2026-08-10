from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CustomerAddressCommand:
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
    is_default: bool = True


@dataclass(frozen=True, slots=True)
class CreateCustomerCommand:
    customer_code: str
    customer_name: str
    owner_user_id: UUID | None
    status: str = "ACTIVE"
    tax_id: str | None = None
    country_code: str | None = None
    currency_code: str | None = None
    payment_term_id: UUID | None = None
    default_address: CustomerAddressCommand | None = None


@dataclass(frozen=True, slots=True)
class UpdateCustomerCommand:
    customer_id: UUID
    expected_version: int
    customer_name: str
    owner_user_id: UUID | None
    status: str
    tax_id: str | None = None
    country_code: str | None = None
    currency_code: str | None = None
    payment_term_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CustomerImportRowCommand:
    row_number: int
    customer_code: str | None
    customer_name: str | None
    tax_id: str | None
    country_code: str | None
    currency_code: str | None
    payment_term_id: UUID | None
    owner_user_id: UUID | None
    status: str | None
    address_type: str | None
    address_code: str | None
    contact_name: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    address_country_code: str | None
    phone: str | None
    email: str | None
    is_default: bool | None
