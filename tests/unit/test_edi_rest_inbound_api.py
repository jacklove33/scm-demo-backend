import logging
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.main import app

PATH = "/api/v1/edi/rest/receive"
PAYLOAD = {
    "lines": [{"uom": "EA", "item": "ABC123", "quantity": 100}],
    "poNumber": "PO123456",
}
REQUIRED_HEADERS = {
    "X-Sender-ID": "WPG",
    "X-Receiver-ID": "SYNA",
    "X-Document-Type": "850",
}


def test_receive_rest_edi_payload_returns_accepted_and_logs_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.modules.edi")

    response = TestClient(app).post(
        PATH,
        headers={**REQUIRED_HEADERS, "X-External-Message-ID": "REST-DEMO-001"},
        json=PAYLOAD,
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "RECEIVED",
        "sender_id": "WPG",
        "receiver_id": "SYNA",
        "document_type": "850",
        "external_message_id": "REST-DEMO-001",
    }
    record = next(
        record
        for record in caplog.records
        if record.getMessage().startswith("REST EDI inbound payload received")
    )
    assert "poNumber': 'PO123456'" in record.getMessage()
    metadata = cast(Any, record)
    assert metadata.sender_id == "WPG"
    assert metadata.receiver_id == "SYNA"
    assert metadata.document_type == "850"
    assert metadata.external_message_id == "REST-DEMO-001"
    assert metadata.source_protocol == "REST"
    assert metadata.payload == PAYLOAD


@pytest.mark.parametrize("missing_header", REQUIRED_HEADERS)
def test_receive_rest_edi_payload_requires_routing_headers(missing_header: str) -> None:
    headers = {key: value for key, value in REQUIRED_HEADERS.items() if key != missing_header}

    response = TestClient(app).post(PATH, headers=headers, json=PAYLOAD)

    assert response.status_code == 422


def test_receive_rest_edi_payload_rejects_invalid_json() -> None:
    response = TestClient(app).post(
        PATH,
        headers={**REQUIRED_HEADERS, "Content-Type": "application/json"},
        content='{"poNumber":',
    )

    assert response.status_code == 422
