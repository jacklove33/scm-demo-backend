from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.suppliers.presentation.schemas import CreateSupplierRequest, UpdateSupplierRequest


def test_create_normalizes_code_and_forbids_read_fields() -> None:
    value = CreateSupplierRequest.model_validate(
        {"supplier_code": " sup-1 ", "supplier_name": "ACME"}
    )
    assert value.supplier_code == "SUP-1"
    with pytest.raises(ValidationError, match="owner_display_name"):
        CreateSupplierRequest.model_validate(
            {"supplier_code": "SUP-1", "supplier_name": "ACME", "owner_display_name": "Mary"}
        )


def test_update_is_explicit_and_code_is_immutable() -> None:
    owner = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    value = UpdateSupplierRequest.model_validate(
        {
            "supplier_name": "ACME",
            "owner_user_id": str(owner),
            "status": "ACTIVE",
            "expected_version": 3,
        }
    )
    assert value.owner_user_id == owner
    with pytest.raises(ValidationError, match="supplier_code"):
        UpdateSupplierRequest.model_validate(
            {
                "supplier_code": "SUP-2",
                "supplier_name": "ACME",
                "status": "ACTIVE",
                "expected_version": 3,
            }
        )


@pytest.mark.parametrize(("field", "value"), [("country_code", "TWN"), ("currency_code", "US")])
def test_exact_reference_code_lengths(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        CreateSupplierRequest.model_validate(
            {"supplier_code": "SUP-1", "supplier_name": "ACME", field: value}
        )
