from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProductType = Literal[
    "FINISHED_GOOD", "RAW_MATERIAL", "SEMI_FINISHED", "PACKAGING", "SERVICE", "OTHER"
]
ProductStatus = Literal["ACTIVE", "INACTIVE"]


class ProductFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_name: str = Field(min_length=1, max_length=240)
    description: str | None = None
    product_type: ProductType
    status: ProductStatus = "ACTIVE"
    base_uom: str = Field(min_length=1, max_length=20)
    category: str | None = Field(None, max_length=120)
    brand: str | None = Field(None, max_length=120)
    model: str | None = Field(None, max_length=120)
    barcode: str | None = Field(None, max_length=100)
    country_of_origin: str | None = Field(None, min_length=2, max_length=2)
    weight: Decimal | None = Field(None, ge=0)
    weight_uom: str | None = Field(None, max_length=20)
    length: Decimal | None = Field(None, ge=0)
    width: Decimal | None = Field(None, ge=0)
    height: Decimal | None = Field(None, ge=0)
    dimension_uom: str | None = Field(None, max_length=20)
    default_currency_code: str | None = Field(None, min_length=3, max_length=3)
    standard_cost: Decimal | None = Field(None, ge=0)
    list_price: Decimal | None = Field(None, ge=0)
    owner_user_id: UUID | None = None

    @field_validator(
        "base_uom",
        "weight_uom",
        "dimension_uom",
        "country_of_origin",
        "default_currency_code",
        mode="before",
    )
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class CreateProductRequest(ProductFields):
    product_code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")

    @field_validator("product_code", mode="before")
    @classmethod
    def normalize_product_code(cls, value: str) -> str:
        return value.strip().upper()


class UpdateProductRequest(ProductFields):
    expected_version: int = Field(ge=1)


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class ProductCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    update: bool
    delete: bool
    restore: bool
    assign_owner: bool


class ProductResponse(ProductFields):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_code: str
    owner_display_name: str | None
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    capabilities: ProductCapabilitiesResponse


class ProductListResponse(BaseModel):
    data: list[ProductResponse]
    meta: dict[str, int]


class ProductImportRowRequest(CreateProductRequest):
    row_number: int | None = None


class ProductImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[ProductImportRowRequest]


class ProductImportResponse(BaseModel):
    total: int
    imported: int
    failed: int
