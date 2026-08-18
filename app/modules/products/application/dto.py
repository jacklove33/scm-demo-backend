from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.products.application.capabilities import ProductCapabilities
from app.modules.products.domain.entities import Product


@dataclass(frozen=True, slots=True)
class ProductDTO:
    id: UUID
    product_code: str
    product_name: str
    product_type: str
    status: str
    base_uom: str
    owner_user_id: UUID | None
    owner_display_name: str | None
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    capabilities: ProductCapabilities
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

    @classmethod
    def from_domain(cls, value: Product, capabilities: ProductCapabilities) -> "ProductDTO":
        return cls(
            **{k: v for k, v in asdict(value).items() if k != "tenant_id"},
            capabilities=capabilities,
        )
