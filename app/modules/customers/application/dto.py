from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

from app.modules.customers.application.capabilities import CustomerCapabilities
from app.modules.customers.domain.entities import Customer


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

    @classmethod
    def from_domain(cls, customer: Customer) -> "CustomerDTO":
        return cls(
            id=customer.id,
            customer_code=customer.customer_code,
            customer_name=customer.customer_name,
            owner_user_id=customer.owner_user_id,
            status=customer.status,
            deleted_at=customer.deleted_at,
            row_version=customer.row_version,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
        )


@dataclass(frozen=True, slots=True)
class CustomerSearchDTO(CustomerDTO):
    capabilities: CustomerCapabilities

    @classmethod
    def from_domain_with_capabilities(
        cls,
        customer: Customer,
        capabilities: CustomerCapabilities,
    ) -> "CustomerSearchDTO":
        return cls(**asdict(CustomerDTO.from_domain(customer)), capabilities=capabilities)
