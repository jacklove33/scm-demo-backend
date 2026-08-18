from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.customer_pos.presentation.schemas import (
    CreateCustomerPoRequest,
    CustomerPoResponse,
    UpdateCustomerPoRequest,
)

OWNER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CUSTOMER_ID = UUID("40000000-0000-0000-0000-000000000001")


def line() -> dict[str, object]:
    return {
        "line_number": 1,
        "item_description": "Widget",
        "ordered_quantity": "2",
        "unit_of_measure": "EA",
        "unit_price": "5",
    }


def test_update_accepts_owner_user_id_and_rejects_owner_display_name() -> None:
    request = UpdateCustomerPoRequest.model_validate(
        {
            "expected_version": 4,
            "currency_code": "USD",
            "owner_user_id": str(OWNER_ID),
            "lines": [line()],
        }
    )
    assert request.owner_user_id == OWNER_ID

    with pytest.raises(ValidationError, match="owner_display_name"):
        UpdateCustomerPoRequest.model_validate(
            {
                "expected_version": 4,
                "currency_code": "USD",
                "owner_user_id": str(OWNER_ID),
                "owner_display_name": "Kevin Admin",
                "lines": [line()],
            }
        )


def test_create_also_rejects_owner_display_name() -> None:
    with pytest.raises(ValidationError, match="owner_display_name"):
        CreateCustomerPoRequest.model_validate(
            {
                "customer_id": str(CUSTOMER_ID),
                "customer_po_number": "PO-001",
                "currency_code": "USD",
                "owner_user_id": str(OWNER_ID),
                "owner_display_name": "Kevin Admin",
                "lines": [line()],
            }
        )


def test_response_keeps_owner_id_and_display_name_as_read_fields() -> None:
    assert "owner_user_id" in CustomerPoResponse.model_fields
    assert "owner_display_name" in CustomerPoResponse.model_fields
