from typing import Any

from botocore.exceptions import ClientError


class S3ClientError(Exception):
    """Raised when an S3 operation fails."""

    def __init__(self, message: str, code: str = "S3_CLIENT_ERROR") -> None:
        super().__init__(message)
        self.code = code


class S3ObjectNotFoundError(S3ClientError):
    """Raised when an S3 object does not exist."""

    def __init__(self, key: str) -> None:
        super().__init__(f"S3 object '{key}' was not found.", code="S3_OBJECT_NOT_FOUND")


class S3Client:
    """Application wrapper around one S3 bucket."""

    def __init__(self, client: Any, bucket_name: str) -> None:
        self.client = client
        self.bucket_name = bucket_name

    def put_bytes(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata=metadata or {},
            )
        except Exception as error:
            raise S3ClientError(
                f"Failed to write S3 object '{key}': {error}",
                code="S3_PUT_OBJECT_FAILED",
            ) from error
        return key

    def put_text(
        self,
        *,
        key: str,
        content: str,
        content_type: str = "text/plain; charset=utf-8",
        metadata: dict[str, str] | None = None,
    ) -> str:
        return self.put_bytes(
            key=key,
            content=content.encode("utf-8"),
            content_type=content_type,
            metadata=metadata,
        )

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read()
        except ClientError as error:
            self._raise_client_error(error, key, "S3_GET_OBJECT_FAILED")
        except Exception as error:
            raise S3ClientError(
                f"Failed to read S3 object '{key}': {error}",
                code="S3_GET_OBJECT_FAILED",
            ) from error

    def get_text(self, key: str, encoding: str = "utf-8") -> str:
        return self.get_bytes(key).decode(encoding)

    def object_exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as error:
            if self._is_not_found(error):
                return False
            raise S3ClientError(
                f"Failed to check S3 object '{key}': {error}",
                code="S3_HEAD_OBJECT_FAILED",
            ) from error
        except Exception as error:
            raise S3ClientError(
                f"Failed to check S3 object '{key}': {error}",
                code="S3_HEAD_OBJECT_FAILED",
            ) from error

    def delete_object(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
        except Exception as error:
            raise S3ClientError(
                f"Failed to delete S3 object '{key}': {error}",
                code="S3_DELETE_OBJECT_FAILED",
            ) from error

    def create_download_url(self, key: str, expires_in_seconds: int = 900) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in_seconds,
            )
        except Exception as error:
            raise S3ClientError(
                f"Failed to create a download URL for S3 object '{key}': {error}",
                code="S3_PRESIGN_OBJECT_FAILED",
            ) from error

    @staticmethod
    def _is_not_found(error: ClientError) -> bool:
        code = str(error.response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchKey", "NotFound"}

    @classmethod
    def _raise_client_error(cls, error: ClientError, key: str, code: str) -> None:
        if cls._is_not_found(error):
            raise S3ObjectNotFoundError(key) from error
        raise S3ClientError(f"S3 operation failed for '{key}': {error}", code=code) from error
