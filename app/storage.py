from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app


class StorageError(Exception):
    """Raised when encrypted object storage cannot complete an operation."""


class StorageNotFound(StorageError):
    """Raised when an encrypted object does not exist."""


class LocalEncryptedStorage:
    def __init__(self, root):
        self.root = Path(root)

    def put(self, object_name, data):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / object_name).write_bytes(data)

    def get(self, object_name):
        path = self.root / object_name
        if not path.exists():
            raise StorageNotFound(object_name)
        return path.read_bytes()

    def delete(self, object_name):
        (self.root / object_name).unlink(missing_ok=True)


class S3EncryptedStorage:
    def __init__(self, config):
        self.bucket = config["STORAGE_BUCKET"]
        self.client = boto3.client(
            "s3",
            endpoint_url=config["S3_ENDPOINT_URL"],
            aws_access_key_id=config["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=config["S3_SECRET_ACCESS_KEY"],
            region_name=config["S3_REGION"],
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def put(self, object_name, data):
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=object_name,
                Body=data,
                ContentType="application/octet-stream",
            )
        except (BotoCoreError, ClientError) as error:
            raise StorageError("Could not store encrypted object") from error

    def get(self, object_name):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_name)
            return response["Body"].read()
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                raise StorageNotFound(object_name) from error
            raise StorageError("Could not retrieve encrypted object") from error
        except BotoCoreError as error:
            raise StorageError("Could not retrieve encrypted object") from error

    def delete(self, object_name):
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_name)
        except (BotoCoreError, ClientError) as error:
            raise StorageError("Could not delete encrypted object") from error


def get_encrypted_storage():
    if current_app.config["STORAGE_BACKEND"] == "s3":
        return S3EncryptedStorage(current_app.config)
    return LocalEncryptedStorage(current_app.config["UPLOAD_FOLDER"])
