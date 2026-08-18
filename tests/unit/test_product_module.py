from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.products.domain.entities import Product
from app.modules.products.presentation.schemas import CreateProductRequest


def valid_request(**overrides: object) -> CreateProductRequest:
    values: dict[str, object] = {
        "product_code": " fg-10001 ",
        "product_name": "Widget A",
        "product_type": "FINISHED_GOOD",
        "base_uom": " ea ",
    }
    values.update(overrides)
    return CreateProductRequest.model_validate(values)


def test_product_create_contract_normalizes_codes_and_uses_decimal() -> None:
    request = valid_request(standard_cost="12.3456", default_currency_code=" usd ")
    assert request.product_code == "FG-10001"
    assert request.base_uom == "EA"
    assert request.default_currency_code == "USD"
    assert request.standard_cost == Decimal("12.3456")


@pytest.mark.parametrize("field", ["standard_cost", "list_price", "weight", "length"])
def test_product_create_contract_rejects_negative_values(field: str) -> None:
    with pytest.raises(ValidationError):
        valid_request(**{field: "-0.01"})


def test_product_code_validation_and_immutability_contract() -> None:
    assert Product.valid_code("RM-STEEL_001")
    assert not Product.valid_code("bad code")
    from app.modules.products.presentation.schemas import UpdateProductRequest

    assert "product_code" not in UpdateProductRequest.model_fields


def test_product_migration_has_rls_permissions_constraints_and_no_inventory() -> None:
    migration = (Path(__file__).parents[2] / "alembic/versions/0015_products.py").read_text()
    for expected in (
        "ENABLE ROW LEVEL SECURITY",
        "app_runtime",
        "products.read",
        "products.detail.read",
        "products.assign_owner",
        "products.export",
        "uq_products_tenant_code",
        "row_version",
    ):
        assert expected in migration
    assert "product_inventory" not in migration
    assert "warehouse_stock" not in migration
