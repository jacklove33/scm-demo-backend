from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreateCustomerCommand:
    customer_code: str
    customer_name: str
    owner_user_id: UUID | None
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class UpdateCustomerCommand:
    customer_id: UUID
    expected_version: int
    customer_code: str
    customer_name: str
    owner_user_id: UUID | None
    status: str
