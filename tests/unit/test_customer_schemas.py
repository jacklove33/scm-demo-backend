import pytest
from pydantic import ValidationError

from app.modules.customers.presentation.schemas import CreateCustomerRequest, UpdateCustomerRequest


def test_create_normalizes_customer_code() -> None:
    request = CreateCustomerRequest(customer_code="abc-001", customer_name="ACME")
    assert request.customer_code == "ABC-001"


def test_update_contract_makes_customer_code_immutable() -> None:
    with pytest.raises(ValidationError):
        UpdateCustomerRequest.model_validate(
            {
                "expected_version": 1,
                "customer_code": "CHANGED",
                "customer_name": "ACME",
            }
        )
