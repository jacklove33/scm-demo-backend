import os
from uuid import UUID

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "false"

from app.main import app

PO_ID = UUID("60000000-0000-0000-0000-000000000001")


def test_attachment_endpoints_require_authentication() -> None:
    client = TestClient(app)
    assert (
        client.get(
            "/api/v1/attachments",
            params={"entity_type": "CUSTOMER_PO", "entity_id": str(PO_ID)},
        ).status_code
        == 401
    )
    assert client.get(f"/api/v1/attachments/{PO_ID}/download").status_code == 401
