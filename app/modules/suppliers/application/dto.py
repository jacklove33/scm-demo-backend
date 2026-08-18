from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

from app.modules.suppliers.application.capabilities import SupplierCapabilities
from app.modules.suppliers.domain.entities import Supplier, SupplierAddress


@dataclass(frozen=True, slots=True)
class SupplierAddressDTO:
    id: UUID
    address_code: str
    address_type: str
    contact_name: str | None
    address1: str | None
    address2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country_code: str | None
    phone: str | None
    email: str | None
    is_default: bool

    @classmethod
    def from_domain(cls, value: SupplierAddress) -> "SupplierAddressDTO":
        return cls(**asdict(value))


@dataclass(frozen=True, slots=True)
class SupplierDTO:
    id: UUID
    supplier_code: str
    supplier_name: str
    owner_user_id: UUID | None
    owner_display_name: str | None
    status: str
    deleted_at: datetime | None
    row_version: int
    created_at: datetime
    updated_at: datetime
    capabilities: SupplierCapabilities
    tax_id: str | None = None
    country_code: str | None = None
    currency_code: str | None = None
    payment_term_id: UUID | None = None
    addresses: tuple[SupplierAddressDTO, ...] = ()

    @classmethod
    def from_domain(cls, value: Supplier, caps: SupplierCapabilities) -> "SupplierDTO":
        return cls(
            id=value.id,
            supplier_code=value.supplier_code,
            supplier_name=value.supplier_name,
            owner_user_id=value.owner_user_id,
            owner_display_name=value.owner_display_name,
            status=value.status,
            deleted_at=value.deleted_at,
            row_version=value.row_version,
            created_at=value.created_at,
            updated_at=value.updated_at,
            capabilities=caps,
            tax_id=value.tax_id,
            country_code=value.country_code,
            currency_code=value.currency_code,
            payment_term_id=value.payment_term_id,
            addresses=tuple(SupplierAddressDTO.from_domain(a) for a in value.addresses),
        )
