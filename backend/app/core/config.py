from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://peblo:peblo_secret@db:5432/peblo_tv"
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 480
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_PATH: str = "/app/storage"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "peblo-tv-catalogue"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"
    SEED_ON_START: bool = True
    # Path to the ffmpeg binary used to generate placeholder demo clips on boot.
    # Set to an empty string to skip video generation (e.g. in tests).
    FFMPEG_BIN: str = "ffmpeg"

    class Config:
        env_file = ".env"
        extra = "allow"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]


settings = Settings()
