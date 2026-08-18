from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProductFieldsCommand:
    product_name: str
    product_type: str
    status: str
    base_uom: str
    owner_user_id: UUID | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    model: str | None = None
    barcode: str | None = None
    country_of_origin: str | None = None
    weight: Decimal | None = None
    weight_uom: str | None = None
    length: Decimal | None = None
    width: Decimal | None = None
    height: Decimal | None = None
    dimension_uom: str | None = None
    default_currency_code: str | None = None
    standard_cost: Decimal | None = None
    list_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class CreateProductCommand(ProductFieldsCommand):
    product_code: str = ""


@dataclass(frozen=True, slots=True)
class UpdateProductCommand(ProductFieldsCommand):
    product_id: UUID = UUID(int=0)
    expected_version: int = 1


@dataclass(frozen=True, slots=True)
class ProductImportRowCommand(CreateProductCommand):
    row_number: int = 0
