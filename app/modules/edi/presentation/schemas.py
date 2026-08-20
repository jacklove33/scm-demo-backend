from typing import Any
from uuid import UUID

from pydantic import BaseModel, RootModel


class RestEdiPayloadRequest(RootModel[dict[str, Any]]):
    """An intentionally generic JSON object for the transport smoke test."""


class RestEdiReceiptResponse(BaseModel):
    status: str
    sender_id: str
    receiver_id: str
    document_type: str
    external_message_id: str | None
    customer_po_id: UUID
