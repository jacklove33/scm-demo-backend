from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

from app.modules.customers.application.capabilities import CustomerCapabilities
from app.modules.customers.domain.entities import Customer, CustomerAddress


@dataclass(frozen=True, slots=True)
class CustomerAddressDTO:
    id: UUID
    address_code: str
    address_type: str
    contact_name: str | None
    address1: str | None
    address2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country_code: str | None
    phone: str | None
    email: str | None
    is_default: bool

    @classmethod
    def from_domain(cls, address: CustomerAddress) -> "CustomerAddressDTO":
        return cls(**asdict(address))


@dataclass(frozen=True, slots=True)
class CustomerDTO:
    id: UUID
    customer_code: str
    customer_name: str
    owner_user_id: UUID | None
    status: str
    deleted_at: datetime | None
    row_version: int
    created_at: datetime
    updated_at: datetime
    capabilities: CustomerCapabilities
    tax_id: str | None = None
    country_code: str | None = None
    currency_code: str | None = None
    payment_term_id: UUID | None = None
    addresses: tuple[CustomerAddressDTO, ...] = ()

    @classmethod
    def from_domain(cls, customer: Customer, capabilities: CustomerCapabilities) -> "CustomerDTO":
        return cls(
            id=customer.id,
            customer_code=customer.customer_code,
            customer_name=customer.customer_name,
            tax_id=customer.tax_id,
            country_code=customer.country_code,
            currency_code=customer.currency_code,
            payment_term_id=customer.payment_term_id,
            owner_user_id=customer.owner_user_id,
            status=customer.status,
            deleted_at=customer.deleted_at,
            row_version=customer.row_version,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
            addresses=tuple(CustomerAddressDTO.from_domain(a) for a in customer.addresses),
            capabilities=capabilities,
        )


CustomerSearchDTO = CustomerDTO
