from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment or defaults."""
    app_name: str = "Blood Donation Matching System"
    environment: str = "development"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = "sqlite:///./blood_donation.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
