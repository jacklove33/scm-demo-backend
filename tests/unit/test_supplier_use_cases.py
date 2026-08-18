from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest

from app.core.exceptions import ImportValidationFailure, PermissionDenied
from app.modules.suppliers.application.commands import (
    CreateSupplierCommand,
    SupplierImportRowCommand,
)
from app.modules.suppliers.application.use_cases import SupplierUseCases
from app.modules.suppliers.domain.entities import Supplier
from app.modules.suppliers.domain.repository import SupplierRepository
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class Store:
    def __init__(self, existing_owner: UUID | None = None) -> None:
        self.created: Supplier | None = None
        self.existing_owner = existing_owner

    async def find_existing_partner_owner(
        self, tenant_id: UUID, supplier_code: str
    ) -> tuple[bool, UUID | None]:
        return (True, self.existing_owner) if self.existing_owner else (False, None)

    async def list_payment_terms(self, tenant_id: UUID) -> list[tuple[UUID, str, str]]:
        return []

    async def find_valid_payment_term_ids(self, tenant_id: UUID, ids: set[UUID]) -> set[UUID]:
        return ids

    async def find_valid_owner_ids(self, tenant_id: UUID, ids: set[UUID]) -> set[UUID]:
        return ids

    async def create(self, supplier: Supplier) -> Supplier:
        self.created = supplier
        return supplier


def actor(*, assign: bool = False) -> CurrentUser:
    permissions = {
        "suppliers.create": EffectivePermission(
            "suppliers.create", PermissionEffect.ALLOW, PermissionScope.ALL, ()
        )
    }
    if assign:
        permissions["suppliers.assign_owner"] = EffectivePermission(
            "suppliers.assign_owner", PermissionEffect.ALLOW, PermissionScope.ALL, ()
        )
    return CurrentUser(ACTOR, TENANT, "kevin@local.test", "Kevin Admin", True, permissions)


@pytest.mark.asyncio
async def test_create_defaults_owner_to_actor_and_normalizes_master_data() -> None:
    store = Store()
    result = await SupplierUseCases(cast(SupplierRepository, cast(Any, store))).create(
        CreateSupplierCommand(" sup-1 ", " ACME   Corp ", None), actor()
    )
    assert store.created is not None
    assert store.created.tenant_id == TENANT
    assert result.supplier_code == "SUP-1"
    assert result.supplier_name == "ACME Corp"
    assert result.owner_user_id == ACTOR


@pytest.mark.asyncio
async def test_create_requires_assign_owner_for_another_user() -> None:
    other = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    with pytest.raises(PermissionDenied):
        await SupplierUseCases(cast(SupplierRepository, cast(Any, Store()))).create(
            CreateSupplierCommand("SUP-1", "ACME", other), actor()
        )


@pytest.mark.asyncio
async def test_multi_role_create_without_owner_preserves_existing_partner_owner() -> None:
    existing_owner = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    store = Store(existing_owner)
    result = await SupplierUseCases(cast(SupplierRepository, cast(Any, store))).create(
        CreateSupplierCommand("SUP-1", "ACME", None), actor()
    )
    assert result.owner_user_id == existing_owner


def test_supplier_entity_uses_role_level_delete_state() -> None:
    now = datetime.now(UTC)
    value = Supplier(
        ACTOR, TENANT, "SUP-1", "ACME", ACTOR, "Kevin", "ACTIVE", now, ACTOR, 2, now, now
    )
    assert value.deleted_at == now


def import_row(**changes: Any) -> SupplierImportRowCommand:
    values: dict[str, Any] = {
        "row_number": 2,
        "supplier_code": " sup-2 ",
        "supplier_name": " ACME  Supply ",
        "tax_id": None,
        "country_code": "tw",
        "currency_code": "twd",
        "payment_term_id": None,
        "owner_user_id": None,
        "status": "active",
        "address_type": "supplier_site",
        "address_code": "main",
        "contact_name": None,
        "address_line1": "1 Main St",
        "address_line2": None,
        "city": None,
        "state": None,
        "postal_code": None,
        "address_country_code": "tw",
        "phone": None,
        "email": "ops@example.test",
        "is_default": True,
    }
    values.update(changes)
    return SupplierImportRowCommand(**values)


@pytest.mark.asyncio
async def test_import_uses_supplier_create_semantics_and_normalization() -> None:
    store = Store()
    imported = await SupplierUseCases(cast(SupplierRepository, cast(Any, store))).import_suppliers(
        [import_row()], actor()
    )
    assert imported == 1
    assert store.created is not None
    assert (store.created.supplier_code, store.created.supplier_name) == ("SUP-2", "ACME Supply")
    assert store.created.addresses[0].address_type == "SUPPLIER_SITE"


@pytest.mark.asyncio
async def test_import_returns_row_level_validation_errors_without_writes() -> None:
    store = Store()
    with pytest.raises(ImportValidationFailure) as raised:
        await SupplierUseCases(cast(SupplierRepository, cast(Any, store))).import_suppliers(
            [import_row(email="invalid")], actor()
        )
    assert store.created is None
    assert raised.value.details["errors"] == [
        {
            "row_number": 2,
            "field": "email",
            "code": "INVALID_EMAIL",
            "message": "Email address is invalid",
        }
    ]
