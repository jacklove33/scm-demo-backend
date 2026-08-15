from typing import Any

import pytest

from app.modules.attachments.infrastructure.s3_storage import S3AttachmentStorage


class Client:
    def __init__(self) -> None:
        self.put: dict[str, Any] | None = None
        self.deleted: dict[str, Any] | None = None
        self.presigned: tuple[str, dict[str, Any], int] | None = None

    def put_object(self, **kwargs: Any) -> None:
        self.put = kwargs

    def delete_object(self, **kwargs: Any) -> None:
        self.deleted = kwargs

    def generate_presigned_url(
        self, operation: str, *, Params: dict[str, Any], ExpiresIn: int
    ) -> str:
        self.presigned = (operation, Params, ExpiresIn)
        return "https://signed.example.test"


@pytest.mark.asyncio
async def test_s3_adapter_uses_private_operations_without_public_acl() -> None:
    client = Client()
    storage = S3AttachmentStorage(
        bucket_name="private-bucket", region="ap-northeast-1", client=client
    )
    await storage.upload(
        object_key="tenant/file.pdf", content=b"pdf", content_type="application/pdf"
    )
    url = await storage.create_download_url(object_key="tenant/file.pdf", expires_in=300)
    await storage.delete(object_key="tenant/file.pdf")

    assert client.put == {
        "Bucket": "private-bucket",
        "Key": "tenant/file.pdf",
        "Body": b"pdf",
        "ContentType": "application/pdf",
    }
    assert "ACL" not in client.put
    assert client.presigned == (
        "get_object",
        {"Bucket": "private-bucket", "Key": "tenant/file.pdf"},
        300,
    )
    assert client.deleted == {"Bucket": "private-bucket", "Key": "tenant/file.pdf"}
    assert url == "https://signed.example.test"
