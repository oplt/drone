from __future__ import annotations

from pathlib import Path


class ObjectStorageClient:
    """S3-compatible client for MinIO and Cloudflare R2."""

    def _make_client_ctx(self):
        from backend.core.config.runtime import settings

        try:
            import aiobotocore.session as aioboto
        except ImportError:
            raise RuntimeError(
                "aiobotocore is not installed. Run: pip install 'aiobotocore>=2.13'"
            ) from None

        session = aioboto.get_session()
        return session.create_client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )

    async def upload_file(self, local_path: Path, object_key: str) -> str:
        from backend.core.config.runtime import settings

        async with self._make_client_ctx() as client:
            with open(local_path, "rb") as file:
                await client.put_object(
                    Bucket=settings.s3_bucket_name,
                    Key=object_key,
                    Body=file,
                )
        return object_key

    async def generate_presigned_url(self, object_key: str, expires_in: int = 3600) -> str:
        from backend.core.config.runtime import settings

        async with self._make_client_ctx() as client:
            url = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket_name, "Key": object_key},
                ExpiresIn=expires_in,
            )

        if settings.s3_public_base_url:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)
            cdn = urlparse(settings.s3_public_base_url)
            url = urlunparse(parsed._replace(scheme=cdn.scheme, netloc=cdn.netloc))

        return url

    async def delete_object(self, object_key: str) -> None:
        from backend.core.config.runtime import settings

        async with self._make_client_ctx() as client:
            await client.delete_object(Bucket=settings.s3_bucket_name, Key=object_key)

    async def list_objects(self, prefix: str) -> list[str]:
        from backend.core.config.runtime import settings

        keys: list[str] = []
        async with self._make_client_ctx() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=settings.s3_bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
        return keys
