import logging
from dataclasses import dataclass
from typing import Any

from app.core.logging import sanitize_log_data

logger = logging.getLogger("app.modules.edi")


@dataclass(frozen=True, slots=True)
class ReceiveRestEdiPayloadCommand:
    sender_id: str
    receiver_id: str
    document_type: str
    external_message_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RestEdiReceipt:
    sender_id: str
    receiver_id: str
    document_type: str
    external_message_id: str | None


class ReceiveRestEdiPayload:
    """Accept a REST transport payload without invoking EDI processing."""

    def execute(self, command: ReceiveRestEdiPayloadCommand) -> RestEdiReceipt:
        logger.info(
            (
                "REST EDI inbound payload received sender_id=%s receiver_id=%s "
                "document_type=%s external_message_id=%s source_protocol=REST payload=%s"
            ),
            command.sender_id,
            command.receiver_id,
            command.document_type,
            command.external_message_id,
            sanitize_log_data(command.payload),
            extra={
                "business_module": "edi",
                "sender_id": command.sender_id,
                "receiver_id": command.receiver_id,
                "document_type": command.document_type,
                "external_message_id": command.external_message_id,
                "source_protocol": "REST",
                "payload": command.payload,
            },
        )
        return RestEdiReceipt(
            sender_id=command.sender_id,
            receiver_id=command.receiver_id,
            document_type=command.document_type,
            external_message_id=command.external_message_id,
        )
