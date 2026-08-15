import asyncio
from typing import Any

import boto3  # type: ignore[import-untyped]


class S3AttachmentStorage:
    def __init__(self, *, bucket_name: str, region: str, client: Any | None = None) -> None:
        self.bucket_name = bucket_name
        self.client = client or boto3.client("s3", region_name=region)

    async def upload(self, *, object_key: str, content: bytes, content_type: str | None) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket_name,
            "Key": object_key,
            "Body": content,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        await asyncio.to_thread(self.client.put_object, **kwargs)

    async def delete(self, *, object_key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket_name, Key=object_key)

    async def create_download_url(self, *, object_key: str, expires_in: int) -> str:
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": object_key},
            ExpiresIn=expires_in,
        )
