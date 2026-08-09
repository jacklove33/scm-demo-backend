from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


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

    @staticmethod
    def normalize_code(value: str) -> str:
        return value.strip().upper()

    @staticmethod
    def normalize_name(value: str) -> str:
        return " ".join(value.strip().split())
