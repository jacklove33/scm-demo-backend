from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomerAddressRequest(BaseModel):
    address_code: str = Field(min_length=1, max_length=40)
    address_type: Literal[
        "SOLD_TO", "SHIP_TO", "BILL_TO", "REMIT_TO", "SUPPLIER_SITE", "WAREHOUSE", "OFFICE"
    ]
    contact_name: str | None = Field(None, max_length=160)
    address1: str | None = Field(None, max_length=240)
    address2: str | None = Field(None, max_length=240)
    city: str | None = Field(None, max_length=120)
    state: str | None = Field(None, max_length=120)
    postal_code: str | None = Field(None, max_length=30)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=320)
    is_default: bool = True


class CustomerFields(BaseModel):
    customer_name: str = Field(min_length=1, max_length=240)
    tax_id: str | None = Field(None, max_length=80)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    currency_code: str | None = Field(None, min_length=3, max_length=3)
    payment_term_id: UUID | None = None
    owner_user_id: UUID | None = None
    status: str = Field("ACTIVE", max_length=30)

    @field_validator("country_code", "currency_code", mode="before")
    @classmethod
    def uppercase_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class CreateCustomerRequest(CustomerFields):
    customer_code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    default_address: CustomerAddressRequest | None = None

    @field_validator("customer_code")
    @classmethod
    def normalize_customer_code(cls, value: str) -> str:
        return value.strip().upper()


class UpdateCustomerRequest(CustomerFields):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class VersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class CustomerAddressResponse(CustomerAddressRequest):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class CustomerCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    update: bool
    delete: bool
    restore: bool
    assign_owner: bool


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_code: str
    customer_name: str
    tax_id: str | None
    country_code: str | None
    currency_code: str | None
    payment_term_id: UUID | None
    owner_user_id: UUID | None
    status: str
    deleted_at: datetime | None
    row_version: int
    created_at: datetime
    updated_at: datetime
    addresses: tuple[CustomerAddressResponse, ...]
    capabilities: CustomerCapabilitiesResponse


CustomerSearchResponse = CustomerResponse


class CustomerListResponse(BaseModel):
    data: list[CustomerSearchResponse]
    meta: dict[str, int]


class CustomerImportRowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    tax_id: str | None = None
    country_code: str | None = None
    currency_code: str | None = None
    payment_term_id: UUID | None = None
    owner_user_id: UUID | None = None
    status: str | None = "ACTIVE"
    address_type: str | None = None
    address_code: str | None = None
    contact_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    address_country_code: str | None = None
    phone: str | None = None
    email: str | None = None
    is_default: bool | None = True


class CustomerImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[CustomerImportRowRequest]


class CustomerImportResponse(BaseModel):
    total: int
    imported: int
    failed: int
