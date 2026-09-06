import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.core.config import settings


class StorageBackend(ABC):
    @abstractmethod
    async def save_file(self, file_data: bytes, path: str, content_type: str = "application/octet-stream") -> str:
        pass

    @abstractmethod
    async def get_file_url(self, path: str) -> str:
        pass

    @abstractmethod
    async def save_json(self, data: dict, path: str) -> str:
        pass

    @abstractmethod
    async def read_json(self, path: str) -> Optional[dict]:
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        pass


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or settings.STORAGE_LOCAL_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_file(self, file_data: bytes, path: str, content_type: str = "application/octet-stream") -> str:
        full_path = self.base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(file_data)
        return path

    async def get_file_url(self, path: str) -> str:
        return f"/storage/{path}"

    async def save_json(self, data: dict, path: str) -> str:
        full_path = self.base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to a temp file in the same directory, then os.replace.
        # Rename is atomic on the same filesystem, so a reader never sees a half-written file.
        tmp_path = full_path.with_suffix(full_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, full_path)
        return path

    async def read_json(self, path: str) -> Optional[dict]:
        full_path = self.base_path / path
        if not full_path.exists():
            return None
        with open(full_path, "r") as f:
            return json.load(f)

    async def delete_file(self, path: str) -> bool:
        full_path = self.base_path / path
        if full_path.exists():
            full_path.unlink()
            return True
        return False


class R2Storage(StorageBackend):
    def __init__(self):
        try:
            import boto3
            self.client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                region_name="auto",
            )
            self.bucket = settings.R2_BUCKET_NAME
        except ImportError:
            raise RuntimeError("boto3 is required for R2 storage. Install with: pip install boto3")

    async def save_file(self, file_data: bytes, path: str, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=path,
            Body=file_data,
            ContentType=content_type,
        )
        return path

    async def get_file_url(self, path: str) -> str:
        return f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/{self.bucket}/{path}"

    async def save_json(self, data: dict, path: str) -> str:
        content = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        return await self.save_file(content, path, "application/json")

    async def read_json(self, path: str) -> Optional[dict]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=path)
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except Exception:
            return None

    async def delete_file(self, path: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=path)
            return True
        except Exception:
            return False


def get_storage() -> StorageBackend:
    if settings.STORAGE_BACKEND == "r2":
        return R2Storage()
    return LocalStorage()
