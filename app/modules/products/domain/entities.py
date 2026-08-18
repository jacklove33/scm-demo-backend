import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

PRODUCT_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]*$")
PRODUCT_TYPES = frozenset(
    {"FINISHED_GOOD", "RAW_MATERIAL", "SEMI_FINISHED", "PACKAGING", "SERVICE", "OTHER"}
)
PRODUCT_STATUSES = frozenset({"ACTIVE", "INACTIVE"})


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    tenant_id: UUID
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

    @staticmethod
    def normalize_code(value: str) -> str:
        return value.strip().upper()

    @staticmethod
    def valid_code(value: str) -> bool:
        code = Product.normalize_code(value)
        return len(code) <= 100 and bool(PRODUCT_CODE_PATTERN.fullmatch(code))
