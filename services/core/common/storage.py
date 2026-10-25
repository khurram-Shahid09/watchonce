"""Object storage (Cloudflare R2 in production, SeaweedFS locally; docs/03-architecture.md).

Clients upload straight to storage with presigned PUT URLs, so large recordings never pass
through the API. ``get_storage()`` returns the configured backend; tests use ``memory``.
"""

from functools import cache
from typing import Protocol

from django.conf import settings


class ObjectStorage(Protocol):
    def presign_put(self, key: str, content_type: str, expires_in: int) -> str: ...
    def presign_get(self, key: str, expires_in: int) -> str: ...
    def size(self, key: str) -> int | None:
        """Object size in bytes, or None if it doesn't exist."""

    def get_bytes(self, key: str) -> bytes: ...
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...


class S3Storage:
    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        config = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        common = {
            "aws_access_key_id": settings.S3_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.S3_SECRET_ACCESS_KEY,
            "region_name": settings.S3_REGION,
            "config": config,
        }
        self.bucket = settings.S3_BUCKET
        self.client = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT, **common)
        # Presigned URLs must use the host browsers can reach, which inside docker differs
        # from the one the API uses.
        public = settings.S3_PUBLIC_ENDPOINT or settings.S3_ENDPOINT
        self.signer = (
            self.client
            if public == settings.S3_ENDPOINT
            else boto3.client("s3", endpoint_url=public, **common)
        )

    def presign_put(self, key: str, content_type: str, expires_in: int) -> str:
        return self.signer.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    def presign_get(self, key: str, expires_in: int) -> str:
        return self.signer.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
        )

    def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            return int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def ensure_bucket(self, cors_origins: list[str]) -> None:
        """Create the bucket if needed and allow browser uploads (the extension PUTs directly)."""
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
        self.client.put_bucket_cors(
            Bucket=self.bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": cors_origins,
                        "AllowedMethods": ["PUT", "GET"],
                        "AllowedHeaders": ["content-type"],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )


class MemoryStorage:
    """In-process fake for tests. ``presign_put`` URLs aren't real; tests upload with
    ``put_bytes``."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def presign_put(self, key: str, content_type: str, expires_in: int) -> str:
        return f"memory://{key}?expires_in={expires_in}"

    def presign_get(self, key: str, expires_in: int) -> str:
        return f"http://storage.memory/{key}?expires_in={expires_in}"  # redirectable

    def size(self, key: str) -> int | None:
        obj = self.objects.get(key)
        return len(obj[0]) if obj else None

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key][0]

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)


@cache
def get_storage() -> ObjectStorage:
    return MemoryStorage() if settings.STORAGE_BACKEND == "memory" else S3Storage()
