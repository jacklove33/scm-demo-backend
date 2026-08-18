from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupplierAddressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
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


class SupplierFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_name: str = Field(min_length=1, max_length=240)
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


class CreateSupplierRequest(SupplierFields):
    supplier_code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    default_address: SupplierAddressRequest | None = None

    @field_validator("supplier_code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class UpdateSupplierRequest(SupplierFields):
    expected_version: int = Field(ge=1)


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class SupplierAddressResponse(SupplierAddressRequest):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class SupplierCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    update: bool
    delete: bool
    restore: bool
    assign_owner: bool


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    supplier_code: str
    supplier_name: str
    tax_id: str | None
    country_code: str | None
    currency_code: str | None
    payment_term_id: UUID | None
    owner_user_id: UUID | None
    owner_display_name: str | None
    status: str
    deleted_at: datetime | None
    row_version: int
    created_at: datetime
    updated_at: datetime
    addresses: tuple[SupplierAddressResponse, ...]
    capabilities: SupplierCapabilitiesResponse


class SupplierListResponse(BaseModel):
    data: list[SupplierResponse]
    meta: dict[str, int]


class SupplierImportRowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_number: int | None = None
    supplier_code: str | None = None
    supplier_name: str | None = None
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


class SupplierImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[SupplierImportRowRequest]


class SupplierImportResponse(BaseModel):
    total: int
    imported: int
    failed: int


class PaymentTermOptionResponse(BaseModel):
    id: UUID
    code: str
    name: str
