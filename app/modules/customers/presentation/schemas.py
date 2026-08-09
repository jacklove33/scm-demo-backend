from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateCustomerRequest(BaseModel):
    customer_code: str = Field(min_length=1, max_length=80)
    customer_name: str = Field(min_length=1, max_length=240)
    owner_user_id: UUID | None = None
    status: str = "ACTIVE"


class UpdateCustomerRequest(BaseModel):
    expected_version: int = Field(ge=1)
    customer_code: str = Field(min_length=1, max_length=80)
    customer_name: str = Field(min_length=1, max_length=240)
    owner_user_id: UUID | None = None
    status: str = "ACTIVE"


class VersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_code: str
    customer_name: str
    owner_user_id: UUID | None
    status: str
    deleted_at: datetime | None
    row_version: int
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    data: list[CustomerResponse]
    meta: dict[str, int]
